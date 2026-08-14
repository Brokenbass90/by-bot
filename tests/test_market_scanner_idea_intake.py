from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from research_lab.hypothesis_memory import HypothesisMemory
from research_lab.idea_intake import ingest, normalize_card
from scripts.market_scanner_ai import _heartbeat_truth, _load_public_source_digest


def _card(**updates):
    base = {
        "type": "new_strategy_idea",
        "target_strategy": "xau_intraday",
        "description": "XAU intraday session continuation",
        "rationale": "liquid session repricing",
        "mechanism": "new information moves price during active session",
        "data_required": ["XAUUSD M5 bid/ask"],
        "cost_model": "broker spread plus slippage stress",
        "test_contract": "next-open, same-day forced flat, four folds",
        "death_criteria": "base or stress expectancy <= 0",
        "source_ids": ["official-broker-spec"],
        "risk_note": "research only",
        "acceptance_gate": "independent audit and prospective shadow",
    }
    base.update(updates)
    return base


def test_stale_heartbeat_is_not_called_offline():
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    truth = _heartbeat_truth({"ts": "2026-08-13T11:00:00Z"}, now=now)
    assert truth["state"] == "STALE_NOT_CONFIRMED"
    assert truth["may_assert_offline"] is False


def test_epoch_seconds_heartbeat_is_online_when_fresh():
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    truth = _heartbeat_truth({"ts": int(now.timestamp()) - 10}, now=now)
    assert truth["state"] == "ONLINE_OBSERVED"


def test_public_digest_strips_arbitrary_shape(tmp_path: Path):
    source = tmp_path / "digest.json"
    source.write_text(
        '{"sources":[{"source_id":"s1","title":"Official","url":"https://example.test/x",'
        '"claims":["claim"],"raw_html":"ignore me"},{"source_id":"bad","url":"file:///x","claims":["x"]}]}',
        encoding="utf-8",
    )
    rows = _load_public_source_digest(source)
    assert len(rows) == 1
    assert "raw_html" not in rows[0]
    assert rows[0]["trust"] == "untrusted_public_claim_requires_reproduction"


def test_intake_rejects_incomplete_and_deduplicates(tmp_path: Path):
    memory = HypothesisMemory(str(tmp_path / "closed.json"))
    valid, errors = normalize_card(_card(), memory)
    assert not errors and valid["authority"].startswith("proposal_only")

    accepted, rejected = ingest([_card(), _card(), {"type": "new_strategy_idea"}], memory=memory, existing_keys=set())
    assert len(accepted) == 1
    assert len(rejected) == 2
    assert any("duplicate_proposal_key" in row["errors"] for row in rejected)


def test_intake_cli_is_directly_executable():
    proc = subprocess.run(
        [sys.executable, "research_lab/idea_intake.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--input" in proc.stdout


def test_att1_closed_slope_does_not_quarantine_other_sloped_family(tmp_path: Path):
    memory = HypothesisMemory(str(tmp_path / "closed.json"))
    sloped, errors = normalize_card(
        _card(
            target_strategy="sloped_break_retest_v2",
            description="Пробой наклонной slope линии и retest",
            mechanism="Каузальный slope break после подтвержденной наклонной линии",
        ),
        memory,
    )
    assert not errors
    assert sloped["status"] == "awaiting_owner_approval"
    assert not sloped["closed_hypothesis_matches"]

    att1, errors = normalize_card(
        _card(
            target_strategy="att1_trendline_touch",
            description="ATT1 минимальный slope наклон",
            mechanism="Изменить min slope наклон ATT1",
        ),
        memory,
    )
    assert not errors
    assert any(row["key"] == "att1_min_slope" for row in att1["closed_hypothesis_matches"])
