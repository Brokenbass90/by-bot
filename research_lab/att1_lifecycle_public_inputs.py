"""Pure causal ATT1 public-H1 input adapter."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Mapping, Sequence

from bot.att1_ets2s_signal_shadow_contract import PROFILE_FIXED51_CONFIG_HASHES
from bot.public_h1_cache_store import H1_MS, validate_closed_h1_rows, CanonicalCachedFeed
from bot.sbr1_universe import FIXED51_UNIVERSE
from research_lab.att1_ets2s_signal_shadow_parity import ATT1_PROFILE, _resolved_config_hash, frozen_profile_env
from research_lab.att1_lifecycle_profile import ProfileViolation, _decimal_text, validate_profile
from strategies.att1_live import ATT1LiveEngine


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _clock(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProfileViolation(f"invalid_integer:{name}")
    return value


def _text(value: object, name: str) -> str:
    try:
        return _decimal_text(Fraction(str(value)))
    except (ValueError, ZeroDivisionError, ProfileViolation) as exc:
        raise ProfileViolation(f"invalid_decimal:{name}") from exc


def signal_from_rows(symbol: str, rows: Sequence[Sequence[object]], profile: Mapping, *, source_available_ms: int, clock_ms: int) -> dict | None:
    """Causally replay the final 48 ATT1 H1 decisions without I/O or ETS2S work."""
    validate_profile(profile)
    source_available = _clock(source_available_ms, "source_available_ms")
    read_clock = clock_ms if callable(clock_ms) else lambda: clock_ms
    ready = _clock(read_clock(), "clock_ms")
    if ready < source_available or ready - source_available > profile["execution"]["max_signal_age_ms"]:
        raise ProfileViolation("public_source_stale_or_future")
    if not isinstance(symbol, str) or symbol not in FIXED51_UNIVERSE:
        raise ProfileViolation("signal_symbol")
    normalized = validate_closed_h1_rows(rows, source_available, min_bars=2160)
    data_sha = hashlib.sha256(_canonical(normalized)).hexdigest()
    feed = CanonicalCachedFeed(symbol, normalized)
    with frozen_profile_env(ATT1_PROFILE, FIXED51_UNIVERSE):
        engine = ATT1LiveEngine(feed)
        if _resolved_config_hash(ATT1_PROFILE, engine._get_strategy(symbol), FIXED51_UNIVERSE) != PROFILE_FIXED51_CONFIG_HASHES["ATT1"]:
            raise ProfileViolation("pinned_resolved_config_drift")
        signal = None
        for index in range(len(normalized) - 48, len(normalized)):
            feed.set_closed_prefix(index + 1)
            row = normalized[index]
            signal = engine.signal(symbol, *row, observed_at_ms=int(row[0]) + H1_MS)
    ready = _clock(read_clock(), "clock_ms")
    if ready < source_available or ready - (int(normalized[-1][0]) + H1_MS) > profile["execution"]["max_signal_age_ms"]:
        raise ProfileViolation("public_source_stale_or_future")
    if signal is None:
        return None
    latest_close = int(normalized[-1][0]) + H1_MS
    base = {
        "schema_id": "att1_lifecycle_signal_v1", "symbol": symbol, "side": str(signal.side),
        "stream": "EXECUTION_FORWARD", "bar_close_ms": latest_close,
        "source_available_ms": source_available, "signal_ready_ms": ready,
        "entry": _text(signal.entry, "entry"), "sl": _text(signal.sl, "sl"),
        "tps": [_text(value, "tps") for value in signal.tps],
        "tp_fracs": [_text(value, "tp_fracs") for value in signal.tp_fracs],
        "be_trigger_rr": profile["strategy"]["be_trigger_rr"], "be_lock_rr": profile["strategy"]["be_lock_rr"],
        "trailing_atr_mult": profile["strategy"]["trailing_atr_mult"], "trailing_atr_period": profile["strategy"]["trailing_atr_period"],
        "trail_activate_rr": profile["strategy"]["trail_activate_rr"], "time_stop_bars_5m": profile["strategy"]["time_stop_bars_5m"],
        "data_sha256": data_sha, "profile_sha256": profile["profile_sha256"],
    }
    base["source_sha256"] = hashlib.sha256(_canonical(base)).hexdigest()
    return base
