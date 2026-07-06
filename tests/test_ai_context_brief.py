import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.ai_context_brief import DEFAULT_NO_GO, HOUSE_RULES, build_brief, compose_from_repo


def test_brief_contains_rules_nogo_and_data_warning():
    b = build_brief()
    for rule in HOUSE_RULES:
        assert rule[:40] in b
    for item in DEFAULT_NO_GO[:3]:
        assert item[:20] in b
    assert "ГРЯЗНУЮ эпоху" in b
    assert "N<20 вердиктов не существует" in b
    assert len(b) <= 3900


def test_overrides_and_live_truth():
    b = build_brief(no_go=["ТОЛЬКО_ЭТО"], queue=["maker-fill redesign"],
                    live_truth={"режим": "bull_trend", "open_trades": 1})
    assert "ТОЛЬКО_ЭТО" in b and "ARF2 failed-breakout" not in b
    assert "maker-fill redesign" in b
    assert "режим: bull_trend" in b


def test_compose_from_repo_tolerates_empty_and_reads_extra(tmp_path):
    assert "ПРАВИЛА" in compose_from_repo(tmp_path)  # ничего нет — brief всё равно есть
    rt = tmp_path / "runtime"
    rt.mkdir()
    (rt / "bot_heartbeat.json").write_text(json.dumps(
        {"regime": "bull_trend", "trade_on": True, "dry_run": False, "open_trades": 1}))
    (rt / "ai_brief_extra.json").write_text(json.dumps(
        {"queue": ["AI observability P1"], "no_go": ["X-strategy"]}))
    b = compose_from_repo(tmp_path)
    assert "X-strategy" in b and "AI observability P1" in b
    assert "торгует: True" in b
