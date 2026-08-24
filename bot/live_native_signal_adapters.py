"""Pure adapters from the real strategy signal shapes to the parity contract.

This module is deliberately default-off and has no broker, environment, order,
runner, persistence, or money-authority imports.  It accepts the repository's
real :class:`strategies.signals.TradeSignal` object and refuses to manufacture a
decision from a fixture-shaped mapping.

The ATT1 adapter binds four independently checkable inputs:

* the actual ``TradeSignal`` returned by ``ATT1LiveEngine.signal``;
* the actual ``build_att1_runtime_contract`` mapping and its self hash;
* exact bytes for the ATT1 strategy and live wrapper;
* exact JSON bytes for the last closed H1 row consumed by the strategy.

SBR1 now has a default-off live-shaped wrapper as well as its research strategy.
The research and live converters bind the same exact strategy/wrapper source
bundle.  The wrapper itself has no order imports or money authority; wiring it
to a zero-risk monolith call site remains a separate release gate.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from bot.live_native_decision_contract import (
    ATT1_FROZEN_PROFILE,
    ContractViolation,
    H1_MS,
    LiveNativeDecisionPlan,
    SBR1_FROZEN_PROFILE,
)
from strategies.signals import TradeSignal
from strategies.sloped_break_retest_v1 import SlopedBreakRetestV1Config


LIVE_NATIVE_SIGNAL_ADAPTERS_ENABLED_BY_DEFAULT = False
ATT1_SPEC_ID = "att1-live-native-v2"
SBR1_SPEC_ID = "sbr1-live-native-v2"
ATT1_STRATEGY_ID = "alt_trendline_touch_v1"
SBR1_STRATEGY_ID = "sloped_break_retest_v1"

_ATT1_SOURCE_PATHS = frozenset(
    {
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    }
)
_SBR1_SOURCE_PATHS = frozenset(
    {
        "strategies/sloped_break_retest_v1.py",
        "strategies/sbr1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    }
)


def _canonical_json_bytes(value: object, code: str) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation(code) from exc


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_integer", field)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ContractViolation("invalid_integer", field)
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ContractViolation("invalid_integer", field) from exc
    else:
        raise ContractViolation("invalid_integer", field)
    if not number.is_finite() or number != number.to_integral_value():
        raise ContractViolation("invalid_integer", field)
    return int(number)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ContractViolation("invalid_decimal", field)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_decimal", field) from exc
    if not number.is_finite():
        raise ContractViolation("non_finite_decimal", field)
    return number


def _sha256_hex(value: object, field: str) -> str:
    result = str(value or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        raise ContractViolation("invalid_sha256", field)
    return result


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_path(value: object) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
        raise ContractViolation("invalid_source_path")
    return path


def verified_source_bundle_hash(
    source_files: Mapping[str, bytes],
    expected_file_hashes: Mapping[str, str],
    *,
    required_paths: frozenset[str],
) -> str:
    """Verify exact source bytes and return a stable bundle SHA-256."""

    if not isinstance(source_files, Mapping) or not isinstance(expected_file_hashes, Mapping):
        raise ContractViolation("invalid_source_bundle")
    normalized_files: dict[str, bytes] = {}
    normalized_expected: dict[str, str] = {}
    for raw_path, raw_bytes in source_files.items():
        path = _normalized_path(raw_path)
        if path in normalized_files or not isinstance(raw_bytes, bytes):
            raise ContractViolation("invalid_source_bundle", path)
        normalized_files[path] = raw_bytes
    for raw_path, raw_hash in expected_file_hashes.items():
        path = _normalized_path(raw_path)
        if path in normalized_expected:
            raise ContractViolation("invalid_source_bundle", path)
        normalized_expected[path] = _sha256_hex(raw_hash, f"source:{path}")
    if frozenset(normalized_files) != required_paths:
        raise ContractViolation("source_bundle_paths_mismatch")
    if frozenset(normalized_expected) != required_paths:
        raise ContractViolation("source_manifest_paths_mismatch")

    actual_hashes = {path: _sha256(data) for path, data in normalized_files.items()}
    for path in sorted(required_paths):
        if actual_hashes[path] != normalized_expected[path]:
            raise ContractViolation("source_hash_mismatch", path)
    payload = {
        "files": [
            {"path": path, "sha256": actual_hashes[path]}
            for path in sorted(actual_hashes)
        ],
        "schema_id": "live_native_source_bundle_v1",
    }
    return _sha256(_canonical_json_bytes(payload, "noncanonical_source_bundle"))


@dataclass(frozen=True)
class ClosedH1Evidence:
    """One exact Bybit-style H1 row observed only after its close."""

    row: tuple[object, ...]
    row_bytes: bytes
    bar_start_ts_ms: int
    closed_h1_ts_ms: int
    observed_at_ms: int
    max_decision_age_ms: int
    age_ms: int
    data_hash: str


def closed_h1_evidence_from_row(
    row: Sequence[object],
    *,
    row_bytes: bytes,
    observed_at_ms: object,
    max_decision_age_ms: object,
) -> ClosedH1Evidence:
    """Validate a real kline row and bind the exact serialized row bytes.

    Bybit rows carry the candle *start* timestamp.  The decision timestamp in
    ``LiveNativeDecisionPlan`` is the aligned H1 close, ``start + 1h``.
    """

    if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) < 6:
        raise ContractViolation("invalid_closed_h1_row")
    if not isinstance(row_bytes, bytes) or not row_bytes:
        raise ContractViolation("missing_closed_h1_row_bytes")
    try:
        decoded = json.loads(row_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("invalid_closed_h1_row_bytes") from exc
    if not isinstance(decoded, list) or decoded != list(row):
        raise ContractViolation("closed_h1_row_bytes_mismatch")

    start = _strict_int(row[0], "bar_start_ts_ms")
    if start <= 0 or start % H1_MS != 0:
        raise ContractViolation("h1_bar_start_not_aligned")
    close_ts = start + H1_MS
    observed = _strict_int(observed_at_ms, "observed_at_ms")
    max_age = _strict_int(max_decision_age_ms, "max_decision_age_ms")
    if max_age <= 0:
        raise ContractViolation("nonpositive_max_decision_age")
    age = observed - close_ts
    if age < 0:
        raise ContractViolation("h1_bar_not_closed")
    if age > max_age:
        raise ContractViolation("closed_h1_decision_too_old")

    open_, high, low, close, volume = (
        _decimal(row[1], "open"),
        _decimal(row[2], "high"),
        _decimal(row[3], "low"),
        _decimal(row[4], "close"),
        _decimal(row[5], "volume"),
    )
    if min(open_, high, low, close) <= 0 or volume < 0:
        raise ContractViolation("invalid_h1_ohlcv")
    if high < max(open_, close) or low > min(open_, close) or low > high:
        raise ContractViolation("incoherent_h1_ohlc")
    return ClosedH1Evidence(
        row=tuple(row),
        row_bytes=row_bytes,
        bar_start_ts_ms=start,
        closed_h1_ts_ms=close_ts,
        observed_at_ms=observed,
        max_decision_age_ms=max_age,
        age_ms=age,
        data_hash=_sha256(row_bytes),
    )


def _verified_closed_h1_evidence(value: object) -> ClosedH1Evidence:
    """Rebuild public evidence so a hand-constructed dataclass cannot bypass gates."""

    if not isinstance(value, ClosedH1Evidence):
        raise ContractViolation("invalid_closed_h1_evidence")
    rebuilt = closed_h1_evidence_from_row(
        value.row,
        row_bytes=value.row_bytes,
        observed_at_ms=value.observed_at_ms,
        max_decision_age_ms=value.max_decision_age_ms,
    )
    if rebuilt != value:
        raise ContractViolation("inconsistent_closed_h1_evidence")
    return rebuilt


def _source_bytes(source_files: Mapping[str, bytes], wanted_path: str) -> bytes:
    matches = [
        data
        for raw_path, data in source_files.items()
        if _normalized_path(raw_path) == wanted_path
    ]
    if len(matches) != 1 or not isinstance(matches[0], bytes):
        raise ContractViolation("source_bundle_paths_mismatch")
    return matches[0]


def _verified_att1_runtime_contract(
    runtime_contract: Mapping[str, object],
    *,
    strategy_source_hash: str,
) -> tuple[Mapping[str, object], str]:
    if not isinstance(runtime_contract, Mapping):
        raise ContractViolation("invalid_att1_runtime_contract")
    if frozenset(runtime_contract) != frozenset({"params", "sha256"}):
        raise ContractViolation("att1_runtime_contract_fields_mismatch")
    params = runtime_contract.get("params")
    if not isinstance(params, Mapping):
        raise ContractViolation("invalid_att1_runtime_params")
    embedded_hash = _sha256_hex(runtime_contract.get("sha256"), "runtime_contract_sha256")
    actual_hash = _sha256(_canonical_json_bytes(params, "noncanonical_att1_runtime_params"))
    if embedded_hash != actual_hash:
        raise ContractViolation("att1_runtime_contract_hash_mismatch")
    source_hash = _sha256_hex(
        params.get("strategy_source_sha256"), "strategy_source_sha256"
    )
    if source_hash != strategy_source_hash:
        raise ContractViolation("att1_runtime_source_hash_mismatch")
    return params, actual_hash


def _require_decimal_param(
    params: Mapping[str, object], field: str, expected: Decimal
) -> None:
    if field not in params or _decimal(params[field], field) != expected:
        raise ContractViolation("selected_config_mismatch", field)


def _require_int_param(params: Mapping[str, object], field: str, expected: int) -> None:
    if field not in params or _strict_int(params[field], field) != expected:
        raise ContractViolation("selected_config_mismatch", field)


def _require_bool_param(params: Mapping[str, object], field: str, expected: bool) -> None:
    if field not in params or not isinstance(params[field], bool) or params[field] is not expected:
        raise ContractViolation("selected_config_mismatch", field)


def _validate_selected_att1_config(params: Mapping[str, object]) -> None:
    _require_bool_param(params, "allow_longs", False)
    _require_bool_param(params, "allow_shorts", True)
    if str(params.get("signal_tf") or "").strip() != "60":
        raise ContractViolation("selected_config_mismatch", "signal_tf")
    for field, expected in (
        ("sl_atr_mult", Decimal("6.6")),
        ("max_stop_pct", Decimal("0.25")),
        ("tp1_rr", ATT1_FROZEN_PROFILE.nominal_rrs[0]),
        ("tp2_rr", ATT1_FROZEN_PROFILE.nominal_rrs[1]),
        ("tp1_frac", ATT1_FROZEN_PROFILE.tp_fractions[0]),
        ("be_trigger_rr", Decimal("0")),
        ("trail_atr_mult", Decimal("0")),
    ):
        _require_decimal_param(params, field, expected)
    _require_int_param(params, "time_stop_bars_5m", 4032)


def _validate_selected_sbr1_config(cfg: SlopedBreakRetestV1Config) -> None:
    if not isinstance(cfg, SlopedBreakRetestV1Config):
        raise ContractViolation("invalid_sbr1_config_object")
    if str(cfg.signal_tf).strip() != "60":
        raise ContractViolation("selected_config_mismatch", "signal_tf")
    if cfg.allow_longs is not True or cfg.allow_shorts is not False:
        raise ContractViolation("selected_config_mismatch", "side_enablement")
    for field, expected in (
        ("sl_atr_mult", Decimal("4.6")),
        ("tp1_rr", SBR1_FROZEN_PROFILE.nominal_rrs[0]),
        ("tp2_rr", SBR1_FROZEN_PROFILE.nominal_rrs[1]),
        ("tp1_frac", SBR1_FROZEN_PROFILE.tp_fractions[0]),
        ("tp2_frac", SBR1_FROZEN_PROFILE.tp_fractions[1]),
        ("be_trigger_rr", Decimal("0")),
        ("trail_atr_mult", Decimal("0")),
    ):
        if _decimal(getattr(cfg, field), field) != expected:
            raise ContractViolation("selected_config_mismatch", field)
    if _strict_int(cfg.time_stop_bars_5m, "time_stop_bars_5m") != 2016:
        raise ContractViolation("selected_config_mismatch", "time_stop_bars_5m")
    if _strict_int(cfg.cooldown_tf_bars, "cooldown_tf_bars") != 6:
        raise ContractViolation("selected_config_mismatch", "cooldown_tf_bars")


def _signal_geometry(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    *,
    expected_strategy: str,
    expected_side: str,
    expected_rrs: tuple[Decimal, ...],
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...], Decimal, int]:
    if not isinstance(signal, TradeSignal):
        raise ContractViolation("invalid_trade_signal_type")
    if str(signal.strategy or "").strip() != expected_strategy:
        raise ContractViolation("strategy_id_mismatch")
    if str(signal.side or "").strip().lower() != expected_side:
        raise ContractViolation("selected_signal_side_mismatch")
    if not signal.validate():
        raise ContractViolation("trade_signal_validation_failed")
    if not isinstance(signal.tps, list) or not isinstance(signal.tp_fracs, list):
        raise ContractViolation("missing_real_multi_target_shape")
    if len(signal.tps) != 2 or len(signal.tp_fracs) != 2:
        raise ContractViolation("unexpected_signal_target_count")
    entry = _decimal(signal.entry, "entry")
    close = _decimal(evidence.row[4], "closed_h1_close")
    if entry != close:
        raise ContractViolation("signal_entry_not_closed_h1_close")
    raw_targets = tuple(_decimal(value, "tps") for value in signal.tps)
    fractions = tuple(_decimal(value, "tp_fracs") for value in signal.tp_fracs)
    if _decimal(signal.tp, "tp") != raw_targets[-1]:
        raise ContractViolation("legacy_tp_not_last_target")
    stop = _decimal(signal.sl, "sl")
    risk = stop - entry if expected_side == "short" else entry - stop
    if risk <= 0:
        raise ContractViolation("trade_signal_validation_failed")
    targets = tuple(
        entry - rr * risk if expected_side == "short" else entry + rr * risk
        for rr in expected_rrs
    )
    # Strategy objects use binary floats.  Bind their intent to the exact
    # frozen Decimal geometry only when the raw values differ by float noise;
    # a material RR change still fails closed.
    tolerance = max(Decimal("1e-18"), risk * Decimal("1e-10"))
    if len(raw_targets) != len(targets) or any(
        abs(raw - exact) > tolerance for raw, exact in zip(raw_targets, targets)
    ):
        raise ContractViolation("wrong_strategy_nominal_rrs")
    residual = Decimal("1") - sum(fractions, Decimal("0"))
    bars = _strict_int(signal.time_stop_bars, "time_stop_bars")
    if bars <= 0 or (bars * 5) % 60 != 0:
        raise ContractViolation("time_stop_not_whole_hours")
    return targets, fractions, residual, (bars * 5) // 60


def adapt_att1_live_signal_to_plan(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    runtime_contract: Mapping[str, object],
    *,
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
) -> LiveNativeDecisionPlan:
    """Convert the actual ATT1 live-wrapper result into a frozen plan."""

    evidence = _verified_closed_h1_evidence(evidence)
    source_hash = verified_source_bundle_hash(
        source_files,
        expected_source_hashes,
        required_paths=_ATT1_SOURCE_PATHS,
    )
    strategy_source_hash = _sha256(
        _source_bytes(source_files, "strategies/alt_trendline_touch_v1.py")
    )
    params, config_hash = _verified_att1_runtime_contract(
        runtime_contract,
        strategy_source_hash=strategy_source_hash,
    )
    _validate_selected_att1_config(params)
    targets, fractions, residual, hours = _signal_geometry(
        signal,
        evidence,
        expected_strategy=ATT1_STRATEGY_ID,
        expected_side="short",
        expected_rrs=ATT1_FROZEN_PROFILE.nominal_rrs,
    )
    if not str(signal.reason or "").startswith("att1_short_trendline "):
        raise ContractViolation("att1_signal_reason_mismatch")
    return LiveNativeDecisionPlan(
        spec_id=ATT1_SPEC_ID,
        sleeve_id="ATT1",
        symbol=signal.symbol,
        side=signal.side,
        closed_h1_ts_ms=evidence.closed_h1_ts_ms,
        planned_entry=_decimal(signal.entry, "entry"),
        frozen_sl=_decimal(signal.sl, "sl"),
        planned_tps=targets,
        tp_fractions=fractions,
        residual_fraction=residual,
        time_stop_hours=hours,
        config_hash=config_hash,
        source_hash=source_hash,
        data_hash=evidence.data_hash,
    )


def adapt_att1_research_signal_to_plan(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    runtime_contract: Mapping[str, object],
    *,
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
) -> LiveNativeDecisionPlan:
    """Convert the direct ATT1 strategy boundary under the same frozen contract."""

    return adapt_att1_live_signal_to_plan(
        signal,
        evidence,
        runtime_contract,
        source_files=source_files,
        expected_source_hashes=expected_source_hashes,
    )


def _adapt_sbr1_signal_to_plan(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    config: SlopedBreakRetestV1Config,
    *,
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
) -> LiveNativeDecisionPlan:

    evidence = _verified_closed_h1_evidence(evidence)
    _validate_selected_sbr1_config(config)
    source_hash = verified_source_bundle_hash(
        source_files,
        expected_source_hashes,
        required_paths=_SBR1_SOURCE_PATHS,
    )
    strategy_source_hash = _sha256(
        _source_bytes(source_files, "strategies/sloped_break_retest_v1.py")
    )
    config_payload = {
        "params": asdict(config),
        "schema_id": "sbr1_research_effective_config_v1",
        "strategy_source_sha256": strategy_source_hash,
    }
    config_hash = _sha256(
        _canonical_json_bytes(config_payload, "noncanonical_sbr1_research_config")
    )
    targets, fractions, residual, hours = _signal_geometry(
        signal,
        evidence,
        expected_strategy=SBR1_STRATEGY_ID,
        expected_side="long",
        expected_rrs=SBR1_FROZEN_PROFILE.nominal_rrs,
    )
    if str(signal.reason or "") != "sbr1_long_channel_break_retest":
        raise ContractViolation("sbr1_signal_reason_mismatch")
    return LiveNativeDecisionPlan(
        spec_id=SBR1_SPEC_ID,
        sleeve_id="SBR1",
        symbol=signal.symbol,
        side=signal.side,
        closed_h1_ts_ms=evidence.closed_h1_ts_ms,
        planned_entry=_decimal(signal.entry, "entry"),
        frozen_sl=_decimal(signal.sl, "sl"),
        planned_tps=targets,
        tp_fractions=fractions,
        residual_fraction=residual,
        time_stop_hours=hours,
        config_hash=config_hash,
        source_hash=source_hash,
        data_hash=evidence.data_hash,
    )


def adapt_sbr1_research_signal_to_plan(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    config: SlopedBreakRetestV1Config,
    *,
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
) -> LiveNativeDecisionPlan:
    """Convert a signal emitted by the direct research strategy boundary."""

    return _adapt_sbr1_signal_to_plan(
        signal,
        evidence,
        config,
        source_files=source_files,
        expected_source_hashes=expected_source_hashes,
    )


def adapt_sbr1_live_signal_to_plan(
    signal: TradeSignal,
    evidence: ClosedH1Evidence,
    config: SlopedBreakRetestV1Config,
    *,
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
) -> LiveNativeDecisionPlan:
    """Convert the output of the real default-off ``SBR1LiveEngine`` boundary."""

    return _adapt_sbr1_signal_to_plan(
        signal,
        evidence,
        config,
        source_files=source_files,
        expected_source_hashes=expected_source_hashes,
    )


__all__ = [
    "ATT1_SPEC_ID",
    "ClosedH1Evidence",
    "LIVE_NATIVE_SIGNAL_ADAPTERS_ENABLED_BY_DEFAULT",
    "SBR1_SPEC_ID",
    "adapt_att1_live_signal_to_plan",
    "adapt_att1_research_signal_to_plan",
    "adapt_sbr1_live_signal_to_plan",
    "adapt_sbr1_research_signal_to_plan",
    "closed_h1_evidence_from_row",
    "verified_source_bundle_hash",
]
