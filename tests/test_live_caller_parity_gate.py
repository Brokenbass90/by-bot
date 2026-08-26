from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path

import pytest

from bot.live_caller_parity_gate import (
    FIXED51,
    MAJOR8,
    ParityGateViolation,
    load_verified_runtime_journal,
    verify_fixed51_evidence_manifest,
    verify_fixed51_runtime_cycles,
    verify_live_config,
)


ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json"


def _fixture(tmp_path: Path) -> Path:
    for rel in (
        "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json",
        "configs/research/att1_fixed51_public_shadow_manifest_v1.json",
        "configs/research/sbr1_fixed51_evidence_manifest_v1.json",
        "configs/att1_fixed51_zero_risk_shadow_v1.json",
        "configs/sbr1_zero_risk_shadow_v1.json",
        "configs/research/att1_sbr1_live_native_parity_candidate.env",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    return tmp_path / "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json"


def test_p4_manifest_passes_and_keeps_evidence_separate_from_money(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    report = verify_fixed51_evidence_manifest(tmp_path, path)
    assert report["decision"] == "PASS"
    assert tuple(report["evidence_universe"]) == FIXED51
    assert tuple(report["money_universe"]) == MAJOR8
    assert report["expected_structurally_unavailable"] == {"HFTUSDT": "bybit_linear_status_closed_observed_2026-08-24"}
    assert report["sealed_holdout_rows_decoded"] == 0


def test_p4_rejects_universe_drift_with_stable_code(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    raw = json.loads(path.read_text())
    raw["evidence_universe"] = list(raw["evidence_universe"][:-1])
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ParityGateViolation, match="p4_evidence_universe_identity_mismatch"):
        verify_fixed51_evidence_manifest(tmp_path, path)


def test_p4_rejects_structural_hft_substitution(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    raw = json.loads(path.read_text())
    raw["expected_structurally_unavailable"] = {"HFTUSDT": "replaced"}
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ParityGateViolation, match="p4_unavailable_symbol_contract_mismatch"):
        verify_fixed51_evidence_manifest(tmp_path, path)


def test_p4_rejects_attached_artifact_byte_drift(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    shadow = tmp_path / "configs/research/att1_fixed51_public_shadow_manifest_v1.json"
    shadow.write_text(shadow.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ParityGateViolation, match="ATT1_manifest_file_hash_mismatch"):
        verify_fixed51_evidence_manifest(tmp_path, path)


def test_p5_positive_fixture_passes_only_with_exact_effective_contract(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    expected = json.loads(path.read_text())["effective_config_contract"]
    report = verify_live_config(tmp_path, path, expected)
    assert report["decision"] == "PASS"
    assert report["fail_codes"] == []
    assert report["sealed_holdout_rows_decoded"] == 0


def test_p5_each_effective_drift_is_machine_readable(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    actual = json.loads(path.read_text())["effective_config_contract"]
    actual["ATT1_TIME_STOP_BARS_5M"] = "2016"
    report = verify_live_config(tmp_path, path, actual)
    assert report["decision"] == "FAIL"
    assert report["fail_codes"] == [
        "effective_config_mismatch:ATT1_TIME_STOP_BARS_5M:expected=4032:actual=2016"
    ]


def test_p5_checks_trailing_is_disabled_by_multiplier_not_activation_threshold(
    tmp_path: Path,
) -> None:
    path = _fixture(tmp_path)
    expected = json.loads(path.read_text())["effective_config_contract"]

    assert expected["ATT1_TRAIL_ATR_MULT"] == "0"
    assert "ATT1_TRAIL_ACTIVATE_RR" not in expected


def test_p5_p4_blocker_is_not_coerced_to_pass(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    raw = json.loads(path.read_text())
    raw["shadows"]["SBR1"]["journal_path"] = raw["shadows"]["ATT1"]["journal_path"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    report = verify_live_config(tmp_path, path, {})
    assert report["decision"] == "BLOCKED"
    assert report["fail_codes"] == ["p4_shadow_journals_not_separate"]


def _runtime_event(
    sleeve: str,
    symbol: str,
    *,
    close_ts: int = 1_800_000_000_000,
) -> dict[str, object]:
    unavailable = symbol == "HFTUSDT"
    if sleeve == "ATT1":
        return {
            "event_type": (
                "expected_symbol_unavailable" if unavailable else "raw_decision"
            ),
            "payload": {
                "symbol": symbol,
                "closed_h1_ts_ms": close_ts,
                "status": (
                    "RAW_DECISION_SHADOW_EXPECTED_UNAVAILABLE"
                    if unavailable
                    else "RAW_DECISION_SHADOW_NO_SIGNAL"
                ),
                "money_authority": False,
                "orders_allowed": False,
                "private_api_allowed": False,
                "release_or_promotion_authority": False,
                "evidence_admitted": False,
                "final_n_eligible": False,
            },
        }
    return {
        "event_type": "evaluation_unavailable" if unavailable else "evaluation",
        "payload": {
            "symbol": symbol,
            "closed_h1_ts_ms": close_ts,
            "status": "expected_structural_gap" if unavailable else "raw_no_signal",
            "evidence_role": (
                "major8_existing_lifecycle"
                if symbol in MAJOR8
                else "preparity_raw_not_final_n"
            ),
            "money_authority": False,
            "orders_allowed": False,
            "promotion_eligible": False,
        },
    }


def test_p4_runtime_cycles_prove_exact_fixed51_and_separate_money_universe() -> None:
    att1 = [
        {"event_type": "cycle_receipt", "payload": {"status": "ok"}},
        *[_runtime_event("ATT1", symbol) for symbol in FIXED51],
    ]
    sbr_symbols = tuple(dict.fromkeys((*FIXED51, *MAJOR8)))
    sbr1 = [
        {"event_type": "regime_bootstrap", "payload": {"status": "ok"}},
        *[_runtime_event("SBR1", symbol) for symbol in sbr_symbols],
    ]

    receipt = verify_fixed51_runtime_cycles(att1, sbr1)

    assert receipt["decision"] == "PASS"
    assert receipt["closed_h1_ts_ms"] == 1_800_000_000_000
    assert receipt["ATT1"]["cycle_symbol_count"] == 51
    assert receipt["SBR1"]["cycle_symbol_count"] == 54
    assert receipt["SBR1"]["fixed51_evidence_symbol_count"] == 51
    assert receipt["SBR1"]["money_only_extra_symbols"] == [
        "DOTUSDT",
        "LINKUSDT",
        "LTCUSDT",
    ]
    assert receipt["orders_created_or_changed"] == 0


def test_p4_runtime_cycles_fail_on_missing_symbol_or_unsafe_authority() -> None:
    att1 = [_runtime_event("ATT1", symbol) for symbol in FIXED51]
    sbr_symbols = tuple(dict.fromkeys((*FIXED51, *MAJOR8)))
    sbr1 = [_runtime_event("SBR1", symbol) for symbol in sbr_symbols]
    att1.pop()
    with pytest.raises(ParityGateViolation, match="ATT1_latest_cycle_universe_mismatch"):
        verify_fixed51_runtime_cycles(att1, sbr1)

    att1 = [_runtime_event("ATT1", symbol) for symbol in FIXED51]
    att1[0]["payload"]["orders_allowed"] = True
    with pytest.raises(ParityGateViolation, match="ATT1_runtime_unsafe_authority:orders_allowed"):
        verify_fixed51_runtime_cycles(att1, sbr1)


def _canon(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _write_runtime_journal(path: Path, sleeve: str, events: list[dict]) -> None:
    previous = "0" * 64
    lines: list[bytes] = []
    for index, source in enumerate(events):
        event_type = str(source["event_type"])
        payload = source["payload"]
        claim = f"{sleeve}:{index}"
        if sleeve == "ATT1":
            body = {
                "schema_id": "att1_fixed51_raw_shadow_event_v2",
                "event_type": event_type,
                "claim_key": claim,
                "identity_sha256": "c" * 64,
                "payload": payload,
                "previous_event_hash": previous,
            }
        else:
            body = {
                "claim_key": claim,
                "event_type": event_type,
                "payload": payload,
            }
        event_id = hashlib.sha256(_canon(body)).hexdigest()
        event_hash = hashlib.sha256(
            _canon({"event_id": event_id, "previous_event_hash": previous})
        ).hexdigest()
        if sleeve == "ATT1":
            row = {**body, "event_id": event_id, "event_hash": event_hash}
        else:
            row = {
                "schema_id": "sbr1_zero_risk_shadow_event_v1",
                "event_type": event_type,
                "claim_key": claim,
                "payload": payload,
                "event_id": event_id,
                "previous_event_hash": previous,
                "event_hash": event_hash,
            }
        lines.append(_canon(row) + b"\n")
        previous = event_hash
    path.write_bytes(b"".join(lines))
    os.chmod(path, 0o600)


def test_p4_runtime_journal_loader_verifies_native_hash_chains(tmp_path: Path) -> None:
    path = tmp_path / "att1.jsonl"
    expected = [_runtime_event("ATT1", symbol) for symbol in FIXED51]
    _write_runtime_journal(path, "ATT1", expected)

    loaded = load_verified_runtime_journal(path, sleeve="ATT1")

    assert len(loaded) == 51
    verify_fixed51_runtime_cycles(
        loaded,
        [_runtime_event("SBR1", symbol) for symbol in tuple(dict.fromkeys((*FIXED51, *MAJOR8)))],
    )
    damaged = path.read_bytes().replace(b"RAW_DECISION_SHADOW_NO_SIGNAL", b"RAW_DECISION_SHADOW_BAD_SIGNAL", 1)
    path.write_bytes(damaged)
    with pytest.raises(ParityGateViolation, match="ATT1_runtime_journal_event_id_mismatch"):
        load_verified_runtime_journal(path, sleeve="ATT1")
