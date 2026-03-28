#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dynamic_allowlist.py — Generates per-strategy symbol allowlists from live market data.

Combines two signals:
  1. Live market scan (Bybit tickers + instruments-info + ATR% on 1h candles)
  2. Optional backtest performance gate (trades.csv from a recent run)

Each strategy family has its own filter profile — ATR range, min turnover, listing
age, top-N cap — tuned to the mechanics of that strategy:

  ASC1  (sloped channel longs):   trending mid-caps, moderate ATR
  ARF1  (flat resistance fade):   range-bound mid-caps, moderate ATR
  BREAKDOWN (breakdown shorts):   liquid, somewhat volatile

Outputs:
  configs/dynamic_allowlist_YYYYMMDD_HHMMSS.env  — drop-in env overlay
  (or --out-env <path> if specified)

Usage examples:
  # Live scan, no backtest gate, dry-run (prints but does not write):
  python3 scripts/dynamic_allowlist.py --dry-run

  # Live scan + backtest gate from a recent portfolio run:
  python3 scripts/dynamic_allowlist.py \\
      --trades-csv backtest_runs/portfolio_20260327_161054_full_stack_iteration_20260327_annual/trades.csv

  # Explicit output path:
  python3 scripts/dynamic_allowlist.py \\
      --out-env configs/dynamic_allowlist_latest.env

  # Weekly cron (silent except errors):
  python3 scripts/dynamic_allowlist.py --quiet \\
      --out-env configs/dynamic_allowlist_latest.env

Notes:
  - Requires live internet (Bybit public API, no auth needed).
  - ATR fetch politely rate-limits; with 200+ symbols expect ~3-5 minutes.
  - Use --max-scan-symbols to cap how many symbols get ATR-fetched (default 120).
  - The produced .env file can be applied with:
      python3 scripts/apply_env_overlay.py configs/dynamic_allowlist_YYYYMMDD.env
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

try:
    sys.path.insert(0, str(ROOT))
    from backtest.bybit_data import DEFAULT_BYBIT_BASE, fetch_klines_public
    from indicators import atr_pct_from_ohlc
    _HAS_BACKTEST_LIBS = True
except ImportError:
    _HAS_BACKTEST_LIBS = False
    DEFAULT_BYBIT_BASE = "https://api.bybit.com"


# ---------------------------------------------------------------------------
# Market data helpers (standalone — mirrors universe_scan.py)
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v or 0)
    except Exception:
        return default


def _get_tickers(base: str) -> List[dict]:
    url = f"{base.rstrip('/')}/v5/market/tickers"
    js = requests.get(url, params={"category": "linear"}, timeout=20).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    return (js.get("result") or {}).get("list") or []


def _get_instruments_info(base: str) -> Dict[str, dict]:
    url = f"{base.rstrip('/')}/v5/market/instruments-info"
    out: Dict[str, dict] = {}
    cursor = None
    while True:
        params: dict = {"category": "linear"}
        if cursor:
            params["cursor"] = cursor
        js = requests.get(url, params=params, timeout=20).json()
        if js.get("retCode") != 0:
            raise RuntimeError(f"Bybit instruments error {js.get('retCode')}: {js.get('retMsg')}")
        lst = (js.get("result") or {}).get("list") or []
        for it in lst:
            sym = str(it.get("symbol") or "").upper()
            if sym:
                out[sym] = it
        cursor = (js.get("result") or {}).get("nextPageCursor")
        if not cursor:
            break
    return out


def _atr_pct_1h(symbol: str, *, base: str, lookback_days: int, sleep_sec: float) -> float:
    """Fetch 1h klines and return ATR% (requires backtest libs)."""
    if not _HAS_BACKTEST_LIBS:
        return 0.0
    end_ms = _now_ms()
    start_ms = end_ms - int(lookback_days) * 86_400_000
    try:
        kl = fetch_klines_public(
            symbol,
            interval="60",
            start_ms=start_ms,
            end_ms=end_ms,
            base=base,
            cache=True,
            polite_sleep_sec=sleep_sec,
        )
    except Exception:
        return 0.0
    if len(kl) < 20:
        return 0.0
    h = [float(k.h) for k in kl]
    l = [float(k.l) for k in kl]
    c = [float(k.c) for k in kl]
    return float(atr_pct_from_ohlc(h, l, c, period=14, fallback=0.0))


# ---------------------------------------------------------------------------
# Backtest performance gate
# ---------------------------------------------------------------------------

@dataclass
class SymPerf:
    symbol: str
    strategy: str
    trades: int = 0
    net: float = 0.0
    wins: int = 0
    gross_profit: float = 0.0
    gross_loss_abs: float = 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss_abs > 0:
            return self.gross_profit / self.gross_loss_abs
        return 9999.0 if self.gross_profit > 0 else 0.0

    @property
    def winrate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0


def _load_backtest_perf(trades_csv: Path) -> Dict[Tuple[str, str], SymPerf]:
    """Load symbol+strategy performance from a trades.csv."""
    out: Dict[Tuple[str, str], SymPerf] = {}
    if not trades_csv.exists():
        return out
    with trades_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = str(row.get("symbol") or "").strip().upper()
            strat = str(row.get("strategy") or "").strip()
            if not sym or not strat:
                continue
            key = (sym, strat)
            if key not in out:
                out[key] = SymPerf(symbol=sym, strategy=strat)
            pnl = _safe_float(row.get("pnl"), 0.0)
            sp = out[key]
            sp.trades += 1
            sp.net += pnl
            if pnl > 0:
                sp.wins += 1
                sp.gross_profit += pnl
            elif pnl < 0:
                sp.gross_loss_abs += abs(pnl)
    # round floats
    for sp in out.values():
        sp.net = round(sp.net, 6)
        sp.gross_profit = round(sp.gross_profit, 6)
        sp.gross_loss_abs = round(sp.gross_loss_abs, 6)
    return out


# ---------------------------------------------------------------------------
# Strategy profiles
# ---------------------------------------------------------------------------

@dataclass
class StrategyProfile:
    """Per-strategy-family filter configuration."""
    name: str
    env_key: str                        # e.g. ASC1_SYMBOL_ALLOWLIST
    strategy_tags: List[str]            # strategy names in trades.csv
    min_turnover: float = 20_000_000.0  # 24h turnover USD
    min_atr_pct: float = 0.30
    max_atr_pct: float = 2.00
    min_listing_days: int = 60
    top_n: int = 8
    # Backtest gate (only applied if trades_csv provided)
    bt_min_trades: int = 5
    bt_min_net: float = 0.0
    bt_min_pf: float = 1.0
    # Fixed always-include symbols (never removed by market filter)
    anchor_symbols: List[str] = field(default_factory=list)


# Default profiles — tuned to each strategy's mechanics
_DEFAULT_PROFILES: List[StrategyProfile] = [
    StrategyProfile(
        name="ASC1 (sloped channel)",
        env_key="ASC1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_sloped_channel_v1", "sloped_channel", "asc1", "flat_slope_asc1"],
        min_turnover=30_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=0.90,   # avoid highly volatile coins — strategy needs structure
        min_listing_days=120,
        top_n=8,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["LINKUSDT", "ATOMUSDT"],  # historical core
    ),
    StrategyProfile(
        name="ARF1 (flat resistance fade)",
        env_key="ARF1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_resistance_fade_v1", "flat_resistance_fade", "arf1", "flat_arf1"],
        min_turnover=20_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=1.10,
        min_listing_days=90,
        top_n=10,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["LINKUSDT", "LTCUSDT"],
    ),
    StrategyProfile(
        name="BREAKDOWN (breakdown shorts)",
        env_key="BREAKDOWN_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_inplay_breakdown_v1", "inplay_breakdown", "breakdown", "breakdown_short"],
        min_turnover=50_000_000.0,
        min_atr_pct=0.30,
        max_atr_pct=3.00,   # breakdown tolerates volatility
        min_listing_days=90,
        top_n=12,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    ),
]


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

@dataclass
class CandidateRow:
    symbol: str
    turnover24h: float
    atr_pct: float
    listing_age_days: float
    passes_market: bool = False
    bt_perf: Optional[SymPerf] = None

    def market_summary(self) -> str:
        return (
            f"turn={self.turnover24h/1e6:.1f}M "
            f"ATR%={self.atr_pct:.3f} "
            f"age={self.listing_age_days:.0f}d"
        )

    def bt_summary(self) -> str:
        if self.bt_perf is None:
            return "no-bt-data"
        p = self.bt_perf
        return f"bt_trades={p.trades} bt_net={p.net:+.4f} bt_pf={p.profit_factor:.2f}"


def run_scan(
    *,
    bybit_base: str,
    max_scan_symbols: int,
    atr_lookback_days: int,
    polite_sleep_sec: float,
    quiet: bool,
) -> Dict[str, CandidateRow]:
    """Fetch tickers, instruments, and ATR% for every USDT perp candidate."""
    if not quiet:
        print("[scan] Fetching Bybit tickers...")
    tickers = _get_tickers(bybit_base)

    if not quiet:
        print("[scan] Fetching instruments info...")
    instruments = _get_instruments_info(bybit_base)

    now_ms = _now_ms()
    pre_rows: List[Tuple[float, str, dict]] = []  # (turnover, symbol, ticker)
    for it in tickers:
        sym = str(it.get("symbol") or "").upper()
        if not sym.endswith("USDT"):
            continue
        turn = _safe_float(it.get("turnover24h"), 0.0)
        if turn < 1_000_000.0:
            continue  # below floor — skip entirely
        pre_rows.append((turn, sym, it))

    # Sort by turnover desc and cap to max_scan_symbols
    pre_rows.sort(reverse=True)
    pre_rows = pre_rows[:max_scan_symbols]

    if not quiet:
        print(f"[scan] Fetching ATR% for {len(pre_rows)} symbols (may take several minutes)...")

    out: Dict[str, CandidateRow] = {}
    for idx, (turn, sym, it) in enumerate(pre_rows, 1):
        info = instruments.get(sym, {})
        try:
            launch_ms = int(info.get("launchTime") or 0)
        except Exception:
            launch_ms = 0
        age_days = (now_ms - launch_ms) / 86_400_000.0 if launch_ms else -1.0

        atr_pct = _atr_pct_1h(sym, base=bybit_base, lookback_days=atr_lookback_days, sleep_sec=polite_sleep_sec)

        out[sym] = CandidateRow(
            symbol=sym,
            turnover24h=turn,
            atr_pct=atr_pct,
            listing_age_days=age_days,
        )
        if not quiet and idx % 20 == 0:
            print(f"[scan]   {idx}/{len(pre_rows)} done ({sym} ATR%={atr_pct:.3f})")

    if not quiet:
        print(f"[scan] Scan complete. {len(out)} symbols profiled.")
    return out


# ---------------------------------------------------------------------------
# Per-profile selection
# ---------------------------------------------------------------------------

def select_for_profile(
    profile: StrategyProfile,
    scan: Dict[str, CandidateRow],
    backtest: Dict[Tuple[str, str], SymPerf],
    *,
    quiet: bool,
) -> List[str]:
    """Return ordered list of symbols for this strategy family."""

    selected: List[str] = []
    rejected_market: List[str] = []
    rejected_bt: List[str] = []

    # Build per-symbol aggregated backtest perf across all matching strategy tags
    bt_by_sym: Dict[str, SymPerf] = {}
    for (sym, strat), perf in backtest.items():
        if any(tag in strat for tag in profile.strategy_tags):
            if sym not in bt_by_sym:
                bt_by_sym[sym] = SymPerf(symbol=sym, strategy=strat)
            agg = bt_by_sym[sym]
            agg.trades += perf.trades
            agg.net += perf.net
            agg.wins += perf.wins
            agg.gross_profit += perf.gross_profit
            agg.gross_loss_abs += perf.gross_loss_abs

    # Score candidates
    candidates: List[Tuple[float, str]] = []  # (score, symbol)

    # All known symbols = scan union anchor_symbols union bt symbols
    all_symbols = set(scan.keys()) | set(profile.anchor_symbols) | set(bt_by_sym.keys())

    for sym in sorted(all_symbols):
        row = scan.get(sym)
        bt_perf = bt_by_sym.get(sym)

        # ---- Market filter ----
        if row is None:
            # Not in scan pool (below turnover floor or not USDT perp)
            if sym in profile.anchor_symbols:
                # Always keep anchors even if market data is missing
                score = -999.0
                candidates.append((score, sym))
            continue

        market_ok = True
        if row.turnover24h < profile.min_turnover:
            market_ok = False
        if row.atr_pct < profile.min_atr_pct or row.atr_pct > profile.max_atr_pct:
            market_ok = False
        if row.listing_age_days >= 0 and row.listing_age_days < profile.min_listing_days:
            market_ok = False

        if not market_ok and sym not in profile.anchor_symbols:
            rejected_market.append(sym)
            continue

        # ---- Backtest gate (optional) ----
        if backtest and sym not in profile.anchor_symbols:
            if bt_perf is None:
                # No backtest data for this symbol+strategy — skip only if we
                # have backtest data for at least some symbols (meaning the file
                # had relevant strategy trades). If file is empty/unrelated, skip gate.
                if bt_by_sym:
                    rejected_bt.append(sym)
                    continue
            else:
                bt_ok = (
                    bt_perf.trades >= profile.bt_min_trades
                    and bt_perf.net >= profile.bt_min_net
                    and bt_perf.profit_factor >= profile.bt_min_pf
                )
                if not bt_ok:
                    rejected_bt.append(sym)
                    continue

        # Score = turnover (primary) + ATR% bonus for mid-range
        atr_mid = (profile.min_atr_pct + profile.max_atr_pct) / 2.0
        atr_score = 1.0 - abs(row.atr_pct - atr_mid) / max(atr_mid, 0.01)
        score = row.turnover24h / 1e9 + atr_score * 0.1
        candidates.append((score, sym))

    # Sort by score desc, take top_n
    candidates.sort(reverse=True)
    selected = [sym for _, sym in candidates[: profile.top_n]]

    if not quiet:
        print(f"\n[{profile.name}]")
        print(f"  Selected ({len(selected)}): {','.join(selected)}")
        if rejected_market:
            print(f"  Rejected by market filter: {len(rejected_market)} symbols")
        if rejected_bt:
            print(f"  Rejected by backtest gate: {len(rejected_bt)} symbols")

    return selected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate per-strategy symbol allowlists from live market data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--bybit-base", default=os.getenv("BYBIT_BASE_URL", DEFAULT_BYBIT_BASE),
        help="Bybit API base URL.",
    )
    ap.add_argument(
        "--trades-csv", default="",
        help="Optional path to trades.csv from a recent backtest run. "
             "Enables per-symbol backtest performance gate.",
    )
    ap.add_argument(
        "--atr-lookback-days", type=int, default=14,
        help="ATR lookback on 1h candles (default 14).",
    )
    ap.add_argument(
        "--max-scan-symbols", type=int, default=120,
        help="Cap ATR scan to top-N symbols by turnover (default 120). "
             "Higher = more candidates but slower.",
    )
    ap.add_argument(
        "--polite-sleep-sec", type=float,
        default=float(os.getenv("BYBIT_DATA_POLITE_SLEEP_SEC", "0.6")),
        help="Delay between ATR kline fetches to avoid rate-limits.",
    )
    ap.add_argument(
        "--out-env", default="",
        help="Output .env file path. Default: configs/dynamic_allowlist_YYYYMMDD_HHMMSS.env",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print allowlists but do not write any files.",
    )
    ap.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output (errors still print).",
    )
    # Per-profile overrides
    ap.add_argument("--asc1-top-n", type=int, default=0, help="Override ASC1 top-N.")
    ap.add_argument("--arf1-top-n", type=int, default=0, help="Override ARF1 top-N.")
    ap.add_argument("--breakdown-top-n", type=int, default=0, help="Override BREAKDOWN top-N.")
    ap.add_argument(
        "--bt-min-trades", type=int, default=0,
        help="Override min backtest trades gate for all profiles.",
    )
    ap.add_argument(
        "--bt-min-pf", type=float, default=0.0,
        help="Override min backtest profit-factor gate for all profiles.",
    )
    args = ap.parse_args()

    if not _HAS_BACKTEST_LIBS:
        print(
            "ERROR: backtest libs not importable. "
            "Run from the bot root directory: python3 scripts/dynamic_allowlist.py",
            file=sys.stderr,
        )
        return 1

    # Apply overrides to profiles
    profiles = _DEFAULT_PROFILES[:]
    overrides = {
        "ASC1_SYMBOL_ALLOWLIST": args.asc1_top_n,
        "ARF1_SYMBOL_ALLOWLIST": args.arf1_top_n,
        "BREAKDOWN_SYMBOL_ALLOWLIST": args.breakdown_top_n,
    }
    for p in profiles:
        n = overrides.get(p.env_key, 0)
        if n > 0:
            p.top_n = n
        if args.bt_min_trades > 0:
            p.bt_min_trades = args.bt_min_trades
        if args.bt_min_pf > 0.0:
            p.bt_min_pf = args.bt_min_pf

    # Load backtest data (optional)
    backtest: Dict[Tuple[str, str], SymPerf] = {}
    if args.trades_csv:
        trades_path = Path(args.trades_csv)
        if not trades_path.is_absolute():
            trades_path = ROOT / trades_path
        if not trades_path.exists():
            print(f"ERROR: --trades-csv not found: {trades_path}", file=sys.stderr)
            return 1
        backtest = _load_backtest_perf(trades_path)
        if not args.quiet:
            strats_found = set(strat for _, strat in backtest.keys())
            print(f"[bt] Loaded {len(backtest)} symbol+strategy records from {trades_path.name}")
            print(f"[bt] Strategies present: {', '.join(sorted(strats_found))}")

    # Run market scan
    scan = run_scan(
        bybit_base=args.bybit_base,
        max_scan_symbols=args.max_scan_symbols,
        atr_lookback_days=args.atr_lookback_days,
        polite_sleep_sec=args.polite_sleep_sec,
        quiet=args.quiet,
    )

    # Select per profile
    results: Dict[str, List[str]] = {}
    for profile in profiles:
        results[profile.env_key] = select_for_profile(
            profile, scan, backtest, quiet=args.quiet
        )

    # Build .env content
    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S")
    generated_at = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    bt_note = f"  # backtest gate: {Path(args.trades_csv).name}" if args.trades_csv else ""
    lines = [
        f"## dynamic_allowlist — auto-generated {generated_at}",
        f"## scan: top {args.max_scan_symbols} symbols by turnover, ATR lookback {args.atr_lookback_days}d",
        f"## backtest gate: {Path(args.trades_csv).name if args.trades_csv else 'none'}",
        "##",
        "## Apply with: python3 scripts/apply_env_overlay.py <this-file>",
        "##",
        "",
    ]
    for env_key, syms in results.items():
        comment = f"## {len(syms)} symbols"
        lines.append(comment)
        lines.append(f"{env_key}={','.join(syms)}")
        lines.append("")

    env_text = "\n".join(lines)

    # Print summary
    print("\n" + "=" * 60)
    print("DYNAMIC ALLOWLIST SUMMARY")
    print("=" * 60)
    for env_key, syms in results.items():
        print(f"  {env_key} ({len(syms)}): {','.join(syms)}")
    print()

    if args.dry_run:
        print("[dry-run] Skipping file write.")
        print("\nProposed .env content:")
        print("-" * 40)
        print(env_text)
        return 0

    # Write file
    if args.out_env:
        out_path = Path(args.out_env)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
    else:
        out_path = ROOT / "configs" / f"dynamic_allowlist_{ts_str}.env"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env_text, encoding="utf-8")
    print(f"Written: {out_path}")
    print()
    print("To apply:")
    print(f"  python3 scripts/apply_env_overlay.py {out_path.relative_to(ROOT)}")
    print()
    print("Or deploy to server:")
    print(f"  scp {out_path} root@64.226.73.119:/root/bybit-bot/configs/")
    print(f"  ssh root@64.226.73.119 'cd /root/bybit-bot && python3 scripts/apply_env_overlay.py configs/{out_path.name} && systemctl restart bybit-bot'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
