#!/usr/bin/env python3
"""Weekly live-vs-backtest comparison report.

This is intentionally read-only for live trading. It compares closed live trade
events from the last N days with a fresh portfolio backtest over the same
calendar window, then writes a small Markdown/CSV report and optionally sends it
to Telegram.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from run_live_effective_parity import build_live_effective_inputs


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGIES = "alt_trendline_touch_v1,alt_resistance_fade_v1,btc_eth_midterm_pullback"
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_ts(row: dict[str, Any]) -> float:
    raw = row.get("ts") or row.get("timestamp") or row.get("time")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return float(raw)
        except ValueError:
            pass
    ts_utc = str(row.get("ts_utc") or row.get("time_utc") or "").strip()
    if ts_utc:
        for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(ts_utc, fmt).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                pass
    return 0.0


@dataclass
class Stats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net: float = 0.0
    gross_win: float = 0.0
    gross_loss: float = 0.0

    @property
    def pf(self) -> float | None:
        if self.gross_loss <= 0:
            return None if self.gross_win <= 0 else float("inf")
        return self.gross_win / self.gross_loss

    @property
    def wr(self) -> float:
        return self.wins / self.trades if self.trades else 0.0


def _add_pnl(stats: Stats, pnl: float) -> None:
    stats.trades += 1
    stats.net += pnl
    if pnl > 0:
        stats.wins += 1
        stats.gross_win += pnl
    elif pnl < 0:
        stats.losses += 1
        stats.gross_loss += abs(pnl)


def _read_live(days: int) -> tuple[Stats, dict[str, Stats]]:
    events = ROOT / "runtime" / "live_trade_events.jsonl"
    cutoff = time.time() - days * 86400
    total = Stats()
    by_strategy: dict[str, Stats] = defaultdict(Stats)
    if not events.exists():
        return total, by_strategy
    for line in events.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("event") or "").lower() not in {"close", "closed", "exit"}:
            continue
        if _parse_ts(row) < cutoff:
            continue
        try:
            pnl = float(row.get("pnl") or row.get("realized_pnl") or 0.0)
        except (TypeError, ValueError):
            pnl = 0.0
        strategy = str(row.get("strategy") or "unknown")
        _add_pnl(total, pnl)
        _add_pnl(by_strategy[strategy], pnl)
    return total, by_strategy


def _symbols_from_allocator() -> str:
    state_path = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    if not state_path.exists():
        return DEFAULT_SYMBOLS
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SYMBOLS
    symbols: list[str] = []
    for sleeve in (state.get("sleeves") or {}).values():
        if not isinstance(sleeve, dict) or not sleeve.get("enabled"):
            continue
        for sym in sleeve.get("symbols") or []:
            if sym not in symbols:
                symbols.append(str(sym))
    if _env("WEEKLY_COMPARE_CACHE_ONLY", "1") not in {"0", "false", "False"}:
        symbols = [sym for sym in symbols if _has_kline_cache(sym)]
    return ",".join(symbols[:16]) if symbols else DEFAULT_SYMBOLS


def _has_kline_cache(symbol: str) -> bool:
    cache_dir = ROOT / ".cache" / "klines"
    if not cache_dir.exists():
        return True
    return any(cache_dir.glob(f"{symbol}_5_*.json")) or any(cache_dir.glob(f"{symbol}_1_*.json"))


def _latest_summary_for_tag(tag: str) -> Path | None:
    candidates = sorted(
        ROOT.glob(f"backtest_runs/portfolio_*_{tag}/summary.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _run_backtest(days: int, end_date: str, strategies: str, symbols: str) -> tuple[dict[str, str], str]:
    tag = f"weekly_live_vs_backtest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    cmd = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols", symbols,
        "--strategies", strategies,
        "--days", str(days),
        "--end", end_date,
        "--starting_equity", "100",
        "--risk_pct", _env("WEEKLY_COMPARE_RISK_PCT", "0.01"),
        "--leverage", _env("WEEKLY_COMPARE_LEVERAGE", "1"),
        "--max_positions", _env("WEEKLY_COMPARE_MAX_POSITIONS", "3"),
        "--fee_bps", _env("WEEKLY_COMPARE_FEE_BPS", "6"),
        "--slippage_bps", _env("WEEKLY_COMPARE_SLIPPAGE_BPS", "2"),
        "--tag", tag,
    ]
    env = os.environ.copy()
    env.setdefault("BACKTEST_CACHE_ONLY", _env("WEEKLY_COMPARE_CACHE_ONLY", "1"))
    try:
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    except subprocess.CalledProcessError:
        if env.get("BACKTEST_CACHE_ONLY") in {"0", "false", "False"}:
            raise
        # Weekly reporting is diagnostic, not a deterministic research gate. If
        # the latest live allocator symbols are missing from cache, retry with
        # the normal fetch path so the Friday report still arrives.
        env["BACKTEST_CACHE_ONLY"] = "0"
        env.setdefault("BACKTEST_CACHE_FALLBACK_ENABLE", "1")
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    summary_path = _latest_summary_for_tag(tag)
    if not summary_path:
        raise RuntimeError(f"summary.csv not found for tag {tag}")
    with summary_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return (rows[0] if rows else {}), str(summary_path.parent.relative_to(ROOT))


def _parse_backtest_ts(raw: Any) -> float:
    if raw in (None, ""):
        return 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    # Portfolio backtests store millisecond timestamps.
    if value > 10_000_000_000:
        return value / 1000.0
    return value


def _read_backtest_window(run_dir: str, cutoff_ts: float) -> tuple[Stats, dict[str, Stats], int]:
    trades_path = ROOT / run_dir / "trades.csv"
    total = Stats()
    by_strategy: dict[str, Stats] = defaultdict(Stats)
    entries = 0
    if not trades_path.exists():
        raise RuntimeError(f"Backtest trades.csv not found: {trades_path}")
    with trades_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entry_ts = _parse_backtest_ts(row.get("entry_ts"))
            exit_ts = _parse_backtest_ts(row.get("exit_ts"))
            if entry_ts >= cutoff_ts:
                entries += 1
            if exit_ts < cutoff_ts:
                continue
            try:
                pnl = float(row.get("pnl") or 0.0)
            except (TypeError, ValueError):
                pnl = 0.0
            strategy = str(row.get("strategy") or "unknown")
            _add_pnl(total, pnl)
            _add_pnl(by_strategy[strategy], pnl)
    return total, by_strategy, entries


def _run_live_effective_backtest(report_days: int, warmup_days: int, end_date: str, health_filter: str) -> tuple[
    dict[str, str],
    str,
    str,
    str,
    Stats,
    dict[str, Stats],
    int,
]:
    symbols_list, strategies_list, loaded_env, rows = build_live_effective_inputs(
        ROOT,
        health_filter=health_filter,
    )
    if not symbols_list or not strategies_list:
        raise RuntimeError("No active live-effective strategies/symbols found")
    symbols = ",".join(symbols_list)
    strategies = ",".join(strategies_list)
    tag = f"weekly_live_effective_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    cmd = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols",
        symbols,
        "--strategies",
        strategies,
        "--days",
        str(max(report_days, warmup_days)),
        "--end",
        end_date,
        "--starting_equity",
        "100",
        "--risk_pct",
        _env("WEEKLY_COMPARE_RISK_PCT", "0.01"),
        "--leverage",
        _env("WEEKLY_COMPARE_LEVERAGE", "3"),
        "--max_positions",
        _env("WEEKLY_COMPARE_MAX_POSITIONS", "3"),
        "--fee_bps",
        _env("WEEKLY_COMPARE_FEE_BPS", "6"),
        "--slippage_bps",
        _env("WEEKLY_COMPARE_SLIPPAGE_BPS", "2"),
        "--tag",
        tag,
    ]
    env = os.environ.copy()
    env.update(loaded_env)
    env["BACKTEST_CACHE_ONLY"] = _env("WEEKLY_COMPARE_CACHE_ONLY", "0")
    env.setdefault("BACKTEST_CACHE_FALLBACK_ENABLE", "1")
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    summary_path = _latest_summary_for_tag(tag)
    if not summary_path:
        raise RuntimeError(f"summary.csv not found for tag {tag}")
    with summary_path.open(newline="", encoding="utf-8") as f:
        rows_summary = list(csv.DictReader(f))
    run_dir = str(summary_path.parent.relative_to(ROOT))
    cutoff_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(days=report_days)
    window_total, window_by_strategy, window_entries = _read_backtest_window(run_dir, cutoff_dt.timestamp())
    return (
        rows_summary[0] if rows_summary else {},
        run_dir,
        strategies,
        symbols,
        window_total,
        window_by_strategy,
        window_entries,
    )


def _fmt_pf(value: float | None) -> str:
    if value is None:
        return "-"
    if value == float("inf"):
        return "inf"
    return f"{value:.3f}"


def _send_tg(text: str) -> None:
    token = _env("TG_TOKEN")
    chat = _env("TG_CHAT_ID") or _env("TG_CHAT")
    if not token or not chat:
        return
    payload = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
    with urllib.request.urlopen(req, timeout=15):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=int(_env("WEEKLY_COMPARE_DAYS", "7")))
    ap.add_argument("--warmup-days", type=int, default=int(_env("WEEKLY_COMPARE_WARMUP_DAYS", "60")))
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--strategies", default=_env("WEEKLY_COMPARE_STRATEGIES", DEFAULT_STRATEGIES))
    ap.add_argument("--symbols", default=_env("WEEKLY_COMPARE_SYMBOLS", "") or _symbols_from_allocator())
    ap.add_argument("--fixed-legacy", action="store_true", help="Use explicit --strategies/--symbols instead of live-effective allocator state")
    ap.add_argument(
        "--health-filter",
        choices=["all", "ok", "ok-watch"],
        default=_env("WEEKLY_COMPARE_HEALTH_FILTER", "ok"),
        help="For live-effective mode, include all active sleeves, only OK sleeves, or OK+WATCH sleeves.",
    )
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")
    _load_env_file(ROOT / "configs" / "server.env")

    live_total, live_by_strategy = _read_live(args.days)
    if args.fixed_legacy:
        bt_summary, bt_run = _run_backtest(args.days, args.end, args.strategies, args.symbols)
        bt_window_total = Stats(
            trades=int(float(bt_summary.get("trades") or 0)),
            net=float(bt_summary.get("net_pnl") or 0.0),
        )
        bt_window_by_strategy: dict[str, Stats] = {}
        bt_window_entries = bt_window_total.trades
        strategies = args.strategies
        symbols = args.symbols
    else:
        (
            bt_summary,
            bt_run,
            strategies,
            symbols,
            bt_window_total,
            bt_window_by_strategy,
            bt_window_entries,
        ) = _run_live_effective_backtest(args.days, args.warmup_days, args.end, args.health_filter)

    out_dir = ROOT / "reports" / "weekly_live_vs_backtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"weekly_live_vs_backtest_{stamp}.md"
    csv_path = out_dir / f"weekly_live_vs_backtest_{stamp}.csv"

    bt_net = bt_window_total.net
    bt_trades = bt_window_total.trades
    bt_pf = _fmt_pf(bt_window_total.pf)
    bt_wr = bt_window_total.wr
    bt_dd = float(bt_summary.get("max_drawdown") or 0.0)

    md = [
        f"# Weekly Live vs Backtest — {stamp}",
        "",
        f"Window: last {args.days}d ending {args.end}",
        f"Mode: `{'fixed legacy' if args.fixed_legacy else 'live-effective allocator'}`",
        f"Health filter: `{'fixed legacy n/a' if args.fixed_legacy else args.health_filter}`",
        f"Warmup: `{args.warmup_days}d`; reported window: `{args.days}d`",
        f"Strategies: `{strategies}`",
        f"Symbols: `{symbols}`",
        "",
        "| Source | Exits | Entries | Net PnL | PF | Winrate | Max DD |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Live closed events | {live_total.trades} | - | {live_total.net:.4f} | {_fmt_pf(live_total.pf)} | {live_total.wr:.1%} | - |",
        f"| Backtest replay | {bt_trades} | {bt_window_entries} | {bt_net:.4f} | {bt_pf} | {bt_wr:.1%} | {bt_dd:.2f}% |",
        "",
        f"Backtest run: `{bt_run}`",
        "",
        "## Drift Read",
        "",
        "- If live has `0` closes while backtest has recent entries, check auth/order placement/log skips immediately.",
        "- If both live and backtest have `0` recent entries, the silence is probably strategy/opportunity scarcity for that window.",
        "",
        "## Live Strategy Breakdown",
        "| Strategy | Trades | Net PnL | PF | Winrate |",
        "|---|---:|---:|---:|---:|",
    ]
    if live_by_strategy:
        for strategy, stats in sorted(live_by_strategy.items(), key=lambda kv: kv[1].net, reverse=True):
            md.append(f"| {strategy} | {stats.trades} | {stats.net:.4f} | {_fmt_pf(stats.pf)} | {stats.wr:.1%} |")
    else:
        md.append("| no live closes | 0 | 0.0000 | - | 0.0% |")
    md.extend(["", "## Backtest Strategy Breakdown", "| Strategy | Exits | Net PnL | PF | Winrate |", "|---|---:|---:|---:|---:|"])
    if bt_window_by_strategy:
        for strategy, stats in sorted(bt_window_by_strategy.items(), key=lambda kv: kv[1].net, reverse=True):
            md.append(f"| {strategy} | {stats.trades} | {stats.net:.4f} | {_fmt_pf(stats.pf)} | {stats.wr:.1%} |")
    else:
        md.append("| no backtest exits | 0 | 0.0000 | - | 0.0% |")
    md.append("")
    md_path.write_text("\n".join(md), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "exits", "entries", "net_pnl", "profit_factor", "winrate", "max_drawdown"])
        writer.writerow(["live", live_total.trades, "", f"{live_total.net:.4f}", _fmt_pf(live_total.pf), f"{live_total.wr:.6f}", ""])
        writer.writerow(["backtest", bt_trades, bt_window_entries, f"{bt_net:.4f}", bt_pf, f"{bt_wr:.6f}", f"{bt_dd:.4f}"])

    message = (
        f"Weekly live vs backtest ({args.days}d)\n"
        f"Mode: {'fixed legacy' if args.fixed_legacy else 'live-effective'}; health={args.health_filter if not args.fixed_legacy else 'n/a'}\n"
        f"Live: trades={live_total.trades}, pnl={live_total.net:.4f}, PF={_fmt_pf(live_total.pf)}\n"
        f"Backtest: exits={bt_trades}, entries={bt_window_entries}, pnl={bt_net:.4f}, PF={bt_pf}, DD={bt_dd:.2f}%\n"
        f"Report: {md_path.relative_to(ROOT)}"
    )
    print(message)
    if args.telegram:
        _send_tg(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
