from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"


def test_preexecution_audit_is_metadata_only_and_ready() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import build_preexecution_audit

    receipt = build_preexecution_audit(ROOT)

    assert receipt["decision"] == "READY_FOR_OWNER_AUTHORIZATION"
    assert receipt["reserved_market_files_opened"] == 0
    assert receipt["reserved_market_rows_decoded"] == 0
    assert receipt["performance_computed"] is False
    assert receipt["owner_authorization_present"] is False
    assert receipt["claim_present"] is False
    assert receipt["result_present"] is False


def test_preexecution_audit_rejects_authorization_claim_or_result(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, build_preexecution_audit

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    (tmp_path / "configs/research").mkdir(parents=True)
    (tmp_path / "configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json").write_text("{}\n")

    with pytest.raises(AuditViolation, match="owner authorization"):
        build_preexecution_audit(tmp_path, config=config)


def test_preexecution_audit_does_not_import_runner() -> None:
    import sys

    from scripts.audit_att1_sbr1_reserved_oos_v1 import build_preexecution_audit

    sys.modules.pop("scripts.run_att1_sbr1_reserved_oos_v1", None)
    build_preexecution_audit(ROOT)
    assert "scripts.run_att1_sbr1_reserved_oos_v1" not in sys.modules


def test_audit_receipt_self_hash_tampering_fails_closed() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, canonical_sha256, verify_audit_receipt

    receipt = {"schema_id": "fixture", "decision": "AUDIT_PASS_RESEARCH_ONLY", "money_authority": False}
    receipt["audit_receipt_sha256"] = canonical_sha256(receipt)
    verify_audit_receipt(receipt)
    receipt["decision"] = "PASS_ZERO_RISK_INTEGRATION_ONLY"
    with pytest.raises(AuditViolation, match="audit receipt self hash drift"):
        verify_audit_receipt(receipt)


def test_reported_runner_decision_tampering_fails_independent_check() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_reported_sleeves

    independent = {
        "ATT1": {"modes": {"base": {"metrics": {"n": 1}}, "stress": {"metrics": {"n": 1}}}, "checks": {"base": {"n_gte": False}, "stress": {"n_gte": False}}, "decision": "INCONCLUSIVE_LOW_N"},
        "SBR1": {"modes": {"base": {"metrics": {"n": 1}}, "stress": {"metrics": {"n": 1}}}, "checks": {"base": {"n_gte": False}, "stress": {"n_gte": False}}, "decision": "INCONCLUSIVE_LOW_N"},
    }
    reported = json.loads(json.dumps(independent))
    reported["ATT1"]["decision"] = "PASS_ZERO_RISK_INTEGRATION_ONLY"
    with pytest.raises(AuditViolation, match="runner sleeve decision drift:ATT1"):
        verify_reported_sleeves(reported, independent)


def test_postexecution_missing_artifacts_fail_before_ledger_access(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, audit_postexecution

    with pytest.raises(AuditViolation, match="missing regular file"):
        audit_postexecution(tmp_path)


def test_claim_receipt_timing_inversion_fails_closed() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_claim_timing

    with pytest.raises(AuditViolation, match="claim receipt timing inversion"):
        verify_claim_timing("2026-08-27T00:00:01Z", "2026-08-27T00:00:00Z", "2026-08-27T00:00:02Z")


def test_ledger_mismatch_fails_independent_comparator() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_ledger_parity

    with pytest.raises(AuditViolation, match="research/live ledger mismatch:ATT1:base"):
        verify_ledger_parity({("BTCUSDT", 1, "long"): {}}, {}, "ATT1", "base")


def test_missing_output_artifact_fails_exact_inventory(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_output_inventory

    with pytest.raises(AuditViolation, match="output hash inventory drift"):
        verify_output_inventory(tmp_path, {})


def test_manifest_top_level_schema_rejects_extra_or_missing_metadata() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, _validate_manifest_metadata

    manifest = json.loads((ROOT / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json").read_text())
    manifest["unexpected"] = True
    with pytest.raises(AuditViolation, match="reserved manifest top-level schema drift"):
        _validate_manifest_metadata(manifest)


def test_runner_sleeve_comparison_rejects_raw_occupancy_parity_or_threshold_drift() -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, verify_reported_sleeves

    mode = {"raw_signals": 2, "accepted_signals": 1, "same_symbol_occupancy_drops": 1, "metrics": {"n": 1}, "parity": {"decision": "PASS"}}
    independent = {sleeve: {"modes": {"base": dict(mode), "stress": dict(mode)}, "thresholds": {"n_gte": 2}, "checks": {"base": {"n_gte": False}, "stress": {"n_gte": False}}, "decision": "INCONCLUSIVE_LOW_N"} for sleeve in ("ATT1", "SBR1")}
    reported = json.loads(json.dumps(independent))
    reported["ATT1"]["modes"]["base"]["raw_signals"] = 3
    with pytest.raises(AuditViolation, match="runner sleeve metrics drift:ATT1:base"):
        verify_reported_sleeves(reported, independent)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_row(sleeve: str) -> dict[str, object]:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import canonical_sha256

    digest = "a" * 64
    frozen = {"config_hash": digest, "source_hash": digest, "data_hash": digest, "profile_hash": digest}
    decision_id = canonical_sha256(frozen)
    final_fill = {"decision_id": decision_id, "fill_id": "fill-1", "order_id": "order-1"}
    policy = {"spec_id": "spec-1", "profile_hash": digest}
    receipt = {"schema_id": "research_live_adapter_parity_receipt_v2", "claim_key": "claim-1", "decision_id": decision_id, "order_id": "order-1", "fill_id": "fill-1", "fill_fingerprint": canonical_sha256(final_fill), "policy_fingerprint": canonical_sha256(policy), "execution_fingerprint": digest}
    receipt["receipt_id"] = canonical_sha256(receipt)
    return {
        "schema_id": "research_live_adapter_parity_v2", "release_or_promotion_authority": False, "adapter_emitters_default_off": True,
        "sleeve_id": sleeve, "spec_id": "spec-1", "profile_id": "profile-1", "profile_hash": digest, "symbol": "BTCUSDT", "bar_ts": 1_759_276_800_000, "side": "long", "signal_id": decision_id, "decision_id": decision_id,
        "entry": "1", "sl": "0.9", "tp1": "1.1", "tp2": "1.2", "tp_fracs": ["0.5", "0.5"], "runner_fraction": "1", "time_stop": {"deadline_ms": 1_759_277_100_000}, "cooldown_state": {}, "regime_value": "0", "regime_bar_ts": 1_759_276_800_000, "validator_drop_reason": None,
        "config_hash": digest, "source_hash": digest, "data_hash": digest, "tick_size": "0.1", "fill_id": "fill-1", "order_id": "order-1", "fill_lifecycle": "finalized", "fill_ts_ms": 1_759_276_800_000, "fill_finalized_ts_ms": 1_759_276_800_000, "fill_age_ms": 0, "fill_finalization_delay_ms": 0, "exit_ts_ms": 1_759_276_900_000,
        "fill_fingerprint": canonical_sha256(final_fill), "policy_fingerprint": canonical_sha256(policy), "rebase_claim_key": "claim-1", "rebase_receipt_id": receipt["receipt_id"], "execution_fingerprint": digest, "frozen_decision": frozen, "final_fill": final_fill, "rebase_policy": policy, "rebase_receipt": receipt, "cost_contract_hash": digest, "outcome": {}, "net_r": "1", "exception": None,
    }


def _fixture_evaluation_row(sleeve: str) -> dict[str, object]:
    return {
        "bar_ts": 1_759_276_800_000,
        "eligible_regime": True,
        "regime_bar_ts": 1_759_276_800_000,
        "regime_value": 0.01,
        "side_contract": "long",
        "sleeve_id": sleeve,
        "symbol": "BTCUSDT",
        "exception": None,
        "signal": None,
    }


def _synthetic_postexecution_tree(tmp_path: Path) -> Path:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import OUTPUT_REL, canonical_sha256, sha256_file, threshold_checks, three_way_decision
    from research_lab.adapter_parity import read_jsonl
    from research_lab.summarize_att1_sbr1_presealed_economics import chronological_symbol_occupancy, metrics

    config = json.loads(CONFIG.read_text())
    for row in config["source_pins"]:
        target = tmp_path / row["path"]; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / row["path"], target)
    for path in ("scripts/run_att1_sbr1_reserved_oos_v1.py", "scripts/audit_att1_sbr1_reserved_oos_v1.py", "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"):
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / path, target)
    config_path = tmp_path / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"; config_path.write_text(json.dumps(config, sort_keys=True))
    identities = {"config_sha256": _sha(config_path), "input_manifest_sha256": _sha(tmp_path / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"), "runner_sha256": _sha(tmp_path / "scripts/run_att1_sbr1_reserved_oos_v1.py"), "audit_sha256": _sha(tmp_path / "scripts/audit_att1_sbr1_reserved_oos_v1.py")}
    auth = {"schema_id": "att1_sbr1_reserved_oos_owner_authorization_v1", "authority": "owner_explicit_one_shot_reserved_diagnostic_only", "owner_authorization_id": "synthetic-owner", "execute_once": True, "known_contamination_acknowledged": True, "money_authority": False, "reserved_window": config["reserved_window"], "output_path": OUTPUT_REL.as_posix(), "claim_path": (OUTPUT_REL / "one_shot_claim.json").as_posix(), **identities}
    auth_path = tmp_path / "configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json"; auth_path.write_text(json.dumps(auth, sort_keys=True))
    identities["authorization_sha256"] = _sha(auth_path)
    output = tmp_path / OUTPUT_REL; output.mkdir(parents=True)
    for sleeve in ("ATT1", "SBR1"):
        for mode in ("evaluation", "base", "stress"):
            for shaped in ("research", "live"):
                row = _fixture_evaluation_row(sleeve) if mode == "evaluation" else _fixture_row(sleeve)
                (output / f"{sleeve.lower()}_{mode}_{shaped}.jsonl").write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        for mode in ("base", "stress"):
            (output / f"{sleeve.lower()}_{mode}_parity_report.json").write_text('{"decision":"PASS"}\n')
    claim = {"schema_id": "att1_sbr1_reserved_oos_one_shot_claim_v1", "state": "CLAIMED_BEFORE_MARKET_DECODE", "claim_created_at_utc": "2026-08-27T00:00:00Z", "reserved_window": {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"}, "output_path": OUTPUT_REL.as_posix(), "claim_path": (OUTPUT_REL / "one_shot_claim.json").as_posix(), "private_api_calls": 0, "live_or_broker_calls": False, "orders_created_or_changed": 0, "money_authority": False, "promotion_authority": False, **identities}
    claim_path = output / "one_shot_claim.json"; claim_path.write_text(json.dumps(claim, sort_keys=True))
    thresholds = json.loads((tmp_path / config["threshold_source"]["path"]).read_text())["sleeves"]
    sleeves = {}
    for sleeve in ("ATT1", "SBR1"):
        modes = {}
        for mode in ("base", "stress"):
            rows = read_jsonl(output / f"{sleeve.lower()}_{mode}_live.jsonl"); accepted = chronological_symbol_occupancy(tuple(rows.values()), sleeve)
            modes[mode] = {"raw_signals": len(rows), "accepted_signals": len(accepted.rows), "same_symbol_occupancy_drops": accepted.overlap_drops, "metrics": metrics(accepted.rows), "parity": "PASS"}
        threshold = thresholds[sleeve]["zero_risk_shadow_gate"]["thresholds"]
        sleeves[sleeve] = {"modes": modes, "thresholds": threshold, "checks": {mode: threshold_checks(modes[mode]["metrics"], threshold) for mode in ("base", "stress")}, "decision": three_way_decision(modes["base"]["metrics"], modes["stress"]["metrics"], threshold, negative_stress_n=20)}
    inventory = {path.name: sha256_file(path) for path in output.iterdir() if path.name != "one_shot_claim.json"}
    result = {"schema_id": "att1_sbr1_reserved_oos_one_shot_receipt_v1", "authority": "research_only_reserved_diagnostic_no_live_no_broker_no_money_no_promotion", "classification": config["classification"], **identities, "claim_sha256": _sha(claim_path), "reserved_window": {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"}, "output_path": OUTPUT_REL.as_posix(), "claim_path": (OUTPUT_REL / "one_shot_claim.json").as_posix(), "private_api_calls": 0, "live_or_broker_calls": False, "orders_created_or_changed": 0, "money_authority": False, "promotion_authority": False, "market_decode_started_at_utc": "2026-08-27T00:00:01Z", "market_decode_finished_at_utc": "2026-08-27T00:00:02Z", "sleeves": sleeves, "output_file_sha256": inventory}
    result["receipt_sha256"] = canonical_sha256(result)
    (output / "receipt.json").write_text(json.dumps(result, sort_keys=True))
    return tmp_path


def test_synthetic_postexecution_happy_path_is_independently_audited(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import audit_postexecution

    assert audit_postexecution(_synthetic_postexecution_tree(tmp_path))["decision"] == "AUDIT_PASS_RESEARCH_ONLY"


def _rewrite_result(root: Path, mutation) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import OUTPUT_REL, canonical_sha256

    path = root / OUTPUT_REL / "receipt.json"
    result = json.loads(path.read_text())
    mutation(result)
    result.pop("receipt_sha256", None)
    result["receipt_sha256"] = canonical_sha256(result)
    path.write_text(json.dumps(result, sort_keys=True))


def test_postexecution_rejects_rehashed_authorization_contract_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AUTHORIZATION_REL, AuditViolation, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)
    path = root / AUTHORIZATION_REL
    authorization = json.loads(path.read_text())
    authorization["schema_id"] = "forged_owner_authorization_v2"
    path.write_text(json.dumps(authorization, sort_keys=True))

    with pytest.raises(AuditViolation, match="authorization contract drift"):
        audit_postexecution(root)


def test_postexecution_rejects_rehashed_claim_authority_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import CLAIM_REL, AuditViolation, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)
    path = root / CLAIM_REL
    claim = json.loads(path.read_text())
    claim["money_authority"] = True
    path.write_text(json.dumps(claim, sort_keys=True))
    _rewrite_result(root, lambda result: result.update({"claim_sha256": _sha(path)}))

    with pytest.raises(AuditViolation, match="claim forensic contract drift"):
        audit_postexecution(root)


def test_postexecution_rejects_refingerprinted_threshold_source_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, canonical_sha256, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)
    path = root / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"
    config = json.loads(path.read_text())
    config["threshold_source"]["json_pointer"] = "/forged/thresholds"
    config.pop("config_fingerprint_sha256", None)
    config["config_fingerprint_sha256"] = canonical_sha256(config)
    path.write_text(json.dumps(config, sort_keys=True))

    with pytest.raises(AuditViolation, match="threshold source pin drift"):
        audit_postexecution(root)


def test_postexecution_rejects_extra_output_symlink(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import OUTPUT_REL, AuditViolation, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)
    output = root / OUTPUT_REL
    (output / "forged-extra").symlink_to(output / "att1_base_live.jsonl")

    with pytest.raises(AuditViolation, match="actual output directory inventory drift"):
        audit_postexecution(root)


def test_postexecution_rejects_rehashed_evaluation_ledger_mismatch(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import OUTPUT_REL, AuditViolation, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)
    output = root / OUTPUT_REL
    path = output / "att1_evaluation_live.jsonl"
    row = json.loads(path.read_text())
    row["eligible_regime"] = False
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    _rewrite_result(root, lambda result: result["output_file_sha256"].update({path.name: _sha(path)}))

    with pytest.raises(AuditViolation, match="research/live ledger mismatch:ATT1:evaluation"):
        audit_postexecution(root)


def test_postexecution_rejects_rehashed_runner_sleeve_evidence_tamper(tmp_path: Path) -> None:
    from scripts.audit_att1_sbr1_reserved_oos_v1 import AuditViolation, audit_postexecution

    root = _synthetic_postexecution_tree(tmp_path)

    def mutate(result: dict[str, object]) -> None:
        result["sleeves"]["ATT1"]["modes"]["base"]["accepted_signals"] = 2

    _rewrite_result(root, mutate)
    with pytest.raises(AuditViolation, match="runner sleeve metrics drift:ATT1:base"):
        audit_postexecution(root)
