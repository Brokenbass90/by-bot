from dataclasses import replace

import pytest

from bot.fx_contracts import FxEvent, FxTradePlan
from bot.fx_instruments import (
    get_instrument,
    instrument_round_levels,
    load_oanda_public_cost_contract,
    with_public_oanda_costs,
)


def _event(side="long"):
    return FxEvent("e1", "test", side, 100, 100.0, "horizontal", "unit")


def test_plan_rejects_same_bar_style_invalid_stop():
    with pytest.raises(ValueError):
        FxTradePlan(_event("long"), "market_next_open", 100, 101, 2, 10)


def test_limit_requires_price():
    with pytest.raises(ValueError):
        FxTradePlan(_event("long"), "limit", 100, 99, 2, 10)


def test_instrument_round_grids_are_scale_aware():
    jpy = instrument_round_levels(get_instrument("USDJPY"), 160.23)
    assert 160.0 in jpy and 160.5 in jpy
    assert 170.0 not in jpy  # legacy inferred decade grid must not reappear
    xau = instrument_round_levels(get_instrument("XAUUSD"), 2417.0)
    assert 2400.0 in xau and 2450.0 in xau


def test_stress_costs_are_strictly_more_adverse():
    spec = get_instrument("EURUSD")
    assert spec.stress_costs.round_trip_bps("market_next_open") > spec.base_costs.round_trip_bps("market_next_open")
    assert spec.stress_costs.financing_bps_per_day > spec.base_costs.financing_bps_per_day


def test_public_oanda_costs_preserve_signed_side_specific_swaps():
    contract = load_oanda_public_cost_contract(
        "configs/research/fx_oanda_public_cost_contract_20260729.json"
    )
    eurusd = with_public_oanda_costs(
        get_instrument("EURUSD"), contract=contract, reference_price=1.10
    )
    assert eurusd.base_costs.financing_cashflow_bps_per_day("long") < 0
    assert eurusd.base_costs.financing_cashflow_bps_per_day("short") > 0
    assert (
        eurusd.stress_costs.financing_cashflow_bps_per_day("long")
        < eurusd.base_costs.financing_cashflow_bps_per_day("long")
    )
    assert (
        eurusd.stress_costs.financing_cashflow_bps_per_day("short")
        < eurusd.base_costs.financing_cashflow_bps_per_day("short")
    )
    assert eurusd.stress_costs.spread_bps > eurusd.base_costs.spread_bps
