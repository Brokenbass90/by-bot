"""Shared market-context / levels layer.

One place that turns raw OHLC into the structure a discretionary trader actually
looks at — horizontal support/resistance clusters *and* sloped trendlines — so
strategies stop each re-deriving primitive ``min(lows)`` / ``max(highs)`` levels.

Consolidates proven logic already living inside strategies:
- horizontal pivot clusters, volume-at-price (HVN), VWAP  -> from ARF2
  (``alt_resistance_fade_v2``);
- swing-pivot sloped trendline fit with R^2                -> from ATT1
  (``alt_trendline_touch_v1``).

Row format (Bybit/backtest kline): ``[ts, open, high, low, close, volume]``.
Pure stdlib; safe to import from the monolith, strategies, or backtests.

Typical use::

    from bot.market_context import build_context
    ctx = build_context(rows, atr_value=atr)
    res = ctx["resistance"]          # nearest overhead structure
    if res and res["dist_atr"] < 0.4 and res["touches"] >= 3:
        ...   # price is tagging a real, repeatedly-tested resistance
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple

# Column indices for an OHLCV row.
TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


def _f(row: list, i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


# ── ATR ──────────────────────────────────────────────────────────────────────
def atr(rows: List[list], period: int = 14) -> float:
    """Simple average true range over the last ``period`` bars."""
    if len(rows) < 2:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(rows)):
        h = _f(rows[i], HIGH)
        l = _f(rows[i], LOW)
        pc = _f(rows[i - 1], CLOSE)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        if math.isfinite(tr):
            trs.append(tr)
    if not trs:
        return float("nan")
    window = trs[-int(max(1, period)):]
    return sum(window) / len(window)


# ── Pivots ───────────────────────────────────────────────────────────────────
def pivot_highs(rows: List[list], left: int = 2, right: int = 2) -> List[dict]:
    """Swing highs: a bar whose high dominates ``left`` bars back and ``right``
    bars forward (>= on the left, > on the right to avoid flat-top dupes)."""
    out: List[dict] = []
    n = len(rows)
    if n < left + right + 1:
        return out
    highs = [_f(r, HIGH) for r in rows]
    for i in range(left, n - right):
        px = highs[i]
        if all(px >= highs[j] for j in range(i - left, i)) and all(
            px > highs[j] for j in range(i + 1, i + right + 1)
        ):
            out.append({"price": px, "idx": i, "ts": int(_f(rows[i], TS))})
    return out


def pivot_lows(rows: List[list], left: int = 2, right: int = 2) -> List[dict]:
    """Swing lows (mirror of :func:`pivot_highs`)."""
    out: List[dict] = []
    n = len(rows)
    if n < left + right + 1:
        return out
    lows = [_f(r, LOW) for r in rows]
    for i in range(left, n - right):
        px = lows[i]
        if all(px <= lows[j] for j in range(i - left, i)) and all(
            px < lows[j] for j in range(i + 1, i + right + 1)
        ):
            out.append({"price": px, "idx": i, "ts": int(_f(rows[i], TS))})
    return out


# ── Horizontal clusters ──────────────────────────────────────────────────────
def cluster_levels(pivots: List[dict], tol: float) -> List[dict]:
    """Group nearby pivots (within ``tol`` price) into horizontal levels.

    Returns clusters sorted by price, each: level, touches, last_idx, last_ts.
    """
    if not pivots or tol <= 0:
        return []
    clusters: List[dict] = []
    for p in sorted(pivots, key=lambda d: d["price"]):
        price = p["price"]
        if not clusters or abs(price - clusters[-1]["level"]) > tol:
            clusters.append(
                {"prices": [price], "indices": [p["idx"]], "ts": [p["ts"]], "level": price}
            )
        else:
            c = clusters[-1]
            c["prices"].append(price)
            c["indices"].append(p["idx"])
            c["ts"].append(p["ts"])
            c["level"] = sum(c["prices"]) / len(c["prices"])
    for c in clusters:
        c["touches"] = len(c["prices"])
        c["last_idx"] = max(c["indices"])
        c["last_ts"] = max(c["ts"])
    return clusters


def horizontal_levels(
    rows: List[list],
    *,
    side: str,
    atr_value: float,
    left: int = 2,
    right: int = 2,
    tol_atr: float = 0.45,
    min_touches: int = 2,
) -> List[dict]:
    """Repeatedly-tested horizontal levels above (resistance) / below (support)."""
    if not math.isfinite(atr_value) or atr_value <= 0:
        return []
    tol = max(1e-12, tol_atr * atr_value)
    pivots = pivot_highs(rows, left, right) if side == "resistance" else pivot_lows(rows, left, right)
    clusters = [c for c in cluster_levels(pivots, tol) if c["touches"] >= int(min_touches)]
    return clusters


# ── Sloped trendlines ────────────────────────────────────────────────────────
def fit_line(points: List[Tuple[float, float]]) -> Tuple[float, float, float]:
    """Least-squares fit through (x, y); returns (slope, intercept, r_squared)."""
    n = len(points)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    if n == 2:
        dx = xs[1] - xs[0]
        if abs(dx) < 1e-12:
            return 0.0, (ys[0] + ys[1]) / 2.0, 1.0
        m = (ys[1] - ys[0]) / dx
        return m, ys[0] - m * xs[0], 1.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0, y_mean, 0.0
    m = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / den
    b = y_mean - m * x_mean
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / max(1e-12, ss_tot) if ss_tot > 1e-12 else 1.0
    return m, b, r2


def sloped_level(
    rows: List[list],
    *,
    side: str,
    left: int = 2,
    right: int = 2,
    min_pivots: int = 2,
    min_r2: float = 0.0,
) -> Optional[dict]:
    """Fit a trendline through recent swing highs (resistance) / lows (support).

    Returns dict: slope, intercept, r2, level_now (line value at last bar idx),
    pivots (count). ``None`` if not enough colinear pivots.
    """
    pivots = pivot_highs(rows, left, right) if side == "resistance" else pivot_lows(rows, left, right)
    if len(pivots) < int(min_pivots):
        return None
    pts = [(float(p["idx"]), float(p["price"])) for p in pivots]
    m, b, r2 = fit_line(pts)
    if not math.isfinite(m) or (math.isfinite(r2) and r2 < float(min_r2)):
        return None
    last_idx = len(rows) - 1
    return {
        "slope": m,
        "intercept": b,
        "r2": r2,
        "level_now": m * last_idx + b,
        "pivots": len(pivots),
    }


# ── Volume-at-price / VWAP ───────────────────────────────────────────────────
def volume_hvns(rows: List[list], bins: int = 24, top_n: int = 5) -> List[float]:
    """High-volume nodes: price levels where most volume traded."""
    if not rows or bins <= 1 or top_n <= 0:
        return []
    lo = min(_f(r, LOW) for r in rows)
    hi = max(_f(r, HIGH) for r in rows)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return []
    width = (hi - lo) / float(bins)
    vols = [0.0] * bins
    for r in rows:
        typ = (_f(r, HIGH) + _f(r, LOW) + _f(r, CLOSE)) / 3.0
        v = max(0.0, _f(r, VOL) if len(r) > VOL else 0.0)
        idx = min(bins - 1, max(0, int((typ - lo) / width)))
        vols[idx] += v
    ranked = sorted(range(bins), key=lambda i: vols[i], reverse=True)[:top_n]
    return [lo + (i + 0.5) * width for i in ranked if vols[i] > 0]


def vwap(rows: List[list]) -> float:
    num = den = 0.0
    for r in rows:
        v = max(0.0, _f(r, VOL) if len(r) > VOL else 0.0)
        typ = (_f(r, HIGH) + _f(r, LOW) + _f(r, CLOSE)) / 3.0
        num += typ * v
        den += v
    return num / den if den > 1e-12 else float("nan")


# ── Convenience context ──────────────────────────────────────────────────────
def _nearest(levels: List[dict], price: float, *, above: bool, atr_value: float,
             last_idx: int) -> Optional[dict]:
    cands = []
    for c in levels:
        lv = c["level"]
        if above and lv > price:
            cands.append(c)
        elif not above and lv < price:
            cands.append(c)
    if not cands:
        return None
    best = min(cands, key=lambda c: abs(c["level"] - price))
    return {
        "level": best["level"],
        "touches": best["touches"],
        "age_bars": last_idx - best["last_idx"],
        "dist_atr": abs(best["level"] - price) / atr_value if atr_value > 0 else float("nan"),
    }


def build_context(
    rows: List[list],
    *,
    atr_value: Optional[float] = None,
    atr_period: int = 14,
    pivot_left: int = 2,
    pivot_right: int = 2,
    tol_atr: float = 0.45,
    min_touches: int = 2,
    min_pivots: int = 2,
    min_r2: float = 0.0,
) -> dict[str, Any]:
    """Build a compact, strategy-ready view of current structure.

    Returns: price, atr, resistance/support (nearest horizontal, with touches,
    age_bars, dist_atr), sloped_resistance/sloped_support (slope, r2, level_now,
    dist_atr), hvns, vwap.
    """
    out: dict[str, Any] = {
        "price": float("nan"), "atr": float("nan"),
        "resistance": None, "support": None,
        "sloped_resistance": None, "sloped_support": None,
        "hvns": [], "vwap": float("nan"),
    }
    if not rows:
        return out
    price = _f(rows[-1], CLOSE)
    a = float(atr_value) if (atr_value is not None and atr_value > 0) else atr(rows, atr_period)
    out["price"] = price
    out["atr"] = a
    if not (math.isfinite(a) and a > 0):
        return out
    last_idx = len(rows) - 1

    res = horizontal_levels(rows, side="resistance", atr_value=a, left=pivot_left,
                            right=pivot_right, tol_atr=tol_atr, min_touches=min_touches)
    sup = horizontal_levels(rows, side="support", atr_value=a, left=pivot_left,
                            right=pivot_right, tol_atr=tol_atr, min_touches=min_touches)
    out["resistance"] = _nearest(res, price, above=True, atr_value=a, last_idx=last_idx)
    out["support"] = _nearest(sup, price, above=False, atr_value=a, last_idx=last_idx)

    sr = sloped_level(rows, side="resistance", left=pivot_left, right=pivot_right,
                      min_pivots=min_pivots, min_r2=min_r2)
    ss = sloped_level(rows, side="support", left=pivot_left, right=pivot_right,
                      min_pivots=min_pivots, min_r2=min_r2)
    for key, sl in (("sloped_resistance", sr), ("sloped_support", ss)):
        if sl is not None:
            sl = dict(sl)
            sl["dist_atr"] = abs(sl["level_now"] - price) / a
            out[key] = sl

    out["hvns"] = volume_hvns(rows)
    out["vwap"] = vwap(rows)
    return out
