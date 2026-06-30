"""AdaptiveContextProvider — regime-aware tuning over market_context.

The "AI in control" piece, done the SAFE way: the AI (or a rule-set) tunes the
*parameters* of the proven level detector to the current regime — it does NOT
generate strategy code and it does NOT predict price. Strategies keep consuming
`market_context`; this layer just decides HOW sensitive the detector should be
right now (tighter levels in chop, wider in high volatility, freshness window).

- Works FREE today via `adaptive_params` (rule-based, no API calls).
- API-ready: pass a `tuner(snapshot)->dict` callback (e.g. a DeepSeek wrapper) to
  override params later, without changing strategy code.
- Emits a serializable `snapshot` for an external AI to read.

Pure stdlib + bot.market_context. Anti-lookahead: uses exclude_last ATR and
freshness filtering.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from bot import market_context as mc


def adaptive_params(atr_pct: float, regime: str) -> dict[str, Any]:
    """Rule-based detector params by regime + volatility (DeepSeek's recipe).

    atr_pct = ATR as % of price. regime in {flat, ascending, descending, unknown}.
    """
    # chop/flat: tighter levels, demand more touches (cleaner ranges)
    if regime == "flat":
        return {"tol_atr": 0.30, "min_touches": 3, "pivot_left": 2, "pivot_right": 2,
                "max_age_bars": 60}
    # high volatility: widen tolerance + pivots so we don't shred into noise levels
    if atr_pct >= 5.0:
        return {"tol_atr": 0.55, "min_touches": 2, "pivot_left": 3, "pivot_right": 3,
                "max_age_bars": 40}
    # trending (normal vol): medium sensitivity, fresher levels matter more
    if regime in ("ascending", "descending"):
        return {"tol_atr": 0.40, "min_touches": 2, "pivot_left": 2, "pivot_right": 2,
                "max_age_bars": 36}
    # default
    return {"tol_atr": 0.40, "min_touches": 2, "pivot_left": 2, "pivot_right": 2,
            "max_age_bars": 48}


def context_snapshot(ctx: dict, regime: str, params: dict, atr_pct: float,
                     extra: Optional[dict] = None) -> dict[str, Any]:
    """Compact, JSON-serializable view for an external AI to reason over."""
    snap = {
        "price": ctx.get("price"),
        "atr": ctx.get("atr"),
        "atr_pct": round(atr_pct, 4) if atr_pct == atr_pct else None,
        "regime": regime,
        "params": params,
        "resistance": ctx.get("resistance"),
        "support": ctx.get("support"),
        "sloped_resistance": ctx.get("sloped_resistance"),
        "sloped_support": ctx.get("sloped_support"),
        "broken_support": ctx.get("broken_support"),
        "broken_resistance": ctx.get("broken_resistance"),
        "hvns": ctx.get("hvns"),
        "vwap": ctx.get("vwap"),
    }
    if extra:
        snap["extra"] = extra
    return snap


def get_adaptive_context(
    rows: list,
    *,
    atr_period: int = 14,
    tuner: Optional[Callable[[dict], dict]] = None,
    extra: Optional[dict] = None,
    flat_slope_atr: float = 0.04,
) -> dict[str, Any]:
    """Return {ctx, params, regime, snapshot}.

    1) classify regime (anti-lookahead ATR), 2) pick rule-based params,
    3) optionally let `tuner(snapshot)` override params (DeepSeek hook),
    4) rebuild context with chosen params + add broken levels for retests.
    """
    out = {"ctx": None, "params": {}, "regime": "unknown", "snapshot": None}
    if not rows:
        return out

    a = mc.atr(rows, atr_period, exclude_last=True)
    price = mc._f(rows[-1], mc.CLOSE)
    atr_pct = (a / price * 100.0) if (a == a and a > 0 and price) else float("nan")

    ch = mc.classify_channel(rows, atr_value=a, flat_slope_atr=flat_slope_atr)
    regime = ch.get("regime", "unknown")

    params = adaptive_params(atr_pct if atr_pct == atr_pct else 0.0, regime)

    # optional external tuner (e.g. DeepSeek) — gets a snapshot, returns overrides
    if tuner is not None:
        try:
            base_ctx = mc.build_context(rows, atr_value=a, exclude_last_atr=True,
                                        tol_atr=params["tol_atr"], min_touches=params["min_touches"],
                                        pivot_left=params["pivot_left"], pivot_right=params["pivot_right"],
                                        max_age_bars=params["max_age_bars"])
            snap0 = context_snapshot(base_ctx, regime, params, atr_pct, extra)
            override = tuner(snap0) or {}
            params.update({k: override[k] for k in
                           ("tol_atr", "min_touches", "pivot_left", "pivot_right", "max_age_bars")
                           if k in override})
        except Exception:
            pass  # fail safe to rule-based params

    ctx = mc.build_context(rows, atr_value=a, exclude_last_atr=True,
                           tol_atr=params["tol_atr"], min_touches=params["min_touches"],
                           pivot_left=params["pivot_left"], pivot_right=params["pivot_right"],
                           max_age_bars=params["max_age_bars"])

    # add broken (flipped) levels for breakout-retest entries
    if a == a and a > 0:
        res_levels = mc.horizontal_levels(rows, side="resistance", atr_value=a,
                                          left=params["pivot_left"], right=params["pivot_right"],
                                          tol_atr=params["tol_atr"], min_touches=params["min_touches"])
        sup_levels = mc.horizontal_levels(rows, side="support", atr_value=a,
                                          left=params["pivot_left"], right=params["pivot_right"],
                                          tol_atr=params["tol_atr"], min_touches=params["min_touches"])
        ctx["broken_support"] = mc.nearest_broken_level(rows, res_levels, price, a, "support",
                                                        max_age_bars=params["max_age_bars"])
        ctx["broken_resistance"] = mc.nearest_broken_level(rows, sup_levels, price, a, "resistance",
                                                           max_age_bars=params["max_age_bars"])
    else:
        ctx["broken_support"] = ctx["broken_resistance"] = None

    out["ctx"] = ctx
    out["params"] = params
    out["regime"] = regime
    out["snapshot"] = context_snapshot(ctx, regime, params, atr_pct, extra)
    return out
