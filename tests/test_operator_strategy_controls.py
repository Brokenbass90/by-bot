from __future__ import annotations

from pathlib import Path

import pytest

from bot.operator_strategy_controls import (
    OperatorControlError,
    format_status,
    is_paused,
    pause,
    resume,
    snapshot,
)


def test_pause_and_resume_are_persistent_and_entry_only(tmp_path: Path) -> None:
    path = tmp_path / "controls.json"

    paused = pause("att1_trendline_touch", source="telegram_admin", path=path)

    assert paused["paused_sleeves"] == ["att1"]
    assert paused["paused"]["att1"]["scope"] == "new_entries_only"
    assert is_paused("att1", path=path) is True
    assert "att1" in format_status(path)

    resumed = resume("att1", path=path)

    assert resumed["paused_sleeves"] == []
    assert is_paused("att1", path=path) is False


def test_malformed_control_state_fails_open_but_cannot_be_overwritten(
    tmp_path: Path,
) -> None:
    path = tmp_path / "controls.json"
    path.write_text("{broken", encoding="utf-8")

    assert is_paused("att1", path=path) is False
    assert snapshot(path)["read_error"]
    assert "fail-open" in format_status(path)
    with pytest.raises(OperatorControlError):
        pause("att1", path=path)


def test_unknown_strategy_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(OperatorControlError):
        pause("not_a_sleeve", path=tmp_path / "controls.json")
