"""
bot/runner_state.py — shared live-runner state hydration for TradeState.
"""
from __future__ import annotations

from typing import Any

from trade_state import TradeState


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
