"""Default-off, authority-free ATT1 production-caller decision receipts.

The pure :func:`build_att1_decision_receipt` boundary accepts everything the
real caller or a replay has already observed.  It never fetches market data,
recomputes the BTC regime, reads environment variables, or reaches an order
surface.  Equal consumed rows, effective config, signal, source manifest, and
persisted regime receipt therefore produce byte-equal receipts.

File loading and durable append-only storage are separate helpers.  The live
monolith does not call either helper unless its explicit default-off flag is
enabled.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence

from bot.live_native_decision_contract import (
    ContractViolation,
    H1_MS,
    apply_exchange_stop_filter,
)
from bot.live_native_signal_adapters import (
    adapt_att1_live_signal_to_plan,
    closed_h1_evidence_from_row,
    verified_source_bundle_hash,
)
from bot.persisted_btc_h1_regime import (
    BTCRegimeContractError,
    BTCRegimeReceipt,
    regime_evidence,
)
from strategies.signals import TradeSignal


ATT1_CALLER_RECEIPTS_ENABLED_BY_DEFAULT = False
RECEIPT_SCHEMA_ID = "att1_live_caller_decision_receipt_v1"
SOURCE_MANIFEST_SCHEMA_ID = "att1_sbr1_live_native_parity_manifest_v1"
CALLER_CONTEXT_SCHEMA_ID = "live_native_caller_context_v1"
FILE_MODE = 0o600
ATT1_SOURCE_PATHS = frozenset(
    {
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ReceiptPersistenceError(RuntimeError):
    """The decision was not durably appended; an enabled caller must stop."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractViolation("noncanonical_att1_caller_receipt") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_field(value: object, field: str) -> str:
    result = str(value or "").strip()
    if _SHA256_RE.fullmatch(result) is None:
        raise ContractViolation("invalid_sha256", field)
    return result


def _strict_int(value: object, field: str) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise ContractViolation("invalid_integer", field)
    try:
        result = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ContractViolation("invalid_integer", field) from exc
    if str(result) != str(value).strip():
        raise ContractViolation("invalid_integer", field)
    return result


def _decimal_text(value: object, field: str, *, allow_zero: bool = False) -> str:
    if isinstance(value, bool):
        raise ContractViolation("invalid_decimal", field)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ContractViolation("invalid_decimal", field) from exc
    if not result.is_finite() or (result < 0 if allow_zero else result <= 0):
        raise ContractViolation("invalid_decimal", field)
    return format(result, "f")


def _symbol(value: object) -> str:
    result = str(value or "").strip().upper()
    if not result or re.fullmatch(r"[A-Z0-9]{3,32}", result) is None:
        raise ContractViolation("invalid_att1_symbol")
    return result


def _runtime_contract_hash(runtime_contract: Mapping[str, object]) -> str:
    if not isinstance(runtime_contract, Mapping) or set(runtime_contract) != {
        "params",
        "sha256",
    }:
        raise ContractViolation("invalid_att1_runtime_contract")
    params = runtime_contract.get("params")
    if not isinstance(params, Mapping):
        raise ContractViolation("invalid_att1_runtime_contract")
    expected = _sha256_field(runtime_contract.get("sha256"), "runtime_contract")
    actual = _sha256(_canonical(dict(params)))
    if actual != expected:
        raise ContractViolation("att1_runtime_contract_hash_mismatch")
    return expected


def _validated_consumed_rows(
    consumed_closed_rows: Sequence[Sequence[object]],
) -> tuple[list[list[object]], str]:
    if isinstance(consumed_closed_rows, (str, bytes, bytearray)):
        raise ContractViolation("invalid_consumed_closed_rows")
    try:
        rows = [list(row) for row in consumed_closed_rows]
    except (TypeError, ValueError) as exc:
        raise ContractViolation("invalid_consumed_closed_rows") from exc
    if not rows:
        raise ContractViolation("missing_consumed_closed_rows")
    previous: int | None = None
    for row in rows:
        if len(row) < 6:
            raise ContractViolation("invalid_consumed_closed_row")
        start = _strict_int(row[0], "consumed_bar_start_ts_ms")
        if start <= 0 or start % H1_MS != 0:
            raise ContractViolation("invalid_consumed_closed_row")
        if previous is not None and start != previous + H1_MS:
            raise ContractViolation("noncontiguous_consumed_closed_rows")
        previous = start
    return rows, _sha256(_canonical(rows))


def _source_hash(
    source_files: Mapping[str, bytes], expected_source_hashes: Mapping[str, str]
) -> str:
    return verified_source_bundle_hash(
        source_files,
        expected_source_hashes,
        required_paths=ATT1_SOURCE_PATHS,
    )


def _bind_runtime_contract_to_strategy_source(
    runtime_contract: Mapping[str, object], source_files: Mapping[str, bytes]
) -> None:
    params = runtime_contract.get("params")
    source = source_files.get("strategies/alt_trendline_touch_v1.py")
    if not isinstance(params, Mapping) or not isinstance(source, bytes):
        raise ContractViolation("invalid_att1_runtime_source_binding")
    expected = _sha256_field(
        params.get("strategy_source_sha256"), "strategy_source_sha256"
    )
    if expected != _sha256(source):
        raise ContractViolation("att1_runtime_strategy_source_mismatch")


def _validated_caller_context(
    value: Mapping[str, object], *, symbol: str
) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_id",
        "exchange_filter",
        "intended_fill",
        "portfolio",
    }:
        raise ContractViolation("invalid_live_caller_context")
    if value.get("schema_id") != CALLER_CONTEXT_SCHEMA_ID:
        raise ContractViolation("invalid_live_caller_context")

    exchange = value.get("exchange_filter")
    if not isinstance(exchange, Mapping) or set(exchange) != {
        "symbol",
        "tick_size",
        "qty_step",
        "min_notional",
    }:
        raise ContractViolation("invalid_exchange_filter_context")
    exchange_symbol = _symbol(exchange.get("symbol"))
    if exchange_symbol != symbol:
        raise ContractViolation("exchange_filter_symbol_mismatch")
    exchange_payload = {
        "symbol": exchange_symbol,
        "tick_size": _decimal_text(exchange.get("tick_size"), "tick_size"),
        "qty_step": _decimal_text(exchange.get("qty_step"), "qty_step"),
        "min_notional": _decimal_text(
            exchange.get("min_notional"), "min_notional"
        ),
    }

    intended = value.get("intended_fill")
    if not isinstance(intended, Mapping) or set(intended) != {
        "entry_order",
        "fill_source",
        "max_fill_age_ms",
        "max_finalize_delay_ms",
        "max_adverse_risk_expansion",
    }:
        raise ContractViolation("invalid_intended_fill_context")
    fill_payload = {
        "entry_order": str(intended.get("entry_order") or "").strip(),
        "fill_source": str(intended.get("fill_source") or "").strip(),
        "max_fill_age_ms": _strict_int(
            intended.get("max_fill_age_ms"), "max_fill_age_ms"
        ),
        "max_finalize_delay_ms": _strict_int(
            intended.get("max_finalize_delay_ms"), "max_finalize_delay_ms"
        ),
        "max_adverse_risk_expansion": _decimal_text(
            intended.get("max_adverse_risk_expansion"),
            "max_adverse_risk_expansion",
            allow_zero=True,
        ),
    }
    if (
        fill_payload["entry_order"] != "market"
        or fill_payload["fill_source"]
        != "terminal_order_plus_complete_executions"
        or fill_payload["max_fill_age_ms"] != 300_000
        or fill_payload["max_finalize_delay_ms"] != 60_000
        or Decimal(str(fill_payload["max_adverse_risk_expansion"]))
        != Decimal("0.20")
    ):
        raise ContractViolation("intended_fill_contract_mismatch")

    portfolio = value.get("portfolio")
    if not isinstance(portfolio, Mapping) or set(portfolio) != {
        "slot_allowed",
        "open_positions",
        "max_positions",
        "exposure_gate_required",
        "exposure_gate_enforced",
        "exposure_allowed",
        "drop_reason",
    }:
        raise ContractViolation("invalid_portfolio_context")
    for field in (
        "slot_allowed",
        "exposure_gate_required",
        "exposure_gate_enforced",
    ):
        if not isinstance(portfolio.get(field), bool):
            raise ContractViolation("invalid_portfolio_context", field)
    open_positions = _strict_int(portfolio.get("open_positions"), "open_positions")
    max_positions = _strict_int(portfolio.get("max_positions"), "max_positions")
    if open_positions < 0 or max_positions <= 0:
        raise ContractViolation("invalid_portfolio_context")
    slot_allowed = bool(portfolio.get("slot_allowed"))
    drop_reason = str(portfolio.get("drop_reason") or "").strip()
    if slot_allowed and open_positions >= max_positions:
        raise ContractViolation("slot_gate_inconsistent")
    if not slot_allowed:
        raise ContractViolation("slot_gate_blocked", drop_reason or "slot_blocked")
    if portfolio.get("exposure_gate_required") is not True:
        raise ContractViolation("exposure_gate_requirement_missing")
    exposure_enforced = bool(portfolio.get("exposure_gate_enforced"))
    exposure_allowed = portfolio.get("exposure_allowed")
    if exposure_enforced:
        if not isinstance(exposure_allowed, bool):
            raise ContractViolation("invalid_exposure_gate_decision")
        if not exposure_allowed:
            raise ContractViolation(
                "exposure_gate_blocked", drop_reason or "exposure_blocked"
            )
    else:
        if exposure_allowed is not None:
            raise ContractViolation("unenforced_exposure_has_decision")
        drop_reason = drop_reason or "exposure_gate_not_connected"
    return {
        "schema_id": CALLER_CONTEXT_SCHEMA_ID,
        "exchange_filter": exchange_payload,
        "intended_fill": fill_payload,
        "portfolio": {
            "slot_allowed": True,
            "open_positions": open_positions,
            "max_positions": max_positions,
            "exposure_gate_required": True,
            "exposure_gate_enforced": exposure_enforced,
            "exposure_allowed": exposure_allowed,
            "drop_reason": drop_reason,
        },
    }


def _exception_payload(exc: Exception, stage: str) -> dict[str, str]:
    code = getattr(exc, "code", "unexpected_exception")
    code = str(code or "unexpected_exception").strip() or "unexpected_exception"
    safe_stage = str(stage or "decision_contract").strip() or "decision_contract"
    return {
        "code": code[:120],
        "stage": safe_stage[:80],
        "type": type(exc).__name__[:80],
    }


def _seal(payload: Mapping[str, object]) -> dict[str, object]:
    result = dict(payload)
    result["receipt_sha256"] = _sha256(_canonical(result))
    return result


def _base_payload(
    *,
    symbol: str,
    observed_at_ms: int,
    consumed_rows_count: int,
    consumed_rows_sha256: str | None,
    latest_closed_h1_ts_ms: int | None,
    latest_closed_row_sha256: str | None,
    runtime_contract_sha256: str | None,
    effective_config: Mapping[str, object] | None,
    source_bundle_sha256: str | None,
    source_manifest_sha256: str | None,
    caller_context: Mapping[str, object] | None,
    regime_required: bool,
) -> dict[str, object]:
    return {
        "schema_id": RECEIPT_SCHEMA_ID,
        "sleeve_id": "ATT1",
        "symbol": symbol,
        "observed_at_ms": observed_at_ms,
        "closed_h1_ts_ms": latest_closed_h1_ts_ms,
        "consumed_rows_count": consumed_rows_count,
        "consumed_rows_sha256": consumed_rows_sha256,
        "latest_closed_row_sha256": latest_closed_row_sha256,
        "runtime_contract_sha256": runtime_contract_sha256,
        "effective_config": (
            dict(effective_config) if effective_config is not None else None
        ),
        "source_bundle_sha256": source_bundle_sha256,
        "source_manifest_sha256": source_manifest_sha256,
        "caller_context": dict(caller_context) if caller_context is not None else None,
        "regime_required": bool(regime_required),
        "caller_boundary_default_off": True,
        "research_only": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "release_or_promotion_authority": False,
    }


def build_att1_decision_receipt(
    *,
    symbol: str,
    observed_at_ms: object,
    consumed_closed_rows: Sequence[Sequence[object]],
    signal: TradeSignal | None,
    no_signal_reason: str,
    runtime_contract: Mapping[str, object],
    source_files: Mapping[str, bytes],
    expected_source_hashes: Mapping[str, str],
    source_manifest_sha256: str,
    regime_required: bool,
    persisted_regime_receipt: BTCRegimeReceipt | None,
    max_decision_age_ms: object,
    caller_context: Mapping[str, object],
    evaluation_error: Exception | None = None,
    error_stage: str = "strategy_evaluation",
) -> dict[str, object]:
    """Build one deterministic success/no-signal/error receipt without I/O.

    Contract errors are intentionally converted into ``FAIL_CLOSED`` receipts.
    Arbitrary exception messages are never serialized; only their stable type,
    machine code (when available), and stage are recorded.
    """

    safe_symbol = str(symbol or "").strip().upper() or "UNKNOWN"
    safe_observed = 0
    consumed_count = 0
    consumed_hash: str | None = None
    latest_closed_h1_ts_ms: int | None = None
    latest_row_hash: str | None = None
    runtime_hash: str | None = None
    effective_config: dict[str, object] | None = None
    source_hash: str | None = None
    manifest_hash: str | None = None
    normalized_caller_context: dict[str, object] | None = None
    regime_payload: dict[str, object] = {
        "enabled": bool(regime_required),
        "receipt_sha256": None,
        "state_sha256": None,
        "closed_h1_ts_ms": None,
        "value": None,
        "allows_att1": None,
    }
    try:
        safe_symbol = _symbol(symbol)
        safe_observed = _strict_int(observed_at_ms, "observed_at_ms")
        # Preserve the actual strategy exception even when the engine failed
        # before it could consume a candle.  Evidence fields remain best-effort
        # diagnostics in this branch; they can never turn the error into a
        # no-signal or gain authority.
        if evaluation_error is not None:
            try:
                rows, consumed_hash = _validated_consumed_rows(
                    consumed_closed_rows
                )
                consumed_count = len(rows)
                latest_closed_h1_ts_ms = _strict_int(
                    rows[-1][0], "consumed_bar_start_ts_ms"
                ) + H1_MS
                latest_row_hash = _sha256(_canonical(rows[-1]))
            except Exception:
                consumed_count = 0
                consumed_hash = None
                latest_closed_h1_ts_ms = None
                latest_row_hash = None
            try:
                runtime_hash = _runtime_contract_hash(runtime_contract)
                raw_params = runtime_contract.get("params")
                if isinstance(raw_params, Mapping):
                    effective_config = dict(raw_params)
            except Exception:
                runtime_hash = None
                effective_config = None
            try:
                source_hash = _source_hash(source_files, expected_source_hashes)
            except Exception:
                source_hash = None
            try:
                manifest_hash = _sha256_field(
                    source_manifest_sha256, "source_manifest_sha256"
                )
            except Exception:
                manifest_hash = None
            try:
                normalized_caller_context = _validated_caller_context(
                    caller_context,
                    symbol=safe_symbol,
                )
            except Exception:
                normalized_caller_context = None
            raise evaluation_error
        max_age = _strict_int(max_decision_age_ms, "max_decision_age_ms")
        if safe_observed <= 0 or max_age <= 0:
            raise ContractViolation("invalid_att1_decision_time")
        rows, consumed_hash = _validated_consumed_rows(consumed_closed_rows)
        consumed_count = len(rows)
        runtime_hash = _runtime_contract_hash(runtime_contract)
        raw_params = runtime_contract.get("params")
        assert isinstance(raw_params, Mapping)
        effective_config = dict(raw_params)
        source_hash = _source_hash(source_files, expected_source_hashes)
        _bind_runtime_contract_to_strategy_source(runtime_contract, source_files)
        manifest_hash = _sha256_field(
            source_manifest_sha256, "source_manifest_sha256"
        )
        normalized_caller_context = _validated_caller_context(
            caller_context,
            symbol=safe_symbol,
        )
        latest_bytes = _canonical(rows[-1])
        evidence = closed_h1_evidence_from_row(
            rows[-1],
            row_bytes=latest_bytes,
            observed_at_ms=safe_observed,
            max_decision_age_ms=max_age,
        )
        latest_closed_h1_ts_ms = evidence.closed_h1_ts_ms
        latest_row_hash = evidence.data_hash

        regime_allows: bool | None = None
        if regime_required:
            if persisted_regime_receipt is None:
                raise BTCRegimeContractError(
                    "missing_persisted_btc_regime_receipt"
                )
            persisted = regime_evidence(
                persisted_regime_receipt,
                observed_at_ms=safe_observed,
                max_age_ms=max_age,
            )
            if persisted.closed_h1_ts_ms != latest_closed_h1_ts_ms:
                raise BTCRegimeContractError("regime_decision_bar_mismatch")
            regime_allows = persisted.allows("ATT1")
            regime_payload = {
                "enabled": True,
                "receipt_sha256": persisted_regime_receipt.receipt_sha256,
                "state_sha256": persisted_regime_receipt.state.state_sha256,
                "closed_h1_ts_ms": persisted.closed_h1_ts_ms,
                "value": persisted.value,
                "allows_att1": regime_allows,
            }

        if signal is None:
            explicit_reason = str(no_signal_reason or "").strip()
            if not explicit_reason:
                raise ContractViolation("missing_no_signal_reason")
            decision: dict[str, object] = {
                "kind": "no_signal",
                "no_signal_reason": explicit_reason,
                "plan": None,
            }
            status = "NO_SIGNAL"
        else:
            if str(no_signal_reason or ""):
                raise ContractViolation("signal_carries_no_signal_reason")
            if str(signal.symbol or "").strip().upper() != safe_symbol:
                raise ContractViolation("att1_signal_symbol_mismatch")
            plan = adapt_att1_live_signal_to_plan(
                signal,
                evidence,
                runtime_contract,
                source_files=source_files,
                expected_source_hashes=expected_source_hashes,
            )
            exchange = normalized_caller_context["exchange_filter"]
            assert isinstance(exchange, Mapping)
            plan = apply_exchange_stop_filter(plan, exchange["tick_size"])
            decision = {
                **plan.decision_payload(),
                "decision_id": plan.decision_id,
                "kind": "signal",
            }
            status = "REGIME_BLOCKED" if regime_allows is False else "SIGNAL"

        payload = _base_payload(
            symbol=safe_symbol,
            observed_at_ms=safe_observed,
            consumed_rows_count=consumed_count,
            consumed_rows_sha256=consumed_hash,
            latest_closed_h1_ts_ms=latest_closed_h1_ts_ms,
            latest_closed_row_sha256=latest_row_hash,
            runtime_contract_sha256=runtime_hash,
            effective_config=effective_config,
            source_bundle_sha256=source_hash,
            source_manifest_sha256=manifest_hash,
            caller_context=normalized_caller_context,
            regime_required=regime_required,
        )
        payload.update(
            {
                "status": status,
                "decision": decision,
                "regime": regime_payload,
                "exception": None,
            }
        )
        return _seal(payload)
    except Exception as exc:
        payload = _base_payload(
            symbol=safe_symbol,
            observed_at_ms=safe_observed,
            consumed_rows_count=consumed_count,
            consumed_rows_sha256=consumed_hash,
            latest_closed_h1_ts_ms=latest_closed_h1_ts_ms,
            latest_closed_row_sha256=latest_row_hash,
            runtime_contract_sha256=runtime_hash,
            effective_config=effective_config,
            source_bundle_sha256=source_hash,
            source_manifest_sha256=manifest_hash,
            caller_context=normalized_caller_context,
            regime_required=regime_required,
        )
        payload.update(
            {
                "status": "FAIL_CLOSED",
                "decision": {
                    "kind": "error",
                    "no_signal_reason": "",
                    "plan": None,
                },
                "regime": regime_payload,
                "exception": _exception_payload(
                    exc,
                    error_stage if evaluation_error is exc else "decision_contract",
                ),
            }
        )
        return _seal(payload)


def receipt_jsonl_bytes(receipt: Mapping[str, object]) -> bytes:
    """Verify the self hash and return deterministic one-record JSONL bytes."""

    if not isinstance(receipt, Mapping) or receipt.get("schema_id") != RECEIPT_SCHEMA_ID:
        raise ContractViolation("invalid_att1_caller_receipt_schema")
    raw = dict(receipt)
    expected = _sha256_field(raw.pop("receipt_sha256", None), "receipt_sha256")
    if _sha256(_canonical(raw)) != expected:
        raise ContractViolation("att1_caller_receipt_hash_mismatch")
    for field in (
        "money_authority",
        "orders_allowed",
        "private_api_allowed",
        "release_or_promotion_authority",
    ):
        if raw.get(field) is not False:
            raise ContractViolation("att1_caller_receipt_authority_forbidden", field)
    if raw.get("research_only") is not True:
        raise ContractViolation("att1_caller_receipt_not_research_only")
    return _canonical(dict(receipt)) + b"\n"


def append_att1_decision_receipt(
    path: Path | str, receipt: Mapping[str, object]
) -> None:
    """Append exactly one locked, fsynced JSONL record with mode ``0600``."""

    payload = receipt_jsonl_bytes(receipt)
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_APPEND
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(target, flags, FILE_MODE)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ReceiptPersistenceError("att1_receipt_journal_not_regular")
            os.fchmod(fd, FILE_MODE)
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short att1 receipt append")
                    view = view[written:]
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    except (OSError, ContractViolation) as exc:
        raise ReceiptPersistenceError("att1_receipt_append_failed") from exc


def load_att1_source_inputs(
    root: Path | str, manifest_path: Path | str
) -> tuple[dict[str, bytes], dict[str, str], str]:
    """Read only the hash-bound source closure from the existing manifest."""

    root_path = Path(root).resolve()
    candidate = Path(manifest_path)
    path = candidate if candidate.is_absolute() else root_path / candidate
    try:
        manifest_bytes = path.read_bytes()
        raw = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("att1_source_manifest_unreadable") from exc
    if (
        not isinstance(raw, Mapping)
        or raw.get("schema_id") != SOURCE_MANIFEST_SCHEMA_ID
        or not isinstance(raw.get("source_files"), list)
    ):
        raise ContractViolation("invalid_att1_source_manifest")
    records: dict[str, str] = {}
    for item in raw["source_files"]:
        if not isinstance(item, Mapping):
            raise ContractViolation("invalid_att1_source_manifest")
        item_path = str(item.get("path") or "").strip().replace("\\", "/")
        if item_path in ATT1_SOURCE_PATHS:
            if item_path in records:
                raise ContractViolation("duplicate_att1_source_manifest_path")
            records[item_path] = _sha256_field(
                item.get("sha256"), f"source:{item_path}"
            )
    if frozenset(records) != ATT1_SOURCE_PATHS:
        raise ContractViolation("att1_source_manifest_paths_mismatch")
    files = {item: (root_path / item).read_bytes() for item in ATT1_SOURCE_PATHS}
    _source_hash(files, records)
    return files, records, _sha256(manifest_bytes)


__all__ = [
    "ATT1_CALLER_RECEIPTS_ENABLED_BY_DEFAULT",
    "ATT1_SOURCE_PATHS",
    "RECEIPT_SCHEMA_ID",
    "ReceiptPersistenceError",
    "append_att1_decision_receipt",
    "build_att1_decision_receipt",
    "load_att1_source_inputs",
    "receipt_jsonl_bytes",
]
