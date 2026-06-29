"""Volume-fade early exit — the owner's missing edge for setup A.

Owner's manual rule (OWNER_STRATEGY_SPEC §3, "ключевая деталь"): ride a move
toward the next strong level, BUT if the impulse's volume dies before price gets
there, get out early instead of waiting for a fixed take-profit. Automated legs
today use a fixed TP and miss this — this module supplies the volume-exhaustion
signal they can trail with.

Two independent exhaustion checks (either can fire, configurable):
  1. baseline fade — recent impulse volume dropped below its own recent norm
     (recent_vol / baseline_vol < ``fade_ratio``);
  2. peak fade — volume collapsed to a fraction of the impulse's peak bar
     (recent_vol / peak_vol < ``peak_fade_ratio``).

Optionally require price to also have stalled (no fresh progress in the trade
direction over the impulse window) so we don't exit a quiet-but-still-advancing
move. Default requires stall — exit only when volume dies AND price isn't
making new ground.

Row format: ``[ts, open, high, low, close, volume]``. Pure stdlib; deterministic.
"""
from __future__ import annotations

from typing import Any, List, Optional

TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


def _f(row: list, i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]  # drop NaN
    return sum(xs) / len(xs) if xs else float("nan")


def volume_fade_exit(
    rows: List[list],
    *,
    side: str,
    baseline_window: int = 20,
    impulse_window: int = 3,
    fade_ratio: float = 0.70,
    peak_fade_ratio: float = 0.45,
    peak_window: int = 10,
    min_impulse_mult: float = 2.0,
    require_stall: bool = True,
    min_bars: int = 8,
) -> dict[str, Any]:
    """Decide whether to exit early because the impulse's volume is fading.

    Returns: exit (bool), reason (str), vol_ratio (recent/baseline),
    peak_ratio (recent/peak), stalled (bool), recent_vol, baseline_vol, peak_vol.
    """
    out: dict[str, Any] = {
        "exit": False, "reason": "", "vol_ratio": float("nan"),
        "peak_ratio": float("nan"), "stalled": False,
        "recent_vol": float("nan"), "baseline_vol": float("nan"),
        "peak_vol": float("nan"), "impulse_present": False,
    }
    n = len(rows)
    if n < max(int(min_bars), int(impulse_window) + 2):
        out["reason"] = "not_enough_bars"
        return out
    side = str(side).lower()
    if side not in ("long", "short", "buy", "sell"):
        out["reason"] = "bad_side"
        return out
    is_long = side in ("long", "buy")

    vols = [_f(r, VOL) for r in rows]
    iw = max(1, int(impulse_window))
    bw = max(iw + 1, int(baseline_window))
    pw = max(iw, int(peak_window))

    recent_vol = _mean(vols[-iw:])
    # baseline = bars before the impulse window, so we compare impulse vs its run-up
    baseline_slice = vols[-(bw + iw):-iw] if n >= bw + iw else vols[:-iw]
    baseline_vol = _mean(baseline_slice)
    peak_vol = max([v for v in vols[-pw:] if v == v] or [float("nan")])

    out["recent_vol"] = recent_vol
    out["baseline_vol"] = baseline_vol
    out["peak_vol"] = peak_vol
    if not (recent_vol == recent_vol and baseline_vol == baseline_vol and baseline_vol > 0):
        out["reason"] = "volume_unavailable"
        return out

    vol_ratio = recent_vol / baseline_vol
    peak_ratio = recent_vol / peak_vol if (peak_vol == peak_vol and peak_vol > 0) else float("nan")
    out["vol_ratio"] = round(vol_ratio, 4)
    out["peak_ratio"] = round(peak_ratio, 4) if peak_ratio == peak_ratio else float("nan")

    # Impulse gate: only ride/exit a move that actually had a volume thrust.
    # Without a real prior impulse (peak >> baseline) there is nothing to "fade
    # from" — flat chop must NOT trigger an exit.
    impulse_present = (peak_vol == peak_vol) and (peak_vol >= float(min_impulse_mult) * baseline_vol)
    out["impulse_present"] = bool(impulse_present)
    if not impulse_present:
        out["reason"] = "no_prior_impulse"
        return out

    # Price stall: no fresh progress in trade direction over the impulse window.
    window_highs = [_f(r, HIGH) for r in rows[-iw:]]
    window_lows = [_f(r, LOW) for r in rows[-iw:]]
    prior_high = max(_f(r, HIGH) for r in rows[-(iw + iw):-iw])
    prior_low = min(_f(r, LOW) for r in rows[-(iw + iw):-iw])
    if is_long:
        stalled = max(window_highs) <= prior_high  # no new high
    else:
        stalled = min(window_lows) >= prior_low     # no new low
    out["stalled"] = bool(stalled)

    baseline_fade = vol_ratio < float(fade_ratio)
    peak_fade = (peak_ratio == peak_ratio) and (peak_ratio < float(peak_fade_ratio))

    if not (baseline_fade or peak_fade):
        out["reason"] = "volume_alive"
        return out
    if require_stall and not stalled:
        out["reason"] = "volume_fading_but_price_advancing"
        return out

    reasons = []
    if baseline_fade:
        reasons.append(f"vol {vol_ratio:.2f}x<{fade_ratio:g} of run-up")
    if peak_fade:
        reasons.append(f"vol {peak_ratio:.2f}x<{peak_fade_ratio:g} of peak")
    if require_stall:
        reasons.append("price stalled")
    out["exit"] = True
    out["reason"] = "; ".join(reasons)
    return out
