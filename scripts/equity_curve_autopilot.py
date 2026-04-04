#!/usr/bin/env python3
"""
Equity Curve Autopilot — Anti-Degradation System for Bybit Bot
===============================================================
Monitors per-strategy equity curves from recent backtest/live trade data.
Detects degradation early and triggers alerts before significant drawdowns.

What it does:
  1. Scans the latest portfolio backtest run (trades.csv)
  2. Builds per-strategy equity curves (cumulative PnL over time)
  3. Checks each curve against its own MA:
       • If curve < MA20  → WATCH  (possible regime drift)
       • If curve < MA20 AND rolling 30-day PnL < 0 → PAUSE  (active degradation)
       • If rolling 60-day PnL < 0 → KILL  (strategy not working)
  4. Writes configs/strategy_health.json (the main bot can check this)
  5. Sends Telegram digest with per-strategy status
  6. Logs to docs/weekly_reports/ alongside DeepSeek reports

Output (strategy_health.json):
  {
    "timestamp": "2026-03-29T...",
    "strategies": {
      "alt_inplay_breakdown_v1": {
        "status": "OK",          # OK | WATCH | PAUSE | KILL
        "rolling_30d_pnl": 4.2,  # % of total
        "rolling_60d_pnl": 8.1,
        "curve_vs_ma20": 0.03,   # positive = above MA
        "trades_30d": 12,
        "winrate_30d": 0.58,
        "pf_30d": 1.42
      },
      ...
    },
    "paused_strategies": ["alt_resistance_fade_v1"],
    "overall_health": "WATCH"   # OK | WATCH | PAUSE | KILL
  }

Usage:
  # Manual check
  python3 scripts/equity_curve_autopilot.py

  # Specify a particular run directory
  python3 scripts/equity_curve_autopilot.py --run-dir backtest_runs/portfolio_20260325_.../

  # Skip Telegram (just print)
  python3 scripts/equity_curve_autopilot.py --no-tg

  # Write health file only (for integration with main bot)
  python3 scripts/equity_curve_autopilot.py --quiet

Cron (weekly, same slot as DeepSeek):
  30 22 * * 0 cd /root/by-bot && python3 scripts/equity_curve_autopilot.py \
    >> logs/equity_autopilot.log 2>&1

Integration with main bot (optional):
  Add to your main trading loop before entering positions:
    from scripts.equity_curve_autopilot import strategy_is_healthy
    if not strategy_is_healthy("alt_inplay_breakdown_v1"):
        skip_entry()
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE    = ROOT / "configs" / "alpaca_paper_local.env"
HEALTH_FILE = ROOT / "configs" / "strategy_health.json"
REPORTS_DIR = ROOT / "docs" / "weekly_reports"
CONTROL_PLANE_DIR = ROOT / "runtime" / "control_plane"
BASELINE_REPORT = CONTROL_PLANE_DIR / "baseline_regression_latest.json"

# ── Thresholds ──────────────────────────────────────────────────────────────────
WATCH_THRESHOLD_MA  = 0.0    # curve below its own MA → WATCH
PAUSE_30D_LOSS      = -0.02  # rolling 30d PnL < -2% total PnL → PAUSE
KILL_60D_LOSS       = -0.04  # rolling 60d PnL < -4% total PnL → KILL
MIN_TRADES_FOR_EVAL = 5      # min trades in window to evaluate
MA_PERIOD_LONG      = 20     # equity curve MA period (trade count based)

# ── Env helpers ─────────────────────────────────────────────────────────────────
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()

# ── Telegram ─────────────────────────────────────────────────────────────────────
_TG_CHUNK = 3900


def _tg_chunk(token: str, chat_id: str, text: str) -> None:
    """Send single pre-sized chunk."""
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=10):
            pass
    except Exception:
        pass


def _tg(token: str, chat_id: str, msg: str) -> None:
    """Send Telegram message with automatic chunking (Telegram limit = 4096 chars)."""
    if not token or not chat_id or not msg:
        return
    msg = str(msg)
    if len(msg) <= _TG_CHUNK:
        _tg_chunk(token, chat_id, msg)
        return
    lines = msg.split("\n")
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
        _tg_chunk(token, chat_id, f"{prefix}{ch}")

# ── Data structures ──────────────────────────────────────────────────────────────
@dataclass
class Trade:
    strategy: str
    symbol: str
    exit_ts: int       # epoch ms → will convert to seconds
    pnl: float
    outcome: str       # tp | sl | timeout

@dataclass
class StrategyHealth:
    name: str
    status: str = "OK"          # OK | WATCH | PAUSE | KILL
    total_pnl: float = 0.0
    rolling_30d_pnl: float = 0.0
    rolling_60d_pnl: float = 0.0
    curve_vs_ma20: float = 0.0   # > 0 = above MA (healthy), < 0 = below MA
    trades_total: int = 0
    trades_30d: int = 0
    winrate_total: float = 0.0
    winrate_30d: float = 0.0
    pf_30d: float = 0.0
    notes: str = ""

# ── Load trades ──────────────────────────────────────────────────────────────────
def _summary_row(run_dir: Path) -> Dict[str, str]:
    path = run_dir / "summary.csv"
    if not path.exists():
        return {}
    try:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                return {str(k): str(v) for k, v in row.items()}
    except Exception:
        return {}
    return {}


def _is_exploratory_run(run_dir: Path) -> bool:
    """
    Reject research/probe/sweep style runs by default.
    The autopilot should not silently promote or demote live sleeves based on
    exploratory artifacts.
    """
    name = run_dir.name.lower()
    summary = _summary_row(run_dir)
    tag = str(summary.get("tag", "")).lower()
    hay = f"{name} {tag}"
    markers = (
        "sweep",
        "autoresearch",
        "probe",
        "compare",
        "smoke",
        "debug",
        "candidate",
    )
    if any(m in hay for m in markers):
        return True
    if re.search(r"_r\d+\b", hay):
        return True
    return False


def _baseline_report_run() -> Optional[Path]:
    if not BASELINE_REPORT.exists():
        return None
    try:
        data = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return None
    run_dir = str(data.get("run_dir", "") or "").strip()
    if not run_dir:
        return None
    p = Path(run_dir)
    return p if p.exists() else None


def _find_latest_run(*, allow_exploratory: bool = False) -> Optional[Path]:
    """
    Find the most recent trusted portfolio run directory.

    We prefer the latest validated baseline regression artifact. Fallback to
    archived baseline-like runs only; do not silently pick exploratory sweep
    outputs.
    """
    report_run = _baseline_report_run()
    if report_run is not None and (allow_exploratory or not _is_exploratory_run(report_run)):
        return report_run

    candidates: List[Path] = []
    patterns = [
        "backtest_runs/portfolio_*validated_baseline_regression*/trades.csv",
        "backtest_archive/portfolio_*baseline*/trades.csv",
        "backtest_runs/portfolio_*current90_true/trades.csv",
        "backtest_runs/portfolio_*180d_true/trades.csv",
    ]
    for pat in patterns:
        candidates.extend(ROOT.glob(pat))
    runs = sorted(candidates, key=lambda p: p.parent.stat().st_mtime, reverse=True)
    for csv_path in runs:
        run_dir = csv_path.parent
        if allow_exploratory or not _is_exploratory_run(run_dir):
            return run_dir
    return None

def _load_trades(run_dir: Path) -> List[Trade]:
    csv_path = run_dir / "trades.csv"
    if not csv_path.exists():
        return []
    trades: List[Trade] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                exit_ts_raw = int(float(row.get("exit_ts") or 0))
                # Convert ms → s if needed
                if exit_ts_raw > 10_000_000_000:
                    exit_ts_raw //= 1000
                trades.append(Trade(
                    strategy=row.get("strategy", "").strip(),
                    symbol=row.get("symbol", "").strip(),
                    exit_ts=exit_ts_raw,
                    pnl=float(row.get("pnl") or 0),
                    outcome=row.get("outcome", "").strip(),
                ))
            except Exception:
                continue
    return sorted(trades, key=lambda t: t.exit_ts)

# ── Equity curve analysis ────────────────────────────────────────────────────────
def _simple_ma(values: List[float], period: int) -> float:
    """Simple moving average of last `period` values."""
    if len(values) < period:
        return sum(values) / max(1, len(values))
    return sum(values[-period:]) / period

def _profit_factor(trades: List[Trade]) -> float:
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = abs(sum(t.pnl for t in trades if t.pnl < 0))
    return wins / losses if losses > 0 else (float("inf") if wins > 0 else 1.0)

def _analyze_strategy(name: str, trades: List[Trade], now_ts: int) -> StrategyHealth:
    h = StrategyHealth(name=name)
    if not trades:
        h.notes = "No trades"
        return h

    ts_30d = now_ts - 30 * 86400
    ts_60d = now_ts - 60 * 86400

    trades_30d = [t for t in trades if t.exit_ts >= ts_30d]
    trades_60d = [t for t in trades if t.exit_ts >= ts_60d]

    # Total stats
    h.trades_total   = len(trades)
    h.total_pnl      = sum(t.pnl for t in trades)
    wins_total       = sum(1 for t in trades if t.pnl > 0)
    h.winrate_total  = wins_total / len(trades) if trades else 0.0

    # 30d stats
    h.trades_30d     = len(trades_30d)
    h.rolling_30d_pnl = sum(t.pnl for t in trades_30d)
    h.rolling_60d_pnl = sum(t.pnl for t in trades_60d)

    if h.trades_30d >= MIN_TRADES_FOR_EVAL:
        wins_30d        = sum(1 for t in trades_30d if t.pnl > 0)
        h.winrate_30d   = wins_30d / h.trades_30d
        h.pf_30d        = _profit_factor(trades_30d)
    else:
        h.notes += f"Only {h.trades_30d} trades in 30d (min {MIN_TRADES_FOR_EVAL}). "

    # Equity curve: cumulative PnL series (one point per trade)
    cumulative = []
    running = 0.0
    for t in trades:
        running += t.pnl
        cumulative.append(running)

    # Current position vs MA20 of equity curve
    if len(cumulative) >= MA_PERIOD_LONG:
        ma_val            = _simple_ma(cumulative, MA_PERIOD_LONG)
        current_val       = cumulative[-1]
        h.curve_vs_ma20   = current_val - ma_val
    else:
        h.curve_vs_ma20 = 0.0  # not enough data yet

    # ── Status logic ──────────────────────────────────────────────
    total_abs = max(1e-9, abs(h.total_pnl)) if h.total_pnl != 0 else 1.0

    # Normalise rolling PnL as fraction of total absolute PnL
    rolling_30d_norm = h.rolling_30d_pnl / total_abs
    rolling_60d_norm = h.rolling_60d_pnl / total_abs

    status = "OK"
    reasons = []

    if h.curve_vs_ma20 < WATCH_THRESHOLD_MA and len(cumulative) >= MA_PERIOD_LONG:
        status = "WATCH"
        reasons.append(f"curve below MA{MA_PERIOD_LONG}")

    if h.trades_30d >= MIN_TRADES_FOR_EVAL and rolling_30d_norm < PAUSE_30D_LOSS:
        status = "PAUSE"
        reasons.append(f"30d P&L negative ({h.rolling_30d_pnl:.3f})")

    if h.trades_30d >= MIN_TRADES_FOR_EVAL and rolling_60d_norm < KILL_60D_LOSS:
        status = "KILL"
        reasons.append(f"60d P&L strongly negative ({h.rolling_60d_pnl:.3f})")

    h.status = status
    if reasons:
        h.notes += " | ".join(reasons)

    return h

# ── Overall health ────────────────────────────────────────────────────────────────
def _overall_status(healths: List[StrategyHealth]) -> str:
    statuses = [h.status for h in healths]
    if "KILL" in statuses:
        return "KILL"
    if "PAUSE" in statuses:
        return "PAUSE"
    if "WATCH" in statuses:
        return "WATCH"
    return "OK"

# ── Report formatting ────────────────────────────────────────────────────────────
STATUS_EMOJI = {"OK": "✅", "WATCH": "⚠️", "PAUSE": "🟠", "KILL": "🔴"}

def _format_tg(healths: List[StrategyHealth], run_dir: Path,
               overall: str, now_str: str) -> str:
    lines = [
        f"<b>🤖 Equity Curve Autopilot — {now_str}</b>",
        f"Run: <code>{run_dir.name}</code>",
        f"Overall: {STATUS_EMOJI.get(overall, '?')} <b>{overall}</b>",
        "",
    ]
    for h in sorted(healths, key=lambda x: x.status):
        emoji = STATUS_EMOJI.get(h.status, "?")
        lines.append(
            f"{emoji} <b>{h.name}</b>  [{h.status}]\n"
            f"   PnL total={h.total_pnl:.3f} | 30d={h.rolling_30d_pnl:+.3f} | "
            f"60d={h.rolling_60d_pnl:+.3f}\n"
            f"   Trades: {h.trades_total} (30d={h.trades_30d}, WR={h.winrate_30d:.0%})\n"
            f"   Curve vs MA20: {h.curve_vs_ma20:+.3f}"
            + (f"\n   ⚡ {h.notes}" if h.notes else "")
        )

    paused = [h.name for h in healths if h.status in ("PAUSE", "KILL")]
    if paused:
        lines += ["", f"⛔ <b>Action required</b>: Review {', '.join(paused)}"]
        lines.append("Run autoresearch or adjust parameters before next live session.")
    return "\n".join(lines)

def _format_report(healths: List[StrategyHealth], run_dir: Path,
                   overall: str, now_str: str) -> str:
    lines = [
        f"# Equity Curve Autopilot Report",
        f"**Date:** {now_str}",
        f"**Run:** `{run_dir.name}`",
        f"**Overall Health:** {overall}",
        "",
        "## Per-Strategy Health",
        "",
        "| Strategy | Status | Total PnL | 30d PnL | 60d PnL | Trades | WR 30d | PF 30d | Curve vs MA |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for h in healths:
        lines.append(
            f"| {h.name} | {h.status} | {h.total_pnl:.3f} | "
            f"{h.rolling_30d_pnl:+.3f} | {h.rolling_60d_pnl:+.3f} | "
            f"{h.trades_total} ({h.trades_30d}/30d) | "
            f"{h.winrate_30d:.0%} | {h.pf_30d:.2f} | {h.curve_vs_ma20:+.3f} |"
        )

    lines += [
        "",
        "## Status Legend",
        "- **OK** — Equity curve above MA, recent P&L positive. Normal operation.",
        "- **WATCH** — Curve below MA20. Monitor closely, no action yet.",
        "- **PAUSE** — 30d rolling P&L negative. Stop new entries, run autoresearch.",
        "- **KILL** — 60d rolling P&L strongly negative. Disable strategy, investigate.",
        "",
        "## Paused/Kill Strategies",
    ]
    paused = [h.name for h in healths if h.status in ("PAUSE", "KILL")]
    if paused:
        for name in paused:
            h = next(x for x in healths if x.name == name)
            lines.append(f"- **{name}** [{h.status}]: {h.notes}")
        lines += [
            "",
            "**Recommended action:** Run autoresearch spec for flagged strategies",
            "and check parameter drift vs current market regime.",
        ]
    else:
        lines.append("None — all strategies within acceptable ranges.")
    return "\n".join(lines)

# ── Public API for main bot integration ──────────────────────────────────────────
def strategy_is_healthy(strategy_name: str) -> bool:
    """
    Call this from the main bot before entering a new position.
    Returns False if strategy is in PAUSE or KILL state.
    Reads from configs/strategy_health.json (updated by this script).
    """
    if not HEALTH_FILE.exists():
        return True  # no health file = assume OK
    try:
        data = json.loads(HEALTH_FILE.read_text())
        st = data.get("strategies", {}).get(strategy_name, {})
        status = st.get("status", "OK")
        return status not in ("PAUSE", "KILL")
    except Exception:
        return True  # on error, allow trading

# ── Main ─────────────────────────────────────────────────────────────────────────
def main() -> None:
    _load_env_file(ENV_FILE)
    _load_env_file(ROOT / "configs" / "alpaca_paper_local.env")

    ap = argparse.ArgumentParser(description="Equity Curve Autopilot")
    ap.add_argument("--run-dir", default="", help="Specific backtest run dir to analyse")
    ap.add_argument("--allow-exploratory", action="store_true",
                    help="Allow exploratory/probe/sweep runs. Default is to reject them.")
    ap.add_argument("--no-tg",   action="store_true", help="Skip Telegram")
    ap.add_argument("--quiet",   action="store_true", help="Minimal output (just write files)")
    ap.add_argument("--days",    type=int, default=0,
                    help="Only use trades from last N days (0=all)")
    args = ap.parse_args()

    tg_token = _env("TG_TOKEN")
    tg_chat  = _env("TG_CHAT_ID")

    now_utc  = datetime.now(timezone.utc)
    now_ts   = int(now_utc.timestamp())
    now_str  = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    # Find run directory
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
        if run_dir.exists() and (not args.allow_exploratory) and _is_exploratory_run(run_dir):
            print(f"ERROR: Refusing exploratory run by default: {run_dir.name}")
            print("       Pass --allow-exploratory only for explicit research use.")
            sys.exit(1)
    else:
        run_dir = _find_latest_run(allow_exploratory=args.allow_exploratory)

    if not run_dir or not run_dir.exists():
        print("ERROR: No backtest run found. Run a portfolio backtest first.")
        sys.exit(1)

    if not args.quiet:
        print(f"Equity Curve Autopilot — {now_str}")
        print(f"Run dir: {run_dir.name}")

    # Load trades
    all_trades = _load_trades(run_dir)
    if not all_trades:
        print("ERROR: No trades found in trades.csv")
        sys.exit(1)

    # Optional: restrict to last N days
    if args.days > 0:
        cutoff = now_ts - args.days * 86400
        all_trades = [t for t in all_trades if t.exit_ts >= cutoff]

    if not args.quiet:
        print(f"Loaded {len(all_trades)} trades | "
              f"date range: "
              f"{datetime.fromtimestamp(all_trades[0].exit_ts, tz=timezone.utc).date()} → "
              f"{datetime.fromtimestamp(all_trades[-1].exit_ts, tz=timezone.utc).date()}")

    # Group by strategy
    by_strategy: Dict[str, List[Trade]] = {}
    for t in all_trades:
        by_strategy.setdefault(t.strategy, []).append(t)

    # Analyse each strategy
    healths: List[StrategyHealth] = []
    for name, trades in sorted(by_strategy.items()):
        h = _analyze_strategy(name, trades, now_ts)
        healths.append(h)
        if not args.quiet:
            emoji = STATUS_EMOJI.get(h.status, "?")
            print(f"  {emoji} {name:40s} [{h.status:5s}] "
                  f"PnL={h.total_pnl:+.3f} 30d={h.rolling_30d_pnl:+.3f} "
                  f"trades={h.trades_total}({h.trades_30d}/30d) "
                  f"curveΔ={h.curve_vs_ma20:+.3f}")

    overall = _overall_status(healths)
    if not args.quiet:
        print(f"\nOverall: {STATUS_EMOJI.get(overall, '?')} {overall}")

    # Write health JSON
    health_data = {
        "timestamp": now_utc.isoformat(),
        "run_dir": run_dir.name,
        "strategies": {
            h.name: {
                "status": h.status,
                "total_pnl": round(h.total_pnl, 4),
                "rolling_30d_pnl": round(h.rolling_30d_pnl, 4),
                "rolling_60d_pnl": round(h.rolling_60d_pnl, 4),
                "curve_vs_ma20": round(h.curve_vs_ma20, 4),
                "trades_total": h.trades_total,
                "trades_30d": h.trades_30d,
                "winrate_total": round(h.winrate_total, 3),
                "winrate_30d": round(h.winrate_30d, 3),
                "pf_30d": round(h.pf_30d, 3),
                "notes": h.notes,
            }
            for h in healths
        },
        "paused_strategies": [h.name for h in healths if h.status in ("PAUSE", "KILL")],
        "overall_health": overall,
    }
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(health_data, indent=2))
    if not args.quiet:
        print(f"Health file written: {HEALTH_FILE}")

    # Write markdown report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"equity_autopilot_{now_utc.strftime('%Y%m%d')}.md"
    report_path.write_text(_format_report(healths, run_dir, overall, now_str))
    if not args.quiet:
        print(f"Report written: {report_path}")

    # Send Telegram
    if not args.no_tg and tg_token and tg_chat:
        msg = _format_tg(healths, run_dir, overall, now_str)
        _tg(tg_token, tg_chat, msg)
        if not args.quiet:
            print("Telegram sent.")

    # Final warning output
    paused = [h.name for h in healths if h.status in ("PAUSE", "KILL")]
    if paused:
        print(f"\n⚠️  ACTION REQUIRED: {', '.join(paused)}")
        print("   Run autoresearch for flagged strategies or disable them.")
        sys.exit(2)   # non-zero exit for cron alerting


if __name__ == "__main__":
    main()
