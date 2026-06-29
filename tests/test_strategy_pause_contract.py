from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_att1_risk_mult_respects_explicit_zero_pause_in_all_runtime_refreshes():
    src = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")

    assert 'ATT1_RISK_MULT = max(0.05' not in src
    assert src.count('ATT1_RISK_MULT = _risk_mult_or_pause("ATT1_RISK_MULT"') >= 3


def test_att1_canary_breaker_uses_live_strategy_id_and_scales_sizing():
    src = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")
    env = (ROOT / "configs" / "att1_short_canary_20260629.env").read_text(encoding="utf-8")

    assert 'ATT1_BREAKER_STRATEGY_NAME", "att1_trendline_touch"' in src
    assert 'strategy_name = "att1_trendline_touch"' in src
    assert src.count("risk_mult=effective_att1_risk_mult") >= 2
    assert '"att1": _att1_breaker_state()' in src
    assert "ATT1_BREAKER_STRATEGY_NAME=att1_trendline_touch" in env
    assert "ATT1_MAX_OPEN_TRADES=3" in env
    assert "FLAT_RISK_MULT=0.0" in env
    assert "ENABLE_ATT1_TRADING=1" in env


def test_operator_live_override_loads_after_strategy_pause():
    src = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")

    assert "ALLOW_OPERATOR_LIVE_OVERRIDES" in src
    assert "OPERATOR_LIVE_OVERRIDE_ENV" in src
    assert src.index("STRATEGY_PAUSE_ENV.exists()") < src.index("OPERATOR_LIVE_OVERRIDE_ENV")
    assert src.count("_refresh_operator_live_override_env()") >= 2
