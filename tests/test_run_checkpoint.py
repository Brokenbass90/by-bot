"""Tests for bot.run_checkpoint — resumable research runs (sleep/kill safe)."""
import os
import tempfile
import pytest

from bot.run_checkpoint import Checkpoint, run_resumable


def _tmp():
    return tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False).name


def test_record_and_done_keys():
    p = _tmp()
    try:
        cp = Checkpoint(p)
        cp.record("SOL", {"pf": 1.4})
        cp.record("AVAX", {"pf": 0.9})
        assert cp.done_keys() == {"SOL", "AVAX"}
        assert cp.results()["SOL"] == {"pf": 1.4}
    finally:
        os.unlink(p)


def test_pending_excludes_done_and_dedupes():
    p = _tmp()
    try:
        cp = Checkpoint(p)
        cp.record("SOL")
        assert cp.pending(["SOL", "AVAX", "AVAX", "LINK"]) == ["AVAX", "LINK"]
    finally:
        os.unlink(p)


def test_missing_file_is_empty():
    cp = Checkpoint("/tmp/nope_checkpoint_zzz.jsonl")
    assert cp.records() == [] and cp.done_keys() == set()


def test_resume_after_crash():
    p = _tmp()
    try:
        cp = Checkpoint(p)
        keys = ["SOL", "AVAX", "LINK", "MATIC"]
        done = []

        def work(k):
            done.append(k)
            if len(done) == 3:
                raise RuntimeError("mac slept")
            return {"pf": 1.4}

        with pytest.raises(RuntimeError):
            run_resumable(keys, work, cp)
        assert cp.done_keys() == {"SOL", "AVAX"}

        res = run_resumable(keys, lambda k: {"pf": 1.5}, cp)   # resume
        assert set(cp.done_keys()) == set(keys)
        assert len(res) == 4
    finally:
        os.unlink(p)


def test_tolerates_half_written_last_line():
    p = _tmp()
    try:
        with open(p, "w") as f:
            f.write('{"key":"SOL","result":1}\n{"key":"AVAX","resu')  # truncated line
        cp = Checkpoint(p)
        assert cp.done_keys() == {"SOL"}
    finally:
        os.unlink(p)
