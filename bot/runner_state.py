"""
bot/runner_state.py — shared live-runner state hydration for TradeState.
"""
from __future__ import annotations

from typing import Any

from trade_state import TradeState


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_list(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[float] = []
    for item in value:
        num = _float_or_none(item)
        if num is not None:
            out.append(float(num))
    return out


def _bool_list(value: Any) -> list[bool]:
    if not isinstance(value, (list, tuple)):
        return []
    return [bool(x) for x in value]


def apply_runner_state(
    tr: TradeState,
    sig: Any,
    qty: float,
    *,
    use_runner: bool,
) -> bool:
    """Populate shared runner fields from a signal.

    Returns True when the trade should be managed by the live runner.
    """
    tr.runner_enabled = False
    tr.tps = []
    tr.tp_fracs = []
    tr.tp_hit = []
    tr.initial_qty = 0.0
    tr.remaining_qty = 0.0
    tr.initial_sl_price = (
        float(getattr(tr, "sl_price", 0.0) or 0.0)
        if getattr(tr, "sl_price", None) is not None
        else None
    )
    tr.be_trigger_rr = float(getattr(sig, "be_trigger_rr", 0.0) or 0.0)
    tr.be_lock_rr = float(getattr(sig, "be_lock_rr", 0.0) or 0.0)
    tr.trail_activate_rr = float(getattr(sig, "trail_activate_rr", 0.0) or 0.0)
    tr.trail_armed = tr.trail_activate_rr <= 0.0
    tr.trail_mult = float(getattr(sig, "trailing_atr_mult", 0.0) or 0.0)
    tr.trail_period = int(getattr(sig, "trailing_atr_period", 14) or 14)
    tr.time_stop_sec = int(int(getattr(sig, "time_stop_bars", 0) or 0) * 300)

    partial_runner = False
    if use_runner:
        targets = [float(x) for x in (getattr(sig, "tps", None) or []) if x is not None]
        fracs = [float(x) for x in (getattr(sig, "tp_fracs", None) or []) if x is not None]
        if targets:
            if not fracs:
                frac = 1.0 / float(len(targets))
                fracs = [frac for _ in targets]
            if len(fracs) == len(targets):
                total = sum(max(0.0, x) for x in fracs)
                if total > 0:
                    if total > 1.0 + 1e-9:
                        scale = 1.0 / total
                        fracs = [x * scale for x in fracs]
                    tr.tps = targets
                    tr.tp_fracs = fracs
                    tr.tp_hit = [False for _ in targets]
                    partial_runner = True

    dynamic_runner = bool(
        tr.be_trigger_rr > 0.0
        or tr.trail_mult > 0.0
        or tr.time_stop_sec > 0
    )
    if not partial_runner and not dynamic_runner:
        return False

    tr.runner_enabled = True
    tr.initial_qty = float(qty)
    tr.remaining_qty = float(qty)
    return True


def sync_runner_qty_after_fill(tr: TradeState, actual_qty: float) -> bool:
    """Align runner quantities with the exchange-confirmed filled position size.

    Entries can be rounded or filled at a different size than the submitted
    quantity. Runner ladders must manage the real open size, not the request
    size, otherwise partial exits/time stops can leave residual exposure.
    """
    if not bool(getattr(tr, "runner_enabled", False)):
        return False
    qty = float(actual_qty or 0.0)
    if qty <= 0.0:
        return False

    hits = list(getattr(tr, "tp_hit", None) or [])
    if any(bool(x) for x in hits):
        return False

    old_initial = float(getattr(tr, "initial_qty", 0.0) or 0.0)
    old_remaining = float(getattr(tr, "remaining_qty", 0.0) or 0.0)
    if abs(old_initial - qty) <= 1e-12 and abs(old_remaining - qty) <= 1e-12:
        return False

    tr.initial_qty = qty
    tr.remaining_qty = qty
    return True


def runner_snapshot_from_trade(tr: TradeState) -> dict[str, Any]:
    """Serialize live runner fields for durable event logs.

    Exchange TP is intentionally empty for runner-managed positions, so these
    fields are the only durable source of the TP ladder, breakeven and trailing
    state across process restarts.
    """
    return {
        "runner_enabled": bool(getattr(tr, "runner_enabled", False)),
        "initial_qty": float(getattr(tr, "initial_qty", 0.0) or 0.0),
        "remaining_qty": float(getattr(tr, "remaining_qty", 0.0) or 0.0),
        "tps": [float(x) for x in (getattr(tr, "tps", None) or []) if x is not None],
        "tp_fracs": [float(x) for x in (getattr(tr, "tp_fracs", None) or []) if x is not None],
        "tp_hit": [bool(x) for x in (getattr(tr, "tp_hit", None) or [])],
        "trail_mult": float(getattr(tr, "trail_mult", 0.0) or 0.0),
        "trail_period": int(getattr(tr, "trail_period", 14) or 14),
        "trail_activate_rr": float(getattr(tr, "trail_activate_rr", 0.0) or 0.0),
        "trail_armed": bool(getattr(tr, "trail_armed", False)),
        "initial_sl_price": (
            float(getattr(tr, "initial_sl_price", 0.0) or 0.0)
            if getattr(tr, "initial_sl_price", None) is not None
            else None
        ),
        "be_trigger_rr": float(getattr(tr, "be_trigger_rr", 0.0) or 0.0),
        "be_lock_rr": float(getattr(tr, "be_lock_rr", 0.0) or 0.0),
        "be_armed": bool(getattr(tr, "be_armed", False)),
        "hh": (
            float(getattr(tr, "hh", 0.0) or 0.0)
            if getattr(tr, "hh", None) is not None
            else None
        ),
        "ll": (
            float(getattr(tr, "ll", 0.0) or 0.0)
            if getattr(tr, "ll", None) is not None
            else None
        ),
        "time_stop_sec": int(getattr(tr, "time_stop_sec", 0) or 0),
        "last_runner_action_ts": int(getattr(tr, "last_runner_action_ts", 0) or 0),
    }


def apply_runner_snapshot(
    tr: TradeState,
    snapshot: dict[str, Any] | None,
    *,
    exchange_qty: float | None = None,
) -> bool:
    """Hydrate live runner fields from a durable event snapshot.

    Returns False when the snapshot does not describe a runner. If exchange_qty
    is lower than the original runner size, infer already-hit ladder targets so
    a restart cannot close the same TP slice twice.
    """
    if not isinstance(snapshot, dict):
        return False

    tps = _float_list(snapshot.get("tps"))
    fracs = _float_list(snapshot.get("tp_fracs"))
    hits = _bool_list(snapshot.get("tp_hit"))
    if tps and not fracs:
        fracs = [1.0 / float(len(tps)) for _ in tps]
    if tps and len(fracs) != len(tps):
        return False
    hits = (hits + [False] * len(tps))[: len(tps)]

    trail_mult = float(_float_or_none(snapshot.get("trail_mult")) or 0.0)
    be_trigger_rr = float(_float_or_none(snapshot.get("be_trigger_rr")) or 0.0)
    time_stop_sec = int(_float_or_none(snapshot.get("time_stop_sec")) or 0)
    runner_enabled = bool(snapshot.get("runner_enabled"))
    if not (runner_enabled or tps or trail_mult > 0.0 or be_trigger_rr > 0.0 or time_stop_sec > 0):
        return False

    qty_live = _float_or_none(exchange_qty)
    initial_qty = _float_or_none(snapshot.get("initial_qty"))
    remaining_qty = _float_or_none(snapshot.get("remaining_qty"))
    if qty_live is not None and qty_live > 0:
        if initial_qty is None or initial_qty <= 0:
            initial_qty = max(qty_live, remaining_qty or 0.0)
        remaining_qty = qty_live
    if initial_qty is None or initial_qty <= 0:
        initial_qty = remaining_qty or float(getattr(tr, "qty", 0.0) or 0.0)
    if remaining_qty is None or remaining_qty <= 0:
        remaining_qty = qty_live or initial_qty

    if tps and initial_qty > 0 and qty_live is not None and qty_live > 0 and qty_live < initial_qty:
        closed_qty = max(0.0, initial_qty - qty_live)
        tolerance = max(1e-9, initial_qty * 0.002)
        cumulative = 0.0
        for idx, frac in enumerate(fracs):
            cumulative += max(0.0, frac) * initial_qty
            if closed_qty + tolerance >= cumulative:
                hits[idx] = True

    tr.runner_enabled = True
    tr.initial_qty = float(initial_qty or 0.0)
    tr.remaining_qty = float(remaining_qty or 0.0)
    tr.tps = tps
    tr.tp_fracs = fracs
    tr.tp_hit = hits
    tr.trail_mult = trail_mult
    tr.trail_period = int(_float_or_none(snapshot.get("trail_period")) or 14)
    tr.trail_activate_rr = float(_float_or_none(snapshot.get("trail_activate_rr")) or 0.0)
    tr.trail_armed = bool(snapshot.get("trail_armed"))
    tr.initial_sl_price = _float_or_none(snapshot.get("initial_sl_price"))
    tr.be_trigger_rr = be_trigger_rr
    tr.be_lock_rr = float(_float_or_none(snapshot.get("be_lock_rr")) or 0.0)
    tr.be_armed = bool(snapshot.get("be_armed"))
    tr.hh = _float_or_none(snapshot.get("hh"))
    tr.ll = _float_or_none(snapshot.get("ll"))
    tr.time_stop_sec = time_stop_sec
    tr.last_runner_action_ts = int(_float_or_none(snapshot.get("last_runner_action_ts")) or 0)
    return True
