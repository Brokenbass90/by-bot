#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deepseek_weekly_cron.py — Autonomous DeepSeek weekly research & self-improvement agent.

Runs automatically on a schedule (cron) or manually. Does the full weekly cycle:

  1. AUDIT       — checks live strategy health (recent trades PF, DD trend)
  2. TUNE        — calls DeepSeek to analyze each strategy's autoresearch results
                   and propose parameter improvements (queued for human approval)
  3. RESEARCH    — flags finished autoresearch runs, summarises best combos
  4. UNIVERSE    — asks DeepSeek to suggest new symbols to test per strategy family
  5. REPORT      — sends a structured weekly digest via Telegram

Nothing is auto-applied. All changes go through the approval queue
(/ai_approve <id> via Telegram). This script is purely analytical + advisory.

Usage:
  # Manual run (full sweep):
  python3 scripts/deepseek_weekly_cron.py

  # Dry run (no DeepSeek API calls, no Telegram):
  python3 scripts/deepseek_weekly_cron.py --dry-run

  # Only specific phases:
  python3 scripts/deepseek_weekly_cron.py --phases audit,research,report

  # Cron (every Sunday at 22:00 local):
  # 0 22 * * 0 cd /root/by-bot && python3 scripts/deepseek_weekly_cron.py --quiet >> logs/deepseek_weekly.log 2>&1

Env vars required (same as bot):
  DEEPSEEK_ENABLE=1
  DEEPSEEK_API_KEY=<key>
  TG_TOKEN=<token>        (optional — for Telegram report)
  TG_CHAT_ID=<chat_id>    (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BOT_DIR = ROOT / "bot"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

try:
    from bot.deepseek_research_gate import gate as _research_gate
    _GATE_AVAILABLE = True
except ImportError:
    _research_gate = None  # type: ignore[assignment]
    _GATE_AVAILABLE = False

try:
    from bot.operator_snapshot import build_operator_snapshot
except ImportError:
    build_operator_snapshot = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "y", "on"}


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

_TG_CHUNK = 3900  # safe below Telegram 4096 hard limit


def _tg_send_chunk(token: str, chat_id: str, text: str) -> None:
    """Send a single chunk (caller must ensure len ≤ 4096)."""
    import urllib.request, ssl, json as _json
    payload = _json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15):
            pass
    except Exception as e:
        print(f"[tg] send failed: {e}", file=sys.stderr)


def _tg_send(token: str, chat_id: str, text: str) -> None:
    """Send message with automatic chunking for messages > 3900 chars."""
    if not token or not chat_id or not text:
        return
    text = str(text)
    if len(text) <= _TG_CHUNK:
        _tg_send_chunk(token, chat_id, text)
        return
    # Split on newlines, fall back to hard cut
    lines = text.split("\n")
    chunk = ""
    chunks: list = []
    for line in lines:
        candidate = (chunk + "\n" + line) if chunk else line
        if len(candidate) > _TG_CHUNK:
            if chunk:
                chunks.append(chunk)
                chunk = line
            else:
                while line:
                    chunks.append(line[:_TG_CHUNK])
                    line = line[_TG_CHUNK:]
        else:
            chunk = candidate
    if chunk:
        chunks.append(chunk)
    total = len(chunks)
    for i, ch in enumerate(chunks, 1):
        prefix = f"[{i}/{total}]\n" if total > 1 else ""
        _tg_send_chunk(token, chat_id, f"{prefix}{ch}")


# ---------------------------------------------------------------------------
# Live performance audit (reads recent backtest runs as proxy)
# ---------------------------------------------------------------------------

def _audit_recent_runs(days_lookback: int = 14) -> dict[str, Any]:
    """Scan backtest_runs for portfolio runs in last N days and aggregate per-strategy health."""
    runs_dir = ROOT / "backtest_runs"
    cutoff = time.time() - days_lookback * 86400
    strategy_stats: dict[str, dict[str, Any]] = {}
    scanned = 0

    for run_path in sorted(runs_dir.glob("portfolio_*"), reverse=True)[:80]:
        try:
            mtime = run_path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        summary_path = run_path / "summary.csv"
        if not summary_path.exists():
            continue
        try:
            import csv
            with summary_path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if not rows:
                continue
            row = rows[0]
            strats = [s.strip() for s in str(row.get("strategies") or "").split(";") if s.strip()]
            pf = float(row.get("profit_factor") or 0.0)
            dd = float(row.get("max_drawdown") or 0.0)
            trades = int(row.get("trades") or 0)
            net = float(row.get("net_pnl") or 0.0)
            for st in strats:
                if st not in strategy_stats:
                    strategy_stats[st] = {"runs": 0, "pf_sum": 0.0, "dd_max": 0.0, "net_sum": 0.0, "trades_sum": 0}
                s = strategy_stats[st]
                s["runs"] += 1
                s["pf_sum"] += pf
                s["dd_max"] = max(s["dd_max"], dd)
                s["net_sum"] += net
                s["trades_sum"] += trades
            scanned += 1
        except Exception:
            continue

    summary: dict[str, Any] = {"scanned_runs": scanned, "strategies": {}}
    for st, s in strategy_stats.items():
        r = s["runs"]
        summary["strategies"][st] = {
            "runs": r,
            "avg_pf": round(s["pf_sum"] / r, 3) if r else 0.0,
            "avg_net": round(s["net_sum"] / r, 3) if r else 0.0,
            "max_dd": round(s["dd_max"], 3),
            "avg_trades_per_run": round(s["trades_sum"] / r, 1) if r else 0,
            "health": "OK" if (s["pf_sum"] / r >= 1.5 and s["dd_max"] < 10.0) else "WATCH",
        }
    return summary


# ---------------------------------------------------------------------------
# Autoresearch scanner
# ---------------------------------------------------------------------------

def _scan_finished_autoresearch(days_lookback: int = 14) -> list[dict[str, Any]]:
    """Find autoresearch runs finished in last N days with at least 1 PASS combo."""
    runs_dir = ROOT / "backtest_runs"
    cutoff = time.time() - days_lookback * 86400
    results = []

    for run_path in sorted(runs_dir.glob("autoresearch_*"), reverse=True)[:30]:
        try:
            mtime = run_path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        ranked = run_path / "ranked_results.csv"
        if not ranked.exists():
            continue
        try:
            import csv
            with ranked.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            passed = [r for r in rows if str(r.get("passed", "")).strip().lower() in {"true", "1", "yes"}]
            if not passed:
                continue
            best = passed[0]
            results.append({
                "name": run_path.name,
                "pass_count": len(passed),
                "best_pf": float(best.get("profit_factor") or 0.0),
                "best_net": float(best.get("net_pnl") or 0.0),
                "best_trades": int(best.get("trades") or 0),
                "best_overrides": best.get("overrides_json", ""),
            })
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# DeepSeek universe expansion prompt
# ---------------------------------------------------------------------------

UNIVERSE_SYSTEM = """You are a quantitative trading research assistant for a Bybit perpetual futures bot.
You analyse market conditions and suggest symbol universes for specific strategy families.
Respond ONLY with a JSON object, no markdown."""

def _build_universe_prompt(strategy_family: str, current_symbols: list[str], perf_summary: str) -> str:
    return f"""Strategy family: {strategy_family}
Current symbols: {', '.join(current_symbols)}
Recent performance summary: {perf_summary}

Based on this strategy's mechanics, suggest:
1. Up to 5 NEW symbols to ADD to the universe (Bybit USDT perps, liquid, >$30M daily volume)
2. Up to 2 symbols to REMOVE if they look structurally wrong for this strategy
3. One sentence explaining the rationale

Reply with JSON:
{{
  "add": ["SYMBOL1USDT", "SYMBOL2USDT"],
  "remove": ["SYMBOLUSDT"],
  "rationale": "..."
}}"""


def _ds_universe_suggest(strategy_family: str, current_symbols: list[str],
                          perf_summary: str, api_key: str, base_url: str, model: str) -> dict[str, Any]:
    """Call DeepSeek for universe expansion suggestions."""
    import urllib.request, ssl, json as _json
    payload = _json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": UNIVERSE_SYSTEM},
            {"role": "user", "content": _build_universe_prompt(strategy_family, current_symbols, perf_summary)},
        ],
        "max_tokens": 400,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            js = _json.loads(resp.read().decode())
        raw = js["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.splitlines()[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.splitlines()[:-1])
        return _json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Strategy tune via existing agent
# ---------------------------------------------------------------------------

def _run_tune_phase(strategies: list[str], dry_run: bool, quiet: bool) -> list[str]:
    """Call tune_strategy for each strategy. Returns list of result strings."""
    if dry_run:
        return [f"[dry-run] Would tune: {', '.join(strategies)}"]
    try:
        from deepseek_autoresearch_agent import tune_strategy, build_research_context
        from deepseek_overlay import DeepSeekOverlay
    except ImportError as e:
        return [f"[tune] Import error: {e}"]

    overlay = DeepSeekOverlay()
    if not overlay.is_ready():
        return ["[tune] DeepSeek не готов — проверь DEEPSEEK_ENABLE и DEEPSEEK_API_KEY"]

    snapshot = build_research_context()
    if build_operator_snapshot is not None:
        snapshot["operator_context"] = build_operator_snapshot(ROOT)
    results = []
    for st in strategies:
        if not quiet:
            print(f"[tune] Analyzing {st}...")
        try:
            msg = tune_strategy(st, overlay, snapshot)
            results.append(f"<b>{st}</b>: {msg[:300]}")
        except Exception as e:
            results.append(f"<b>{st}</b>: ошибка — {e}")
        time.sleep(2)  # polite delay between API calls
    return results


# ---------------------------------------------------------------------------
# Format report sections
# ---------------------------------------------------------------------------

def _format_audit_section(audit: dict[str, Any]) -> str:
    lines = ["📊 <b>Аудит стратегий (последние 14 дней)</b>"]
    strats = audit.get("strategies", {})
    if not strats:
        lines.append("  Нет данных по недавним прогонам")
        return "\n".join(lines)
    for st, s in sorted(strats.items()):
        icon = "✅" if s["health"] == "OK" else "⚠️"
        lines.append(
            f"  {icon} {st[:30]}: PF={s['avg_pf']:.2f} "
            f"net={s['avg_net']:+.1f}% "
            f"DD={s['max_dd']:.1f}% "
            f"({s['runs']} runs)"
        )
    return "\n".join(lines)


def _format_autoresearch_section(runs: list[dict[str, Any]]) -> str:
    if not runs:
        return "🔬 <b>Новые autoresearch</b>\n  Нет завершённых прогонов за 14 дней"
    lines = ["🔬 <b>Завершённые autoresearch (14 дней)</b>"]
    for r in runs[:5]:
        lines.append(
            f"  📁 {r['name'][:50]}\n"
            f"     PASS: {r['pass_count']} | PF={r['best_pf']:.2f} | "
            f"net={r['best_net']:+.1f}% | trades={r['best_trades']}"
        )
    return "\n".join(lines)


def _format_universe_section(suggestions: dict[str, dict[str, Any]]) -> str:
    if not suggestions:
        return ""
    lines = ["🌐 <b>DeepSeek: расширение universe</b>"]
    for family, s in suggestions.items():
        if "error" in s:
            lines.append(f"  ❌ {family}: {s['error'][:80]}")
            continue
        add = ", ".join(s.get("add") or [])
        rem = ", ".join(s.get("remove") or [])
        rationale = s.get("rationale", "")[:120]
        lines.append(f"  <b>{family}</b>")
        if add:
            lines.append(f"    ➕ Добавить: {add}")
        if rem:
            lines.append(f"    ➖ Убрать: {rem}")
        if rationale:
            lines.append(f"    💡 {rationale}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Active strategies to tune each week
WEEKLY_TUNE_STRATEGIES = ["breakout", "flat", "asc1", "midterm", "breakdown"]

# Universe families with their current symbols
UNIVERSE_FAMILIES = {
    "ASC1 (sloped channel)": ["ATOMUSDT", "LINKUSDT", "DOTUSDT"],
    "ARF1 (flat fade)": ["LINKUSDT", "LTCUSDT", "SUIUSDT", "DOTUSDT", "ADAUSDT", "BCHUSDT"],
    "BREAKDOWN (shorts)": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ATOMUSDT", "LTCUSDT"],
}

ALL_PHASES = ["audit", "tune", "research", "universe", "report"]


def main() -> int:
    ap = argparse.ArgumentParser(description="DeepSeek weekly autonomous research cron")
    ap.add_argument("--dry-run", action="store_true", help="No API calls, no Telegram, just print.")
    ap.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    ap.add_argument(
        "--phases", default=",".join(ALL_PHASES),
        help=f"Comma-separated phases to run. Available: {', '.join(ALL_PHASES)}",
    )
    ap.add_argument("--strategies", default=",".join(WEEKLY_TUNE_STRATEGIES),
                    help="Strategies to tune (comma-separated).")
    ap.add_argument("--skip-universe", action="store_true",
                    help="Skip universe expansion suggestions (saves API tokens).")
    args = ap.parse_args()

    phases = {p.strip() for p in args.phases.split(",") if p.strip()}
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    tg_token = _env("TG_TOKEN")
    tg_chat_id = _env("TG_CHAT_ID")
    api_key = _env("DEEPSEEK_API_KEY")
    base_url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = _env("DEEPSEEK_MODEL", "deepseek-chat")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    report_sections: list[str] = [
        f"🤖 <b>DeepSeek Weekly Report</b>\n📅 {now_str}"
    ]

    # ── Phase 0: Research gate status ────────────────────────────────────────
    if _GATE_AVAILABLE and not args.dry_run:
        gate_status_text = _research_gate.status_report()  # type: ignore[union-attr]
        pending_proposals = _research_gate.list_proposals("pending")  # type: ignore[union-attr]
        if pending_proposals and not args.quiet:
            print(f"[gate] {len(pending_proposals)} pending research proposal(s) awaiting approval")
    else:
        gate_status_text = ""
        pending_proposals = []

    # ── Phase 1: Audit ────────────────────────────────────────────────────────
    audit: dict[str, Any] = {}
    if "audit" in phases:
        if not args.quiet:
            print("[1/5] Running strategy audit...")
        audit = _audit_recent_runs(days_lookback=14)
        section = _format_audit_section(audit)
        report_sections.append(section)
        if not args.quiet:
            print(section)

    # ── Gate: auto-trigger check ──────────────────────────────────────────────
    # Fires after audit so we have strategy stats to evaluate WR / health status
    if _GATE_AVAILABLE and not args.dry_run and "audit" in phases:
        # Build winrate proxy from audit stats (avg_pf as signal quality proxy)
        # Real live winrate would come from trade logs; PF >= 1.5 = rough OK threshold
        strat_stats_for_gate: dict[str, dict] = {}
        for st, s in audit.get("strategies", {}).items():
            # Approx WR from PF: WR ≈ 1 - 1/(1 + PF*R), assume R≈1.5 avg winner/loser
            avg_pf = s.get("avg_pf", 1.0)
            approx_wr = avg_pf / (avg_pf + 1.0)           # crude but directionally correct
            strat_stats_for_gate[st] = {"winrate_30d": approx_wr}

        triggered_specs = _research_gate.check_triggers(  # type: ignore[union-attr]
            strategy_stats=strat_stats_for_gate or None,
        )
        if triggered_specs:
            if not args.quiet:
                print(f"[gate] {len(triggered_specs)} auto-trigger(s) fired → queuing proposals")
            for spec in triggered_specs:
                pid = _research_gate.propose(  # type: ignore[union-attr]
                    spec,
                    reason="Auto-trigger: weekly audit (low WR or equity curve degradation)",
                )
                if not args.quiet:
                    print(f"  [gate] Proposal queued: {Path(spec).name} → id={pid}")

    # ── Phase 2: Tune ─────────────────────────────────────────────────────────
    if "tune" in phases:
        if not args.quiet:
            print(f"[2/5] Running DeepSeek tune for: {', '.join(strategies)}...")
        tune_results = _run_tune_phase(strategies, dry_run=args.dry_run, quiet=args.quiet)
        section = "🔧 <b>DeepSeek param proposals</b>\n" + "\n\n".join(tune_results[:3])
        report_sections.append(section)

    # ── Phase 3: Research scan ────────────────────────────────────────────────
    if "research" in phases:
        if not args.quiet:
            print("[3/5] Scanning finished autoresearch runs...")
        finished = _scan_finished_autoresearch(days_lookback=14)
        section = _format_autoresearch_section(finished)
        report_sections.append(section)
        if not args.quiet:
            print(f"  Found {len(finished)} finished runs with PASS combos")

    # ── Phase 4: Universe expansion ───────────────────────────────────────────
    if "universe" in phases and not args.skip_universe:
        if not args.quiet:
            print("[4/5] Asking DeepSeek for universe suggestions...")
        universe_suggestions: dict[str, dict[str, Any]] = {}
        if not args.dry_run and api_key:
            for family, symbols in UNIVERSE_FAMILIES.items():
                if not args.quiet:
                    print(f"  Universe expand: {family}...")
                perf = "recent autoresearch shows stable PF around 2.0"
                sugg = _ds_universe_suggest(family, symbols, perf, api_key, base_url, model)
                universe_suggestions[family] = sugg
                time.sleep(3)
        elif args.dry_run:
            universe_suggestions = {f: {"add": ["EXAMPLE1USDT"], "remove": [], "rationale": "dry-run"} for f in UNIVERSE_FAMILIES}

        section = _format_universe_section(universe_suggestions)
        if section:
            report_sections.append(section)

    # ── Phase 5: Report ───────────────────────────────────────────────────────
    if "report" in phases:
        # Append research gate status block
        if gate_status_text:
            report_sections.append(gate_status_text)

        # Footer with next actions
        approve_hint = ""
        if pending_proposals:
            approve_hint = (
                "\n\n⚠️ <b>Research proposals waiting:</b>\n"
                + "\n".join(
                    f"  /approve {p['id'][:20]}…  — {p.get('spec_name','?')}"
                    for p in pending_proposals[:3]
                )
            )
        report_sections.append(
            "─────────────────────\n"
            "💡 <b>Следующие шаги</b>\n"
            "  /ai_approve &lt;id&gt;     — применить предложение DeepSeek\n"
            "  /ai_reject &lt;id&gt;      — отклонить\n"
            "  /ai_results            — последние autoresearch\n"
            "  /ai_tune breakout      — tune вручную\n"
            "  /research_status       — статус research gate\n"
            "  dynamic_allowlist.py --dry-run  — обновить монеты"
            + approve_hint
        )

    full_report = "\n\n".join(report_sections)

    # Save to file
    report_dir = ROOT / "docs" / "weekly_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"deepseek_weekly_{ts}.md"

    md_content = full_report.replace("<b>", "**").replace("</b>", "**").replace("<br>", "\n")
    report_path.write_text(md_content, encoding="utf-8")
    if not args.quiet:
        print(f"\nReport saved: {report_path}")

    # Send Telegram
    if "report" in phases and not args.dry_run:
        if tg_token and tg_chat_id:
            _tg_send(tg_token, tg_chat_id, full_report)
            if not args.quiet:
                print("Telegram report sent.")
        else:
            if not args.quiet:
                print("Telegram not configured (TG_TOKEN / TG_CHAT_ID missing).")

    if args.dry_run:
        print("\n[dry-run] Full report preview:")
        print("─" * 50)
        print(full_report[:2000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
