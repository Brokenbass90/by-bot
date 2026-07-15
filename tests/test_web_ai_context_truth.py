import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyotp")

from web.routes import ai_routes


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_disabled_allocator_without_hard_block_is_explained_as_entry_capable(monkeypatch, tmp_path):
    _write_json(
        tmp_path / "bot_heartbeat.json",
        {"open_trades": 0, "trade_on": True, "dry_run": False, "regime": "bull_chop"},
    )
    (tmp_path / "bot_heartbeat.json").touch()
    _write_json(
        tmp_path / "control_plane" / "portfolio_allocator_state.json",
        {
            "status": "disabled",
            "safe_mode": False,
            "hard_block_new_entries": False,
            "sleeves": {"range": {"enabled": True, "final_risk_mult": 0.25}},
        },
    )
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "append_ai_context_lines", lambda _parts, _root: None)
    monkeypatch.setattr(ai_routes, "_append_operator_snapshot_context", lambda _parts: None)
    monkeypatch.setattr(ai_routes, "_append_ai_runtime_packs_context", lambda _parts: None)

    context = ai_routes._build_context()

    assert "allocator overlay is disabled" in context
    assert "new entries are not globally blocked" in context
    assert "SLEEVES ACTIVE: range" in context


def test_runtime_reader_prefers_fresher_live_mirror(monkeypatch, tmp_path):
    root = tmp_path
    runtime = root / "runtime"
    direct = runtime / "bot_heartbeat.json"
    mirror = runtime / "live_mirror" / "bot_heartbeat.json"
    _write_json(direct, {"regime": "old"})
    _write_json(mirror, {"regime": "fresh"})
    old = time.time() - 10_000
    os.utime(direct, (old, old))

    monkeypatch.setattr(ai_routes, "_ROOT", root)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    assert ai_routes._rt("bot_heartbeat.json") == mirror


def test_stale_allocator_and_operator_are_excluded_from_prompt(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    _write_json(runtime / "bot_heartbeat.json", {"open_trades": 0, "trade_on": True})
    _write_json(
        runtime / "control_plane" / "portfolio_allocator_state.json",
        {
            "status": "safe_mode",
            "safe_mode": True,
            "hard_block_new_entries": True,
            "sleeves": {"range": {"enabled": True, "final_risk_mult": 1.0}},
        },
    )
    _write_json(runtime / "operator" / "operator_snapshot.json", {"urgent_alerts": [{"summary": "old"}]})
    old = time.time() - 10_000
    for path in (
        runtime / "control_plane" / "portfolio_allocator_state.json",
        runtime / "operator" / "operator_snapshot.json",
    ):
        os.utime(path, (old, old))

    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    context = ai_routes._build_context()

    assert "BOT MIRROR: FRESH" in context
    assert "STALE_EXCLUDED allocator" in context
    assert "STALE_EXCLUDED operator_snapshot" in context
    assert "SLEEVES ACTIVE: range" not in context
    assert "control_recommendations_allowed=False" in context


def test_stale_heartbeat_never_implies_open_positions(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    _write_json(runtime / "bot_heartbeat.json", {"open_trades": 7})
    old = time.time() - 10_000
    os.utime(runtime / "bot_heartbeat.json", (old, old))
    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    context = ai_routes._build_context()

    assert "position state unknown" in context
    assert "SERVER STATUS: UNKNOWN_FROM_THIS_MIRROR" in context
    assert "(has open positions)" not in context


def test_mirror_truth_gate_requires_complete_bundle_manifest(monkeypatch, tmp_path):
    root = tmp_path
    runtime = root / "runtime"
    mirror = runtime / "live_mirror"
    authority = {
        "complete": True,
        "unclassified_sleeves": [],
        "live_money_sleeves": [],
        "components": {},
    }
    required = {
        "bot_heartbeat.json": {
            "trade_on": True,
            "strategy_runtime_config": {"authority": authority},
        },
        "live_positions.json": {"count": 0, "positions": []},
        "control_plane/portfolio_allocator_state.json": {"sleeves": {}},
        "regime/orchestrator_state.json": {"regime": "bear_chop"},
        "operator/operator_snapshot.json": {"generated_at_utc": "now"},
        "ai_context/full_context.json": {
            "generated_at_utc": "now",
            "heartbeat": {"strategy_runtime_config": {"authority": authority}},
            "critical_truth_assessment": {
                "control_recommendations_allowed": True,
                "blockers": [],
                "live_money_sleeves_by_heartbeat": [],
            },
        },
    }
    for rel, payload in required.items():
        _write_json(mirror / rel, payload)

    monkeypatch.setattr(ai_routes, "_ROOT", root)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    ok, blockers = ai_routes._web_live_truth_gate()
    assert ok is False
    assert any("mirror_bundle_not_complete" in blocker for blocker in blockers)

    _write_json(mirror / "sync_bundle_manifest.json", {"status": "complete"})
    ok, blockers = ai_routes._web_live_truth_gate()
    assert ok is True
    assert blockers == []


def test_truth_gate_rejects_fresh_semantic_conflict(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    required = {
        "bot_heartbeat.json": {"trade_on": True},
        "live_positions.json": {"count": 0, "positions": []},
        "control_plane/portfolio_allocator_state.json": {"sleeves": {}},
        "regime/orchestrator_state.json": {"regime": "bull_chop"},
        "operator/operator_snapshot.json": {"generated_at_utc": "now"},
        "ai_context/full_context.json": {
            "critical_truth_assessment": {
                "control_recommendations_allowed": False,
                "blockers": ["money_sleeve_conflict"],
            }
        },
    }
    for rel, payload in required.items():
        _write_json(runtime / rel, payload)

    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    ok, blockers = ai_routes._web_live_truth_gate()

    assert ok is False
    assert any("money_sleeve_conflict" in blocker for blocker in blockers)


def test_truth_gate_never_mixes_direct_and_mirror_files(monkeypatch, tmp_path):
    root = tmp_path
    runtime = root / "runtime"
    mirror = runtime / "live_mirror"
    _write_json(runtime / "bot_heartbeat.json", {"trade_on": True})
    for rel, payload in {
        "live_positions.json": {"count": 0, "positions": []},
        "control_plane/portfolio_allocator_state.json": {"sleeves": {}},
        "regime/orchestrator_state.json": {"regime": "bull_chop"},
        "operator/operator_snapshot.json": {"generated_at_utc": "now"},
        "ai_context/full_context.json": {
            "critical_truth_assessment": {
                "control_recommendations_allowed": True,
                "blockers": [],
            }
        },
        "sync_bundle_manifest.json": {"status": "complete"},
    }.items():
        _write_json(mirror / rel, payload)
    old = time.time() - 60
    _write_json(mirror / "bot_heartbeat.json", {"trade_on": True})
    os.utime(mirror / "bot_heartbeat.json", (old, old))

    monkeypatch.setattr(ai_routes, "_ROOT", root)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    assert ai_routes._runtime_source_root() == runtime
    ok, blockers = ai_routes._web_live_truth_gate()

    assert ok is False
    assert any("positions_missing_or_stale" in blocker for blocker in blockers)


def test_truth_gate_binds_cached_context_to_current_heartbeat_authority(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    authority = {
        "complete": True,
        "unclassified_sleeves": [],
        "live_money_sleeves": ["range"],
        "components": {
            "range": {"enabled": True, "execution_authority": "money"},
        },
    }
    required = {
        "bot_heartbeat.json": {
            "trade_on": True,
            "strategy_runtime_config": {"authority": authority},
        },
        "live_positions.json": {"count": 0, "positions": []},
        "control_plane/portfolio_allocator_state.json": {"sleeves": {}},
        "regime/orchestrator_state.json": {"regime": "bull_chop"},
        "operator/operator_snapshot.json": {"generated_at_utc": "now"},
        "ai_context/full_context.json": {
            "critical_truth_assessment": {
                "control_recommendations_allowed": True,
                "blockers": [],
                "live_money_sleeves_by_heartbeat": ["att1"],
            }
        },
    }
    for rel, payload in required.items():
        _write_json(runtime / rel, payload)

    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    ok, blockers = ai_routes._web_live_truth_gate()

    assert ok is False
    assert any("heartbeat_ai_context_authority_mismatch" in blocker for blocker in blockers)


def test_truth_gate_rejects_same_sleeve_risk_contract_race(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime"
    current = {
        "complete": True,
        "unclassified_sleeves": [],
        "live_money_sleeves": ["att1"],
        "components": {
            "att1": {"enabled": True, "risk_mult": 0.7, "execution_authority": "money"}
        },
    }
    cached = {
        **current,
        "components": {
            "att1": {"enabled": True, "risk_mult": 0.1, "execution_authority": "money"}
        },
    }
    required = {
        "bot_heartbeat.json": {
            "trade_on": True,
            "strategy_runtime_config": {"authority": current},
        },
        "live_positions.json": {"count": 0, "positions": []},
        "control_plane/portfolio_allocator_state.json": {"sleeves": {}},
        "regime/orchestrator_state.json": {"regime": "bull_chop"},
        "operator/operator_snapshot.json": {"generated_at_utc": "now"},
        "ai_context/full_context.json": {
            "heartbeat": {"strategy_runtime_config": {"authority": cached}},
            "critical_truth_assessment": {
                "control_recommendations_allowed": True,
                "blockers": [],
                "live_money_sleeves_by_heartbeat": ["att1"],
            },
        },
    }
    for rel, payload in required.items():
        _write_json(runtime / rel, payload)
    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_RUNTIME_ROOT", runtime)

    ok, blockers = ai_routes._web_live_truth_gate()

    assert ok is False
    assert "heartbeat_ai_context_authority_contract_mismatch" in blockers
