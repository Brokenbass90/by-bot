from pathlib import Path


def test_breakdown_minqty_fallback_uses_breaker_risk_mult() -> None:
    src = Path("smart_pump_reversal_bot.py").read_text(encoding="utf-8")
    fn = src.split("async def try_breakdown_entry_async", 1)[1].split(
        "async def try_micro_scalper_entry_async", 1
    )[0]

    assert "effective_breakdown_risk_mult = float(BREAKDOWN_RISK_MULT) * breaker_mult" in fn
    assert "risk_mult=effective_breakdown_risk_mult" in fn
    assert "tr.breakdown_effective_risk_mult" in fn
    assert "effective_risk_mult=float(effective_breakdown_risk_mult)" in fn
