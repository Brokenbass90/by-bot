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
                    live_truth={"режим": "bull_trend", "open_trades": 1},
                    research_truth=["XSEC shadow active, risk zero"])
    assert "ТОЛЬКО_ЭТО" in b and "ARF2 failed-breakout" not in b
    assert "maker-fill redesign" in b
    assert "режим: bull_trend" in b
    assert "XSEC shadow active, risk zero" in b


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


def test_compose_prefers_heartbeat_runtime_truth_and_canonical_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.ai_context_brief.time.time", lambda: 200.0)
    rt = tmp_path / "runtime"
    cfg = tmp_path / "configs"
    rt.mkdir()
    cfg.mkdir()
    (rt / "bot_heartbeat.json").write_text(json.dumps({
        "ts": 190,
        "regime": "bear_chop",
        "trade_on": True,
        "dry_run": False,
        "open_trades": 0,
        "strategy_runtime_config": {
            "enabled": {"att1": True, "ivb1": True},
            "risk_mult": {"att1": 0.1, "ivb1": 0.0},
        },
    }))
    (cfg / "ai_operator_canonical_state.json").write_text(json.dumps({
        "live": {"crypto_money_sleeves": ["att1"]},
        "no_promotion": ["legacy_inplay_short"],
        "research_queue": ["pump_exhaustion_unwind_short_v1"],
    }))

    brief = compose_from_repo(tmp_path)

    assert "live_money_sleeves_by_heartbeat: ['att1']" in brief
    assert "strategy_runtime_summary" in brief
    assert "'enabled': ['att1', 'ivb1']" in brief
    assert "'positive_risk_mult': {'att1': 0.1}" in brief
    assert "legacy_inplay_short" in brief
    assert "pump_exhaustion_unwind_short_v1" in brief


def test_compose_includes_fresh_research_overlay_and_expires_it(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.ai_context_brief.time.time", lambda: 10_000.0)
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "ai_operator_research_overlay.json").write_text(json.dumps({
        "generated_at_epoch": 9_000,
        "max_age_hours": 1,
        "facts": ["XSEC risk-zero shadow active"],
    }))

    fresh = compose_from_repo(tmp_path)
    assert "XSEC risk-zero shadow active" in fresh
    assert "НЕ LIVE" in fresh

    (cfg / "ai_operator_research_overlay.json").write_text(json.dumps({
        "generated_at_epoch": 1_000,
        "max_age_hours": 1,
        "facts": ["XSEC risk-zero shadow active"],
    }))
    stale = compose_from_repo(tmp_path)
    assert "XSEC risk-zero shadow active" not in stale
    assert "RESEARCH_OVERLAY_STALE" in stale


def test_long_no_go_list_cannot_truncate_research_truth_or_format():
    brief = build_brief(
        no_go=[f"dead_strategy_{idx}" for idx in range(100)],
        research_truth=["XSEC audited shadow truth"],
    )
    assert "XSEC audited shadow truth" in brief
    assert "ФОРМАТ ТВОИХ ПРЕДЛОЖЕНИЙ" in brief
    assert "dead_strategy_99" not in brief
    assert "ещё 82 no-go записей" in brief
