"""Build the AI/web-facing view of open live positions.

The exchange TP can legitimately be empty for runner-managed strategies.  This
module keeps that distinction explicit so dashboards and AI prompts do not
mistake ``tp=None`` for "the strategy has no take-profit plan".
"""
from __future__ import annotations

from typing import Any


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_price(value: Any) -> float | None:
    num = _float_or_none(value)
    return round(num, 6) if num else None


def runner_exit_snapshot(tr: Any) -> dict[str, Any]:
    """Return a serializable runner/TP view for a TradeState-like object."""
    runner_enabled = bool(getattr(tr, "runner_enabled", False))
    raw_tps = list(getattr(tr, "tps", None) or [])
    raw_fracs = list(getattr(tr, "tp_fracs", None) or [])
    raw_hits = list(getattr(tr, "tp_hit", None) or [])
    targets: list[dict[str, Any]] = []
    for i, raw_tp in enumerate(raw_tps):
        tp = _round_price(raw_tp)
        if tp is None:
            continue
        frac = _float_or_none(raw_fracs[i]) if i < len(raw_fracs) else None
        hit = bool(raw_hits[i]) if i < len(raw_hits) else False
        targets.append(
            {
                "index": i + 1,
                "price": tp,
                "frac": round(frac, 6) if frac is not None else None,
                "hit": hit,
                "status": "hit" if hit else "pending",
            }
        )

    trail_mult = float(getattr(tr, "trail_mult", 0.0) or 0.0)
    be_trigger_rr = float(getattr(tr, "be_trigger_rr", 0.0) or 0.0)
    time_stop_sec = int(getattr(tr, "time_stop_sec", 0) or 0)
    return {
        "enabled": runner_enabled,
        "targets": targets,
        "initial_qty": _float_or_none(getattr(tr, "initial_qty", None)),
        "remaining_qty": _float_or_none(getattr(tr, "remaining_qty", None)),
        "breakeven": {
            "enabled": be_trigger_rr > 0.0,
            "trigger_rr": round(be_trigger_rr, 6),
            "lock_rr": round(float(getattr(tr, "be_lock_rr", 0.0) or 0.0), 6),
            "armed": bool(getattr(tr, "be_armed", False)),
        },
        "trailing": {
            "enabled": trail_mult > 0.0,
            "atr_mult": round(trail_mult, 6),
            "atr_period": int(getattr(tr, "trail_period", 14) or 14),
            "activate_rr": round(float(getattr(tr, "trail_activate_rr", 0.0) or 0.0), 6),
            "armed": bool(getattr(tr, "trail_armed", False)),
        },
        "time_stop_sec": time_stop_sec,
        "time_stop_enabled": time_stop_sec > 0,
    }


def build_live_position_row(*, exchange: str, symbol: str, tr: Any, current: float) -> dict[str, Any]:
    """Build the stable runtime/live_positions.json row used by web + AI."""
    entry = float(getattr(tr, "avg", None) or getattr(tr, "entry_price", 0.0) or 0.0)
    side = str(getattr(tr, "side", "") or "")
    qty = float(getattr(tr, "qty", 0.0) or 0.0)
    sl = _round_price(getattr(tr, "sl_price", None))
    exchange_tp = _round_price(getattr(tr, "tp_price", None))
    strategy = str(getattr(tr, "strategy", "") or "")
    entry_ts = int(getattr(tr, "entry_ts", 0) or 0)

    if entry > 0 and current > 0:
        pct = (current - entry) / entry * 100.0
        if side.lower() == "sell":
            pct = -pct
        upnl = pct * entry * qty / 100.0 if qty > 0 else 0.0
    else:
        pct = 0.0
        upnl = 0.0

    runner = runner_exit_snapshot(tr)
    if runner["enabled"]:
        tp_model = "runner_ladder"
    elif exchange_tp:
        tp_model = "exchange_tp"
    else:
        tp_model = "none"

    return {
        "symbol": symbol,
        "exchange": exchange,
        "side": side,
        "strategy": strategy,
        "entry": round(entry, 6),
        "current": round(float(current), 6),
        "qty": qty,
        # Backward-compatible field: exchange TP only.
        "tp": exchange_tp,
        "sl": sl,
        "upnl_pct": round(pct, 3),
        "upnl_usd": round(upnl, 4),
        "entry_ts": entry_ts,
        "tp_model": tp_model,
        "exchange_tp": exchange_tp,
        "exchange_sl": sl,
        "runner": runner,
    }
