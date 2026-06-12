import asyncio

from web.routes.extra_routes import AnalyzeLivePositionRequest, ai_analyze_live_position


def _run(coro):
    return asyncio.run(coro)


def test_live_position_analysis_flags_missing_stop():
    res = _run(ai_analyze_live_position(
        AnalyzeLivePositionRequest(
            symbol="LTCUSDT",
            side="Sell",
            entry=42.57,
            current=42.30,
            upnl_pct=0.6,
        ),
        _="tester",
    ))

    assert res["tone"] == "danger"
    assert res["verdict"] == "missing_sl"
    assert "нет стопа" in res["human_summary"]


def test_live_position_analysis_recommends_profit_protection_after_one_r():
    res = _run(ai_analyze_live_position(
        AnalyzeLivePositionRequest(
            symbol="DOTUSDT",
            side="Sell",
            entry=1.00,
            current=0.97,
            sl=1.03,
            upnl_pct=3.0,
        ),
        _="tester",
    ))

    assert res["tone"] == "ok"
    assert res["verdict"] == "protect_profit"
    assert res["metrics"]["r_multiple"] == 1.0
    assert any(a["action"] == "consider_be" for a in res["suggested_actions"])


def test_live_position_analysis_flags_near_stop():
    res = _run(ai_analyze_live_position(
        AnalyzeLivePositionRequest(
            symbol="ADAUSDT",
            side="Buy",
            entry=1.00,
            current=0.982,
            sl=0.98,
            upnl_pct=-1.8,
        ),
        _="tester",
    ))

    assert res["tone"] == "danger"
    assert res["verdict"] == "near_stop"
