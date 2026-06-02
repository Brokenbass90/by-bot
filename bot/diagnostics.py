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

DIAG_KEYS = [
    "ws_connect", "ws_disconnect", "ws_handshake_timeout",
    "ws_disconnect_timeout", "ws_disconnect_invalid_status",
    "ws_disconnect_closed", "ws_disconnect_oserror", "ws_disconnect_other",
    "detect_call", "detect_skip_same_second", "detect_skip_no_window",
    "detect_gate_on", "detect_gate_off", "detect_sched_seen",
    "breakout_try", "breakout_no_signal", "breakout_entry",
    "breakout_skip_liq", "breakout_skip_pullback",
    "breakout_skip_quality", "breakout_skip_minqty", "breakout_skip_news",
    "breakout_skip_symbol_lock",
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
    "midterm_try", "midterm_no_signal", "midterm_signal", "midterm_entry",
    "midterm_skip_rounding", "midterm_skip_notional_small",
    "midterm_skip_minqty", "midterm_skip_open_risk",
    "midterm_skip_reserve", "midterm_skip_submit", "midterm_skip_symbol_lock",
    "midterm_ns_blank", "midterm_ns_symbol", "midterm_ns_history",
    "midterm_ns_first_bar", "midterm_ns_same_bar", "midterm_ns_atr",
    "midterm_ns_macro", "midterm_ns_trend", "midterm_ns_rsi",
    "midterm_ns_zone_far", "midterm_ns_zone_close",
    "midterm_ns_volume", "midterm_ns_trigger_absent",
    "midterm_ns_trigger_invalid", "midterm_ns_risk",
    "midterm_ns_limit", "midterm_ns_direction",
    "midterm_ns_unknown", "midterm_ns_other",
    "sloped_sched", "sloped_try", "sloped_signal", "sloped_entry",
    "sloped_no_signal", "sloped_signal_error",
    "sloped_skip_no_engine", "sloped_skip_trade_off",
    "sloped_skip_no_client", "sloped_skip_open_trade",
    "sloped_skip_max_open", "sloped_skip_portfolio",
    "sloped_skip_disabled", "sloped_skip_max_positions",
    "sloped_skip_overlap", "sloped_skip_global_risk",
    "sloped_skip_portfolio_other",
    "sloped_skip_cooldown", "sloped_skip_symbol_lock",
    "sloped_skip_rounding", "sloped_skip_notional_small",
    "sloped_skip_minqty", "sloped_skip_open_risk",
    "sloped_skip_reserve", "sloped_skip_submit",
    "sloped_ns_blank", "sloped_ns_symbol", "sloped_ns_cooldown",
    "sloped_ns_history", "sloped_ns_same_bar", "sloped_ns_confirm",
    "sloped_ns_atr", "sloped_ns_channel", "sloped_ns_slope",
    "sloped_ns_r2", "sloped_ns_body", "sloped_ns_touch",
    "sloped_ns_reclaim", "sloped_ns_reject", "sloped_ns_rsi",
    "sloped_ns_direction", "sloped_ns_short_filter",
    "sloped_ns_risk", "sloped_ns_unknown", "sloped_ns_other",
    "att1_sched", "att1_try", "att1_signal", "att1_entry",
    "att1_no_signal", "att1_skip_no_engine", "att1_skip_trade_off",
    "att1_skip_no_client", "att1_skip_open_trade",
    "att1_skip_max_open", "att1_skip_portfolio",
    "att1_skip_disabled", "att1_skip_max_positions",
    "att1_skip_overlap", "att1_skip_global_risk",
    "att1_skip_portfolio_other",
    "att1_skip_cooldown", "att1_skip_symbol_lock",
    "att1_skip_rounding", "att1_skip_notional_small",
    "att1_skip_minqty", "att1_skip_open_risk",
    "att1_skip_reserve", "att1_skip_submit",
    "att1_ns_symbol", "att1_ns_cooldown", "att1_ns_history",
    "att1_ns_first_bar", "att1_ns_same_bar", "att1_ns_trendline", "att1_ns_touch",
    "att1_ns_reject", "att1_ns_body", "att1_ns_rsi",
    "att1_ns_atr", "att1_ns_risk", "att1_ns_blank",
    "att1_ns_unknown", "att1_ns_other",
    "asm1_sched", "asm1_try", "asm1_signal", "asm1_entry",
    "asm1_no_signal", "asm1_skip_no_engine", "asm1_skip_trade_off",
    "asm1_skip_no_client", "asm1_skip_open_trade",
    "asm1_skip_max_open", "asm1_skip_portfolio",
    "asm1_skip_disabled", "asm1_skip_max_positions",
    "asm1_skip_overlap", "asm1_skip_global_risk",
    "asm1_skip_portfolio_other",
    "asm1_skip_cooldown", "asm1_skip_symbol_lock",
    "asm1_skip_rounding", "asm1_skip_notional_small",
    "asm1_skip_minqty", "asm1_skip_open_risk",
    "asm1_skip_reserve", "asm1_skip_submit",
    "asm1_ns_symbol", "asm1_ns_cooldown", "asm1_ns_history",
    "asm1_ns_first_bar", "asm1_ns_same_bar", "asm1_ns_atr", "asm1_ns_er",
    "asm1_ns_channel", "asm1_ns_breakout", "asm1_ns_body",
    "asm1_ns_volume", "asm1_ns_trend", "asm1_ns_risk",
    "asm1_ns_blank", "asm1_ns_unknown", "asm1_ns_other",
    "flat_sched", "flat_try", "flat_signal", "flat_entry",
    "flat_no_signal",
    "flat_skip_no_engine", "flat_skip_trade_off",
    "flat_skip_no_client", "flat_skip_open_trade",
    "flat_skip_max_open", "flat_skip_portfolio",
    "flat_skip_disabled", "flat_skip_max_positions",
    "flat_skip_overlap", "flat_skip_global_risk",
    "flat_skip_portfolio_other",
    "flat_skip_cooldown", "flat_skip_symbol_lock",
    "flat_skip_rounding", "flat_skip_notional_small",
    "flat_skip_minqty", "flat_skip_open_risk",
    "flat_skip_reserve", "flat_skip_submit",
    "flat_ns_symbol", "flat_ns_cooldown", "flat_ns_regime",
    "flat_ns_history", "flat_ns_same_bar", "flat_ns_range",
    "flat_ns_touch", "flat_ns_reject", "flat_ns_body",
    "flat_ns_dist", "flat_ns_rsi", "flat_ns_ema",
    "flat_ns_risk", "flat_ns_blank", "flat_ns_unknown", "flat_ns_other",
    "breakdown_sched", "breakdown_try", "breakdown_signal", "breakdown_entry",
    "breakdown_skip_no_engine", "breakdown_skip_trade_off",
    "breakdown_skip_no_client", "breakdown_skip_open_trade",
    "breakdown_skip_max_open", "breakdown_skip_portfolio",
    "breakdown_skip_disabled", "breakdown_skip_max_positions",
    "breakdown_skip_overlap", "breakdown_skip_global_risk",
    "breakdown_skip_portfolio_other",
    "breakdown_skip_cooldown", "breakdown_skip_symbol_lock",
    "breakdown_skip_direction_cap", "breakdown_skip_breaker",
    "breakdown_skip_rounding", "breakdown_skip_notional_small",
    "breakdown_skip_minqty", "breakdown_skip_open_risk",
    "breakdown_skip_reserve", "breakdown_skip_submit",
    "breakdown_no_signal", "breakdown_ns_symbol", "breakdown_ns_cooldown",
    "breakdown_ns_history", "breakdown_ns_same_bar", "breakdown_ns_structure_idle", "breakdown_ns_regime",
    "breakdown_ns_rsi", "breakdown_ns_support", "breakdown_ns_impulse",
    "breakdown_ns_dist", "breakdown_ns_flat", "breakdown_ns_reclaim",
    "breakdown_ns_entry_timing", "breakdown_ns_entry_confirm",
    "breakdown_ns_risk", "breakdown_ns_blank", "breakdown_ns_unknown",
    "breakdown_ns_other",
    "ivb1_sched", "ivb1_try", "ivb1_no_signal", "ivb1_entry",
    "ivb1_skip_max_open", "ivb1_skip_portfolio", "ivb1_skip_symbol_lock",
    "ivb1_skip_disabled", "ivb1_skip_max_positions",
    "ivb1_skip_overlap", "ivb1_skip_global_risk",
    "ivb1_skip_portfolio_other",
    "ivb1_ns_history", "ivb1_ns_regime", "ivb1_ns_cooldown",
    "ivb1_ns_atr", "ivb1_ns_volume", "ivb1_ns_no_breakout",
    "ivb1_ns_impulse_small",
    "ivb1_ns_impulse_vol", "ivb1_ns_impulse_body", "ivb1_ns_impulse_range",
    "ivb1_ns_armed", "ivb1_ns_retrace_wait", "ivb1_ns_retrace_expired",
    "ivb1_ns_lost_level", "ivb1_ns_stop", "ivb1_ns_other",
    "elder_sched", "elder_try", "elder_no_signal", "elder_entry",
    "elder_skip_max_open", "elder_skip_portfolio", "elder_skip_symbol_lock",
    "elder_skip_disabled", "elder_skip_max_positions",
    "elder_skip_overlap", "elder_skip_global_risk",
    "elder_skip_portfolio_other",
    "elder_ns_history", "elder_ns_limit", "elder_ns_trend",
    "elder_ns_wave", "elder_ns_entry", "elder_ns_atr", "elder_ns_other",
    "brc1_sched", "brc1_try", "brc1_no_signal", "brc1_signal",
    "brc1_shadow_signal", "brc1_entry",
    "brc1_skip_max_open", "brc1_skip_portfolio",
    "brc1_skip_disabled", "brc1_skip_max_positions",
    "brc1_skip_overlap", "brc1_skip_global_risk",
    "brc1_skip_portfolio_other",
    "brc1_skip_direction_cap", "brc1_skip_symbol_lock",
    "brc1_ns_regime_not_bear", "brc1_ns_symbol_blocked",
    "brc1_ns_not_enough_bars", "brc1_ns_cooldown",
    "brc1_ns_htf_not_downtrend", "brc1_ns_5m_not_downtrend",
    "brc1_ns_no_pullback", "brc1_ns_rsi_out_of_zone",
    "brc1_ns_no_rejection_wick", "brc1_ns_volume_too_high",
    "brc1_ns_other",
    "ts132_try", "ts132_entry",
]


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

def _runtime_diag_snapshot(*, include_zero: bool = False, max_items: int = 40) -> str:
    """Return a compact string of key counters for Telegram/logging.

    By default this hides zero-valued counters so restart-fresh reports do not
    masquerade as "24h" operational truth. Pass include_zero=True for full dumps.
    """
    if not RUNTIME_DIAG_ENABLE:
        return "diag=off"
    parts = []
    for key in DIAG_KEYS:
        val = int(RUNTIME_COUNTER.get(key, 0))
        if include_zero or val != 0:
            parts.append(f"{key}={val}")
    if not parts:
        return "diag idle"
    if max_items > 0 and len(parts) > max_items:
        extra = len(parts) - max_items
        return "diag " + " ".join(parts[:max_items]) + f" ...(+{extra} more)"
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


def _ivb1_no_signal_diag_key(reason: str) -> str:
    """Map IVB1 no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "ivb1_ns_other"
    if "history_short" in r or "not_enough_5m_bars" in r:
        return "ivb1_ns_history"
    if "bar_not_bullish" in r:
        return "ivb1_ns_impulse_body"
    if "no_breakout" in r:
        return "ivb1_ns_no_breakout"
    if "regime_" in r:
        return "ivb1_ns_regime"
    if "cooldown" in r:
        return "ivb1_ns_cooldown"
    if "atr_invalid" in r:
        return "ivb1_ns_atr"
    if "volume_baseline_invalid" in r:
        return "ivb1_ns_volume"
    if "impulse_too_small" in r:
        return "ivb1_ns_impulse_small"
    if "impulse_vol_weak" in r:
        return "ivb1_ns_impulse_vol"
    if "impulse_body_weak" in r:
        return "ivb1_ns_impulse_body"
    if "impulse_range_weak" in r:
        return "ivb1_ns_impulse_range"
    if "armed_impulse_breakout" in r:
        return "ivb1_ns_armed"
    if "armed_waiting_retrace" in r:
        return "ivb1_ns_retrace_wait"
    if "armed_expired" in r:
        return "ivb1_ns_retrace_expired"
    if "armed_lost_breakout_level" in r:
        return "ivb1_ns_lost_level"
    if "stop_too_" in r or "sl_at_or_above_entry" in r:
        return "ivb1_ns_stop"
    return "ivb1_ns_other"


def _flat_no_signal_diag_key(reason: str) -> str:
    """Map flat sleeve no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "flat_ns_blank"
    if "symbol_" in r:
        return "flat_ns_symbol"
    if "cooldown" in r:
        return "flat_ns_cooldown"
    if "regime_" in r:
        return "flat_ns_regime"
    if "history_short" in r or "signal_invalid" in r:
        return "flat_ns_history"
    if "first_signal_bar" in r or "same_signal_bar" in r:
        return "flat_ns_same_bar"
    if "range_too_" in r:
        return "flat_ns_range"
    if "no_res_touch" in r:
        return "flat_ns_touch"
    if "no_reject_back" in r:
        return "flat_ns_reject"
    if "body_weak" in r:
        return "flat_ns_body"
    if "dist_too_far" in r:
        return "flat_ns_dist"
    if "rsi_too_low" in r:
        return "flat_ns_rsi"
    if "ema_extension" in r:
        return "flat_ns_ema"
    if "sl_below_entry" in r or "tp_above_entry" in r or "signal_invalid_post" in r:
        return "flat_ns_risk"
    return "flat_ns_unknown"


def _sloped_no_signal_diag_key(reason: str) -> str:
    """Map sloped-channel no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "sloped_ns_blank"
    if "symbol_" in r:
        return "sloped_ns_symbol"
    if "cooldown" in r:
        return "sloped_ns_cooldown"
    if "history" in r:
        return "sloped_ns_history"
    if "first_signal_bar" in r or "same_signal_bar" in r:
        return "sloped_ns_same_bar"
    if "pending_" in r:
        return "sloped_ns_confirm"
    if "atr" in r or "rsi_invalid" in r:
        return "sloped_ns_atr"
    if "channel" in r or "regression" in r:
        return "sloped_ns_channel"
    if "slope" in r:
        return "sloped_ns_slope"
    if "r2" in r:
        return "sloped_ns_r2"
    if "body_weak" in r:
        return "sloped_ns_body"
    if "no_channel_touch" in r or "touch" in r:
        return "sloped_ns_touch"
    if "reclaim" in r:
        return "sloped_ns_reclaim"
    if "reject" in r:
        return "sloped_ns_reject"
    if "rsi" in r:
        return "sloped_ns_rsi"
    if "direction" in r or "disabled" in r or "bias" in r:
        return "sloped_ns_direction"
    if "short_" in r:
        return "sloped_ns_short_filter"
    if "invalid_post" in r or "risk" in r:
        return "sloped_ns_risk"
    if "no_setup" in r:
        return "sloped_ns_other"
    return "sloped_ns_unknown"


def _att1_no_signal_diag_key(reason: str) -> str:
    """Map ATT1 no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "att1_ns_blank"
    if "symbol_" in r:
        return "att1_ns_symbol"
    if "cooldown" in r:
        return "att1_ns_cooldown"
    if "history" in r:
        return "att1_ns_history"
    if "first_signal_bar" in r:
        return "att1_ns_first_bar"
    if "same_signal_bar" in r:
        return "att1_ns_same_bar"
    if "atr" in r or "rsi_invalid" in r or "price_invalid" in r:
        return "att1_ns_atr"
    if "pivot" in r or "line_invalid" in r or "slope" in r or "r2" in r:
        return "att1_ns_trendline"
    if "no_touch" in r:
        return "att1_ns_touch"
    if "no_reject" in r or "candle_not_" in r:
        return "att1_ns_reject"
    if "body_weak" in r:
        return "att1_ns_body"
    if "rsi_too" in r:
        return "att1_ns_rsi"
    if "invalid_risk" in r:
        return "att1_ns_risk"
    if "no_setup" in r:
        return "att1_ns_other"
    return "att1_ns_unknown"


def _asm1_no_signal_diag_key(reason: str) -> str:
    """Map ASM1 no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "asm1_ns_blank"
    if "symbol_" in r:
        return "asm1_ns_symbol"
    if "cooldown" in r:
        return "asm1_ns_cooldown"
    if "history" in r:
        return "asm1_ns_history"
    if "first_signal_bar" in r:
        return "asm1_ns_first_bar"
    if "same_signal_bar" in r:
        return "asm1_ns_same_bar"
    if "atr" in r or "price_invalid" in r:
        return "asm1_ns_atr"
    if "er_gate" in r:
        return "asm1_ns_er"
    if "channel" in r or "regression" in r or "r2" in r:
        return "asm1_ns_channel"
    if "no_breakout" in r or "not_inside" in r:
        return "asm1_ns_breakout"
    if "body_weak" in r or "candle_not_" in r:
        return "asm1_ns_body"
    if "volume" in r:
        return "asm1_ns_volume"
    if "trend_filter" in r:
        return "asm1_ns_trend"
    if "invalid_risk" in r:
        return "asm1_ns_risk"
    if "no_setup" in r:
        return "asm1_ns_other"
    return "asm1_ns_unknown"


def _midterm_no_signal_diag_key(reason: str) -> str:
    """Map midterm no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "midterm_ns_blank"
    if "symbol_" in r:
        return "midterm_ns_symbol"
    if "history" in r or "insufficient" in r or "not_enough" in r:
        return "midterm_ns_history"
    if "first_signal_bar" in r:
        return "midterm_ns_first_bar"
    if "same_signal_bar" in r:
        return "midterm_ns_same_bar"
    if "atr" in r or "ema_invalid" in r:
        return "midterm_ns_atr"
    if "macro" in r or "macd" in r:
        return "midterm_ns_macro"
    if "trend" in r or "weekly" in r or "bias" in r:
        return "midterm_ns_trend"
    if "rsi" in r:
        return "midterm_ns_rsi"
    if "zone_too_far" in r or "pullback_too_deep" in r:
        return "midterm_ns_zone_far"
    if "zone_too_close" in r or "no_fresh_touch" in r or "no_recent_touch" in r:
        return "midterm_ns_zone_close"
    if "volume" in r or "vol_" in r:
        return "midterm_ns_volume"
    if "trigger_absent" in r or "reclaim_absent" in r:
        return "midterm_ns_trigger_absent"
    if "trigger_invalid" in r:
        return "midterm_ns_trigger_invalid"
    if "invalid_risk" in r or "sl_" in r or "tp_" in r:
        return "midterm_ns_risk"
    if "day_cap" in r or "cooldown" in r:
        return "midterm_ns_limit"
    if "direction" in r or "disabled" in r:
        return "midterm_ns_direction"
    if "no_setup" in r:
        return "midterm_ns_other"
    return "midterm_ns_unknown"


def _breakdown_no_signal_diag_key(reason: str) -> str:
    """Map breakdown sleeve no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "breakdown_ns_blank"
    if "symbol_" in r:
        return "breakdown_ns_symbol"
    if "cooldown" in r:
        return "breakdown_ns_cooldown"
    if "history" in r or "invalid" in r and ("structure" in r or "entry" in r):
        return "breakdown_ns_history"
    # 2026-06-02: split overloaded same_bar bucket.
    # `structure_unchanged` is the normal "same setup re-evaluated each bar" state
    # and dominated the bucket (~89% of live no_signal). Bucket it separately so
    # the real same-bar guard and the routine idle state are visible.
    if "structure_unchanged" in r:
        return "breakdown_ns_structure_idle"
    if "same_" in r:
        return "breakdown_ns_same_bar"
    if "regime_" in r:
        return "breakdown_ns_regime"
    if "rsi_too_high" in r:
        return "breakdown_ns_rsi"
    if "no_real_break" in r:
        return "breakdown_ns_support"
    if "weak_break_body" in r:
        return "breakdown_ns_impulse"
    if "break_too_" in r or "too_extended" in r:
        return "breakdown_ns_dist"
    if "flat_after_break" in r:
        return "breakdown_ns_flat"
    if "reclaim_invalidated" in r:
        return "breakdown_ns_reclaim"
    if "stale_break" in r or "setup_timeout" in r or "entry_too_late" in r:
        return "breakdown_ns_entry_timing"
    if "entry_not_confirmed" in r:
        return "breakdown_ns_entry_confirm"
    if "sl_invalid" in r or "tp_invalid" in r:
        return "breakdown_ns_risk"
    if "armed_breakdown" in r:
        return "breakdown_ns_other"
    return "breakdown_ns_unknown"


def _elder_no_signal_diag_key(reason: str) -> str:
    """Map Elder no-signal reasons to grouped diagnostic keys."""
    r = str(reason or "").strip().lower()
    if not r:
        return "elder_ns_other"
    if "not_enough_entry_bars" in r:
        return "elder_ns_history"
    if "max_signals_per_day" in r or "cooldown" in r:
        return "elder_ns_limit"
    if "screen1" in r:
        return "elder_ns_trend"
    if "screen2" in r:
        return "elder_ns_wave"
    if "screen3" in r:
        return "elder_ns_entry"
    if "atr_invalid" in r:
        return "elder_ns_atr"
    return "elder_ns_other"
