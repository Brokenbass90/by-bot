"""Liquidation-sweep research — the falsifiable test for a NEW, uncorrelated edge.

Hypothesis (owner's own discretionary experience + reviewer): a cluster of
forced liquidations sweeps stops and creates a temporary imbalance that snaps
back. Microstructure edge where a SMALL account has an advantage funds don't.

Direction (the code is correct; this comment now matches it):
  * LONG liquidations  = forced SELLS -> price spikes DOWN -> we BUY the dip  -> enter LONG
  * SHORT liquidations = forced BUYS  -> price spikes UP   -> we SELL the pop -> enter SHORT
So the reversal trade side is the SAME as the liquidated side: we FADE the
liquidation spike (buy the forced-sell dip / sell the forced-buy pop).

This is RESEARCH, not a live strategy: it measures whether the bounce actually
happens often enough, after costs, to be worth building. Pure / standalone:
Codex feeds real Bybit liquidation history (WS already streams it) + price bars;
this engine returns win-rate / expectancy. If it fails -> we drop it and do Elder.

A liquidation event: {"ts_ms", "side" ("long"|"short"), "usd"}.
Price bars: list of (ts_ms, high, low, close), ascending.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple


def detect_clusters(events: Sequence[dict], *, window_ms: int = 5 * 60_000,
                    min_usd: float = 1_000_000.0, dominance: float = 0.7) -> List[dict]:
    """Group liquidations into clusters where one side dominates and exceeds min_usd.

    Returns clusters: {"ts_ms", "side" (liquidated side), "usd", "reversal_side"}.
    """
    ev = sorted([e for e in events if e.get("usd")], key=lambda e: e["ts_ms"])
    clusters: List[dict] = []
    i = 0
    n = len(ev)
    while i < n:
        t0 = ev[i]["ts_ms"]
        long_usd = short_usd = 0.0
        j = i
        last_ts = t0
        while j < n and ev[j]["ts_ms"] - t0 <= window_ms:
            side = str(ev[j].get("side", "")).lower()
            if side == "long":
                long_usd += float(ev[j]["usd"])
            elif side == "short":
                short_usd += float(ev[j]["usd"])
            last_ts = ev[j]["ts_ms"]
            j += 1
        total = long_usd + short_usd
        if total >= min_usd and total > 0:
            dom_side = "long" if long_usd >= short_usd else "short"
            dom_frac = max(long_usd, short_usd) / total
            if dom_frac >= dominance:
                clusters.append({
                    "ts_ms": last_ts,
                    "side": dom_side,
                    "usd": round(total, 2),
                    "reversal_side": "long" if dom_side == "long" else "short",
                })
        i = j if j > i else i + 1
    return clusters


def _price_at(bars: Sequence[Tuple[int, float, float, float]], ts_ms: int) -> Optional[int]:
    """Index of the first bar at/after ts_ms."""
    for k, b in enumerate(bars):
        if b[0] >= ts_ms:
            return k
    return None


def measure_bounce(cluster: dict, bars: Sequence[Tuple[int, float, float, float]],
                   *, horizon_ms: int = 15 * 60_000, target_pct: float = 0.4,
                   stop_pct: float = 0.4, fee_bps: float = 10.0) -> Optional[float]:
    """Return realised R for one cluster's reversal trade (target/stop in %), or None.

    Enter at the close of the cluster bar in reversal_side; target_pct / stop_pct
    define a symmetric 1R trade; fees subtracted in R units.

    Note: if a single bar touches BOTH target and stop, the stop is counted first
    (conservative bias) — for research we'd rather under- than over-state edge.
    """
    k = _price_at(bars, cluster["ts_ms"])
    if k is None or k + 1 >= len(bars):
        return None
    entry = bars[k][3]
    if entry <= 0:
        return None
    is_long = cluster["reversal_side"] == "long"
    tgt = entry * (1 + target_pct / 100.0) if is_long else entry * (1 - target_pct / 100.0)
    stp = entry * (1 - stop_pct / 100.0) if is_long else entry * (1 + stop_pct / 100.0)
    end_ts = cluster["ts_ms"] + horizon_ms
    fee_R = (2 * fee_bps / 10000.0) / (stop_pct / 100.0)  # round-trip fee in R
    for b in bars[k + 1:]:
        if b[0] > end_ts:
            break
        hi, lo = b[1], b[2]
        if is_long:
            if lo <= stp:
                return -1.0 - fee_R
            if hi >= tgt:
                return (target_pct / stop_pct) - fee_R
        else:
            if hi >= stp:
                return -1.0 - fee_R
            if lo <= tgt:
                return (target_pct / stop_pct) - fee_R
    # time-stop at last close in horizon
    last_close = None
    for b in bars[k + 1:]:
        if b[0] > end_ts:
            break
        last_close = b[3]
    if last_close is None:
        return None
    move = ((last_close - entry) if is_long else (entry - last_close)) / (entry * stop_pct / 100.0)
    return move - fee_R


def hypothesis_test(events: Sequence[dict], bars: Sequence[Tuple[int, float, float, float]],
                    *, window_ms=5 * 60_000, min_usd=1_000_000.0,
                    horizon_ms=15 * 60_000, target_pct=0.4, stop_pct=0.4,
                    fee_bps=10.0) -> Dict[str, object]:
    """Run the full falsifiable test. Verdict: pass if WR>55% and expectancy>0."""
    clusters = detect_clusters(events, window_ms=window_ms, min_usd=min_usd)
    Rs: List[float] = []
    for c in clusters:
        r = measure_bounce(c, bars, horizon_ms=horizon_ms, target_pct=target_pct,
                           stop_pct=stop_pct, fee_bps=fee_bps)
        if r is not None:
            Rs.append(r)
    n = len(Rs)
    if n == 0:
        return {"clusters": len(clusters), "trades": 0, "verdict": "NO DATA"}
    wins = sum(1 for r in Rs if r > 0)
    wr = 100.0 * wins / n
    exp = sum(Rs) / n
    gp = sum(r for r in Rs if r > 0)
    gl = -sum(r for r in Rs if r <= 0)
    pf = (gp / gl) if gl > 0 else float("inf")
    verdict = "PASS (research)" if (wr > 55.0 and exp > 0) else "FAIL (noise / no edge)"
    return {"clusters": len(clusters), "trades": n, "win_pct": round(wr, 1),
            "expectancy_R": round(exp, 3),
            "profit_factor": (round(pf, 2) if pf != float("inf") else "inf"),
            "verdict": verdict}
