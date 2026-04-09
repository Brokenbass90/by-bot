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
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_HTTP_TIMEOUT_SEC = float(os.getenv("ALLOWLIST_HTTP_TIMEOUT_SEC", "8"))
DEFAULT_KLINE_MAX_RETRIES = int(os.getenv("ALLOWLIST_KLINES_MAX_RETRIES", "3"))
DEFAULT_KLINE_BACKOFF_MAX_SEC = float(os.getenv("ALLOWLIST_KLINES_BACKOFF_MAX_SEC", "5.0"))

# Strategy-state scorer (optional — degrades gracefully if import fails)
try:
    from scripts.strategy_scorer import score_for_strategy, explain_score
    _HAS_SCORER = True
except ImportError:
    try:
        from strategy_scorer import score_for_strategy, explain_score  # type: ignore
        _HAS_SCORER = True
    except ImportError:
        _HAS_SCORER = False
        def score_for_strategy(env_key, closes, highs, lows):  # type: ignore
            return 0.5
        def explain_score(env_key, closes, highs, lows):  # type: ignore
            return "scorer_unavailable"

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


def _get_tickers(base: str, *, timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC) -> List[dict]:
    url = f"{base.rstrip('/')}/v5/market/tickers"
    js = requests.get(url, params={"category": "linear"}, timeout=timeout_sec).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    return (js.get("result") or {}).get("list") or []


def _get_instruments_info(base: str, *, timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC) -> Dict[str, dict]:
    url = f"{base.rstrip('/')}/v5/market/instruments-info"
    out: Dict[str, dict] = {}
    cursor = None
    while True:
        params: dict = {"category": "linear"}
        if cursor:
            params["cursor"] = cursor
        js = requests.get(url, params=params, timeout=timeout_sec).json()
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


def _fetch_1h_data(
    symbol: str,
    *,
    base: str,
    lookback_days: int,
    sleep_sec: float,
    max_retries: int,
    backoff_max_sec: float,
) -> tuple:
    """
    Fetch 1h klines and return (atr_pct, closes, highs, lows).
    All four values are needed by strategy_scorer — fetching once avoids
    extra API calls per symbol.
    Returns (0.0, [], [], []) on failure or insufficient data.
    """
    if not _HAS_BACKTEST_LIBS:
        return 0.0, [], [], []
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
            max_retries=max_retries,
            backoff_max_sec=backoff_max_sec,
        )
    except Exception:
        return 0.0, [], [], []
    if len(kl) < 20:
        return 0.0, [], [], []
    h = [float(k.h) for k in kl]
    l = [float(k.l) for k in kl]
    c = [float(k.c) for k in kl]
    atr_pct = float(atr_pct_from_ohlc(h, l, c, period=14, fallback=0.0))
    return atr_pct, c, h, l


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
    bt_require_history: bool = False
    # Fixed always-include symbols (never removed by market filter)
    anchor_symbols: List[str] = field(default_factory=list)


# Default profiles — tuned to each strategy's mechanics.
# NOTE: These are fallback defaults used by dynamic_allowlist.py standalone mode
# and by build_symbol_router.py when no matching registry profile exists.
# The authoritative per-regime profiles live in configs/strategy_profile_registry.json.
_DEFAULT_PROFILES: List[StrategyProfile] = [
    StrategyProfile(
        name="ASC1 (sloped channel)",
        env_key="ASC1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_sloped_channel_v1", "sloped_channel", "asc1"],
        min_turnover=30_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=0.95,
        min_listing_days=120,
        top_n=6,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["LINKUSDT", "ATOMUSDT", "DOTUSDT"],
    ),
    StrategyProfile(
        name="ARF1 (flat resistance fade)",
        env_key="ARF1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_resistance_fade_v1", "arf1"],
        min_turnover=20_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=1.10,
        min_listing_days=90,
        top_n=8,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["LINKUSDT", "LTCUSDT", "SUIUSDT"],
    ),
    StrategyProfile(
        name="BREAKDOWN v1 (breakdown shorts)",
        env_key="BREAKDOWN_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_inplay_breakdown_v1", "inplay_breakdown", "breakdown"],
        min_turnover=50_000_000.0,
        min_atr_pct=0.30,
        max_atr_pct=3.00,
        min_listing_days=90,
        top_n=8,
        bt_min_trades=5,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    ),
    # ── New strategies ──────────────────────────────────────────────────────
    StrategyProfile(
        name="BREAKDOWN v2 (1h breakdown shorts)",
        env_key="BREAKDOWN2_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_inplay_breakdown_v2"],
        min_turnover=20_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=2.50,
        min_listing_days=90,
        top_n=8,
        bt_min_trades=3,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["ADAUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT"],
    ),
    StrategyProfile(
        name="ASB1 (support bounce longs)",
        env_key="ASB1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_support_bounce_v1"],
        min_turnover=20_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=1.20,
        min_listing_days=90,
        top_n=8,
        bt_min_trades=3,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["ADAUSDT", "LINKUSDT", "SUIUSDT", "DOTUSDT"],
    ),
    StrategyProfile(
        name="ARS1 (range scalp BB)",
        env_key="ARS1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_range_scalp_v1"],
        min_turnover=50_000_000.0,
        min_atr_pct=0.25,
        max_atr_pct=1.50,
        min_listing_days=90,
        top_n=6,
        bt_min_trades=3,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    ),
    StrategyProfile(
        name="AVW1 (VWAP mean reversion)",
        env_key="AVW1_SYMBOL_ALLOWLIST",
        strategy_tags=["alt_vwap_mean_reversion_v1"],
        min_turnover=50_000_000.0,
        min_atr_pct=0.20,
        max_atr_pct=1.40,
        min_listing_days=90,
        top_n=6,
        bt_min_trades=3,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"],
    ),
    StrategyProfile(
        name="PF2 (pump/dump fade)",
        env_key="PF2_SYMBOL_ALLOWLIST",
        strategy_tags=["pump_fade_v2"],
        min_turnover=50_000_000.0,
        min_atr_pct=0.30,
        max_atr_pct=5.00,
        min_listing_days=60,
        top_n=8,
        bt_min_trades=3,
        bt_min_net=0.0,
        bt_min_pf=1.0,
        anchor_symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"],
    ),
    StrategyProfile(
        name="ETS2 (Elder Triple Screen)",
        env_key="ETS2_SYMBOL_ALLOWLIST",
        strategy_tags=["elder_triple_screen_v2"],
        min_turnover=30_000_000.0,
        min_atr_pct=0.28,
        max_atr_pct=2.00,
        min_listing_days=90,
        top_n=6,
        bt_min_trades=3,
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
    # 1h OHLC series stored here so strategy_scorer can use them
    # without triggering extra API calls (fetched once in run_scan)
    closes_1h: List[float] = field(default_factory=list)
    highs_1h: List[float] = field(default_factory=list)
    lows_1h: List[float] = field(default_factory=list)

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
    http_timeout_sec: float = DEFAULT_HTTP_TIMEOUT_SEC,
    kline_max_retries: int = DEFAULT_KLINE_MAX_RETRIES,
    kline_backoff_max_sec: float = DEFAULT_KLINE_BACKOFF_MAX_SEC,
    quiet: bool,
) -> Dict[str, CandidateRow]:
    """Fetch tickers, instruments, and ATR% for every USDT perp candidate."""
    if not quiet:
        print("[scan] Fetching Bybit tickers...")
    tickers = _get_tickers(bybit_base, timeout_sec=http_timeout_sec)

    if not quiet:
        print("[scan] Fetching instruments info...")
    instruments = _get_instruments_info(bybit_base, timeout_sec=http_timeout_sec)

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

        atr_pct, closes_1h, highs_1h, lows_1h = _fetch_1h_data(
            sym,
            base=bybit_base,
            lookback_days=atr_lookback_days,
            sleep_sec=polite_sleep_sec,
            max_retries=kline_max_retries,
            backoff_max_sec=kline_backoff_max_sec,
        )

        out[sym] = CandidateRow(
            symbol=sym,
            turnover24h=turn,
            atr_pct=atr_pct,
            listing_age_days=age_days,
            closes_1h=closes_1h,
            highs_1h=highs_1h,
            lows_1h=lows_1h,
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
    symbol_penalties: Optional[Dict[str, Any]] = None,
    return_ranked: bool = False,
    quiet: bool,
) -> List[str] | Tuple[List[str], List[Dict[str, Any]]]:
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
    ranked_rows: List[Dict[str, Any]] = []

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
                ranked_rows.append(
                    {
                        "symbol": sym,
                        "anchor": True,
                        "market_score": None,
                        "strategy_score": None,
                        "memory_penalty": 0.0,
                        "memory_note": "anchor_missing_scan",
                        "final_score": score,
                        "market_summary": None,
                        "bt_summary": "no-bt-data",
                    }
                )
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
        # Only reject if this symbol has backtest data AND it fails the gate.
        # Symbols with NO backtest data are allowed through — this lets the
        # scanner explore new coins rather than being permanently locked to
        # the set that happened to trade in the reference run.
        if backtest and sym not in profile.anchor_symbols:
            if bt_perf is not None:
                bt_ok = (
                    bt_perf.trades >= profile.bt_min_trades
                    and bt_perf.net >= profile.bt_min_net
                    and bt_perf.profit_factor >= profile.bt_min_pf
                )
                if not bt_ok:
                    rejected_bt.append(sym)
                    continue
            elif profile.bt_require_history:
                rejected_bt.append(sym)
                continue
            # bt_perf is None → no history for this symbol → allow through
            # unless the profile explicitly requires historical evidence.

        # ── Market fit: ATR profile + liquidity ───────────────────────────
        # ATR fit: Gaussian score — peaks at 1.0 when ATR is at ideal midpoint
        import math as _math
        atr_mid = (profile.min_atr_pct + profile.max_atr_pct) / 2.0
        atr_half_width = max((profile.max_atr_pct - profile.min_atr_pct) / 2.0, 0.01)
        atr_fit = max(0.0, 1.0 - ((row.atr_pct - atr_mid) / atr_half_width) ** 2)
        # Liquidity: log-scaled so $5B and $500M aren't miles apart (~0.6–1.0)
        liq_score = _math.log10(max(row.turnover24h, 1_000_000.0)) / 10.0
        market_score = atr_fit * 0.70 + liq_score * 0.30

        # ── Strategy fit: current price state for this specific strategy ───
        strategy_score = score_for_strategy(
            profile.env_key,
            row.closes_1h,
            row.highs_1h,
            row.lows_1h,
        )

        # ── Combined: strategy state matters more than generic market fit ──
        # Anchors always get a neutral strategy score (0.5) to avoid being
        # penalised when they're not currently in the ideal setup zone.
        is_anchor = sym in profile.anchor_symbols
        if is_anchor:
            score = market_score * 0.70 + 0.5 * 0.30  # anchors: market-weighted
        else:
            score = market_score * 0.40 + strategy_score * 0.60

        memory_penalty = 0.0
        memory_note = ""
        if symbol_penalties:
            raw_penalty = symbol_penalties.get(sym)
            if isinstance(raw_penalty, dict):
                memory_penalty = float(raw_penalty.get("penalty", 0.0) or 0.0)
                memory_note = str(raw_penalty.get("reason") or "")
            elif raw_penalty is not None:
                memory_penalty = float(raw_penalty or 0.0)
            if is_anchor:
                memory_penalty *= 0.50
            score -= 0.25 * max(0.0, min(1.0, memory_penalty))

        candidates.append((score, sym))
        if bt_perf is None:
            bt_summary = "no-bt-data"
        else:
            bt_summary = (
                f"bt_trades={bt_perf.trades} "
                f"bt_net={bt_perf.net:+.4f} "
                f"bt_pf={bt_perf.profit_factor:.2f}"
            )

        ranked_rows.append(
            {
                "symbol": sym,
                "anchor": bool(is_anchor),
                "market_score": round(float(market_score), 4),
                "strategy_score": round(float(strategy_score), 4),
                "memory_penalty": round(float(memory_penalty), 4),
                "memory_note": memory_note,
                "final_score": round(float(score), 4),
                "market_summary": row.market_summary(),
                "bt_summary": bt_summary,
            }
        )

    # Sort by score desc, take top_n
    candidates.sort(reverse=True)
    selected = [sym for _, sym in candidates[: profile.top_n]]
    ranked_rows.sort(key=lambda item: (-float(item["final_score"]), item["symbol"]))

    if not quiet:
        print(f"\n[{profile.name}]")
        print(f"  Selected ({len(selected)}): {','.join(selected)}")
        if rejected_market:
            print(f"  Rejected by market filter: {len(rejected_market)} symbols")
        if rejected_bt:
            print(f"  Rejected by backtest gate: {len(rejected_bt)} symbols")

    if return_ranked:
        return selected, ranked_rows
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
        "--http-timeout-sec", type=float, default=DEFAULT_HTTP_TIMEOUT_SEC,
        help="Timeout for Bybit public REST requests (default from ALLOWLIST_HTTP_TIMEOUT_SEC or 8).",
    )
    ap.add_argument(
        "--kline-max-retries", type=int, default=DEFAULT_KLINE_MAX_RETRIES,
        help="Max retries per ATR kline fetch (default from ALLOWLIST_KLINES_MAX_RETRIES or 3).",
    )
    ap.add_argument(
        "--kline-backoff-max-sec", type=float, default=DEFAULT_KLINE_BACKOFF_MAX_SEC,
        help="Max backoff for ATR kline retries (default from ALLOWLIST_KLINES_BACKOFF_MAX_SEC or 5).",
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
        http_timeout_sec=args.http_timeout_sec,
        kline_max_retries=args.kline_max_retries,
        kline_backoff_max_sec=args.kline_backoff_max_sec,
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
