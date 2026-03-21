"""
deepseek_autoresearch_agent.py
================================
Reads autoresearch backtest results, analyses them with DeepSeek,
and submits concrete parameter-change proposals to the approval queue.

Also provides helpers to trigger a new mini-backtest from TG.

Telegram commands wired in smart_pump_reversal_bot.py:
  /ai_results          – summary of the best recent autoresearch run
  /ai_tune             – ask DeepSeek to propose parameter changes
  /ai_tune breakout    – tune only the breakout strategy
  /ai_tune flat        – tune only the flat/ARF1 strategy
  /ai_tune asc1        – tune sloped channel

Context building:
  build_research_context() – enriches the DeepSeek snapshot with
    best-known parameters, running autoresearch status, and recent
    backtest history for all 4 strategies.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

# ── paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip().lower() in {
        "1", "true", "yes", "y", "on"
    }


# ── autoresearch result reader ───────────────────────────────────────────────

STRATEGY_TAGS = {
    "breakout": "breakout_live",
    "flat": "flat_trendline",
    "asc1": "full_stack",
    "combined": "full_stack",
}


def find_latest_autoresearch_dirs(
    tag_filter: str | None = None, limit: int = 3
) -> list[Path]:
    """Return the most recently modified autoresearch run dirs matching tag."""
    runs_root = _ROOT / "backtest_runs"
    if not runs_root.exists():
        return []
    dirs = sorted(
        [d for d in runs_root.iterdir() if d.is_dir() and d.name.startswith("autoresearch_")],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if tag_filter:
        dirs = [d for d in dirs if tag_filter.lower() in d.name.lower()]
    return dirs[:limit]


def read_best_candidates(
    run_dir: Path, top_n: int = 5
) -> list[dict[str, Any]]:
    """Return top_n passing candidates sorted by score."""
    csv_path = run_dir / "results.csv"
    if not csv_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("passed") == "True":
                try:
                    overrides = json.loads(r.get("overrides_json") or "{}")
                except Exception:
                    overrides = {}
                rows.append({
                    "score": float(r.get("score") or 0),
                    "trades": int(r.get("trades") or 0),
                    "net_pnl": float(r.get("net_pnl") or 0),
                    "profit_factor": float(r.get("profit_factor") or 0),
                    "winrate": float(r.get("winrate") or 0),
                    "max_drawdown": float(r.get("max_drawdown") or 0),
                    "negative_months": int(r.get("negative_months") or 0),
                    "worst_month_pnl": float(r.get("worst_month_pnl") or 0),
                    "overrides": overrides,
                })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:top_n]


def summarize_run(run_dir: Path) -> str:
    """One-line text summary of a run (for Telegram)."""
    bests = read_best_candidates(run_dir, top_n=1)
    total_lines = 0
    csv_path = run_dir / "results.csv"
    if csv_path.exists():
        with csv_path.open() as f:
            total_lines = sum(1 for _ in f) - 1  # minus header
    if not bests:
        return f"📂 {run_dir.name}: {total_lines} кандидатов, ни один не прошёл фильтры."
    b = bests[0]
    return (
        f"📂 {run_dir.name}\n"
        f"  всего={total_lines}  лучший score={b['score']:.2f}\n"
        f"  trades={b['trades']}  pnl={b['net_pnl']:.1f}%  "
        f"pf={b['profit_factor']:.3f}  wr={b['winrate']:.1%}\n"
        f"  dd={b['max_drawdown']:.2f}%  red_months={b['negative_months']}"
    )


def results_report_text(strategy_hint: str | None = None, top_n: int = 3) -> str:
    """Full text report for /ai_results command."""
    tag_filter = STRATEGY_TAGS.get(strategy_hint or "", strategy_hint or "")
    dirs = find_latest_autoresearch_dirs(tag_filter=tag_filter or None, limit=5)
    if not dirs:
        return "Результатов autoresearch не найдено."
    lines = [f"📊 Последние autoresearch{'  (' + strategy_hint + ')' if strategy_hint else ''}:\n"]
    for d in dirs[:3]:
        lines.append(summarize_run(d))
    # Detail on the freshest
    freshest = dirs[0]
    bests = read_best_candidates(freshest, top_n=top_n)
    if bests:
        lines.append(f"\n🏆 TOP {min(top_n, len(bests))} из {freshest.name}:")
        for i, b in enumerate(bests, 1):
            ov_str = "  ".join(f"{k}={v}" for k, v in b["overrides"].items())
            lines.append(
                f"#{i} score={b['score']:.2f} trades={b['trades']} "
                f"pnl={b['net_pnl']:.1f}% pf={b['profit_factor']:.3f}\n"
                f"   {ov_str}"
            )
    return "\n".join(lines)


# ── DeepSeek param-tuning ────────────────────────────────────────────────────

def _ds_chat(system: str, user: str, model: str | None = None) -> str:
    """Direct call to DeepSeek chat API, returns answer string."""
    api_key = _env("DEEPSEEK_API_KEY")
    if not api_key:
        return "DEEPSEEK_API_KEY не задан."
    base_url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    m = model or _env("DEEPSEEK_MODEL", "deepseek-chat")
    timeout = float(_env("DEEPSEEK_TIMEOUT_SEC", "15") or 15)
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": m,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.15,
        "max_tokens": 700,
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        if choices:
            return str(choices[0].get("message", {}).get("content", "")).strip()
        return "DeepSeek вернул пустой ответ."
    except Exception as e:
        return f"DeepSeek error: {e}"


def _build_tune_prompt(strategy: str, bests: list[dict[str, Any]]) -> tuple[str, str]:
    """Build system + user prompt for param-tuning request."""
    system = (
        "Ты — квантовый аналитик торговых стратегий. "
        "Ты анализируешь результаты backtesting-исследований и предлагаешь "
        "конкретные улучшения параметров. "
        "Отвечай строго в формате JSON-объекта со следующими полями:\n"
        "  changes: [{env_key, old_value, new_value, reason}]  (1–4 изменения)\n"
        "  summary: string  (объяснение на русском, до 200 символов)\n"
        "Не выходи за рамки параметров, которые ты видишь в overrides. "
        "Если данных недостаточно — верни changes=[] и объясни в summary."
    )
    top_json = json.dumps(bests, ensure_ascii=False, indent=2)
    user = (
        f"Стратегия: {strategy}\n"
        f"Текущие лучшие кандидаты из autoresearch (топ по score):\n"
        f"{top_json}\n\n"
        "Проанализируй вариацию параметров. Найди, какие значения стабильно "
        "дают лучший score/PF/WR. Предложи 1–3 конкретных изменения параметров "
        "по сравнению с текущим продакшн конфигом. "
        "Отвечай только JSON-объектом, без лишнего текста."
    )
    return system, user


def build_research_context() -> dict[str, Any]:
    """
    Build a rich context dict with the latest autoresearch findings.
    This is merged into the DeepSeek snapshot so the AI has full
    historical knowledge when answering /ai questions.
    """
    ctx: dict[str, Any] = {
        "known_best_params": {
            "inplay_breakout": {
                "BT_BREAKOUT_QUALITY_MIN_SCORE": "0.54",
                "BREAKOUT_BUFFER_ATR": "0.12",
                "BREAKOUT_MAX_CHASE_PCT": "0.14",
                "BREAKOUT_MAX_DIST_ATR": "1.4",
                "BREAKOUT_RECLAIM_ATR": "0.12",
                "BREAKOUT_ALLOW_SHORTS": "0",
                "source": "breakout_live_bridge_v2_focus 528-candidate run + full_stack_v2 r002 ALLOW_SHORTS=1 fails neg_months",
                "result": "346 trades/year, WR 65.6%, PF 1.399, DD 2.95%, 2 red months",
            },
            "alt_sloped_channel_v1": {
                "ASC1_SYMBOL_ALLOWLIST": "ATOMUSDT,LINKUSDT",
                "ASC1_ALLOW_SHORTS": "1",
                "ASC1_ALLOW_LONGS": "0",
                "ASC1_SHORT_MIN_REJECT_DEPTH_ATR": "0.75",
                "ASC1_SHORT_MIN_RSI": "60",
                "ASC1_CONFIRM_5M_BARS": "6",
                "SLOPED_RISK_MULT": "0.10",
                "source": "autoresearch asc1 + live deploy 2026-03-21",
                "result": "24 trades/year, WR 58%, PF 8.94, DD 0.88%, 0 red months",
            },
            "alt_resistance_fade_v1": {
                "ARF1_SYMBOL_ALLOWLIST": "LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT",
                "FLAT_RISK_MULT": "0.10",
                "source": "live deploy 2026-03-21",
                "result": "13-17 trades/year, WR 59-62%, PF 2.5",
            },
            "btc_eth_midterm_pullback": {
                "MIDTERM_SYMBOLS": "BTCUSDT,ETHUSDT",
                "source": "live deploy 2026-03-21",
                "result": "71 trades/year, WR 46%, PF 1.3, diversification layer",
            },
        },
        "combined_4strat_best": {
            "net_pnl": "46.77%",
            "profit_factor": "1.610",
            "winrate": "62.9%",
            "max_drawdown": "4.18%",
            "trades": "~470/year",
            "negative_months": "1",
            "note": "full_stack_v2_overnight r003: quality=0.48, allow_shorts=0, max_chase=0.13",
        },
        "pending_autoresearch": [],
    }

    # Append running autoresearch status
    for spec_name, log_path in [
        ("full_stack_v2_overnight", "/tmp/autoresearch_fullstack_v2.log"),
        ("equities_monthly_v22_balance", "/tmp/autoresearch_equities_v22.log"),
    ]:
        try:
            lines = Path(log_path).read_text().splitlines() if Path(log_path).exists() else []
            last = [l for l in lines if l.strip()]
            prog = last[-1] if last else "no output yet"
            ctx["pending_autoresearch"].append({"spec": spec_name, "last_line": prog, "total_lines": len(last)})
        except Exception:
            pass

    # Collect top 3 candidates from the most relevant recent runs
    summaries: list[dict[str, Any]] = []
    for tag in ["full_stack_v2_overnight", "breakout_live_bridge_v2_focus", "equities_monthly_v22"]:
        dirs = find_latest_autoresearch_dirs(tag_filter=tag, limit=1)
        if not dirs:
            continue
        bests = read_best_candidates(dirs[0], top_n=3)
        if bests:
            summaries.append({"run": dirs[0].name, "top3": bests[:3]})
    ctx["recent_autoresearch_tops"] = summaries

    return ctx


def tune_strategy(
    strategy: str,
    overlay: Any,   # DeepSeekOverlay instance for proposal submission
    snapshot: dict[str, Any],
) -> str:
    """
    Ask DeepSeek to analyse autoresearch results for the strategy,
    then submit a proposal to the approval queue.
    Returns a Telegram message string.
    """
    if not _env_bool("DEEPSEEK_ENABLE"):
        return "DeepSeek выключен. Включи DEEPSEEK_ENABLE=1."
    if not _env("DEEPSEEK_API_KEY"):
        return "DeepSeek API key не задан."

    # Find relevant results
    tag_filter = STRATEGY_TAGS.get(strategy, strategy)
    dirs = find_latest_autoresearch_dirs(tag_filter=tag_filter, limit=2)
    if not dirs:
        return f"Нет данных autoresearch для стратегии '{strategy}'."

    bests = read_best_candidates(dirs[0], top_n=8)
    if not bests:
        return f"Нет прошедших кандидатов в {dirs[0].name}."

    system, user = _build_tune_prompt(strategy, bests)
    raw = _ds_chat(system, user)

    # Try to parse JSON
    try:
        # strip markdown fences if present
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            raw_clean = "\n".join(raw_clean.splitlines()[1:])
        if raw_clean.endswith("```"):
            raw_clean = "\n".join(raw_clean.splitlines()[:-1])
        proposal = json.loads(raw_clean)
    except Exception:
        return f"DeepSeek вернул нечитаемый ответ:\n{raw[:600]}"

    changes = proposal.get("changes") or []
    summary = str(proposal.get("summary") or "").strip()

    if not changes:
        return f"DeepSeek не нашёл улучшений:\n{summary}"

    # Submit to approval queue
    changes_text = "\n".join(
        f"  {c['env_key']}: {c.get('old_value','?')} → {c['new_value']}  ({c.get('reason','')})"
        for c in changes
    )
    prop_summary = f"[{strategy}] {summary}\n{changes_text}"
    prop_payload = {
        "strategy": strategy,
        "source_run": dirs[0].name,
        "changes": changes,
        "raw_deepseek": raw[:1000],
    }
    msg = overlay.submit_proposal(prop_summary, payload=prop_payload, kind="param_tune")
    return (
        f"🤖 DeepSeek предложил изменения для <b>{strategy}</b>:\n\n"
        f"{changes_text}\n\n"
        f"📝 {summary}\n\n"
        f"✅ {msg}\n"
        f"Используй /ai_approve &lt;id&gt; или /ai_reject &lt;id&gt;"
    )


# ── quick mini-backtest trigger ───────────────────────────────────────────────

def trigger_mini_backtest(
    overrides: dict[str, str] | None = None,
    strategies: str = "alt_sloped_channel_v1,alt_resistance_fade_v1,inplay_breakout,btc_eth_midterm_pullback",
    symbols: str = "ATOMUSDT,LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT,BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,DOGEUSDT,BCHUSDT,AVAXUSDT",
    days: int = 90,
) -> str:
    """
    Launch a background portfolio backtest (cache-only) with optional overrides.
    Returns a message string for Telegram.
    """
    env = os.environ.copy()
    env["BACKTEST_CACHE_ONLY"] = "1"
    if overrides:
        for k, v in overrides.items():
            env[str(k)] = str(v)

    tag = f"ai_tune_{int(time.time())}"
    cmd = [
        sys.executable, str(_ROOT / "backtest" / "run_portfolio.py"),
        "--symbols", symbols,
        "--strategies", strategies,
        "--days", str(days),
        "--tag", tag,
        "--starting_equity", "100",
        "--risk_pct", "0.005",
        "--leverage", "3",
        "--max_positions", "3",
        "--fee_bps", "10",
        "--slippage_bps", "10",
    ]
    log_path = _ROOT / "backtest_runs" / f"ai_mini_{tag}.log"
    log_path.parent.mkdir(exist_ok=True)
    try:
        with log_path.open("w") as lf:
            proc = subprocess.Popen(
                cmd, env=env,
                stdout=lf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        overrides_txt = ""
        if overrides:
            overrides_txt = "\n".join(f"  {k}={v}" for k, v in overrides.items())
            overrides_txt = f"\n<b>Overrides:</b>\n{overrides_txt}"
        return (
            f"🚀 Мини-бэктест запущен (PID {proc.pid})\n"
            f"tag={tag}  days={days}{overrides_txt}\n"
            f"Лог: {log_path.name}\n"
            f"Результат появится через ~3–5 минут."
        )
    except Exception as e:
        return f"Ошибка запуска бэктеста: {e}"
