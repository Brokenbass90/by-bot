from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from bot.att1_ets2s_shadow_journal import HashChainedJournal, JournalViolation


def _row(*, value: int = 1) -> dict[str, object]:
    return {
        "schema_id": "att1_ets2s_signal_shadow_decision_v1",
        "claim_key": "decision:EXECUTION_FORWARD:ATT1:ETHUSDT:3600000",
        "value": value,
    }


def test_journal_append_exact_retry_conflict_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = HashChainedJournal(path)

    assert journal.append(_row()) is True
    assert journal.append(_row()) is False
    assert journal.tip()["row_count"] == 1
    assert path.stat().st_mode & 0o777 == 0o600

    restarted = HashChainedJournal(path)
    assert restarted.append(_row()) is False
    with pytest.raises(JournalViolation, match="claim conflict"):
        restarted.append(_row(value=2))


def test_journal_rejects_corrupt_truncated_symlink_and_nonregular(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    HashChainedJournal(path).append(_row())
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(JournalViolation, match="truncated"):
        HashChainedJournal(path).tip()

    path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("", encoding="utf-8")
    path.symlink_to(outside)
    with pytest.raises(JournalViolation, match="symlink|open"):
        HashChainedJournal(path).tip()

    path.unlink()
    path.mkdir()
    with pytest.raises(JournalViolation, match="regular"):
        HashChainedJournal(path).tip()


def test_journal_uses_nonblocking_exclusive_lock(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    HashChainedJournal(path).append(_row())
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(JournalViolation, match="locked"):
            HashChainedJournal(path).append(
                {
                    **_row(),
                    "claim_key": "decision:EXECUTION_FORWARD:ETS2S:ETHUSDT:3600000",
                }
            )
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_journal_write_enforces_0600_under_hostile_umask(tmp_path: Path) -> None:
    previous = os.umask(0o200)
    try:
        path = tmp_path / "events.jsonl"
        HashChainedJournal(path).append(_row())
    finally:
        os.umask(previous)
    assert path.stat().st_mode & 0o777 == 0o600
