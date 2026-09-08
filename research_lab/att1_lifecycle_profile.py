"""Fail-closed ATT1 lifecycle profile and causal signal admission.

The module binds the frozen ATT1 source/configuration to a synthetic research
profile.  It has no network, broker, order, runtime, or outcome dependencies.
"""
from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from bot.att1_ets2s_signal_shadow_contract import (
    PROFILE_FIXED51_CONFIG_HASHES,
    PROFILE_SOURCE_HASHES,
)
from bot.sbr1_universe import FIXED51_UNIVERSE
from research_lab.att1_ets2s_signal_shadow_parity import (
    ATT1_PROFILE,
    H1_MS,
    _resolved_config_hash,
    frozen_profile_env,
)
from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy


PROFILE_SCHEMA_ID = "att1_lifecycle_profile_v1"
PROFILE_ID = "SYNTHETIC_ATT1_LIFECYCLE_V1"
SIGNAL_SCHEMA_ID = "att1_lifecycle_signal_v1"
EXECUTION_FORWARD = "EXECUTION_FORWARD"
L1_SOURCE_PATHS = ATT1_PROFILE.source_paths
PROFILE_SOURCE_PATHS = (*L1_SOURCE_PATHS, "bot/live_native_decision_contract.py")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class ProfileViolation(ValueError):
    """Stable fail-closed error for malformed profile or admission input."""


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ProfileViolation("noncanonical_payload") from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha_text(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProfileViolation(f"invalid_sha256:{field}")
    return value


def _int(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileViolation(f"invalid_integer:{field}")
    if positive and value <= 0:
        raise ProfileViolation(f"invalid_integer:{field}")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> Fraction:
    if (not isinstance(value, str) or len(value) > 128
            or len(value.replace('.', '')) > 64
            or len(value.partition('.')[2]) > 64
            or _DECIMAL_TEXT.fullmatch(value) is None):
        raise ProfileViolation(f"invalid_decimal:{field}")
    result = Fraction(value)
    if positive and result <= 0:
        raise ProfileViolation(f"invalid_decimal:{field}")
    return result


def _decimal_text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    numerator = abs(value.numerator)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ProfileViolation("non_terminating_decimal")
    places = max(twos, fives)
    numerator *= 2 ** (places - twos) * 5 ** (places - fives)
    raw = str(numerator).rjust(places + 1, "0")
    return sign + raw[:-places] + "." + raw[-places:]


def _round_to_step(value: Fraction, step: Fraction, *, up: bool) -> Fraction:
    units, remainder = divmod(value.numerator * step.denominator, value.denominator * step.numerator)
    if up and remainder:
        units += 1
    return units * step


def _floor_to_step(value: Fraction, step: Fraction) -> Fraction:
    return (value // step) * step


def _source_rows(root: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for relative in PROFILE_SOURCE_PATHS:
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ProfileViolation(f"source_unreadable:{relative}") from exc
        rows[relative] = hashlib.sha256(data).hexdigest()
    return rows


def _l1_source_aggregate(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in L1_SOURCE_PATHS:
        try:
            data = (root / relative).read_bytes()
        except OSError as exc:
            raise ProfileViolation(f"source_unreadable:{relative}") from exc
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(data)
    return digest.hexdigest()


def _profile_without_sha(profile: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in profile.items() if key != "profile_sha256"}


def build_profile(root: Path) -> dict:
    """Build a fresh source/config receipt without reading runtime or outcomes."""

    root = Path(root)
    if _l1_source_aggregate(root) != PROFILE_SOURCE_HASHES["ATT1"]:
        raise ProfileViolation("pinned_l1_source_drift")
    source_sha256 = _source_rows(root)
    with frozen_profile_env(ATT1_PROFILE, FIXED51_UNIVERSE):
        strategy = AltTrendlineTouchV1Strategy()
        resolved_config_sha256 = _resolved_config_hash(ATT1_PROFILE, strategy, FIXED51_UNIVERSE)
        config = asdict(strategy.cfg)
    if resolved_config_sha256 != PROFILE_FIXED51_CONFIG_HASHES["ATT1"]:
        raise ProfileViolation("pinned_resolved_config_drift")

    tp1_fraction = Fraction(str(config["tp1_frac"]))
    strategy_profile = {
        "side": "short",
        "entry_type": "market",
        "entry_offset": _decimal_text(Fraction(str(ATT1_PROFILE.entry_offset))),
        "entry_wait_bars": ATT1_PROFILE.entry_wait_bars,
        "signal_bar_ms": H1_MS,
        "short_stop_tick_rounding": "up",
        "short_target_tick_rounding": "down",
        "tp_rr": [_decimal_text(Fraction(str(config["tp1_rr"]))), _decimal_text(Fraction(str(config["tp2_rr"])))] ,
        "tp_fracs": [_decimal_text(tp1_fraction), _decimal_text(1 - tp1_fraction)],
        "be_trigger_rr": _decimal_text(Fraction(str(config["be_trigger_rr"]))),
        "be_lock_rr": _decimal_text(Fraction(str(config["be_lock_rr"]))),
        "trailing_atr_mult": _decimal_text(Fraction(str(config["trail_atr_mult"]))),
        "trailing_atr_period": config["atr_period"],
        "trail_activate_rr": _decimal_text(Fraction(str(config["trail_activate_rr"]))),
        "time_stop_bars_5m": config["time_stop_bars_5m"],
        "cooldown_bars_5m": config["cooldown_bars_5m"],
    }
    profile: dict[str, object] = {
        "schema_id": PROFILE_SCHEMA_ID,
        "profile_id": PROFILE_ID,
        "sleeve_id": "ATT1",
        "l1_source_aggregate_sha256": PROFILE_SOURCE_HASHES["ATT1"],
        "resolved_config_sha256": resolved_config_sha256,
        "source_sha256": source_sha256,
        "universe": list(FIXED51_UNIVERSE),
        "strategy": strategy_profile,
        "execution": {
            "risk_amount": "1",
            "max_notional": "100",
            "max_signal_age_ms": 300_000,
            "max_submit_delay_ms": 1_000,
            "instrument_max_age_ms": 3_600_000,
            "market_observation_max_age_ms": 2_000,
            "entry_ioc_lifetime_ms": 2_000,
            "max_adverse_risk_expansion": "0.1",
        },
        "authority": {
            "money_authority": False,
            "orders_allowed": False,
            "private_api_allowed": False,
            "promotion_authority": False,
        },
    }
    profile["profile_sha256"] = _sha256(profile)
    validate_profile(profile)
    return profile


def validate_profile(profile: Mapping) -> None:
    """Strictly validate the self-contained, default-off synthetic profile."""

    if not isinstance(profile, Mapping):
        raise ProfileViolation("profile_not_mapping")
    required = {
        "schema_id", "profile_id", "sleeve_id", "l1_source_aggregate_sha256",
        "resolved_config_sha256", "source_sha256", "universe", "strategy", "execution",
        "authority", "profile_sha256",
    }
    if set(profile) != required:
        raise ProfileViolation("profile_fields")
    if profile["schema_id"] != PROFILE_SCHEMA_ID or profile["profile_id"] != PROFILE_ID or profile["sleeve_id"] != "ATT1":
        raise ProfileViolation("profile_identity")
    if profile["l1_source_aggregate_sha256"] != PROFILE_SOURCE_HASHES["ATT1"]:
        raise ProfileViolation("profile_l1_source")
    if profile["resolved_config_sha256"] != PROFILE_FIXED51_CONFIG_HASHES["ATT1"]:
        raise ProfileViolation("profile_resolved_config")
    source_sha256 = profile["source_sha256"]
    if not isinstance(source_sha256, Mapping) or set(source_sha256) != set(PROFILE_SOURCE_PATHS):
        raise ProfileViolation("profile_source_map")
    for path, digest in source_sha256.items():
        if not isinstance(path, str):
            raise ProfileViolation("profile_source_map")
        _sha_text(digest, f"source_sha256:{path}")
    if profile["universe"] != list(FIXED51_UNIVERSE):
        raise ProfileViolation("profile_universe")
    strategy = profile["strategy"]
    expected_strategy = {
        "side", "entry_type", "entry_offset", "entry_wait_bars", "signal_bar_ms",
        "short_stop_tick_rounding", "short_target_tick_rounding", "tp_rr", "tp_fracs",
        "be_trigger_rr", "be_lock_rr", "trailing_atr_mult", "trailing_atr_period",
        "trail_activate_rr", "time_stop_bars_5m", "cooldown_bars_5m",
    }
    if not isinstance(strategy, Mapping) or set(strategy) != expected_strategy:
        raise ProfileViolation("profile_strategy")
    if strategy["side"] != "short" or strategy["entry_type"] != "market" or strategy["short_stop_tick_rounding"] != "up" or strategy["short_target_tick_rounding"] != "down":
        raise ProfileViolation("profile_strategy")
    if _decimal(strategy["entry_offset"], "entry_offset") != 0 or _int(strategy["entry_wait_bars"], "entry_wait_bars") != 0 or _int(strategy["signal_bar_ms"], "signal_bar_ms", positive=True) != H1_MS:
        raise ProfileViolation("profile_strategy")
    if not isinstance(strategy["tp_rr"], list) or not isinstance(strategy["tp_fracs"], list):
        raise ProfileViolation("profile_strategy")
    if [_decimal(value, "tp_rr", positive=True) for value in strategy["tp_rr"]] != [Fraction("1.2"), Fraction("2.5")]:
        raise ProfileViolation("profile_strategy")
    if [_decimal(value, "tp_fracs", positive=True) for value in strategy["tp_fracs"]] != [Fraction(".55"), Fraction(".45")]:
        raise ProfileViolation("profile_strategy")
    if _decimal(strategy["be_trigger_rr"], "be_trigger_rr") != 0 or _decimal(strategy["be_lock_rr"], "be_lock_rr") != Fraction(".02") or _decimal(strategy["trailing_atr_mult"], "trailing_atr_mult") != 0 or _int(strategy["trailing_atr_period"], "trailing_atr_period", positive=True) != 14 or _decimal(strategy["trail_activate_rr"], "trail_activate_rr") != 1 or _int(strategy["time_stop_bars_5m"], "time_stop_bars_5m", positive=True) != 4032 or _int(strategy["cooldown_bars_5m"], "cooldown_bars_5m", positive=True) != 96:
        raise ProfileViolation("profile_strategy")
    execution = profile["execution"]
    expected_execution = {"risk_amount", "max_notional", "max_signal_age_ms", "max_submit_delay_ms", "instrument_max_age_ms", "market_observation_max_age_ms", "entry_ioc_lifetime_ms", "max_adverse_risk_expansion"}
    if not isinstance(execution, Mapping) or set(execution) != expected_execution:
        raise ProfileViolation("profile_execution")
    if _decimal(execution["risk_amount"], "risk_amount", positive=True) != 1 or _decimal(execution["max_notional"], "max_notional", positive=True) != 100 or _decimal(execution["max_adverse_risk_expansion"], "max_adverse_risk_expansion") != Fraction(".1"):
        raise ProfileViolation("profile_execution")
    for key, expected in (("max_signal_age_ms", 300_000), ("max_submit_delay_ms", 1_000), ("instrument_max_age_ms", 3_600_000), ("market_observation_max_age_ms", 2_000), ("entry_ioc_lifetime_ms", 2_000)):
        if _int(execution[key], key, positive=True) != expected:
            raise ProfileViolation("profile_execution")
    authority = profile["authority"]
    if (not isinstance(authority, Mapping)
            or set(authority) != {"money_authority", "orders_allowed", "private_api_allowed", "promotion_authority"}
            or any(value is not False for value in authority.values())):
        raise ProfileViolation("profile_authority")
    if _sha_text(profile["profile_sha256"], "profile_sha256") != _sha256(_profile_without_sha(profile)):
        raise ProfileViolation("profile_sha256")


def _strict_mapping(value: object, fields: set[str], name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProfileViolation(f"{name}_fields")
    return value


def _signal(signal: object) -> Mapping[str, object]:
    fields = {"schema_id", "symbol", "side", "stream", "bar_close_ms", "source_available_ms", "signal_ready_ms", "entry", "sl", "tps", "tp_fracs", "be_trigger_rr", "be_lock_rr", "trailing_atr_mult", "trailing_atr_period", "trail_activate_rr", "time_stop_bars_5m", "source_sha256", "data_sha256", "profile_sha256"}
    item = _strict_mapping(signal, fields, "signal")
    if item["schema_id"] != SIGNAL_SCHEMA_ID or not isinstance(item["symbol"], str) or not item["symbol"] or not isinstance(item["side"], str) or not isinstance(item["stream"], str):
        raise ProfileViolation("signal_identity")
    for field in ("bar_close_ms", "source_available_ms", "signal_ready_ms", "trailing_atr_period", "time_stop_bars_5m"):
        _int(item[field], field, positive=True)
    for field in ("entry", "sl", "be_trigger_rr", "be_lock_rr", "trailing_atr_mult", "trail_activate_rr"):
        _decimal(item[field], field, positive=field in {"entry", "sl"})
    for field in ("source_sha256", "data_sha256", "profile_sha256"):
        _sha_text(item[field], field)
    if not isinstance(item["tps"], list) or not isinstance(item["tp_fracs"], list) or len(item["tps"]) != 2 or len(item["tp_fracs"]) != 2:
        raise ProfileViolation("signal_targets")
    for value in item["tps"]:
        _decimal(value, "tps", positive=True)
    for value in item["tp_fracs"]:
        _decimal(value, "tp_fracs", positive=True)
    return item


def _instrument(instrument: object) -> Mapping[str, object]:
    fields = {"symbol", "tick_size", "qty_step", "min_order_qty", "min_notional", "max_market_qty", "observed_ms", "source_sha256"}
    item = _strict_mapping(instrument, fields, "instrument")
    if not isinstance(item["symbol"], str) or not item["symbol"]:
        raise ProfileViolation("instrument_symbol")
    for field in ("tick_size", "qty_step", "min_order_qty", "min_notional", "max_market_qty"):
        _decimal(item[field], field, positive=True)
    _int(item["observed_ms"], "observed_ms", positive=True)
    _sha_text(item["source_sha256"], "instrument_source_sha256")
    return item


def _book_state(book_state: object) -> Mapping[str, object]:
    fields = {"active_decision_id", "last_admitted_bar_ms", "last_terminal_ms"}
    item = _strict_mapping(book_state, fields, "book_state")
    active = item["active_decision_id"]
    if active is not None and (not isinstance(active, str) or not active.strip()):
        raise ProfileViolation("book_state_active_decision_id")
    for field in ("last_admitted_bar_ms", "last_terminal_ms"):
        if item[field] is not None:
            _int(item[field], field, positive=True)
    return item


def _reject(code: str) -> dict:
    return {"accepted": False, "code": code, "plan": None}


def _relative_equal(left: Fraction, right: Fraction) -> bool:
    return abs(left - right) <= abs(right) * Fraction(1, 10_000_000_000)


def admit_signal(profile: Mapping, signal: Mapping, instrument: Mapping, book_state: Mapping, *, book: str, submit_ms: int) -> dict:
    """Admit one causal ATT1 signal, or return its explicit rejection reason."""

    validate_profile(profile)
    signal = _signal(signal)
    instrument = _instrument(instrument)
    book_state = _book_state(book_state)
    if not isinstance(book, str) or not book.strip():
        raise ProfileViolation("invalid_book")
    submit_ms = _int(submit_ms, "submit_ms", positive=True)
    strategy = profile["strategy"]
    execution = profile["execution"]
    if signal["stream"] != EXECUTION_FORWARD:
        return _reject("STREAM_NOT_EXECUTION_FORWARD")
    if signal["symbol"] not in profile["universe"] or instrument["symbol"] not in profile["universe"] or signal["symbol"] != instrument["symbol"]:
        return _reject("SYMBOL_MISMATCH")
    if signal["side"] != strategy["side"]:
        return _reject("SIDE_MISMATCH")
    if signal["profile_sha256"] != profile["profile_sha256"]:
        return _reject("PROFILE_HASH_MISMATCH")
    bar_close_ms = signal["bar_close_ms"]
    source_available_ms = signal["source_available_ms"]
    signal_ready_ms = signal["signal_ready_ms"]
    if bar_close_ms % H1_MS != 0:
        return _reject("BAR_NOT_H1_ALIGNED")
    if not bar_close_ms <= source_available_ms <= signal_ready_ms <= submit_ms:
        return _reject("TIMESTAMP_ORDER")
    if submit_ms - bar_close_ms > execution["max_signal_age_ms"]:
        return _reject("SIGNAL_STALE")
    if submit_ms - signal_ready_ms > execution["max_submit_delay_ms"]:
        return _reject("SUBMIT_DELAY_EXCEEDED")
    observed_ms = instrument["observed_ms"]
    if observed_ms > submit_ms:
        return _reject("INSTRUMENT_FUTURE")
    if submit_ms - observed_ms > execution["instrument_max_age_ms"]:
        return _reject("INSTRUMENT_STALE")
    if book_state["active_decision_id"] is not None:
        return _reject("POSITION_ACTIVE")
    # Persist closes consistently. Subtracting two closes equals subtracting
    # their starts, preserving the source strategy's eight-hour interval.
    previous_bar = book_state["last_admitted_bar_ms"]
    if previous_bar is not None:
        if bar_close_ms <= previous_bar:
            return _reject("BAR_DUPLICATE_OR_EARLIER")
        if bar_close_ms - previous_bar < strategy["cooldown_bars_5m"] * 300_000:
            return _reject("COOLDOWN_ACTIVE")
    if book_state["last_terminal_ms"] is not None and bar_close_ms <= book_state["last_terminal_ms"]:
        return _reject("TERMINAL_BAR_NOT_LATER")
    if signal["be_trigger_rr"] != strategy["be_trigger_rr"] or signal["be_lock_rr"] != strategy["be_lock_rr"] or signal["trailing_atr_mult"] != strategy["trailing_atr_mult"] or signal["trailing_atr_period"] != strategy["trailing_atr_period"] or signal["trail_activate_rr"] != strategy["trail_activate_rr"] or signal["time_stop_bars_5m"] != strategy["time_stop_bars_5m"] or signal["tp_fracs"] != strategy["tp_fracs"]:
        return _reject("FROZEN_SIGNAL_FIELDS_MISMATCH")
    entry = _decimal(signal["entry"], "entry", positive=True)
    stop = _decimal(signal["sl"], "sl", positive=True)
    tick = _decimal(instrument["tick_size"], "tick_size", positive=True)
    rounded_stop = _round_to_step(stop, tick, up=True)
    if stop <= entry or rounded_stop <= entry:
        return _reject("INVALID_SHORT_STOP")
    risk = rounded_stop - entry
    source_risk = stop - entry
    expected_targets = [entry - rr * source_risk for rr in (_decimal(strategy["tp_rr"][0], "tp_rr"), _decimal(strategy["tp_rr"][1], "tp_rr"))]
    actual_targets = [_decimal(value, "tps", positive=True) for value in signal["tps"]]
    if not 0 < actual_targets[1] < actual_targets[0] < entry:
        return _reject("TARGET_RR_MISMATCH")
    if any(not _relative_equal(actual, expected) for actual, expected in zip(actual_targets, expected_targets)):
        return _reject("TARGET_RR_MISMATCH")
    rebased_targets = [_floor_to_step(entry - _decimal(rr, "tp_rr") * risk, tick)
                       for rr in strategy["tp_rr"]]
    if not 0 < rebased_targets[1] < rebased_targets[0] < entry:
        return _reject("REBASED_TARGET_INVALID")
    qty_step = _decimal(instrument["qty_step"], "qty_step", positive=True)
    requested_qty = _floor_to_step(min(_decimal(execution["risk_amount"], "risk_amount", positive=True) / risk, _decimal(execution["max_notional"], "max_notional", positive=True) / entry, _decimal(instrument["max_market_qty"], "max_market_qty", positive=True)), qty_step)
    if requested_qty < _decimal(instrument["min_order_qty"], "min_order_qty", positive=True):
        return _reject("BELOW_MIN_QTY")
    if requested_qty * entry < _decimal(instrument["min_notional"], "min_notional", positive=True):
        return _reject("BELOW_MIN_NOTIONAL")
    decision_id = _sha256({
        "signal_payload_sha256": _sha256(signal),
        "bar_close_ms": bar_close_ms,
        "book": book,
        "data_sha256": signal["data_sha256"],
        "instrument_source_sha256": instrument["source_sha256"],
        "profile_sha256": profile["profile_sha256"],
        "signal_source_sha256": signal["source_sha256"],
        "symbol": signal["symbol"],
    })
    return {
        "accepted": True,
        "code": "ACCEPTED",
        "plan": {
            "profile_id": profile["profile_id"],
            "profile_sha256": profile["profile_sha256"],
            "book": book,
            "symbol": signal["symbol"],
            "decision_id": decision_id,
            "order_id": f"research-order:{decision_id}",
            "bar_close_ms": bar_close_ms,
            "signal_ready_ms": signal_ready_ms,
            "submit_ms": submit_ms,
            "nominal_entry": _decimal_text(entry),
            "original_stop": _decimal_text(rounded_stop),
            "requested_qty": _decimal_text(requested_qty),
            "qty_step": _decimal_text(qty_step),
            "price_tick": _decimal_text(tick),
            "planned_risk_amount": _decimal_text(_decimal(execution["risk_amount"], "risk_amount")),
            "signal_source_sha256": signal["source_sha256"],
            "data_sha256": signal["data_sha256"],
            "instrument_source_sha256": instrument["source_sha256"],
        },
    }


__all__ = ["ProfileViolation", "admit_signal", "build_profile", "validate_profile"]
