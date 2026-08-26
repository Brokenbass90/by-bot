from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from research_lab.att1_major8_regime_replay import (
    CALLER_PASS_SCHEMA_ID,
    FIXED_MAJOR8,
    ReplayBlocker,
    _sha,
    _load_caller_pass,
    build_blocker_manifest,
    score_gate_variants,
)


def test_replay_hash_normalizes_decimal_outcomes() -> None:
    assert _sha([{"net_r": Decimal("1.2300")}]) == _sha([{"net_r": "1.23"}])


def _event(
    symbol: str,
    bar_ts: int,
    net_r: str,
    regime: str,
    *,
    month: str = "2024-04",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "bar_ts": bar_ts,
        "regime_value": regime,
        "net_r": net_r,
        "month": month,
    }


def test_score_gate_variants_changes_only_regime_admission() -> None:
    events = [
        _event("BTCUSDT", 1_000, "1", "flat_down"),
        _event("ETHUSDT", 2_000, "-0.5", "flat_up"),
        _event("SOLUSDT", 3_000, "2", "below_band"),
        _event("ADAUSDT", 4_000, "-1", "flat_down", month="2024-05"),
    ]

    result = score_gate_variants(events)

    assert result["gate_off"]["n"] == 4
    assert result["gate_on"]["n"] == 2
    assert result["gate_off"]["sum_r"] == "1.5"
    assert result["gate_on"]["sum_r"] == "0"
    assert result["gate_off"]["profit_factor"] == "2"
    assert result["gate_on"]["profit_factor"] == "1"
    assert result["gate_off"]["max_drawdown_r"] == "1"
    assert result["gate_on"]["max_drawdown_r"] == "1"
    assert result["gate_off"]["admitted_regimes"] == {
        "below_band": 1,
        "flat_down": 2,
        "flat_up": 1,
    }


def test_score_rejects_unknown_symbol_and_duplicate_claim() -> None:
    with pytest.raises(ReplayBlocker, match="unknown_major8_symbol"):
        score_gate_variants([_event("AVAXUSDT", 1_000, "1", "flat_down")])

    duplicate = [
        _event("BTCUSDT", 1_000, "1", "flat_down"),
        _event("BTCUSDT", 1_000, "1", "flat_down"),
    ]
    with pytest.raises(ReplayBlocker, match="duplicate_event_key"):
        score_gate_variants(duplicate)


def test_blocker_manifest_is_deterministic_and_has_no_metrics(tmp_path: Path) -> None:
    manifest = build_blocker_manifest(
        root=tmp_path,
        reasons=["live_caller_parity_blocked", "caller_receipt_missing"],
    )
    assert manifest["decision"] == "PREFLIGHT_BLOCKED"
    assert manifest["blockers"] == [
        "caller_receipt_missing",
        "live_caller_parity_blocked",
    ]
    assert manifest["money_authority"] is False
    assert manifest["sealed_holdout_rows_decoded"] == 0
    assert "metrics" not in manifest
    first = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    second = json.dumps(
        build_blocker_manifest(
            root=tmp_path,
            reasons=["caller_receipt_missing", "live_caller_parity_blocked"],
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert first == second


def test_fixed_universe_is_exact_frozen_major8() -> None:
    assert FIXED_MAJOR8 == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "ADAUSDT",
        "LINKUSDT",
        "LTCUSDT",
        "DOTUSDT",
        "SUIUSDT",
    )


def test_release_receipt_binds_p1_and_exact_p2_p4_p5_artifacts(tmp_path: Path) -> None:
    decisions = {
        "P2": "P2_ENGINEERING_PASS_P5_STILL_REQUIRED",
        "P4": "PASS",
        "P5": "PASS",
    }
    gates = {}
    for gate, decision in decisions.items():
        path = tmp_path / f"{gate}.json"
        path.write_text(json.dumps({"decision": decision}), encoding="utf-8")
        import hashlib

        gates[gate] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "decision": decision,
        }
    p1_path = tmp_path / "P1.json"
    p1_path.write_text(json.dumps({"decision": "PASS"}), encoding="utf-8")
    payload = {
        "schema_id": CALLER_PASS_SCHEMA_ID,
        "decision": "LIVE_CALLER_PARITY_PASS",
        "authority": "research_only_no_live_no_broker_no_promotion",
        "money_authority": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "sealed_holdout_rows_decoded": 0,
        "parity_manifest_sha256": "a" * 64,
        "P1": {
            "decision": "PASS",
            "path": p1_path.name,
            "sha256": hashlib.sha256(p1_path.read_bytes()).hexdigest(),
            "state_sha256": "b" * 64,
            "receipt_sha256": "c" * 64,
            "money_authority": False,
            "orders_allowed": False,
        },
        "gates": gates,
    }
    import hashlib

    payload["receipt_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    receipt = tmp_path / "release.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    loaded = _load_caller_pass(
        receipt, root=tmp_path, expected_manifest_sha256="a" * 64
    )
    assert loaded["decision"] == "LIVE_CALLER_PARITY_PASS"

    (tmp_path / "P5.json").write_text(json.dumps({"decision": "FAIL"}), encoding="utf-8")
    with pytest.raises(ReplayBlocker, match="caller_receipt_p5_artifact_mismatch"):
        _load_caller_pass(
            receipt, root=tmp_path, expected_manifest_sha256="a" * 64
        )

    (tmp_path / "P5.json").write_text(
        json.dumps({"decision": "PASS"}), encoding="utf-8"
    )
    p1_path.write_text(json.dumps({"decision": "FAIL"}), encoding="utf-8")
    with pytest.raises(ReplayBlocker, match="caller_receipt_p1_artifact_mismatch"):
        _load_caller_pass(
            receipt, root=tmp_path, expected_manifest_sha256="a" * 64
        )
