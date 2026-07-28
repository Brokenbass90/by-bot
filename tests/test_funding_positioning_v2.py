from scripts.audit_funding_positioning_v2 import _funding_cashflow, _quantile


def test_funding_cashflow_has_correct_long_short_sign():
    funding = [(100, 0.001), (200, -0.002), (300, 0.003)]
    assert _funding_cashflow(funding, entry_ts=100, exit_ts=300, side=1) == -0.001
    assert _funding_cashflow(funding, entry_ts=100, exit_ts=300, side=-1) == 0.001


def test_quantile_is_deterministic_and_bounded():
    values = [1.0, 2.0, 3.0, 4.0]
    assert _quantile(values, 0.0) == 1.0
    assert _quantile(values, 0.5) == 3.0
    assert _quantile(values, 1.0) == 4.0

