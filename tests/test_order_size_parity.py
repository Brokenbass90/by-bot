from pathlib import Path

import pytest

from scripts.verify_order_size_parity import ParityError, floor_qty, verify


def _receipt(**overrides):
    payload = {
        "receipt_id": "unit",
        "effective_equity_usd": 1021.71271589,
        "planned_entry_price": 0.7922,
        "sizing_price": 0.7944,
        "stop_price": 0.7981,
        "side": "short",
        "target_risk_fraction": 0.0044,
        "strategy_risk_multiplier": 0.10,
        "volatility_multiplier": 1.0,
        "max_notional_usd": 1021.71271589,
        "min_fill_fraction": 0.40,
        "qty_step": 0.1,
        "min_qty": 0.1,
        "submitted_qty": 75.9,
    }
    payload.update(overrides)
    return payload


def test_dot_live_receipt_matches_backtest_and_exchange_floor():
    result = verify(_receipt())
    assert result["pass"] is True
    assert result["computed"]["expected_qty"] == pytest.approx(75.9)
    assert result["computed"]["pre_round_notional_usd"] == pytest.approx(
        result["computed"]["backtest_notional_usd"]
    )


def test_parity_fails_when_live_qty_does_not_match_contract():
    result = verify(_receipt(submitted_qty=76.1))
    assert result["pass"] is False
    assert result["checks"]["submitted_qty_equals_step_floor"] is False


def test_floor_qty_is_decimal_step_safe():
    assert floor_qty(60.36209456819432, 0.7944, 0.1) == pytest.approx(75.9)
    with pytest.raises(ParityError):
        floor_qty(10.0, 0.0, 0.1)


def test_live_source_persists_sizing_contract():
    source = (Path(__file__).resolve().parents[1] / "smart_pump_reversal_bot.py").read_text()
    assert '"schema_id": "live_order_sizing_contract_v1"' in source
    assert '"sizing_contract": dict(getattr(tr, "sizing_contract", {}) or {})' in source
