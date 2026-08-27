#!/usr/bin/env python3
"""Fail-closed, owner-authorized one-shot ATT1/SBR1 reserved OOS runner.

The CLI deliberately exposes no inputs: all identities and destinations are
frozen by the diagnostic configuration and owner authorization. This is
research-only and never imports a broker or order path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONFIG_REL = Path("configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json")
AUTHORIZATION_REL = Path("configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json")
OUTPUT_REL = Path("research_lab/results/att1_sbr1_reserved_oos_v1")
CLAIM_REL = OUTPUT_REL / "one_shot_claim.json"
RECEIPT_REL = OUTPUT_REL / "receipt.json"
AUDIT_REL = Path("scripts/audit_att1_sbr1_reserved_oos_v1.py")
RUNNER_REL = Path("scripts/run_att1_sbr1_reserved_oos_v1.py")
MANIFEST_REL = Path("configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json")
START_UTC = "2025-10-01T00:00:00Z"
END_UTC = "2026-07-01T00:00:00Z"
START_MS = 1_759_276_800_000
END_MS = 1_782_864_000_000
M5_MS = 300_000
EXPECTED_ROWS = 273 * 288
MAJOR8 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT")


class OneShotViolation(RuntimeError):
    """A safety condition prevented or terminated the one-shot diagnostic."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", "..", ".git"} for part in relative.parts):
        raise OneShotViolation(f"unsafe path:{relative}")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise OneShotViolation(f"symlink path:{relative}")
    if not current.is_file():
        raise OneShotViolation(f"missing regular file:{relative}")
    return current


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OneShotViolation(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OneShotViolation(f"{label} malformed") from exc
    if not isinstance(value, dict):
        raise OneShotViolation(f"{label} must be an object")
    return value


def _pin(root: Path, row: Mapping[str, object], *, expected_path: Path | None = None) -> tuple[Path, str]:
    raw = str(row.get("path") or "")
    relative = Path(raw)
    if expected_path is not None and relative != expected_path:
        raise OneShotViolation(f"pinned path drift:{raw}")
    path = _safe_file(root, relative)
    expected, actual = str(row.get("sha256") or ""), _sha_file(path)
    if len(expected) != 64 or actual != expected:
        raise OneShotViolation(f"pinned SHA drift:{raw}")
    return path, actual


def _validate_manifest_metadata(manifest: Mapping[str, Any]) -> None:
    exact = {
        "schema_id": "att1_sbr1_reserved_m5_input_manifest_v1",
        "authority": "identity_only_materialized_without_scoring_no_live_no_broker",
        "market_rows_decoded_by_preflight": 0, "performance_computed": False, "money_authority": False,
        "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC}, "timeframe_minutes": 5,
    }
    if any(manifest.get(key) != value for key, value in exact.items()):
        raise OneShotViolation("reserved input manifest metadata drift")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(MAJOR8):
        raise OneShotViolation("reserved input inventory drift")
    if [str(row.get("symbol") or "") for row in inputs if isinstance(row, Mapping)] != list(MAJOR8):
        raise OneShotViolation("reserved input universe drift")


def _validate_config(root: Path) -> tuple[dict[str, Any], Path, dict[str, Any], Path, dict[str, Any]]:
    config_path = _safe_file(root, CONFIG_REL)
    config = _read_object(config_path, "diagnostic config")
    frozen, fingerprint = dict(config), str(config.get("config_fingerprint_sha256") or "")
    frozen.pop("config_fingerprint_sha256", None)
    if fingerprint != _canonical_sha(frozen):
        raise OneShotViolation("diagnostic config fingerprint drift")
    exact = {
        "schema_id": "att1_sbr1_reserved_oos_diagnostic_preflight_config_v1",
        "authority": "metadata_only_no_reserved_market_decode_no_live_no_broker_no_money_no_promotion",
        "classification": "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION",
        "money_authority": False, "orders_allowed": False, "private_api_allowed": False,
    }
    if any(config.get(key) != value for key, value in exact.items()):
        raise OneShotViolation("diagnostic authority drift")
    if config.get("reserved_window") != {"start_utc": START_UTC, "end_utc_exclusive": END_UTC, "calendar_days": 273}:
        raise OneShotViolation("reserved window drift")
    candidate_row = config.get("candidate_manifest")
    if not isinstance(candidate_row, Mapping):
        raise OneShotViolation("candidate pin missing")
    candidate_path, _ = _pin(root, candidate_row, expected_path=Path("configs/research/att1_sbr1_live_native_parity_v1.json"))
    candidate = _read_object(candidate_path, "candidate manifest")
    if candidate.get("universe") != list(MAJOR8) or candidate.get("sealed_holdout_guard") != {"start_utc": START_UTC, "end_utc_exclusive": END_UTC, "must_not_read": True}:
        raise OneShotViolation("frozen candidate drift")
    source_pins = config.get("source_pins")
    if not isinstance(source_pins, list) or not source_pins:
        raise OneShotViolation("source pins missing")
    for row in source_pins:
        if not isinstance(row, Mapping):
            raise OneShotViolation("source pin malformed")
        _pin(root, row)
    source_files = candidate.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        raise OneShotViolation("candidate source pins missing")
    for row in source_files:
        if not isinstance(row, Mapping):
            raise OneShotViolation("candidate source pin malformed")
        _pin(root, row)
    future = config.get("future_one_shot")
    if not isinstance(future, Mapping) or any(future.get(key) is not True for key in ("atomic_claim_before_market_decode", "refuse_second_attempt", "owner_authorization_required")):
        raise OneShotViolation("one-shot safety contract drift")
    _pin(root, {"path": future.get("runner_path"), "sha256": future.get("runner_sha256")}, expected_path=RUNNER_REL)
    _pin(root, {"path": future.get("audit_path"), "sha256": future.get("audit_sha256")}, expected_path=AUDIT_REL)
    data = config.get("reserved_data_contract")
    if not isinstance(data, Mapping) or data.get("preflight_may_open_or_hash_market_files") is not False:
        raise OneShotViolation("reserved input contract drift")
    manifest_row = data.get("reserved_m5_input_manifest")
    if not isinstance(manifest_row, Mapping):
        raise OneShotViolation("reserved input manifest pin missing")
    manifest_path, _ = _pin(root, manifest_row, expected_path=MANIFEST_REL)
    manifest = _read_object(manifest_path, "reserved input manifest")
    _validate_manifest_metadata(manifest)
    return config, config_path, candidate, manifest_path, manifest


def _validate_authorization(root: Path, config_path: Path, manifest_path: Path) -> tuple[dict[str, Any], Path]:
    authorization_path = _safe_file(root, AUTHORIZATION_REL)
    authorization = _read_object(authorization_path, "authorization")
    exact = {
        "schema_id": "att1_sbr1_reserved_oos_owner_authorization_v1",
        "authority": "owner_explicit_one_shot_reserved_diagnostic_only",
        "execute_once": True, "known_contamination_acknowledged": True, "money_authority": False,
        "reserved_window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC, "calendar_days": 273},
        "output_path": OUTPUT_REL.as_posix(), "claim_path": CLAIM_REL.as_posix(),
    }
    if any(authorization.get(key) != value for key, value in exact.items()) or not str(authorization.get("owner_authorization_id") or "").strip():
        raise OneShotViolation("authorization contract drift")
    expected_hashes = {
        "config_sha256": _sha_file(config_path), "input_manifest_sha256": _sha_file(manifest_path),
        "runner_sha256": _sha_file(_safe_file(root, RUNNER_REL)), "audit_sha256": _sha_file(_safe_file(root, AUDIT_REL)),
    }
    if any(authorization.get(key) != value for key, value in expected_hashes.items()):
        raise OneShotViolation("authorization SHA drift")
    return authorization, authorization_path


def _fsync_parent(path: Path) -> None:
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _exclusive_claim(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OneShotViolation("ONE_SHOT_ALREADY_CONSUMED") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_parent(path)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_parent(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OneShotViolation(f"invalid decimal:{field}") from exc
    if not result.is_finite():
        raise OneShotViolation(f"invalid decimal:{field}")
    return result


def threshold_checks(metrics: Mapping[str, object], thresholds: Mapping[str, object]) -> dict[str, bool]:
    return {
        "n_gte": int(metrics["n"]) >= int(thresholds["n_gte"]),
        "mean_r_gt": _decimal(metrics["mean_r"], "mean_r") > _decimal(thresholds["mean_r_gt"], "mean_r_gt"),
        "profit_factor_gte": metrics.get("profit_factor") is not None and _decimal(metrics["profit_factor"], "profit_factor") >= _decimal(thresholds["profit_factor_gte"], "profit_factor_gte"),
        "both_halves_r_gt": all(_decimal(value, "half") > _decimal(thresholds["both_halves_r_gt"], "both_halves_r_gt") for value in metrics["chronological_halves_r"]),
        "max_sequential_drawdown_r_lte": _decimal(metrics["max_sequential_drawdown_r"], "drawdown") <= _decimal(thresholds["max_sequential_drawdown_r_lte"], "drawdown_limit"),
        "positive_month_fraction_gte": _decimal(metrics["positive_month_fraction"], "month_fraction") >= _decimal(thresholds["positive_month_fraction_gte"], "month_limit"),
        "positive_symbol_concentration_lte": _decimal(metrics["positive_symbol_concentration"], "concentration") <= _decimal(thresholds["positive_symbol_concentration_lte"], "concentration_limit"),
        "minimum_leave_one_symbol_out_r_gt": _decimal(metrics["minimum_leave_one_symbol_out_r"], "loso") > _decimal(thresholds["minimum_leave_one_symbol_out_r_gt"], "loso_limit"),
    }


def three_way_decision(base: Mapping[str, object], stress: Mapping[str, object], thresholds: Mapping[str, object], *, negative_stress_n: int) -> str:
    if all(threshold_checks(base, thresholds).values()) and all(threshold_checks(stress, thresholds).values()):
        return "PASS_ZERO_RISK_INTEGRATION_ONLY"
    n_gte = int(thresholds["n_gte"])
    if (int(base["n"]) >= n_gte and int(stress["n"]) >= n_gte) or (int(stress["n"]) >= negative_stress_n and _decimal(stress["sum_r"], "sum_r") < 0):
        return "FAIL_CLOSED"
    return "INCONCLUSIVE_LOW_N"


def _decode_inputs(root: Path, manifest: Mapping[str, Any], opener: Callable[[Path], bytes]) -> dict[str, dict[str, Any]]:
    decoded: dict[str, dict[str, Any]] = {}
    for item in manifest["inputs"]:
        assert isinstance(item, Mapping)
        symbol, path = str(item["symbol"]), _safe_file(root, Path(str(item["source_path"])))
        raw = opener(path)
        if len(raw) != int(item["bytes"]) or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise OneShotViolation(f"reserved input hash drift:{symbol}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OneShotViolation(f"reserved input JSON drift:{symbol}") from exc
        expected = {"schema_id": "att1_sbr1_reserved_m5_payload_v1", "authority": "identity_only_materialized_without_scoring_no_live_no_broker", "symbol": symbol, "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC}, "timeframe_minutes": 5, "performance_computed": False, "money_authority": False}
        if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in expected.items()):
            raise OneShotViolation(f"reserved input schema/window drift:{symbol}")
        records = payload.get("records")
        if not isinstance(records, list) or len(records) != EXPECTED_ROWS or int(item["rows"]) != EXPECTED_ROWS:
            raise OneShotViolation(f"reserved input row-count drift:{symbol}")
        timestamps = [int(row["ts_ms"]) for row in records if isinstance(row, Mapping)]
        if len(timestamps) != EXPECTED_ROWS or timestamps[0] != START_MS or timestamps[-1] != END_MS - M5_MS or any(right - left != M5_MS for left, right in zip(timestamps, timestamps[1:])):
            raise OneShotViolation(f"reserved input M5 gap drift:{symbol}")
        if int(item["first_ts_ms"]) != START_MS or int(item["last_ts_ms"]) != END_MS - M5_MS:
            raise OneShotViolation(f"reserved input identity drift:{symbol}")
        decoded[symbol] = payload
    return decoded


def _thresholds(root: Path, config: Mapping[str, Any]) -> dict[str, Mapping[str, object]]:
    row = config.get("threshold_source")
    if not isinstance(row, Mapping):
        raise OneShotViolation("threshold source missing")
    path, _ = _pin(root, row)
    receipt = _read_object(path, "threshold receipt")
    sleeves = receipt.get("sleeves")
    if not isinstance(sleeves, Mapping):
        raise OneShotViolation("threshold sleeves missing")
    out: dict[str, Mapping[str, object]] = {}
    for sleeve in ("ATT1", "SBR1"):
        sleeve_row = sleeves.get(sleeve)
        gate = sleeve_row.get("zero_risk_shadow_gate") if isinstance(sleeve_row, Mapping) else None
        if not isinstance(gate, Mapping) or not isinstance(gate.get("thresholds"), Mapping):
            raise OneShotViolation(f"threshold missing:{sleeve}")
        out[sleeve] = dict(gate["thresholds"])
    return out


def _real_scorer(
    *, root: Path, output: Path, candidate: Mapping[str, Any], market: Mapping[str, Mapping[str, Any]]
) -> object:
    """Invoke the unchanged live-native sleeve boundary on verified in-memory data."""
    from bot.live_native_manifest import VerifiedParityManifest
    from research_lab import run_att1_sbr1_actual_adapter_parity as parity

    market_data = {}
    for symbol, payload in market.items():
        rows = tuple(
            (int(row["ts_ms"]), row["open"], row["high"], row["low"], row["close"], row["volume"])
            for row in payload["records"]
        )
        h1 = parity._aggregate_h1(rows)
        market_data[symbol] = parity.MarketData(
            symbol=symbol, m5=rows, h1=h1,
            m5_index={int(row[0]): index for index, row in enumerate(rows)},
            h1_index={int(row[0]): index for index, row in enumerate(h1)},
        )
    view = dict(candidate)
    view["window"] = {"start_utc": START_UTC, "end_utc_exclusive": END_UTC}
    manifest = VerifiedParityManifest(
        path=Path("<verified-reserved-in-memory>"), manifest_sha256=_canonical_sha(view),
        universe=MAJOR8, source_bundle_sha256="verified-candidate-sources",
        data_bundle_sha256="verified-reserved-inputs", payload=view,
    )
    output.mkdir(parents=True, exist_ok=True)
    regime = parity._build_regime_map(market_data["BTCUSDT"].h1)
    with parity._frozen_env(manifest.universe):
        return {
            sleeve: parity._run_sleeve(sleeve, root, output, manifest, market_data, regime)
            for sleeve in ("ATT1", "SBR1")
        }


def _summarize_ledgers(
    output: Path, thresholds_by_sleeve: Mapping[str, Mapping[str, object]], *, negative_stress_n: int
) -> dict[str, object]:
    from research_lab.adapter_parity import read_jsonl
    from research_lab.summarize_att1_sbr1_presealed_economics import chronological_symbol_occupancy, metrics

    sleeves: dict[str, object] = {}
    for sleeve in ("ATT1", "SBR1"):
        modes: dict[str, object] = {}
        for mode in ("base", "stress"):
            research = read_jsonl(output / f"{sleeve.lower()}_{mode}_research.jsonl")
            live = read_jsonl(output / f"{sleeve.lower()}_{mode}_live.jsonl")
            if research != live:
                raise OneShotViolation(f"research/live field parity drift:{sleeve}:{mode}")
            accepted = chronological_symbol_occupancy(live, sleeve)
            modes[mode] = {
                "raw_signals": len(live), "accepted_signals": len(accepted.rows),
                "same_symbol_occupancy_drops": accepted.overlap_drops,
                "metrics": metrics(accepted.rows), "parity": "PASS",
            }
        thresholds = thresholds_by_sleeve[sleeve]
        sleeves[sleeve] = {
            "modes": modes, "thresholds": dict(thresholds),
            "checks": {mode: threshold_checks(modes[mode]["metrics"], thresholds) for mode in ("base", "stress")},
            "decision": three_way_decision(
                modes["base"]["metrics"], modes["stress"]["metrics"], thresholds,
                negative_stress_n=negative_stress_n,
            ),
        }
    return sleeves


def run_one_shot(root: Path = ROOT, *, market_opener: Callable[[Path], bytes] | None = None, scorer: Callable[..., object] | None = None) -> dict[str, object]:
    """Run a frozen diagnostic; any post-claim failure irreversibly consumes it."""
    root = root.resolve()
    config, config_path, candidate, manifest_path, manifest = _validate_config(root)
    _, authorization_path = _validate_authorization(root, config_path, manifest_path)
    output, claim_path = root / OUTPUT_REL, root / CLAIM_REL
    if claim_path.exists() or claim_path.is_symlink():
        raise OneShotViolation("ONE_SHOT_ALREADY_CONSUMED")
    claim = {"schema_id": "att1_sbr1_reserved_oos_one_shot_claim_v1", "state": "CLAIMED_BEFORE_MARKET_DECODE", "claim_created_at_utc": _utc_now(), "authorization_sha256": _sha_file(authorization_path), "config_sha256": _sha_file(config_path), "input_manifest_sha256": _sha_file(manifest_path), "runner_sha256": _sha_file(_safe_file(root, RUNNER_REL)), "audit_sha256": _sha_file(_safe_file(root, AUDIT_REL)), "output_path": OUTPUT_REL.as_posix(), "claim_path": CLAIM_REL.as_posix()}
    _exclusive_claim(claim_path, claim)
    decode_started = _utc_now()
    try:
        market = _decode_inputs(root, manifest, market_opener or (lambda path: path.read_bytes()))
        (scorer or _real_scorer)(root=root, output=output, candidate=candidate, market=market)
        thresholds = _thresholds(root, config)
        sleeves = _summarize_ledgers(
            output, thresholds,
            negative_stress_n=int(config["decision_contract"]["negative_stress_sum_r_is_fail_when_n_gte"]),
        )
        receipt: dict[str, object] = {"schema_id": "att1_sbr1_reserved_oos_one_shot_receipt_v1", "authority": "research_only_reserved_diagnostic_no_live_no_broker_no_money_no_promotion", "classification": "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION", "money_authority": False, "promotion_authority": False, "live_or_broker_calls": False, "orders_created_or_changed": 0, "authorization_sha256": _sha_file(authorization_path), "config_sha256": _sha_file(config_path), "input_manifest_sha256": _sha_file(manifest_path), "runner_sha256": _sha_file(_safe_file(root, RUNNER_REL)), "audit_sha256": _sha_file(_safe_file(root, AUDIT_REL)), "market_decode_started_at_utc": decode_started, "market_decode_finished_at_utc": _utc_now(), "exact_rows_decoded": {symbol: len(payload["records"]) for symbol, payload in market.items()}, "output_path": OUTPUT_REL.as_posix(), "claim_path": CLAIM_REL.as_posix()}
        receipt["sleeves"] = sleeves
        receipt["output_file_sha256"] = {path.name: _sha_file(path) for path in sorted(output.glob("*.json*")) if path.name != "receipt.json"}
        receipt["receipt_sha256"] = _canonical_sha(receipt)
        _atomic_json(root / RECEIPT_REL, receipt)
        return receipt
    except Exception as exc:
        failure = {"schema_id": "att1_sbr1_reserved_oos_one_shot_receipt_v1", "terminal_state": "FAIL_CLOSED_AFTER_CLAIM", "authority": "research_only_reserved_diagnostic_no_live_no_broker_no_money_no_promotion", "money_authority": False, "promotion_authority": False, "market_decode_started_at_utc": decode_started, "market_decode_finished_at_utc": _utc_now(), "error": f"{type(exc).__name__}:{exc}", "claim_sha256": _sha_file(claim_path)}
        failure["receipt_sha256"] = _canonical_sha(failure)
        _atomic_json(root / RECEIPT_REL, failure)
        if isinstance(exc, OneShotViolation):
            raise
        raise OneShotViolation(f"FAIL_CLOSED_AFTER_CLAIM:{type(exc).__name__}") from exc


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main() -> int:
    build_parser().parse_args()
    try:
        receipt = run_one_shot(ROOT)
    except Exception as exc:
        print(json.dumps({"decision": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 2
    print(json.dumps({"receipt_sha256": receipt["receipt_sha256"], "money_authority": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
