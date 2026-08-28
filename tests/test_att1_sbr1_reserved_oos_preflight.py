from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.preflight_att1_sbr1_reserved_oos_v1 import (
    EXPECTED_END_UTC_EXCLUSIVE,
    EXPECTED_START_UTC,
    PreflightViolation,
    build_preflight,
    calendar_days,
    canonical_sha256,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"


def test_exact_reserved_window_is_273_calendar_days() -> None:
    assert calendar_days(EXPECTED_START_UTC, EXPECTED_END_UTC_EXCLUSIVE) == 273


def test_canonical_preflight_is_metadata_only_and_known_contaminated() -> None:
    receipt = build_preflight(ROOT, CONFIG)

    assert receipt["classification"] == "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION"
    assert receipt["purity"] == "KNOWN_CONTAMINATED"
    assert receipt["reserved_window"] == {
        "start_utc": EXPECTED_START_UTC,
        "end_utc_exclusive": EXPECTED_END_UTC_EXCLUSIVE,
        "calendar_days": 273,
    }
    assert receipt["reserved_market_files_opened"] == 0
    assert receipt["reserved_market_rows_decoded"] == 0
    assert receipt["performance_computed"] is False
    assert receipt["orders_created_or_changed"] == 0
    assert receipt["money_authority"] is False
    assert receipt["decision"] == "READY_FOR_OWNER_AUTHORIZATION"
    assert receipt["blockers"] == []
    assert receipt["one_shot_command_ready"] is True
    assert receipt["verified_reserved_m5_manifest"]["inputs"] == 8
    assert {row["id"] for row in receipt["known_accesses"]} >= {
        "mpl_two_arm_holdout_20260812",
        "xsec_recount_reveal_modern_20260811",
    }
    assert receipt["preflight_implementation"] == {
        "path": "scripts/preflight_att1_sbr1_reserved_oos_v1.py",
        "sha256": sha256_file(ROOT / "scripts/preflight_att1_sbr1_reserved_oos_v1.py"),
    }


def test_preflight_freezes_live_native_major8_not_old_all137_contract() -> None:
    receipt = build_preflight(ROOT, CONFIG)

    frozen = receipt["frozen_candidate"]
    assert frozen["universe"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "ADAUSDT",
        "LINKUSDT",
        "LTCUSDT",
        "DOTUSDT",
        "SUIUSDT",
    ]
    assert frozen["profiles"]["ATT1"]["sl_atr_mult"] == "6.6"
    assert frozen["profiles"]["SBR1"]["sl_atr_mult"] == "4.6"
    assert frozen["execution_contract"]["entry"] == "next_m5_open"
    assert receipt["legacy_contracts_are_not_release_authority"] is True


@pytest.mark.parametrize(
    ("field", "blocker"),
    [
        ("reserved_m5_input_manifest", "RESERVED_M5_INPUT_MANIFEST_MISSING"),
        ("runner_sha256", "ONE_SHOT_RUNNER_NOT_FROZEN"),
        ("audit_sha256", "INDEPENDENT_AUDIT_NOT_FROZEN"),
    ],
)
def test_missing_frozen_identity_blocks_one_shot_release(tmp_path: Path, field: str, blocker: str) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if field == "reserved_m5_input_manifest":
        config["reserved_data_contract"][field] = None
    else:
        config["future_one_shot"][field] = None
    _refingerprint(config)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    receipt = build_preflight(ROOT, config_path)
    assert receipt["decision"] == "BLOCKED_FAIL_CLOSED"
    assert blocker in receipt["blockers"]
    assert receipt["reserved_market_files_opened"] == 0
    assert receipt["reserved_market_rows_decoded"] == 0


def _refingerprint(config: dict[str, object]) -> None:
    config.pop("config_fingerprint_sha256", None)
    config["config_fingerprint_sha256"] = canonical_sha256(config)


def test_future_one_shot_safety_flags_cannot_be_disabled(tmp_path: Path) -> None:
    root = _write_minimal_tree(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["future_one_shot"]["atomic_claim_before_market_decode"] = False
    _refingerprint(config)
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(PreflightViolation, match="one-shot safety contract changed"):
        build_preflight(root, config_path)


def test_arbitrary_market_file_cannot_be_added_as_source_pin(tmp_path: Path) -> None:
    root = _write_minimal_tree(tmp_path)
    market_path = root / "data" / "reserved.json"
    market_path.parent.mkdir(parents=True)
    market_path.write_text('[{"secret_reserved_row": 1}]', encoding="utf-8")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["source_pins"].append(
        {
            "role": "reserved_market_data",
            "path": "data/reserved.json",
            "sha256": sha256_file(market_path),
        }
    )
    _refingerprint(config)
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(PreflightViolation, match="source pin inventory changed"):
        build_preflight(root, config_path)


def test_unrelated_files_cannot_satisfy_manifest_runner_or_audit(tmp_path: Path) -> None:
    root = _write_minimal_tree(tmp_path)
    unrelated = root / "research_lab" / "mpl_v4_holdout.py"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    unrelated.write_bytes((ROOT / "research_lab/mpl_v4_holdout.py").read_bytes())
    unrelated_hash = sha256_file(unrelated)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["reserved_data_contract"]["reserved_m5_input_manifest"] = {
        "path": "research_lab/mpl_v4_holdout.py",
        "sha256": unrelated_hash,
    }
    config["future_one_shot"].update(
        {
            "runner_path": "research_lab/mpl_v4_holdout.py",
            "runner_sha256": unrelated_hash,
            "audit_path": "research_lab/mpl_v4_holdout.py",
            "audit_sha256": unrelated_hash,
        }
    )
    _refingerprint(config)
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(
        PreflightViolation,
        match="(reserved M5 manifest|one-shot runner) path changed",
    ):
        build_preflight(root, config_path)


def _write_minimal_tree(tmp_path: Path) -> Path:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for row in config["source_pins"]:
        target = tmp_path / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / row["path"]).read_bytes())
    for row in config["known_accesses"]:
        for evidence in row["evidence"]:
            target = tmp_path / evidence["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / evidence["path"]).read_bytes())
    return tmp_path


def test_source_pin_drift_fails_before_any_reserved_data_access(tmp_path: Path) -> None:
    root = _write_minimal_tree(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    drift = root / config["source_pins"][0]["path"]
    drift.write_text("drift", encoding="utf-8")

    with pytest.raises(PreflightViolation, match="source pin drift"):
        build_preflight(root, config_path)


def test_config_fingerprint_and_file_hash_are_stable() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    fingerprint = config.pop("config_fingerprint_sha256")
    assert fingerprint == canonical_sha256(config)
    assert len(sha256_file(CONFIG)) == 64
