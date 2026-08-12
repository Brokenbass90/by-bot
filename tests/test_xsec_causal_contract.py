import pytest

from research_lab.xsec_causal_contract import funding_cashflow, next_open_period, period_return


def test_signal_close_cannot_enter_until_next_open():
    assert next_open_period(4, 3, 12) == (5, 8)
    assert next_open_period(8, 3, 12) is None


def test_funding_sign_and_event_boundaries():
    funding = {
        "LONG": [(100, 0.10), (101, 0.01), (105, 0.02)],
        "SHORT": [(101, 0.03), (105, -0.01), (106, 0.50)],
    }
    value = funding_cashflow(
        {"LONG": 0.5, "SHORT": -0.5}, funding, entry_ts_ms=100, exit_ts_ms=105
    )
    assert value == pytest.approx(-0.5 * 0.01 - 0.5 * 0.02 + 0.5 * 0.03 - 0.5 * 0.01)


def test_open_to_open_return_includes_funding_and_cost():
    result = period_return(
        {"A": 0.5, "B": -0.5},
        {"A": 100.0, "B": 100.0},
        {"A": 110.0, "B": 90.0},
        {"A": [(2, 0.01)], "B": [(2, 0.02)]},
        entry_ts_ms=1,
        exit_ts_ms=3,
        round_trip_cost_fraction=0.0015,
    )
    assert result["price_return"] == pytest.approx(0.10)
    assert result["funding_cashflow"] == pytest.approx(0.005)
    assert result["net_return"] == pytest.approx(0.1035)


def test_missing_execution_price_fails_closed():
    with pytest.raises(ValueError, match="missing executable prices"):
        period_return(
            {"A": 1.0}, {"A": 100.0}, {}, {}, entry_ts_ms=1, exit_ts_ms=2,
            round_trip_cost_fraction=0.0,
        )
