from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_att1_risk_mult_respects_explicit_zero_pause_in_all_runtime_refreshes():
    src = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")

    assert 'ATT1_RISK_MULT = max(0.05' not in src
    assert src.count('ATT1_RISK_MULT = _risk_mult_or_pause("ATT1_RISK_MULT"') >= 3
