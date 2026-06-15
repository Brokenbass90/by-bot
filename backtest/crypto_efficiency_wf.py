"""Fee/slippage-aware efficiency check for the crypto mean-reversion core.

Codex's open question: ASB1 smoke looks good, but does the edge SURVIVE fees?
This reuses the BacktestStore from crypto_efficiency_backtest and re-runs with a
round-trip fee/slippage charge converted into R units, sweeping 0/10/20 bps.

Additive / standalone. Imports strategy classes directly (not the monolith).
Still smoke-grade on the fragmentary local cache (TFs overridden to 60/5, small
samples) — the value is "does expectancy stay positive once costs bite?".
"""
from __future__ import annotations

import argparse
import os
from typing import List

from backtest.crypto_efficiency_backtest import BacktestStore, _target_from_signal, _metrics
from backtest.ladder_exit import simulate_ladder_exit


def _slice_recent(rows: List[list], max_rows: int | None) -> List[list]:
    if max_rows is None or max_rows <= 0 or len(rows) <= max_rows:
        return rows
    return rows[-max_rows:]


def backtest_fees(strategy, symbol, signal_tf, regime_tf, fee_bps=0.0, max_hold_bars=200, max_rows: int | None = None):
    store = BacktestStore(symbol, [signal_tf, regime_tf])
    if not store.has(signal_tf):
        return {"error": f"no {signal_tf} data for {symbol}"}
    sig_rows = _slice_recent(store._data[signal_tf], max_rows)
    if not sig_rows:
        return {"error": f"no sliced {signal_tf} data for {symbol}"}
    Rs: List[float] = []
    in_trade_until = -1
    fee_frac = fee_bps / 10000.0
    for i in range(len(sig_rows)):
        ts, o, h, l, c, v = sig_rows[i]
        if i <= in_trade_until:
            continue
        store.set_cursor(ts)
        try:
            sig = strategy.maybe_signal(store, ts, o, h, l, c, v)
        except Exception:
            sig = None
        if sig is None:
            continue
        side = str(getattr(sig, "side", "")).lower()
        entry = float(getattr(sig, "entry", c) or c)
        sl = getattr(sig, "sl", None)
        tp = _target_from_signal(sig)
        if not sl or entry <= 0:
            continue
        sl = float(sl); risk = abs(entry - sl)
        if risk <= 0:
            continue
        exit_R = None
        for j in range(i + 1, min(i + 1 + max_hold_bars, len(sig_rows))):
            hj, lj, cj = sig_rows[j][2], sig_rows[j][3], sig_rows[j][4]
            if side in ("buy", "long"):
                if lj <= sl:
                    exit_R = -1.0; break
                if tp and hj >= tp:
                    exit_R = (tp - entry) / risk; break
            else:
                if hj >= sl:
                    exit_R = -1.0; break
                if tp and lj <= tp:
                    exit_R = (entry - tp) / risk; break
            in_trade_until = j
        if exit_R is None:
            cj = sig_rows[min(i + max_hold_bars, len(sig_rows) - 1)][4]
            exit_R = ((cj - entry) if side in ("buy", "long") else (entry - cj)) / risk
        # round-trip fee/slippage in R units: cost as % of price / stop% of price
        stop_frac = risk / entry
        fee_R = (2.0 * fee_frac) / stop_frac if stop_frac > 0 else 0.0
        Rs.append(exit_R - fee_R)
    m = _metrics(Rs, sig_rows[0][0], sig_rows[-1][0])
    m["fee_bps"] = fee_bps
    return m


# --- realistic runner-ladder exit: TP1 partial -> breakeven -> runner to TP2 ---
def backtest_ladder(strategy, symbol, signal_tf, regime_tf, fee_bps=0.0, max_hold_bars=200, max_rows: int | None = None):
    store = BacktestStore(symbol, [signal_tf, regime_tf])
    if not store.has(signal_tf):
        return {"error": f"no {signal_tf} data for {symbol}"}
    sig_rows = _slice_recent(store._data[signal_tf], max_rows)
    if not sig_rows:
        return {"error": f"no sliced {signal_tf} data for {symbol}"}
    Rs = []
    in_trade_until = -1
    for i in range(len(sig_rows)):
        ts, o, h, l, c, v = sig_rows[i]
        if i <= in_trade_until:
            continue
        store.set_cursor(ts)
        try:
            sig = strategy.maybe_signal(store, ts, o, h, l, c, v)
        except Exception:
            sig = None
        if sig is None:
            continue
        side = str(getattr(sig, "side", "")).lower()
        entry = float(getattr(sig, "entry", c) or c)
        sl = getattr(sig, "sl", None)
        if not sl or entry <= 0:
            continue
        sl = float(sl); risk = abs(entry - sl)
        if risk <= 0:
            continue
        tps = getattr(sig, "tps", None) or ([float(sig.tp)] if getattr(sig, "tp", None) else [])
        fracs = getattr(sig, "tp_fracs", None) or ([1.0] * len(tps))
        if not tps:
            continue
        is_long = side in ("buy", "long")
        end_j = min(i + 1 + max_hold_bars, len(sig_rows))
        bars = [(sig_rows[j][2], sig_rows[j][3]) for j in range(i + 1, end_j)]
        realized, remaining = simulate_ladder_exit(
            is_long,
            entry,
            sl,
            tps,
            fracs,
            bars,
            fee_bps_round_trip=fee_bps,
        )
        in_trade_until = end_j - 1
        if remaining > 0:  # time-stop remainder at close
            cj = sig_rows[min(i + max_hold_bars, len(sig_rows) - 1)][4]
            time_stop_R = ((cj - entry) if is_long else (entry - cj)) / risk
            realized += remaining * time_stop_R
            stop_frac = risk / entry
            if stop_frac > 0:
                realized -= remaining * (fee_bps / 10000.0) / stop_frac
        Rs.append(realized)
    m = _metrics(Rs, sig_rows[0][0], sig_rows[-1][0]); m["fee_bps"] = fee_bps; m["model"] = "ladder"
    return m


def _parse_floats(raw: str) -> tuple[float, ...]:
    return tuple(float(x.strip()) for x in str(raw).split(",") if x.strip())


def _parse_symbols(raw: str) -> tuple[str, ...]:
    return tuple(x.strip().upper() for x in str(raw).split(",") if x.strip())


def _compare(symbols: tuple[str, ...], fees: tuple[float, ...], max_rows: int | None):
    from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
    os.environ.setdefault("ASB1_REGIME_TF", "60"); os.environ.setdefault("ASB1_SIGNAL_TF", "5")
    print("\n=== ASB1: single-final-TP vs realistic runner-ladder (TP1 60% -> BE -> TP2) ===")
    for sym in symbols:
        for fee in fees:
            s = backtest_fees(AltSupportBounceV1Strategy(), sym, "5", "60", fee_bps=fee, max_rows=max_rows)
            lad = backtest_ladder(AltSupportBounceV1Strategy(), sym, "5", "60", fee_bps=fee, max_rows=max_rows)
            if s.get("trades"):
                print(f"{sym} {int(fee)}bps | single: exp={s['expectancy_R']:+.2f}R WR={s['win_pct']}% PF={s['profit_factor']} "
                      f"|| ladder: exp={lad['expectancy_R']:+.2f}R WR={lad['win_pct']}% PF={lad['profit_factor']} n={lad['trades']}")


def main() -> int:
    from strategies.alt_resistance_fade_v1 import AltResistanceFadeV1Strategy
    from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy

    ap = argparse.ArgumentParser(description="Fee/slippage-aware crypto efficiency WF smoke")
    ap.add_argument("--symbols", default="SOLUSDT,LINKUSDT,ADAUSDT")
    ap.add_argument("--fees", default="0,10,20")
    ap.add_argument("--max-rows", type=int, default=0, help="Limit to most recent N signal bars; 0 = full cache")
    ap.add_argument("--skip-ladder-compare", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("ASB1_REGIME_TF", "60"); os.environ.setdefault("ASB1_SIGNAL_TF", "5")
    os.environ.setdefault("ARF1_REGIME_TF", "60"); os.environ.setdefault("ARF1_SIGNAL_TF", "5")
    os.environ.setdefault("ARF1_SYMBOL_ALLOWLIST", "")  # empty = all (default-trap fixed)

    symbols = _parse_symbols(args.symbols)
    fees = _parse_floats(args.fees)
    max_rows = args.max_rows if args.max_rows > 0 else None
    print("=== crypto core: does the edge survive fees? (smoke, local/server cache) ===")
    print(f"fee sweep: {', '.join(str(int(f)) for f in fees)} bps round-trip (slippage+taker)")
    if max_rows:
        print(f"bounded: most recent {max_rows} signal bars")
    print()
    for name, factory in (("ASB1(long)", AltSupportBounceV1Strategy),
                          ("ARF1(short)", AltResistanceFadeV1Strategy)):
        for sym in symbols:
            line = f"{name:<12}{sym:<9}"
            for fee in fees:
                m = backtest_fees(factory(), sym, "5", "60", fee_bps=fee, max_rows=max_rows)
                if m.get("trades", 0) == 0:
                    line += f" | {int(fee)}bps: n=0"
                else:
                    line += f" | {int(fee)}bps: exp={m['expectancy_R']:+.2f}R PF={m['profit_factor']} n={m['trades']}"
            print(line, flush=True)
    if not args.skip_ladder_compare:
        _compare(tuple(s for s in symbols if s in {"SOLUSDT", "ADAUSDT", "LINKUSDT"}), tuple(f for f in fees if f in {0.0, 10.0}), max_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
