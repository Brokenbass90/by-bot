"""Multi-window walk-forward for a crypto strategy — the anti-overfit gate.

ASB1/SOL looks like the best pocket with fees (Codex: +1.08R PF2.66 @10bps).
Before it earns any live risk, the edge must hold across SEVERAL disjoint time
windows, not just one lucky pocket. This splits the available signal bars into K
sequential windows and runs the strategy (ladder exit + fees) independently on
each — signals still use only past data (store cursor), so no look-ahead.

Verdict logic: edge is "consistent" if the majority of windows are positive
expectancy. One positive window among losers = episodic / likely overfit.

Additive / standalone. Uses BacktestStore + the canonical ladder exit. Run:
    PYTHONPATH=. python backtest/crypto_multiwindow_wf.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List

from backtest.crypto_efficiency_backtest import BacktestStore, _metrics
from backtest.ladder_exit import simulate_ladder_exit

ROOT = Path(__file__).resolve().parents[1]


def _target_levels(sig):
    tps = getattr(sig, "tps", None)
    fracs = getattr(sig, "tp_fracs", None)
    if tps and fracs:
        return list(tps), list(fracs)
    tp = getattr(sig, "tp", None)
    return ([float(tp)], [1.0]) if tp else ([], [])


def _fee_R_for_close_fraction(entry: float, sl: float, fee_bps: float, fraction: float) -> float:
    """R-cost of closing a remaining fraction after simulate_ladder_exit."""
    risk = abs(entry - sl)
    if risk <= 0 or entry <= 0 or fraction <= 0:
        return 0.0
    return float(fraction) * (float(fee_bps) / 10000.0) / (risk / entry)


def _aggregate_rows(rows: List[list], base_min: int, target_min: int) -> List[list]:
    """Aggregate sorted OHLCV rows into timestamp-aligned higher timeframe bars."""
    factor = target_min // base_min if base_min > 0 else 0
    if factor <= 1 or len(rows) < factor:
        return []
    bucket_ms = int(target_min) * 60_000
    buckets: dict[int, list[list]] = {}
    for row in rows:
        ts = int(row[0])
        buckets.setdefault((ts // bucket_ms) * bucket_ms, []).append(row)
    out: List[list] = []
    for bucket_ts in sorted(buckets):
        chunk = sorted(buckets[bucket_ts], key=lambda r: int(r[0]))
        if len(chunk) < factor:
            continue
        out.append([
            int(bucket_ts),
            float(chunk[0][1]),
            max(float(r[2]) for r in chunk),
            min(float(r[3]) for r in chunk),
            float(chunk[-1][4]),
            sum(float(r[5]) for r in chunk),
        ])
    return out


def _ensure_derived_interval(store: BacktestStore, target_tf: str, base_tf: str = "60") -> None:
    """Build missing higher timeframe bars from lower timeframe cache for research harnesses."""
    target_tf = str(target_tf)
    base_tf = str(base_tf)
    if store.has(target_tf):
        return
    try:
        target_min = int(target_tf)
        base_min = int(base_tf)
    except Exception:
        return
    if target_min <= base_min or target_min % base_min != 0:
        return
    base_rows = store._data.get(base_tf) or []
    derived = _aggregate_rows(base_rows, base_min, target_min)
    if not derived:
        return
    store._data[target_tf] = derived
    store._ts[target_tf] = [r[0] for r in derived]


def backtest_window(strategy, symbol, signal_tf, regime_tf, lo_frac, hi_frac,
                    fee_bps=10.0, max_hold=200):
    store = BacktestStore(symbol, [signal_tf, regime_tf])
    _ensure_derived_interval(store, str(regime_tf), str(signal_tf))
    if not store.has(signal_tf):
        return {"error": f"no {signal_tf} data for {symbol}"}
    rows = store._data[signal_tf]
    n = len(rows)
    lo = max(210, int(n * lo_frac))      # keep warmup for lookbacks
    hi = int(n * hi_frac)
    Rs: List[float] = []
    in_trade_until = -1
    for i in range(lo, hi):
        ts, o, h, l, c, v = rows[i]
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
        tps, fracs = _target_levels(sig)
        if not tps:
            continue
        future = [(rows[j][2], rows[j][3]) for j in range(i + 1, min(i + 1 + max_hold, n))]
        R, rem = simulate_ladder_exit(side in ("buy", "long"), entry, float(sl), tps, fracs,
                                      future, fee_bps_round_trip=fee_bps)
        if rem > 1e-9 and future:  # time-stop remainder at last close
            last_c = rows[min(i + max_hold, n - 1)][4]
            R += rem * (((last_c - entry) if side in ("buy", "long") else (entry - last_c)) / abs(entry - float(sl)))
            R -= _fee_R_for_close_fraction(entry, float(sl), fee_bps, rem)
        Rs.append(R)
        in_trade_until = min(i + max_hold, n - 1)
    m = _metrics(Rs, rows[lo][0], rows[hi - 1][0])
    return m


def verdict_from_edges(edges: List[float]) -> str:
    pos = sum(1 for e in edges if e > 0)
    nwin = len(edges)
    if nwin < 2:
        return "INSUFFICIENT TRADED WINDOWS (need signals in at least 2 windows)"
    if pos == nwin:
        return "CONSISTENT"
    if pos > nwin / 2.0:
        return "MIXED (promising, majority positive; not fully proven)"
    return "WEAK (episodic / overfit risk)"


def run(strategy_factory, symbol, signal_tf="5", regime_tf="60", k=3, fee_bps=10.0, *, return_details=False):
    edges = []
    details = []
    print(f"\n{symbol} — {k} windows @ {fee_bps}bps (ladder exit, no look-ahead):")
    for w in range(k):
        lo, hi = w / k, (w + 1) / k
        m = backtest_window(strategy_factory(), symbol, signal_tf, regime_tf, lo, hi, fee_bps)
        if m.get("trades", 0) == 0:
            print(f"  window {w+1}/{k}: n=0")
            details.append({"window": w + 1, "trades": 0, "metrics": m})
            continue
        exp = m["expectancy_R"]
        edges.append(exp)
        details.append({"window": w + 1, "trades": m.get("trades", 0), "metrics": m})
        print(f"  window {w+1}/{k}: exp={exp:+.2f}R PF={m['profit_factor']} WR={m['win_pct']}% n={m['trades']}")
    pos = sum(1 for e in edges if e > 0)
    nwin = len(edges)
    verdict = verdict_from_edges(edges)
    print(f"  -> {pos}/{nwin} windows with trades positive -> {verdict}")
    if return_details:
        return {
            "symbol": symbol,
            "signal_tf": str(signal_tf),
            "regime_tf": str(regime_tf),
            "windows": int(k),
            "fee_bps": float(fee_bps),
            "positive_windows": pos,
            "windows_with_trades": nwin,
            "edges": edges,
            "verdict": verdict,
            "details": details,
        }
    return edges


if __name__ == "__main__":
    from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
    parser = argparse.ArgumentParser(description="Multi-window crypto WF anti-overfit gate")
    parser.add_argument("--symbol", default="SOLUSDT")
    parser.add_argument("--signal-tf", default=os.getenv("ASB1_SIGNAL_TF", "60"))
    parser.add_argument("--regime-tf", default=os.getenv("ASB1_REGIME_TF", "240"))
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    os.environ["ASB1_REGIME_TF"] = str(args.regime_tf)
    os.environ["ASB1_SIGNAL_TF"] = str(args.signal_tf)
    print("=== ASB1 multi-window WF (anti-overfit gate) ===")
    result = run(
        AltSupportBounceV1Strategy,
        args.symbol,
        signal_tf=str(args.signal_tf),
        regime_tf=str(args.regime_tf),
        k=int(args.windows),
        fee_bps=float(args.fee_bps),
        return_details=True,
    )
    if args.output_json:
        path = Path(args.output_json)
    else:
        path = ROOT / "reports" / f"CRYPTO_MULTIWINDOW_WF_{args.symbol}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {path}")
