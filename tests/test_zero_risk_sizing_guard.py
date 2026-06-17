from pathlib import Path


def test_zero_risk_mult_pauses_notional_sizing() -> None:
    src = Path("smart_pump_reversal_bot.py").read_text(encoding="utf-8")
    start = src.index("def calc_notional_usd_candidate_from_stop_pct")
    end = src.index("def calc_notional_usd_from_stop_pct", start)
    fn = src[start:end]

    assert "if risk_mult_f <= 0:" in fn
    assert "return 0.0" in fn
    assert "risk_mult or 1.0" not in fn
