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
  /ai_tune midterm     – inspect the ETH/BTC midterm repair sweep
  /ai_tune breakdown   – inspect the live breakdown sleeve
  /ai_tune alpaca      – inspect the monthly equities sleeve

Context building:
  build_research_context() – enriches the DeepSeek snapshot with
    best-known parameters, running autoresearch status, and recent
    backtest history for the current 5-sleeve stack.
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
    "breakout": "breakout_live_bridge",
    "flat": "arf1",
    "arf1": "arf1",
    "asc1": "asc1_expansion",
    "sloped": "asc1_expansion",
    "breakdown": "breakdown_expansion",
    "midterm": "midterm_eth_repair",
    "alpaca": "equities_monthly_v21",
    "equities": "equities_monthly_v21",
    "combined": "new_5strat_final",
    "full_stack": "new_5strat_final",
    "portfolio": "new_5strat_final",
    "stack": "new_5strat_final",
}

_PORTFOLIO_HINTS = {"combined", "full_stack", "portfolio", "stack"}
_EQUITIES_HINTS = {"alpaca", "equities"}
_EQUITIES_AUTORESEARCH_TAGS = (
    "equities_monthly_v23_breadth_exit_cluster",
    "equities_monthly_v21_red_month_push",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def find_latest_run_dirs(
    name_filter: str | None = None,
    limit: int = 3,
    prefixes: tuple[str, ...] = ("autoresearch_", "portfolio_", "equities_monthly_research_"),
) -> list[Path]:
    """Return the most recently modified run dirs matching a substring."""
    runs_root = _ROOT / "backtest_runs"
    if not runs_root.exists():
        return []
    dirs = sorted(
        [
            d for d in runs_root.iterdir()
            if d.is_dir() and any(d.name.startswith(prefix) for prefix in prefixes)
        ],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if name_filter:
        dirs = [d for d in dirs if name_filter.lower() in d.name.lower()]
    return dirs[:limit]


def find_latest_autoresearch_dirs(
    tag_filter: str | None = None, limit: int = 3
) -> list[Path]:
    """Return the most recently modified autoresearch run dirs matching tag."""
    return find_latest_run_dirs(tag_filter, limit=limit, prefixes=("autoresearch_",))


def find_latest_autoresearch_dirs_multi(
    tag_filters: list[str] | tuple[str, ...], limit: int = 3
) -> list[Path]:
    """Return latest autoresearch dirs across multiple tag filters."""
    runs_root = _ROOT / "backtest_runs"
    if not runs_root.exists():
        return []
    tag_filters_lc = [str(t).lower() for t in tag_filters if str(t).strip()]
    dirs = [
        d for d in runs_root.iterdir()
        if d.is_dir()
        and d.name.startswith("autoresearch_")
        and any(tag in d.name.lower() for tag in tag_filters_lc)
    ]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[:limit]


def read_best_candidates(
    run_dir: Path, top_n: int = 5, passed_only: bool = True
) -> list[dict[str, Any]]:
    """Return top_n passing candidates sorted by score."""
    csv_path = run_dir / "results.csv"
    if not csv_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            passed = r.get("passed") == "True"
            if passed_only and not passed:
                continue
            try:
                overrides = json.loads(r.get("overrides_json") or "{}")
            except Exception:
                overrides = {}
            rows.append({
                "passed": passed,
                "fail_reasons": str(r.get("fail_reasons") or "").strip(),
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


def read_portfolio_summary(run_dir: Path) -> dict[str, Any] | None:
    """Read a portfolio summary.csv into a compact dict."""
    csv_path = run_dir / "summary.csv"
    if not csv_path.exists():
        return None
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            row = next(csv.DictReader(f), None)
        if not row:
            return None
        return {
            "run": run_dir.name,
            "strategies": str(row.get("strategies") or ""),
            "symbols": str(row.get("symbols") or ""),
            "trades": int(float(row.get("trades") or 0)),
            "net_pnl": float(row.get("net_pnl") or 0),
            "profit_factor": float(row.get("profit_factor") or 0),
            "winrate": float(row.get("winrate") or 0),
            "max_drawdown": float(row.get("max_drawdown") or 0),
        }
    except Exception:
        return None


def read_progress_snapshot(run_dir: Path) -> dict[str, Any] | None:
    """Read progress.json from an autoresearch dir if available."""
    path = run_dir / "progress.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "run": run_dir.name,
        "current": int(data.get("current") or 0),
        "total": int(data.get("total") or 0),
        "last_tag": str(data.get("last_tag") or ""),
        "last_passed": bool(data.get("last_passed")),
        "last_net_pnl": float(data.get("last_net_pnl") or 0),
        "last_profit_factor": float(data.get("last_profit_factor") or 0),
        "last_fail_reasons": str(data.get("last_fail_reasons") or ""),
        "updated_utc": str(data.get("updated_utc") or ""),
    }


def _read_csv_first(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return next(csv.DictReader(f), None)
    except Exception:
        return None


def _equities_summary_score(row: dict[str, str]) -> float:
    ret = _safe_float(row.get("compounded_return_pct"), float("-inf"))
    trades = _safe_int(row.get("trades"))
    dd = abs(_safe_float(row.get("max_monthly_dd_pct")))
    months = _safe_int(row.get("months"), -1)
    pos_months = _safe_int(row.get("positive_months"), -1)
    neg_months = max(0, months - pos_months) if months > 0 and pos_months >= 0 else 0
    dd_penalty = max(0.0, dd - 8.0) * 1.5
    neg_penalty = float(neg_months) * 4.0
    return ret - neg_penalty - dd_penalty + trades * 0.02


def _find_best_equities_summary_patterns(glob_patterns: list[str]) -> tuple[Path | None, dict[str, str] | None]:
    best_path: Path | None = None
    best_row: dict[str, str] | None = None
    best_score = float("-inf")
    for pattern in glob_patterns:
        for path in _ROOT.glob(pattern):
            row = _read_csv_first(path)
            if not row:
                continue
            score = _equities_summary_score(row)
            if score > best_score:
                best_score = score
                best_path = path
                best_row = row
    return best_path, best_row


def _latest_equities_picks_preview(glob_patterns: list[str], limit: int = 5) -> dict[str, Any] | None:
    latest_csv: Path | None = None
    for pattern in glob_patterns:
        for path in _ROOT.glob(pattern):
            if latest_csv is None or path.stat().st_mtime > latest_csv.stat().st_mtime:
                latest_csv = path
    if latest_csv is None or not latest_csv.exists():
        return None
    try:
        with latest_csv.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return None
    if not rows:
        return None
    latest_month = max(str(r.get("month") or "").strip() for r in rows)
    picks = [r for r in rows if str(r.get("month") or "").strip() == latest_month]
    picks.sort(key=lambda r: _safe_float(r.get("score")), reverse=True)
    return {
        "path": str(latest_csv),
        "month": latest_month,
        "tickers": [str(r.get("ticker") or "").strip().upper() for r in picks[:limit] if str(r.get("ticker") or "").strip()],
    }


def summarize_run(run_dir: Path) -> str:
    """One-line text summary of a run (for Telegram)."""
    bests = read_best_candidates(run_dir, top_n=1)
    total_lines = 0
    csv_path = run_dir / "results.csv"
    if csv_path.exists():
        with csv_path.open() as f:
            total_lines = sum(1 for _ in f) - 1  # minus header
    if not bests:
        raw_best = read_best_candidates(run_dir, top_n=1, passed_only=False)
        if not raw_best:
            return f"📂 {run_dir.name}: {total_lines} кандидатов, ни один не прошёл фильтры."
        b = raw_best[0]
        reasons = f"  fail={b['fail_reasons']}" if b["fail_reasons"] else ""
        return (
            f"📂 {run_dir.name}\n"
            f"  всего={total_lines}  PASS=0  best raw score={b['score']:.2f}\n"
            f"  trades={b['trades']}  pnl={b['net_pnl']:.1f}%  "
            f"pf={b['profit_factor']:.3f}  wr={b['winrate']:.1%}\n"
            f"  dd={b['max_drawdown']:.2f}%  red_months={b['negative_months']}{reasons}"
        )
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
    normalized_hint = (strategy_hint or "").strip().lower()
    if normalized_hint in _PORTFOLIO_HINTS:
        dirs = find_latest_run_dirs("new_5strat_final", limit=1, prefixes=("portfolio_",))
        if not dirs:
            return "Не найден текущий summary полного 5-рукавного стека."
        summary = read_portfolio_summary(dirs[0])
        if not summary:
            return f"Не удалось прочитать summary из {dirs[0].name}."
        sleeves = summary["strategies"].replace(";", ", ")
        return (
            "📦 Текущий лучший 5-рукавный стек:\n\n"
            f"run={summary['run']}\n"
            f"trades={summary['trades']}  pnl={summary['net_pnl']:.2f}%  "
            f"pf={summary['profit_factor']:.3f}  wr={summary['winrate']:.1%}\n"
            f"dd={summary['max_drawdown']:.2f}%\n"
            f"sleeves={sleeves}"
        )

    if normalized_hint in _EQUITIES_HINTS:
        lines = ["📊 Equities / Alpaca research:\n"]
        confirmed_path, confirmed = _find_best_equities_summary_patterns([
            "backtest_runs/*equities_monthly_v21_red_month_push*/summary.csv",
        ])
        if confirmed:
            months = _safe_int(confirmed.get("months"))
            pos_months = _safe_int(confirmed.get("positive_months"))
            neg_months = max(0, months - pos_months) if months > 0 else 0
            lines.append(
                "✅ confirmed frontier\n"
                f"run={confirmed_path.parent.name if confirmed_path else 'n/a'}\n"
                f"return={_safe_float(confirmed.get('compounded_return_pct')):.2f}%  "
                f"trades={_safe_int(confirmed.get('trades'))}  "
                f"WR={_safe_float(confirmed.get('winrate_pct')):.2f}%\n"
                f"red_months={neg_months}  max_month_dd={_safe_float(confirmed.get('max_monthly_dd_pct')):.2f}%"
            )
        repair_path, repair = _find_best_equities_summary_patterns([
            "backtest_runs/*equities_monthly_v23_breadth_exit_cluster*/summary.csv",
        ])
        if repair:
            lines.append(
                "\n🧪 latest repair frontier\n"
                f"run={repair_path.parent.name if repair_path else 'n/a'}\n"
                f"return={_safe_float(repair.get('compounded_return_pct')):.2f}%  "
                f"trades={_safe_int(repair.get('trades'))}  "
                f"WR={_safe_float(repair.get('winrate_pct')):.2f}%\n"
                f"max_month_dd={_safe_float(repair.get('max_monthly_dd_pct')):.2f}%"
            )
        dirs = find_latest_autoresearch_dirs_multi(_EQUITIES_AUTORESEARCH_TAGS, limit=3)
        if dirs:
            progress = read_progress_snapshot(dirs[0])
            if progress:
                lines.append(
                    "\n⏱ latest autoresearch\n"
                    f"run={progress['run']}  {progress['current']}/{progress['total']}  "
                    f"last_net={progress['last_net_pnl']:.2f}%  "
                    f"last_pf={progress['last_profit_factor']:.3f}"
                )
            freshest = dirs[0]
            bests = read_best_candidates(freshest, top_n=top_n)
            if not bests:
                bests = read_best_candidates(freshest, top_n=top_n, passed_only=False)
            if bests:
                lines.append(f"\n🏆 best recent rows from {freshest.name}:")
                for i, b in enumerate(bests[:top_n], 1):
                    pf_text = f"{b['profit_factor']:.3f}" if b["profit_factor"] == b["profit_factor"] else "n/a"
                    lines.append(
                        f"#{i} pnl={b['net_pnl']:.1f}% pf={pf_text} "
                        f"trades={b['trades']} dd={b['max_drawdown']:.2f}% "
                        f"red_months={b['negative_months']}"
                    )
        picks = _latest_equities_picks_preview([
            "backtest_runs/*equities_monthly_v23_breadth_exit_cluster*/picks.csv",
            "backtest_runs/*equities_monthly_v21_red_month_push*/picks.csv",
        ])
        if picks and picks["tickers"]:
            lines.append(
                "\n🧺 latest picks preview\n"
                f"month={picks['month']}  tickers={', '.join(picks['tickers'])}"
            )
        return "\n".join(lines)

    tag_filter = STRATEGY_TAGS.get(normalized_hint, normalized_hint)
    dirs = find_latest_autoresearch_dirs(tag_filter=tag_filter or None, limit=5)
    if not dirs:
        return "Результатов autoresearch не найдено."
    lines = [f"📊 Последние autoresearch{'  (' + normalized_hint + ')' if normalized_hint else ''}:\n"]
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
    else:
        raw_bests = read_best_candidates(freshest, top_n=top_n, passed_only=False)
        if raw_bests:
            lines.append(f"\n🧪 Лучшие raw-карманы из {freshest.name}:")
            for i, b in enumerate(raw_bests[:top_n], 1):
                ov_str = "  ".join(f"{k}={v}" for k, v in b["overrides"].items())
                lines.append(
                    f"#{i} score={b['score']:.2f} trades={b['trades']} "
                    f"pnl={b['net_pnl']:.1f}% pf={b['profit_factor']:.3f} "
                    f"fail={b['fail_reasons'] or '-'}\n"
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
    if strategy in _EQUITIES_HINTS:
        user += (
            "\n\nДля equities обязательно оценивай не только return, но и "
            "breadth/regime gates, max_hold_days, TOP_N, UNIVERSE_TOP_K, "
            "cluster/correlation controls и worst-month smoothness. "
            "Не предлагай ослабления, которые просто раздувают universe без контроля качества."
        )
    return system, user


def build_research_context() -> dict[str, Any]:
    """
    Build a rich context dict with the latest autoresearch findings.
    This is merged into the DeepSeek snapshot so the AI has full
    historical knowledge when answering /ai questions.
    """
    current_stack_dirs = find_latest_run_dirs("new_5strat_final", limit=1, prefixes=("portfolio_",))
    current_stack_best = read_portfolio_summary(current_stack_dirs[0]) if current_stack_dirs else None
    ctx: dict[str, Any] = {
        "known_best_params": {
            "inplay_breakout": {
                "BT_BREAKOUT_QUALITY_MIN_SCORE": "0.54",
                "BREAKOUT_BUFFER_ATR": "0.12",
                "BREAKOUT_MAX_CHASE_PCT": "0.14",
                "BREAKOUT_MAX_DIST_ATR": "1.4",
                "BREAKOUT_RECLAIM_ATR": "0.12",
                "BREAKOUT_ALLOW_SHORTS": "0",
                "source": "breakout_live_bridge_v2/v3 focus runs; denser core without blowing up drawdown",
                "result": "≈337-346 trades/year, WR ≈65%, PF ≈1.40, DD ≈3.0%, 2 red months",
            },
            "alt_sloped_channel_v1": {
                "ASC1_SYMBOL_ALLOWLIST": "ATOMUSDT,LINKUSDT,DOTUSDT",
                "ASC1_ALLOW_SHORTS": "1",
                "ASC1_ALLOW_LONGS": "0",
                "ASC1_SHORT_MIN_REJECT_DEPTH_ATR": "0.75+",
                "ASC1_SHORT_MIN_RSI": "60+",
                "ASC1_CONFIRM_5M_BARS": "4-6",
                "SLOPED_RISK_MULT": "0.10",
                "source": "asc1 expansion + long-mode audit; DOT is the best current additive coin, longs still disabled in bearish regime",
                "result": "≈19.4% net, PF 2.68, WR 52.8%, DD 1.91% on the current expansion frontier",
            },
            "alt_resistance_fade_v1": {
                "ARF1_SYMBOL_ALLOWLIST": "LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT,ADAUSDT,BCHUSDT",
                "FLAT_RISK_MULT": "0.10",
                "source": "arf1 6-coin validation run",
                "result": "37.48% net, PF 3.495, WR 52.6%, DD 1.59%, 0 red months",
            },
            "btc_eth_midterm_pullback": {
                "MIDTERM_SYMBOLS": "BTCUSDT,ETHUSDT (live); ETHUSDT-only repair pocket under test",
                "MTPB_LONG_RECLAIM_PCT": "0.18 (repair sweep baseline)",
                "MTPB_LONG_TOUCH_TOL_PCT": "0.12 (repair sweep baseline)",
                "MTPB_MAX_SIGNALS_PER_DAY": "1-2 (repair sweep baseline)",
                "source": "midterm_eth_repair_v1 early frontier; still below live-upgrade threshold",
                "result": "best raw pocket so far ≈52 trades, +4.24..4.73%, PF ≈1.34..1.39, DD ≈2.19, 3 red months",
            },
            "alt_inplay_breakdown_v1": {
                "BREAKDOWN_SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT,LTCUSDT,BNBUSDT",
                "BREAKDOWN_REGIME_MODE": "off",
                "BREAKDOWN_LOOKBACK_H": "48",
                "BREAKDOWN_RR": "2.0",
                "BREAKDOWN_SL_ATR": "1.8",
                "BREAKDOWN_MAX_DIST_ATR": "2.0",
                "source": "breakdown_expansion_v1 best run; live currently uses a slightly more conservative 6-symbol sleeve",
                "result": "81.22% net, PF 2.118, WR 57.4%, DD 3.56%, ~1 red month",
            },
            "equities_monthly_v21": {
                "TOP_N": "3",
                "UNIVERSE_TOP_K": "8",
                "MAX_HOLD_DAYS": "8",
                "STOP_ATR_MULT": "1.3",
                "TARGET_ATR_MULT": "4.0",
                "REGIME_MIN_BREADTH_MOM_PCT": "60-62",
                "REGIME_MIN_AVG_MOM_PCT": "2.0-2.3",
                "BENCH_MIN_AVG_MOM_PCT": "0.8-1.0",
                "source": "equities_monthly_v21_red_month_push confirmed frontier",
                "result": "≈63.20% net, 46 trades, WR 58.7%, max month DD ≈-8.08%, 4 red months",
            },
            "equities_monthly_repair": {
                "current_focus": "breadth stricter + earlier exits + cluster/correlation discipline",
                "latest_repair_run": "equities_monthly_v23_breadth_exit_cluster",
                "result": "latest repair peaked around 55.79% / 42 trades / WR 57.1%, smoother than weak baselines but still below confirmed v21 frontier",
            },
        },
        "current_portfolio_best": current_stack_best or {},
        "combined_4strat_best": {
            "deprecated_alias": "historical name kept for backward compatibility; now points to the current 5-sleeve stack",
            **(current_stack_best or {}),
        },
        "pending_autoresearch": [],
    }

    # Append running autoresearch status
    for tag in [
        "breakout_live_bridge_v3_density",
        "midterm_eth_repair_v1",
        "breakdown_expansion_v1",
        "asc1_expansion_v1",
        "equities_monthly_v21_red_month_push",
        "equities_monthly_v23_breadth_exit_cluster",
    ]:
        dirs = find_latest_autoresearch_dirs(tag_filter=tag, limit=1)
        if not dirs:
            continue
        progress = read_progress_snapshot(dirs[0])
        if progress:
            progress["tag_filter"] = tag
            ctx["pending_autoresearch"].append(progress)

    # Collect top 3 candidates from the most relevant recent runs
    summaries: list[dict[str, Any]] = []
    for tag in [
        "breakdown_expansion_v1",
        "asc1_expansion_v1",
        "breakout_live_bridge_v3_density",
        "midterm_eth_repair_v1",
        "equities_monthly_v21_red_month_push",
        "equities_monthly_v23_breadth_exit_cluster",
    ]:
        dirs = find_latest_autoresearch_dirs(tag_filter=tag, limit=1)
        if not dirs:
            continue
        bests = read_best_candidates(dirs[0], top_n=3)
        if bests:
            summaries.append({"run": dirs[0].name, "mode": "passed", "top3": bests[:3]})
            continue
        raw_bests = read_best_candidates(dirs[0], top_n=3, passed_only=False)
        if raw_bests:
            summaries.append({"run": dirs[0].name, "mode": "raw", "top3": raw_bests[:3]})
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

    if strategy in _PORTFOLIO_HINTS:
        return (
            "Для полного стека лучше тюнить рукава по отдельности: "
            "breakout, midterm, flat, asc1, breakdown, alpaca."
        )

    # Find relevant results
    if strategy in _EQUITIES_HINTS:
        dirs = find_latest_autoresearch_dirs_multi(_EQUITIES_AUTORESEARCH_TAGS, limit=2)
    else:
        tag_filter = STRATEGY_TAGS.get(strategy, strategy)
        dirs = find_latest_autoresearch_dirs(tag_filter=tag_filter, limit=2)
    if not dirs:
        return f"Нет данных autoresearch для стратегии '{strategy}'."

    bests = read_best_candidates(dirs[0], top_n=8)
    used_raw_candidates = False
    if not bests:
        bests = read_best_candidates(dirs[0], top_n=8, passed_only=False)
        used_raw_candidates = bool(bests)
    if not bests:
        return f"Нет кандидатов для анализа в {dirs[0].name}."

    system, user = _build_tune_prompt(strategy, bests)
    if used_raw_candidates:
        user += (
            "\n\nВнимание: в этом run пока нет PASS-кандидатов. "
            "Анализируй лучшие raw-карманы и предлагай только осторожные, "
            "локальные изменения без агрессивного ослабления фильтров."
        )
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


# ── Bot code audit ────────────────────────────────────────────────────────────

_AUDIT_STRATEGIES = [
    "alt_sloped_channel_v1",
    "alt_resistance_fade_v1",
    "alt_inplay_breakdown_v1",
    "inplay_breakout",
    "btc_eth_midterm_pullback",
]

_SECRET_KEYS_SUBSTRINGS = {"SECRET", "API_KEY", "API_SECRET", "ACCOUNTS_JSON", "TOKEN", "PASSWORD"}


def _redact_env_line(line: str) -> str:
    """Redact secrets from a single env file line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return line
    key = stripped.split("=", 1)[0].strip().upper()
    if any(s in key for s in _SECRET_KEYS_SUBSTRINGS):
        display_key = stripped.split("=", 1)[0].strip()
        return f"{display_key}=<redacted>"
    return line


def read_env_config_redacted(max_lines: int = 120) -> str:
    """Read the bot .env file with secrets redacted — safe for DeepSeek context."""
    candidates = [
        _ROOT / ".env",
        _ROOT / "configs" / "server.env.example",
        _ROOT / "configs" / "server_clean.env",
    ]
    for path in candidates:
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                lines = raw.splitlines()[:max_lines]
                redacted = [_redact_env_line(l) for l in lines]
                suffix = f"\n... ({len(raw.splitlines()) - max_lines} строк скрыто)" if len(raw.splitlines()) > max_lines else ""
                return "\n".join(redacted) + suffix
            except Exception:
                continue
    return "(файл конфига не найден)"


def read_strategy_file(name: str, max_lines: int = 180) -> str:
    """Read a strategy file from strategies/ dir, truncated to max_lines."""
    path = _ROOT / "strategies" / f"{name}.py"
    if not path.exists():
        return f"(не найден: strategies/{name}.py)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        snippet = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            snippet += f"\n... ({len(lines) - max_lines} строк обрезано)"
        return snippet
    except Exception as e:
        return f"(ошибка чтения: {e})"


def read_any_bot_file(relative_path: str, max_lines: int = 250) -> str:
    """
    Read any file relative to bot root for /ai_code <filename>.
    Only paths inside allowed directories to prevent traversal.
    """
    _ALLOWED_DIRS = {"strategies", "bot", "backtest", "configs", "scripts"}
    p = Path(relative_path.replace("\\", "/"))
    parts = p.parts
    if not parts or ".." in parts or p.is_absolute():
        return "❌ Отказано: абсолютный путь или '..' не разрешён."
    if parts[0] not in _ALLOWED_DIRS and p.name != "smart_pump_reversal_bot.py":
        return f"❌ Отказано: разрешены директории {', '.join(sorted(_ALLOWED_DIRS))}."
    full = (_ROOT / p).resolve()
    try:
        full.relative_to(_ROOT.resolve())
    except ValueError:
        return "❌ Отказано: путь вне каталога бота."
    if not full.exists():
        return f"(файл не найден: {relative_path})"
    if not full.is_file():
        return f"(это не файл: {relative_path})"
    try:
        lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
        snippet = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            snippet += f"\n... ({len(lines) - max_lines} строк обрезано)"
        return snippet
    except Exception as e:
        return f"(ошибка чтения: {e})"


def audit_bot_full(snapshot: dict[str, Any]) -> str:
    """
    Full autonomous audit: reads strategy code + config, sends to DeepSeek.
    Returns Telegram-ready report string.
    """
    if not _env_bool("DEEPSEEK_ENABLE"):
        return "⚠️ DeepSeek выключен (DEEPSEEK_ENABLE=0)."
    if not _env("DEEPSEEK_API_KEY"):
        return "⚠️ DEEPSEEK_API_KEY не задан."

    # Collect config (redacted)
    env_text = read_env_config_redacted(max_lines=90)

    # Collect strategy summaries
    strategy_parts = []
    for strat in _AUDIT_STRATEGIES:
        code = read_strategy_file(strat, max_lines=100)
        strategy_parts.append(f"### {strat}.py\n{code}")
    strategies_text = "\n\n".join(strategy_parts)

    # Runtime summary
    rt = snapshot.get("runtime_stats_12h", "n/a")
    health = snapshot.get("health_30d", "n/a")
    eq = snapshot.get("effective_equity", "?")
    trade_on = snapshot.get("trade_on", "?")
    research_json = json.dumps(
        snapshot.get("research", {}).get("known_best_params", {}),
        ensure_ascii=False, indent=2
    )

    system = (
        "Ты senior Python-разработчик и квантовый трейдер. "
        "Тебе дан торговый бот для Bybit perpetual futures. "
        "Проведи честный профессиональный аудит. Отвечай строго на русском языке. "
        "Будь конкретным и прямолинейным. Объём: до 600 слов."
    )
    user = (
        f"== СТАТУС БОТА ==\n"
        f"trade_on={trade_on}, equity≈{eq} USDT\n"
        f"Статистика за 12h:\n{rt}\n\n"
        f"Здоровье за 30d:\n{health}\n\n"
        f"== ЛУЧШИЕ ИЗВЕСТНЫЕ ПАРАМЕТРЫ ==\n{research_json}\n\n"
        f"== КОНФИГ (секреты скрыты) ==\n{env_text}\n\n"
        f"== КОД СТРАТЕГИЙ (первые ~100 строк каждой) ==\n{strategies_text}\n\n"
        "== ЗАДАЧА АУДИТА ==\n"
        "Ответь по трём блокам:\n"
        "1. ⚠️ РИСКИ: конкретные угрозы — что может пойти не так?\n"
        "2. 📊 ПАРАМЕТРЫ: что выглядит не оптимально в текущих настройках?\n"
        "3. 💡 ПРЕДЛОЖЕНИЯ: 3–5 конкретных улучшений.\n"
        "   Каждое начни с «ПРЕДЛОЖЕНИЕ:» чтобы я мог обсудить с разработчиком.\n"
        "Без воды. Только конкретика."
    )

    answer = _ds_chat(system, user, model=_env("DEEPSEEK_MODEL", "deepseek-chat"))
    return "🔍 DeepSeek Аудит бота\n\n" + answer


def ask_about_file(filename: str, question: str | None, snapshot: dict[str, Any]) -> str:
    """
    Read a specific bot file and ask DeepSeek about it.
    Used by /ai_code <filename> [question].
    """
    if not _env_bool("DEEPSEEK_ENABLE"):
        return "⚠️ DeepSeek выключен."
    if not _env("DEEPSEEK_API_KEY"):
        return "⚠️ DEEPSEEK_API_KEY не задан."

    code = read_any_bot_file(filename, max_lines=250)
    if code.startswith("❌") or code.startswith("("):
        return code

    system = (
        "Ты senior Python-разработчик и квантовый трейдер. "
        "Анализируй код торгового бота. Отвечай на русском. Кратко и конкретно."
    )
    q = question or "Что делает этот код? Что работает хорошо и что можно улучшить?"
    user = f"Файл: {filename}\n\n```python\n{code}\n```\n\nВопрос: {q}"

    return _ds_chat(system, user)


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
