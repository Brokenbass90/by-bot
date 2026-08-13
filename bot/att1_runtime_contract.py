"""Truth snapshot for the effective ATT1 strategy configuration.

The live strategy owns its parameter defaults and environment parsing.  This
module deliberately instantiates that same strategy class instead of copying
the parser into the monolith, so heartbeat parity cannot silently drift.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Any

from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy


def _strategy_source_sha256() -> str:
    source = inspect.getsourcefile(AltTrendlineTouchV1Strategy)
    if not source:
        return "unavailable"
    try:
        return hashlib.sha256(Path(source).read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def build_att1_runtime_contract(*, risk_mult: float) -> dict[str, Any]:
    """Return normalized effective ATT1 parameters and a stable SHA-256."""
    cfg = AltTrendlineTouchV1Strategy().cfg
    params: dict[str, Any] = {
        "risk_mult": round(float(risk_mult), 6),
        "allow_longs": bool(cfg.allow_longs),
        "allow_shorts": bool(cfg.allow_shorts),
        "signal_tf": str(cfg.signal_tf),
        "signal_lookback": int(cfg.signal_lookback),
        "atr_period": int(getattr(cfg, "atr_period", 14)),
        "rsi_period": int(getattr(cfg, "rsi_period", 14)),
        "pivot_left": int(cfg.pivot_left),
        "pivot_right": int(cfg.pivot_right),
        "min_pivots": int(cfg.min_pivots),
        "max_pivots_used": int(cfg.max_pivots_used),
        "max_pivot_age": int(cfg.max_pivot_age),
        "min_slope_pct": round(float(cfg.min_slope_pct), 8),
        "max_slope_pct": round(float(cfg.max_slope_pct), 8),
        "long_max_neg_slope": round(
            float(getattr(cfg, "long_max_neg_slope", 0.5)),
            8,
        ),
        "short_max_pos_slope": round(
            float(getattr(cfg, "short_max_pos_slope", 0.5)),
            8,
        ),
        "min_r2": round(float(cfg.min_r2), 6),
        "touch_atr": round(float(cfg.touch_atr), 6),
        "reject_atr": round(float(cfg.reject_atr), 6),
        "min_body_frac": round(float(cfg.min_body_frac), 6),
        "rsi_long_max": round(float(cfg.rsi_long_max), 6),
        "rsi_short_min": round(float(cfg.rsi_short_min), 6),
        # Older deployed ATT1 classes predate the optional upper RSI bound.
        # Their behavior is equivalent to an unbounded maximum, represented by
        # the newer strategy default of 100.0.  Keep telemetry compatible so a
        # truth-only deploy never forces a strategy-code upgrade.
        "rsi_short_max": round(float(getattr(cfg, "rsi_short_max", 100.0)), 6),
        "trend_guard_bars": int(getattr(cfg, "trend_guard_bars", 0)),
        "sl_atr_mult": round(float(cfg.sl_atr_mult), 6),
        "max_entry_dist_atr": round(
            float(getattr(cfg, "max_entry_dist_atr", 2.0)),
            6,
        ),
        "min_entry_dist_atr": round(
            float(getattr(cfg, "min_entry_dist_atr", 0.0)),
            6,
        ),
        "min_rr": round(float(cfg.min_rr), 6),
        "min_stop_pct": round(float(cfg.min_stop_pct), 8),
        "max_stop_pct": round(float(cfg.max_stop_pct), 8),
        "tp1_rr": round(float(cfg.tp1_rr), 6),
        "tp2_rr": round(float(cfg.tp2_rr), 6),
        "tp1_frac": round(float(cfg.tp1_frac), 6),
        "be_trigger_rr": round(float(cfg.be_trigger_rr), 6),
        "be_lock_rr": round(float(cfg.be_lock_rr), 6),
        "trail_atr_mult": round(float(cfg.trail_atr_mult), 6),
        "trail_activate_rr": round(float(cfg.trail_activate_rr), 6),
        "time_stop_bars_5m": int(cfg.time_stop_bars_5m),
        "cooldown_bars_5m": int(cfg.cooldown_bars_5m),
        "canary_expiry_utc": str(os.getenv("ATT1_CANARY_EXPIRY_UTC", "") or ""),
        "strategy_source_sha256": _strategy_source_sha256(),
    }
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "params": params,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
