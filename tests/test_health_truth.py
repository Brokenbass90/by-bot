import json
import os

from bot.health_truth import compact_age, load_health_truth


def _write_with_mtime(path, payload, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    os.utime(path, (mtime, mtime))


def test_health_truth_separates_stale_research_from_fresh_live(tmp_path):
    now = 1_000_000.0
    _write_with_mtime(
        tmp_path / "configs" / "strategy_health.json",
        {"overall_health": "OK", "strategies": {"old": {"status": "OK"}}},
        now - 900_000,
    )
    _write_with_mtime(
        tmp_path / "runtime" / "portfolio_health.json",
        {"ts": 999_900, "sleeves": {"att1": {"status": "watch", "n": 5}}},
        now - 100,
    )

    truth = load_health_truth(tmp_path, now=now)

    assert truth["historical"]["stale"] is True
    assert truth["historical"]["authority"] == "historical_research"
    assert truth["live"]["stale"] is False
    assert truth["live"]["sleeves"]["att1"]["n"] == 5


def test_missing_sources_are_explicitly_stale(tmp_path):
    truth = load_health_truth(tmp_path, now=1_000_000)
    assert truth["historical"]["exists"] is False
    assert truth["historical"]["stale"] is True
    assert truth["live"]["exists"] is False
    assert truth["live"]["stale"] is True
    assert compact_age(None) == "missing"
