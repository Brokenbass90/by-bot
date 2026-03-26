"""
bot/diagnostics.py — Runtime diagnostic counters and helpers.

Extracted from smart_pump_reversal_bot.py (lines ~74-138, 172-210).
RUNTIME_COUNTER is a module-level singleton Counter — all importers share it.
MSG_COUNTER is a module-level dict — same pattern.

Note: _ws_health_from_delta and _fmt_ratio_or_inf are NOT extracted here
because they depend on WS_HEALTH_* env constants defined in the main file
after load_dotenv(). They remain in smart_pump_reversal_bot.py for now (Phase 2).
"""
from __future__ import annotations

import collections
import os

# ─── Shared counters (module-level singletons) ──────────────────────────────
RUNTIME_DIAG_ENABLE: bool = os.getenv("RUNTIME_DIAG_ENABLE", "1").strip().lower() in (
    "1", "true", "yes", "on"
)
RUNTIME_COUNTER = collections.Counter()
MSG_COUNTER: dict = {"Bybit": 0, "Binance": 0}


# ─── Increment / read ────────────────────────────────────────────────────────

def _diag_inc(key: str, n: int = 1) -> None:
    if not RUNTIME_DIAG_ENABLE:
        return
    try:
        RUNTIME_COUNTER[str(key)] += int(n)
    except Exception:
        pass


def _diag_get_int(key: str) -> int:
    try:
        return int(RUNTIME_COUNTER.get(key, 0))
    except Exception:
        return 0


def _diag_reset() -> None:
    """Clear all counters (useful for tests or periodic resets)."""
    RUNTIME_COUNTER.clear()


# ─── Snapshot ────────────────────────────────────────────────────────────────

def _runtime_diag_snapshot() -> str:
    """Return a compact string of key counters for Telegram/logging."""
    if not RUNTIME_DIAG_ENABLE:
        return "diag=off"
    keys = [
        "ws_connect", "ws_disconnect", "ws_handshake_timeout",
        "ws_disconnect_timeout", "ws_disconnect_invalid_status",
        "ws_disconnect_closed", "ws_disconnect_oserror", "ws_disconnect_other",
        "breakout_try", "breakout_no_signal", "breakout_entry",
        "breakout_skip_liq", "breakout_skip_pullback",
        "breakout_skip_quality", "breakout_skip_minqty", "breakout_skip_news",
        "breakout_ns_no_break", "breakout_ns_regime", "breakout_ns_retest",
        "breakout_ns_hold", "breakout_ns_dist", "breakout_ns_impulse",
        "breakout_ns_impulse_weak", "breakout_ns_impulse_body",
        "breakout_ns_impulse_vol",
        "breakout_ns_impulse_q1", "breakout_ns_impulse_q2",
        "breakout_ns_impulse_q3", "breakout_ns_impulse_q4",
        "breakout_ns_entry_timing",
        "breakout_ns_invalid_risk", "breakout_ns_history",
        "breakout_ns_symbol", "breakout_ns_stop", "breakout_ns_atr",
        "breakout_ns_range", "breakout_ns_post", "breakout_ns_other",
        "midterm_try", "midterm_no_signal", "midterm_entry",
        "midterm_skip_minqty",
        "sloped_try", "sloped_entry",
        "flat_try", "flat_entry",
        "breakdown_try", "breakdown_entry",
        "ts132_try", "ts132_entry",
    ]
    parts = [f"{k}={int(RUNTIME_COUNTER.get(k, 0))}" for k in keys]
    return "diag " + " ".join(parts)


# ─── Breakout no-signal reason → diag key ────────────────────────────────────

def _breakout_no_signal_diag_key(reason: str) -> str:
    """Map a no-signal reason string to a diagnostic counter key."""
    r = str(reason or "").strip().lower()
    if not r:
        return "breakout_ns_other"
    if "symbol_not_allowed" in r or "symbol_denied" in r:
        return "breakout_ns_symbol"
    if "entry_timing_guard" in r:
        return "breakout_ns_entry_timing"
    if "invalid_risk" in r:
        return "breakout_ns_invalid_risk"
    if "atr_zero" in r:
        return "breakout_ns_atr"
    if "range_too_wide" in r:
        return "breakout_ns_range"
    if "post_filters_block" in r:
        return "breakout_ns_post"
    if "stop_too_tight" in r or "stop_too_wide" in r:
        return "breakout_ns_stop"
    if "history_short" in r or "ltf_short" in r or "ltf_tail_short" in r:
        return "breakout_ns_history"
    if "no_breakout_side" in r:
        return "breakout_ns_no_break"
    if "regime_block" in r:
        return "breakout_ns_regime"
    if "no_retest_touch" in r:
        return "breakout_ns_retest"
    if "no_reclaim_hold" in r:
        return "breakout_ns_hold"
    if "too_far" in r:
        return "breakout_ns_dist"
    if "impulse_body_weak" in r:
        return "breakout_ns_impulse_body"
    if "impulse_vol_weak" in r:
        return "breakout_ns_impulse_vol"
    if "impulse_weak" in r:
        return "breakout_ns_impulse_weak"
    if "impulse" in r:
        return "breakout_ns_impulse"
    return "breakout_ns_other"
