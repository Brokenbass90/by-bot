from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.preflight_pump_exhaustion_prereg import (
    PreflightError,
    SOURCE_PATHS,
    actual_source_hashes,
    compute_state_source_fingerprint,
    evaluate_preflight,
    sha256_file,
    snapshot_status,
    validate_frozen_contract,
)


SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT"]
START = 1_000_000
INTERVAL = 300_000
END = START + 4 * INTERVAL


def _cfg() -> dict:
    return {
        "schema_version": 1,
        "name": "pump_exhaustion_unwind_short_v1_prereg",
        "research_only": True,
        "frozen_before_results": True,
        "no_parameter_scan": True,
        "live_or_broker_calls": False,
        "strategy": {
            "id": "pump_exhaustion_unwind_short_v1",
            "physical_side_identity": "short_only",
            "signal_side": "short",
            "live_ready": False,
            "persisted_event_state_required": True,
        },
        "source_code": {},
        "state_source_fingerprint": "",
        "data": {
            "symbols": list(SYMBOLS),
            "window_start_ts": START,
            "window_end_ts_exclusive": END,
            "interval_ms": INTERVAL,
            "min_coverage": 1.0,
            "max_internal_gap_bars": 0,
            "input_snapshots": {},
        },
        "execution_contract": {
            "entry": "next_5m_open_after_closed_signal_bar",
            "same_bar_fill_allowed": False,
            "risk_pct": 0,
            "base_costs_bps_per_side": {"fee": 6, "slippage": 2},
            "stress_costs_bps_per_side": {"fee": 10, "slippage": 5},
        },
        "evaluation_contract": {
            "chronological_folds": 4,
            "embargo_bars": 288,
            "untouched_holdout_days": 90,
        },
        "research_pass_gate": {
            "stress_pf_min": 1.2,
            "min_trades": 40,
            "positive_folds_min": 3,
            "min_traded_symbols": 3,
            "min_positive_symbols": 2,
            "max_profit_concentration_pct": 35,
        },
    }


def _row(ts: int) -> dict:
    return {"ts": ts, "o": 10.0, "h": 11.0, "l": 9.5, "c": 10.5, "v": 1000.0}


def _prepare_root(tmp_path: Path, *, pin_snapshots: bool = True) -> tuple[Path, dict]:
    for rel in SOURCE_PATHS.values():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source:{rel}\n", encoding="utf-8")
    cfg = _cfg()
    cfg["source_code"] = actual_source_hashes(tmp_path)
    if pin_snapshots:
        for symbol in SYMBOLS:
            path = tmp_path / "snapshots" / f"{symbol}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps([_row(START + index * INTERVAL) for index in range(4)]),
                encoding="utf-8",
            )
            cfg["data"]["input_snapshots"][symbol] = {
                "path": str(path.relative_to(tmp_path)),
                "sha256": sha256_file(path),
            }
    cfg["state_source_fingerprint"] = compute_state_source_fingerprint(
        cfg, cfg["source_code"]
    )
    return tmp_path, cfg


def test_frozen_contract_rejects_side_fill_risk_and_weak_gates():
    cfg = _cfg()
    validate_frozen_contract(cfg)

    cfg["strategy"]["physical_side_identity"] = "long_short"
    with pytest.raises(PreflightError, match="short-only"):
        validate_frozen_contract(cfg)

    cfg = _cfg()
    cfg["execution_contract"]["same_bar_fill_allowed"] = True
    with pytest.raises(PreflightError, match="same-bar"):
        validate_frozen_contract(cfg)

    cfg = _cfg()
    cfg["execution_contract"]["risk_pct"] = 0.01
    with pytest.raises(PreflightError, match="risk_pct"):
        validate_frozen_contract(cfg)

    cfg = _cfg()
    cfg["research_pass_gate"]["stress_pf_min"] = 1.01
    with pytest.raises(PreflightError, match="weaker"):
        validate_frozen_contract(cfg)


def test_preflight_allows_only_exact_sources_and_pinned_quality_snapshots(tmp_path):
    root, cfg = _prepare_root(tmp_path)

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "PERFORMANCE_RESEARCH_ALLOWED"
    assert result["blockers"] == []
    assert result["side_identity"] == "short_only"
    assert all(row["ok"] for row in result["snapshots"])
    assert result["performance_computed"] is False
    assert result["promotion_authorized"] is False


def test_unpinned_snapshots_block_without_computing_performance(tmp_path):
    root, cfg = _prepare_root(tmp_path, pin_snapshots=False)

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    assert "immutable_input_snapshots_not_ready" in result["blockers"]
    assert all(row["reasons"] == ["snapshot_unpinned"] for row in result["snapshots"])
    assert result["performance_computed"] is False


def test_source_change_and_fingerprint_change_both_block(tmp_path):
    root, cfg = _prepare_root(tmp_path)
    changed = root / SOURCE_PATHS["strategy_sha256"]
    changed.write_text("changed after freeze\n", encoding="utf-8")

    result = evaluate_preflight(root, cfg)

    assert result["permission"] == "BLOCKED_FAIL_CLOSED"
    assert result["source_mismatches"] == ["strategy_sha256"]
    assert "frozen_source_hash_mismatch" in result["blockers"]
    assert "state_source_fingerprint_mismatch" in result["blockers"]


def test_snapshot_hash_gap_and_duplicate_are_fail_closed(tmp_path):
    root, cfg = _prepare_root(tmp_path)
    contract = cfg["data"]["input_snapshots"]["BTCUSDT"]
    path = root / contract["path"]

    path.write_text(json.dumps([_row(START), _row(START + 2 * INTERVAL)]), encoding="utf-8")
    contract["sha256"] = sha256_file(path)
    status = snapshot_status(root, "BTCUSDT", contract, cfg["data"])
    assert not status["ok"]
    assert "coverage_below_gate" in status["reasons"]
    assert "gap_above_gate" in status["reasons"]

    duplicate_rows = [_row(START + index * INTERVAL) for index in range(4)]
    duplicate_rows[1]["ts"] = duplicate_rows[0]["ts"]
    path.write_text(json.dumps(duplicate_rows), encoding="utf-8")
    contract["sha256"] = sha256_file(path)
    status = snapshot_status(root, "BTCUSDT", contract, cfg["data"])
    assert not status["ok"]
    assert "duplicate_timestamps" in status["reasons"]


def test_artifact_paths_cannot_escape_or_follow_symlinks(tmp_path):
    root, cfg = _prepare_root(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("[]", encoding="utf-8")
    linked = root / "snapshots" / "linked.json"
    linked.symlink_to(outside)
    contract = {"path": "snapshots/linked.json", "sha256": hashlib.sha256(b"[]").hexdigest()}

    linked_status = snapshot_status(root, "BTCUSDT", contract, cfg["data"])
    assert not linked_status["ok"]
    assert linked_status["reasons"][0].startswith("unsafe_path:")

    escaped = snapshot_status(
        root,
        "BTCUSDT",
        {"path": "../outside.json", "sha256": "a" * 64},
        cfg["data"],
    )
    assert not escaped["ok"]
    assert escaped["reasons"][0].startswith("unsafe_path:")


def test_state_fingerprint_changes_with_data_or_execution_contract(tmp_path):
    _, cfg = _prepare_root(tmp_path)
    first = compute_state_source_fingerprint(cfg, cfg["source_code"])
    cfg["execution_contract"]["stress_costs_bps_per_side"]["slippage"] = 6
    second = compute_state_source_fingerprint(cfg, cfg["source_code"])
    assert first != second
