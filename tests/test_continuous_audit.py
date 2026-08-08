import os
from pathlib import Path

from research_lab.continuous_audit import collect_liveness


def test_stale_liveness_table_does_not_emit_stale_strategy_verdicts(tmp_path: Path):
    table = tmp_path / "liveness_table.txt"
    table.write_text(
        "strategy SOL ADA verdict\n---\nfoo 0 0 МЁРТВАЯ\n",
        encoding="utf-8",
    )
    os.utime(table, (1_000, 1_000))
    rows = collect_liveness(table, max_age_hours=1.0, now_epoch=10_000)
    assert len(rows) == 1
    assert rows[0]["rule"] == "L0"
    assert "foo" not in rows[0]["what"]


def test_fresh_liveness_table_emits_strategy_candidate(tmp_path: Path):
    table = tmp_path / "liveness_table.txt"
    table.write_text(
        "strategy SOL ADA verdict\n---\nfoo 0 0 МЁРТВАЯ — trace\n",
        encoding="utf-8",
    )
    os.utime(table, (9_900, 9_900))
    rows = collect_liveness(table, max_age_hours=1.0, now_epoch=10_000)
    assert len(rows) == 1
    assert rows[0]["rule"] == "L1"
    assert "foo.py" in rows[0]["where"]
