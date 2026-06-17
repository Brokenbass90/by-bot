import json
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
