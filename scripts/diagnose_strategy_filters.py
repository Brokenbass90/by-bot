#!/usr/bin/env python3
"""
diagnose_strategy_filters.py — Диагностика фильтров ATT1/ATT2/ARF1 на реальных данных.

Прогоняет стратегии на последних N барах из data_cache и показывает
точно какой фильтр блокирует каждый потенциальный вход.

Использование:
    python3 scripts/diagnose_strategy_filters.py
    python3 scripts/diagnose_strategy_filters.py --symbols BTCUSDT,ETHUSDT --tf 60 --bars 120
    python3 scripts/diagnose_strategy_filters.py --strategy att2
    python3 scripts/diagnose_strategy_filters.py --strategy arf1

Выходит таблицей:
    SYMBOL | TF | STRATEGY | REASON | COUNT
    BTCUSDT | 60 | ATT1 | long_no_touch | 45
    ETHUSDT | 60 | ATT1 | long_r2_low   | 12
    ...

Это позволяет точно определить что нужно расслабить в live конфиге.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Dotenv loading — must happen BEFORE strategy configs read os.getenv
# ---------------------------------------------------------------------------
# Load .env from project root so ARF1_SYMBOL_ALLOWLIST and live params are set.
# override=False means vars already in the env (CI, shell) take precedence.
# Pass --no-dotenv to skip entirely.
_SKIP_DOTENV = "--no-dotenv" in sys.argv
if not _SKIP_DOTENV:
    try:
        from dotenv import load_dotenv as _load_dotenv
        _env_path = ROOT / ".env"
        if _env_path.exists():
            _load_dotenv(_env_path, override=False)
            print(f"[dotenv] Loaded {_env_path}", file=sys.stderr)
        else:
            print(f"[dotenv] No .env at {_env_path} — live params not loaded", file=sys.stderr)
    except ImportError:
        print("[dotenv] python-dotenv not installed: pip install python-dotenv", file=sys.stderr)

from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy
from strategies.alt_resistance_fade_v1 import AltResistanceFadeV1Strategy

try:
    from strategies.alt_trendline_touch_v2 import AltTrendlineTouchV2Strategy
    HAS_ATT2 = True
except ImportError:
    HAS_ATT2 = False


# ---------------------------------------------------------------------------
# Kline cache reader
# ---------------------------------------------------------------------------

def find_cache_files(cache_dir: Path, symbol: str, tf: str) -> List[Path]:
    pattern = f"{symbol}_{tf}_*.json"
    files = sorted(cache_dir.glob(pattern))
    return files


def load_klines(cache_dir: Path, symbol: str, tf: str, max_bars: int = 500) -> List[list]:
    """Load klines from data_cache JSON files, most recent bars."""
    files = find_cache_files(cache_dir, symbol, tf)
    if not files:
        return []
    all_rows = []
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            if isinstance(data, list):
                all_rows.extend(data)
            elif isinstance(data, dict) and "data" in data:
                all_rows.extend(data["data"])
        except Exception as e:
            print(f"  [WARN] Could not read {fpath}: {e}", file=sys.stderr)
    # Normalize dict rows to list format [ts, o, h, l, c, v]
    normalized = []
    for r in all_rows:
        if isinstance(r, dict):
            normalized.append([
                r.get("ts", 0), r.get("o", 0), r.get("h", 0),
                r.get("l", 0), r.get("c", 0), r.get("v", 0)
            ])
        else:
            normalized.append(r)
    # Sort by timestamp, deduplicate
    normalized.sort(key=lambda r: r[0])
    seen = set()
    deduped = []
    for r in normalized:
        ts = r[0]
        if ts not in seen:
            seen.add(ts)
            deduped.append(r)
    return deduped[-max_bars:] if len(deduped) > max_bars else deduped


# ---------------------------------------------------------------------------
# Fake store для симуляции runner'а
# ---------------------------------------------------------------------------

class FakeStore:
    """Имитирует store объект бота для вызова maybe_signal."""

    def __init__(self, symbol: str, all_klines: Dict[str, List[list]]) -> None:
        self.symbol = symbol
        self.regime = os.getenv("LIVE_REGIME", "bear_trend")
        self._klines = all_klines  # {tf_str: [rows]}

    def fetch_klines(self, symbol: str, tf: str, n: int) -> List[list]:
        rows = self._klines.get(str(tf), [])
        return rows[-n:] if len(rows) >= n else rows


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------

def simulate_strategy(
    strategy_name: str,
    symbol: str,
    klines: Dict[str, List[list]],
    step_from: int = 20,  # начинаем с бара step_from чтобы было достаточно истории
) -> Counter:
    """
    Прогоняет стратегию побарно на исторических данных.
    Возвращает Counter причин no_signal.
    """
    reasons: Counter = Counter()
    primary_tf = "60"  # default для ATT1/ARF1
    if strategy_name == "arf1":
        primary_tf = "60"
    elif strategy_name in ("att1", "att2"):
        primary_tf = "60"

    rows = klines.get(primary_tf, [])
    if not rows:
        return Counter({"NO_DATA": 1})

    # Создаём стратегию
    if strategy_name == "att1":
        strat = AltTrendlineTouchV1Strategy()
    elif strategy_name == "att2" and HAS_ATT2:
        strat = AltTrendlineTouchV2Strategy()
    elif strategy_name == "arf1":
        strat = AltResistanceFadeV1Strategy()
    else:
        return Counter({f"UNKNOWN_STRATEGY_{strategy_name}": 1})

    # Strategy runs sequentially — we give it the full slice up to each bar.
    # We do NOT reset _last_tf_ts between bars: the strategy should track it naturally.
    # We skip the first "warm-up" bars to let indicators initialize.
    signals = 0
    tested = 0
    warm_up = max(step_from, 30)  # bars needed for indicator warm-up

    for i in range(warm_up, len(rows)):
        # Feed the strategy a growing window of history
        slice_klines = {tf: trows[:i] for tf, trows in klines.items()}
        store = FakeStore(symbol, slice_klines)

        bar = rows[i]
        o_ = float(bar[1])
        h_ = float(bar[2])
        lo_ = float(bar[3])
        c_ = float(bar[4])
        v_ = float(bar[5]) if len(bar) > 5 else 0.0

        sig = strat.maybe_signal(store, int(bar[0]), o_, h_, lo_, c_, v_)
        tested += 1

        if sig is not None:
            signals += 1
            reasons["SIGNAL"] += 1
        else:
            reason = ""
            if hasattr(strat, '_last_no_signal_reason'):
                reason = strat._last_no_signal_reason or "unknown"
            elif hasattr(strat, 'last_no_signal_reason'):
                reason = strat.last_no_signal_reason or "unknown"
            reasons[reason or "unknown"] += 1

    reasons["__SIGNALS__"] = signals
    reasons["__BARS_TESTED__"] = tested
    return reasons


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Diagnose strategy signal filters on cached klines")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT",
                        help="Comma-separated symbols")
    parser.add_argument("--tf", default="60", help="Primary signal timeframe")
    parser.add_argument("--bars", type=int, default=300, help="Max bars to load")
    parser.add_argument("--strategy", default="att1,att2,arf1",
                        help="Comma-separated strategies: att1, att2, arf1")
    parser.add_argument("--cache-dir", default=str(ROOT / "data_cache"),
                        help="Path to data_cache directory")
    parser.add_argument("--no-dotenv", action="store_true",
                        help="Skip loading .env (use when env vars are set externally)")
    parser.add_argument("--top-reasons", type=int, default=8, help="Top N reasons to show")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategies = [s.strip().lower() for s in args.strategy.split(",") if s.strip()]
    tfs_needed = {"60", "240", "5", "15"}  # загружаем все нужные TF

    print(f"\n{'='*70}")
    print(f"Strategy Filter Diagnostic")
    print(f"Cache: {cache_dir}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Strategies: {', '.join(strategies)}")
    print("Scope: cached-strategy diagnosis only; server control-plane overlays are not replayed here.")
    print(f"{'='*70}\n")

    all_results = defaultdict(dict)  # {symbol: {strategy: Counter}}

    for symbol in symbols:
        # Load klines for all needed TFs
        klines: Dict[str, List[list]] = {}
        for tf in tfs_needed:
            rows = load_klines(cache_dir, symbol, tf, args.bars)
            if rows:
                klines[tf] = rows
                print(f"  [{symbol}] TF={tf}: {len(rows)} bars loaded")
            else:
                print(f"  [{symbol}] TF={tf}: NO DATA in cache")

        if not klines.get(args.tf):
            print(f"  [{symbol}] SKIP — no data for primary TF={args.tf}\n")
            continue

        for strat_name in strategies:
            if strat_name == "att2" and not HAS_ATT2:
                print(f"  [{symbol}] ATT2: not available (file not found), skipping")
                continue

            print(f"\n  Running {strat_name.upper()} on {symbol}...")
            reasons = simulate_strategy(strat_name, symbol, klines, step_from=30)
            all_results[symbol][strat_name] = reasons

    # Print summary table
    print(f"\n{'='*70}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*70}")
    for symbol in symbols:
        if symbol not in all_results:
            continue
        print(f"\n  {symbol}")
        for strat_name in strategies:
            if strat_name not in all_results[symbol]:
                continue
            reasons = all_results[symbol][strat_name]
            bars = reasons.get("__BARS_TESTED__", 0)
            signals = reasons.get("__SIGNALS__", 0)
            print(f"    [{strat_name.upper()}] bars={bars} signals={signals} "
                  f"({signals/max(1,bars)*100:.1f}% hit rate)")

            # Top no-signal reasons
            filtered = {k: v for k, v in reasons.items()
                        if not k.startswith("__") and k != "SIGNAL"}
            for reason, count in Counter(filtered).most_common(args.top_reasons):
                pct = count / max(1, bars) * 100
                bar_str = "#" * min(30, int(pct * 2))
                print(f"      {reason:<40s} {count:4d} ({pct:5.1f}%) {bar_str}")

    # Action recommendations
    print(f"\n{'='*70}")
    print("RECOMMENDATIONS:")

    # Aggregate reasons across all symbols per strategy
    for strat_name in strategies:
        agg: Counter = Counter()
        total_bars = 0
        for symbol in symbols:
            if symbol in all_results and strat_name in all_results[symbol]:
                r = all_results[symbol][strat_name]
                total_bars += r.get("__BARS_TESTED__", 0)
                for k, v in r.items():
                    if not k.startswith("__") and k != "SIGNAL":
                        agg[k] += v

        if not agg:
            continue
        top = agg.most_common(3)
        print(f"\n  {strat_name.upper()} — top blockers across all symbols:")
        for reason, count in top:
            pct = count / max(1, total_bars) * 100
            recommendation = _get_recommendation(strat_name, reason)
            print(f"    [{reason}] {count} bars ({pct:.1f}%) → {recommendation}")

    print()


def _get_recommendation(strategy: str, reason: str) -> str:
    """Map common reasons to concrete env var recommendations."""
    recs = {
        # ATT1/ATT2
        "long_r2_low": "Lower ATT1_MIN_R2 from 0.70 → 0.55 (top sweep winner)",
        "short_r2_low": "Lower ATT1_MIN_R2 from 0.70 → 0.55",
        "long_pivot_stale": "Increase ATT1_MAX_PIVOT_AGE from 20 → 24",
        "short_pivot_stale": "Increase ATT1_MAX_PIVOT_AGE from 20 → 24",
        "long_no_touch": "Increase ATT1_TOUCH_ATR from 0.40 → 0.50",
        "short_no_touch": "Increase ATT1_TOUCH_ATR from 0.40 → 0.50",
        "long_no_reject": "Decrease ATT1_REJECT_ATR from 0.10 → 0.07",
        "short_no_reject": "Decrease ATT1_REJECT_ATR from 0.10 → 0.07",
        "long_rsi_too_high": "Increase ATT1_RSI_LONG_MAX from 55 → 58 in research only",
        "short_rsi_too_low": "Decrease ATT1_RSI_SHORT_MIN from 45 → 42 in research only",
        "long_pivots_short": "Decrease ATT1_PIVOT_LEFT/RIGHT from 3 → 2",
        "short_pivots_short": "Decrease ATT1_PIVOT_LEFT/RIGHT from 3 → 2",
        "long_slope_invalid": "Adjust ATT1_MIN_SLOPE_PCT or MAX_SLOPE_PCT",
        "long_slope_direction": "Increase ATT1_LONG_MAX_NEG_SLOPE → 0.6",
        "short_slope_direction": "Increase ATT1_SHORT_MAX_POS_SLOPE from 0.5 → 0.7-0.8 (run att1_short_slope_v1 sweep)",
        "short_slope_invalid": "Test ATT1_MAX_SLOPE_PCT carefully; it affects both sides, not only shorts",
        # ARF1
        "no_res_touch": "Increase ARF1_RES_TOUCH_BUFFER_ATR from 0.35 → 0.50",
        "no_reject_back": "Decrease ARF1_REJECT_BELOW_RES_ATR from 0.12 → 0.08",
        "regime_slope_high": "Relax ARF1_REGIME_MAX_SLOPE_PCT → 2.2",
        "regime_gap_high": "Relax ARF1_REGIME_MAX_GAP_PCT → 4.0",
        "rsi_too_low": "Lower ARF1_MIN_RSI from 58 → 52",
        # Generic
        "same_bar": "Diagnostic noise — expected, not a real blocker",
        "cooldown": "Cooldown working as intended",
        "first_bar": "First bar per session — expected",
        "history_short": "Not enough cached bars — run cache refresh script",
    }
    # Partial match
    for key, rec in recs.items():
        if reason.startswith(key):
            return rec
    return "Inspect manually — rare reason"


if __name__ == "__main__":
    main()
