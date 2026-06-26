"""Owner-style setup context scoring.

This module is intentionally read-only / research-safe.  It formalizes the
manual trading sequence described by the owner:

1. first find an in-play coin with current relative volume inflow;
2. then require a strong 1H level, not a random wick;
3. enter only if price is close enough to the level;
4. require enough room to the next level for the trade to be worth fees/risk.

It does not place orders and does not change live risk.  Strategies can later
use it as a common precondition/gate, and backtests can log these features to
explain whether a failure was caused by universe, levels, entry timing, exits,
or costs.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

from bot.chart_geometry import analyze_geometry
from bot.inplay_volume_universe import InplayVolumeScore, score_inplay_volume


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _last_close(rows: Sequence[Sequence[Any]]) -> float:
    if not rows:
        return 0.0
    return _f(rows[-1][4], 0.0) if len(rows[-1]) > 4 else 0.0


@dataclass(frozen=True)
class OwnerSetupConfig:
    # Volume-first universe gate.
    recent_bars: int = 3
    baseline_bars: int = 72
    min_recent_quote_usd: float = 250_000.0
    min_inflow_mult: float = 1.8
    min_inflow_z: float = 1.5
    max_abs_recent_return_pct: float = 18.0
    require_inplay_volume: bool = True

    # Level/entry quality.
    max_entry_dist_atr: float = 0.85
    min_level_touches: int = 2
    min_level_score: float = 0.6

    # Trade-worthiness proxy before strategy-specific exits.
    min_room_atr: float = 1.0
    min_rr_proxy: float = 1.15
    stop_buffer_atr: float = 0.35


@dataclass(frozen=True)
class OwnerSetupContext:
    ok: bool
    side: str
    setup_kind: str
    score: float
    rejects: list[str]

    price: float
    atr_1h: float

    inplay_ok: bool
    inplay_reason: str
    inplay_score: float
    recent_quote_usd: float
    baseline_quote_usd: float
    inflow_mult: float
    inflow_z: float
    recent_return_pct: float

    level_price: float | None
    level_side_bias: str
    level_touches: int
    level_score: float
    distance_to_level_atr: float | None

    target_price: float | None
    room_to_target_atr: float | None
    rr_proxy: float | None

    channel_position: float | None
    channel_r2: float | None
    compression_ratio: float | None
    is_compressed: bool | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nearest_level(levels: Sequence[dict[str, Any]], *, price: float, side: str) -> dict[str, Any] | None:
    if side == "long":
        candidates = [x for x in levels if _f(x.get("price")) <= price]
        candidates.sort(key=lambda x: price - _f(x.get("price")))
        return candidates[0] if candidates else None
    if side == "short":
        candidates = [x for x in levels if _f(x.get("price")) >= price]
        candidates.sort(key=lambda x: _f(x.get("price")) - price)
        return candidates[0] if candidates else None
    return None


def _nearest_target(levels: Sequence[dict[str, Any]], *, price: float, side: str) -> dict[str, Any] | None:
    if side == "long":
        candidates = [x for x in levels if _f(x.get("price")) > price]
        candidates.sort(key=lambda x: _f(x.get("price")) - price)
        return candidates[0] if candidates else None
    if side == "short":
        candidates = [x for x in levels if _f(x.get("price")) < price]
        candidates.sort(key=lambda x: price - _f(x.get("price")))
        return candidates[0] if candidates else None
    return None


def _component_clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def score_owner_retest_context(
    rows_5m: Sequence[Sequence[Any]],
    rows_1h: Sequence[Sequence[Any]],
    *,
    side: str,
    cfg: OwnerSetupConfig | None = None,
) -> OwnerSetupContext:
    """Score an owner-style level retest/bounce candidate.

    `side="long"` means retest/support bounce toward the next resistance.
    `side="short"` means resistance fade/retest short toward the next support.
    """
    c = cfg or OwnerSetupConfig()
    side_norm = str(side or "").strip().lower()
    if side_norm not in {"long", "short"}:
        raise ValueError("side must be 'long' or 'short'")

    price = _last_close(rows_5m) or _last_close(rows_1h)
    rejects: list[str] = []

    vol: InplayVolumeScore = score_inplay_volume(
        rows_5m,
        recent_bars=c.recent_bars,
        baseline_bars=c.baseline_bars,
        min_recent_quote_usd=c.min_recent_quote_usd,
        min_inflow_mult=c.min_inflow_mult,
        min_inflow_z=c.min_inflow_z,
        max_abs_recent_return_pct=c.max_abs_recent_return_pct,
    )
    if c.require_inplay_volume and not vol.ok:
        rejects.append(f"volume:{vol.reason}")

    geom = analyze_geometry(rows_1h)
    if geom.get("status") != "ok":
        rejects.append(f"geometry:{geom.get('status')}")

    atr = _f(geom.get("atr"), 0.0)
    levels = list(geom.get("levels") or [])
    if price <= 0:
        rejects.append("price_invalid")
    if atr <= 0:
        rejects.append("atr_1h_invalid")

    level = _nearest_level(levels, price=price, side=side_norm) if atr > 0 and price > 0 else None
    target = _nearest_target(levels, price=price, side=side_norm) if atr > 0 and price > 0 else None

    level_price = _f(level.get("price")) if level else None
    level_touches = int(_f(level.get("touches"), 0)) if level else 0
    level_score = _f(level.get("score"), 0.0) if level else 0.0
    level_side_bias = str(level.get("side_bias") or "") if level else ""

    if level is None:
        rejects.append("level_missing")
        dist_atr = None
    else:
        if level_touches < c.min_level_touches:
            rejects.append("level_touches_low")
        if level_score < c.min_level_score:
            rejects.append("level_score_low")
        dist_atr = abs(price - float(level_price)) / atr if atr > 0 and level_price else None
        if dist_atr is not None and dist_atr > c.max_entry_dist_atr:
            rejects.append("entry_far_from_level")

    target_price = _f(target.get("price")) if target else None
    if target is None:
        rejects.append("target_level_missing")
        room_atr = None
        rr_proxy = None
    else:
        room_atr = abs(float(target_price) - price) / atr if atr > 0 else None
        risk_atr = max(c.stop_buffer_atr, (dist_atr or 0.0) + c.stop_buffer_atr)
        rr_proxy = room_atr / max(0.05, risk_atr) if room_atr is not None else None
        if room_atr is not None and room_atr < c.min_room_atr:
            rejects.append("room_to_target_low")
        if rr_proxy is not None and rr_proxy < c.min_rr_proxy:
            rejects.append("rr_proxy_low")

    channel = geom.get("channel") or {}
    compression = geom.get("compression") or {}

    distance_quality = 0.0
    if dist_atr is not None:
        distance_quality = 1.0 - _component_clip(dist_atr / max(0.01, c.max_entry_dist_atr))
    room_quality = 0.0
    if room_atr is not None:
        room_quality = _component_clip(room_atr / max(0.01, c.min_room_atr * 2.5))
    rr_quality = 0.0
    if rr_proxy is not None:
        rr_quality = _component_clip(rr_proxy / max(0.01, c.min_rr_proxy * 2.0))
    level_quality = _component_clip((level_score / 3.0) * 0.65 + (level_touches / 4.0) * 0.35)
    volume_quality = vol.score if vol.ok else (0.25 * vol.score if not c.require_inplay_volume else 0.0)

    score = (
        0.35 * volume_quality
        + 0.25 * level_quality
        + 0.20 * distance_quality
        + 0.10 * room_quality
        + 0.10 * rr_quality
    )
    ok = len(rejects) == 0

    return OwnerSetupContext(
        ok=ok,
        side=side_norm,
        setup_kind="owner_retest",
        score=round(float(score), 6),
        rejects=rejects,
        price=float(price),
        atr_1h=float(atr),
        inplay_ok=bool(vol.ok),
        inplay_reason=str(vol.reason),
        inplay_score=float(vol.score),
        recent_quote_usd=float(vol.recent_quote_usd),
        baseline_quote_usd=float(vol.baseline_quote_usd),
        inflow_mult=float(vol.inflow_mult),
        inflow_z=float(vol.inflow_z),
        recent_return_pct=float(vol.recent_return_pct),
        level_price=float(level_price) if level_price is not None else None,
        level_side_bias=level_side_bias,
        level_touches=int(level_touches),
        level_score=float(level_score),
        distance_to_level_atr=float(dist_atr) if dist_atr is not None else None,
        target_price=float(target_price) if target_price is not None else None,
        room_to_target_atr=float(room_atr) if room_atr is not None else None,
        rr_proxy=float(rr_proxy) if rr_proxy is not None else None,
        channel_position=_f(channel.get("position")) if channel else None,
        channel_r2=_f(channel.get("r2")) if channel else None,
        compression_ratio=_f(compression.get("compression_ratio")) if compression else None,
        is_compressed=bool(compression.get("is_compressed")) if compression else None,
    )

