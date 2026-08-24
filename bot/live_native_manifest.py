"""Fail-closed verifier for the ATT1/SBR1 pre-sealed parity manifest."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping


SCHEMA_ID = "att1_sbr1_live_native_parity_manifest_v1"
AUTHORITY = "research_only_no_live_no_broker_no_promotion"


class ManifestViolation(ValueError):
    pass


def _sha(value: object, field: str) -> str:
    result = str(value or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        raise ManifestViolation(f"invalid_sha256:{field}")
    return result


def _positive_decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ManifestViolation(f"invalid_decimal:{field}") from exc
    if not number.is_finite() or number <= 0:
        raise ManifestViolation(f"nonpositive_decimal:{field}")
    return number


def _nonnegative_decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ManifestViolation(f"invalid_decimal:{field}") from exc
    if not number.is_finite() or number < 0:
        raise ManifestViolation(f"negative_decimal:{field}")
    return number


def _utc_timestamp(value: object, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw.endswith("Z"):
        raise ManifestViolation(f"timestamp_not_utc_z:{field}")
    try:
        result = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise ManifestViolation(f"invalid_timestamp:{field}") from exc
    if result.tzinfo != timezone.utc:
        raise ManifestViolation(f"timestamp_not_utc:{field}")
    return result


def _relative_path(value: object, field: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise ManifestViolation(f"unsafe_path:{field}")
    return raw


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ManifestViolation("noncanonical_manifest") from exc


def _file_sha(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


@dataclass(frozen=True)
class VerifiedParityManifest:
    path: Path
    manifest_sha256: str
    universe: tuple[str, ...]
    source_bundle_sha256: str
    data_bundle_sha256: str
    payload: Mapping[str, object]


def _verify_file_rows(
    root: Path,
    rows: object,
    *,
    role: str,
    verify_bytes: bool,
) -> tuple[list[dict[str, object]], str]:
    if not isinstance(rows, list) or not rows:
        raise ManifestViolation(f"missing_{role}_files")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise ManifestViolation(f"invalid_{role}_file:{index}")
        rel = _relative_path(item.get("path"), f"{role}:{index}")
        if rel in seen:
            raise ManifestViolation(f"duplicate_{role}_path:{rel}")
        seen.add(rel)
        expected_sha = _sha(item.get("sha256"), f"{role}:{rel}")
        expected_bytes = item.get("bytes")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes <= 0:
            raise ManifestViolation(f"invalid_bytes:{role}:{rel}")
        if verify_bytes:
            full = root / rel
            if not full.is_file():
                raise ManifestViolation(f"missing_file:{rel}")
            actual_bytes, actual_sha = _file_sha(full)
            if actual_bytes != expected_bytes:
                raise ManifestViolation(f"byte_mismatch:{rel}")
            if actual_sha != expected_sha:
                raise ManifestViolation(f"sha_mismatch:{rel}")
        row = {"bytes": expected_bytes, "path": rel, "sha256": expected_sha}
        if role == "data":
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                raise ManifestViolation(f"missing_data_symbol:{rel}")
            row["symbol"] = symbol
        normalized.append(row)
    normalized.sort(key=lambda item: str(item["path"]))
    return normalized, hashlib.sha256(_canonical_bytes({"files": normalized, "role": role})).hexdigest()


def load_and_verify_manifest(
    root: Path,
    manifest_path: Path,
    *,
    verify_data_bytes: bool = True,
    verify_source_bytes: bool = True,
) -> VerifiedParityManifest:
    root = root.resolve()
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestViolation("manifest_unreadable") from exc
    if not isinstance(payload, dict):
        raise ManifestViolation("manifest_not_object")
    if payload.get("schema_id") != SCHEMA_ID:
        raise ManifestViolation("wrong_schema_id")
    if payload.get("authority") != AUTHORITY:
        raise ManifestViolation("wrong_authority")
    if payload.get("default_off") is not True or payload.get("enabled") is not False:
        raise ManifestViolation("manifest_not_default_off")
    if payload.get("money_authority") is not False or payload.get("live_or_broker_calls") is not False:
        raise ManifestViolation("manifest_claims_authority")

    window = payload.get("window")
    guard = payload.get("sealed_holdout_guard")
    if not isinstance(window, dict) or not isinstance(guard, dict):
        raise ManifestViolation("missing_window_guard")
    if window.get("end_utc_exclusive") != guard.get("start_utc"):
        raise ManifestViolation("presealed_window_boundary_mismatch")
    if guard.get("must_not_read") is not True:
        raise ManifestViolation("sealed_holdout_not_guarded")
    window_start = _utc_timestamp(window.get("start_utc"), "window_start")
    window_end = _utc_timestamp(window.get("end_utc_exclusive"), "window_end")
    guard_start = _utc_timestamp(guard.get("start_utc"), "guard_start")
    guard_end = _utc_timestamp(guard.get("end_utc_exclusive"), "guard_end")
    if not window_start < window_end == guard_start < guard_end:
        raise ManifestViolation("invalid_window_order")

    universe_raw = payload.get("universe")
    if not isinstance(universe_raw, list) or not universe_raw:
        raise ManifestViolation("missing_universe")
    universe = tuple(str(value or "").strip().upper() for value in universe_raw)
    if any(not value for value in universe) or len(set(universe)) != len(universe):
        raise ManifestViolation("invalid_universe")

    data_rows, data_hash = _verify_file_rows(
        root, payload.get("data_files"), role="data", verify_bytes=verify_data_bytes
    )
    if {str(row["symbol"]) for row in data_rows} != set(universe):
        raise ManifestViolation("data_universe_mismatch")
    _, source_hash = _verify_file_rows(
        root, payload.get("source_files"), role="source", verify_bytes=verify_source_bytes
    )

    filters = payload.get("exchange_filters")
    if not isinstance(filters, dict) or set(filters) != set(universe):
        raise ManifestViolation("exchange_filter_universe_mismatch")
    for symbol, values in filters.items():
        if not isinstance(values, dict):
            raise ManifestViolation(f"invalid_exchange_filter:{symbol}")
        _positive_decimal(values.get("tick_size"), f"tick_size:{symbol}")
        _positive_decimal(values.get("qty_step"), f"qty_step:{symbol}")
        _positive_decimal(values.get("min_notional"), f"min_notional:{symbol}")

    profiles = payload.get("profiles")
    regime = payload.get("regime_contract")
    costs = payload.get("cost_contracts")
    if not isinstance(profiles, dict) or set(profiles) != {"ATT1", "SBR1"}:
        raise ManifestViolation("missing_profiles")
    if not isinstance(regime, dict) or regime.get("timeframe") != "60" or regime.get("ema_period") != 200:
        raise ManifestViolation("invalid_regime_contract")
    if not isinstance(costs, dict) or set(costs) != {"base", "stress"}:
        raise ManifestViolation("invalid_cost_contracts")
    expected_cost_fields = {
        "fee_bps_per_side",
        "slippage_bps_per_side",
        "adverse_funding_bps_per_8h",
    }
    if any(
        not isinstance(costs[mode], dict)
        or set(costs[mode]) != expected_cost_fields
        for mode in ("base", "stress")
    ):
        raise ManifestViolation("invalid_cost_contract_fields")
    base_fee = _nonnegative_decimal(costs["base"].get("fee_bps_per_side"), "base_fee")
    base_slip = _nonnegative_decimal(costs["base"].get("slippage_bps_per_side"), "base_slippage")
    base_funding = _nonnegative_decimal(
        costs["base"].get("adverse_funding_bps_per_8h"), "base_funding"
    )
    stress_fee = _nonnegative_decimal(costs["stress"].get("fee_bps_per_side"), "stress_fee")
    stress_slip = _nonnegative_decimal(costs["stress"].get("slippage_bps_per_side"), "stress_slippage")
    stress_funding = _nonnegative_decimal(
        costs["stress"].get("adverse_funding_bps_per_8h"), "stress_funding"
    )
    if (
        stress_fee < base_fee
        or stress_slip < base_slip
        or stress_funding < base_funding
    ):
        raise ManifestViolation("stress_cost_below_base")

    manifest_hash = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return VerifiedParityManifest(
        path=path.resolve(),
        manifest_sha256=manifest_hash,
        universe=universe,
        source_bundle_sha256=source_hash,
        data_bundle_sha256=data_hash,
        payload=payload,
    )


__all__ = [
    "AUTHORITY",
    "ManifestViolation",
    "SCHEMA_ID",
    "VerifiedParityManifest",
    "load_and_verify_manifest",
]
