import math

from research_lab.pairs_statarb_v2 import Params, fit_ols, run_pair, summarize


def test_fit_ols_recovers_hedge_ratio() -> None:
    x = [1.0, 2.0, 3.0, 4.0]
    y = [3.0 + 2.0 * value for value in x]

    alpha, beta = fit_ols(y, x)

    assert round(alpha, 8) == 3.0
    assert round(beta, 8) == 2.0


def test_summary_folds_trades_chronologically_not_by_pair() -> None:
    trades = [
        {"entry_day": 4, "pair": "A/B", "pnl_bps": -1.0},
        {"entry_day": 1, "pair": "C/D", "pnl_bps": 4.0},
        {"entry_day": 3, "pair": "C/D", "pnl_bps": 3.0},
        {"entry_day": 2, "pair": "A/B", "pnl_bps": 2.0},
    ]

    result = summarize(trades)

    assert result["fold_net_bps"] == [4.0, 2.0, 3.0, -1.0]
    assert result["positive_folds"] == 3


def test_open_spread_is_managed_every_day_and_charged_for_four_leg_sides() -> None:
    # Stable training relation followed by a persistent dislocation.  Once the
    # spread opens it must time out even if later model estimates would fail.
    series = []
    for day in range(30):
        log_b = 1.0 + day * 0.01
        residual = (0.001 if day % 2 else -0.001)
        log_a = 0.2 + 1.5 * log_b + residual
        series.append((day, log_a, log_b))
    for day in range(30, 45):
        log_b = 1.0 + day * 0.01
        series.append((day, 0.2 + 1.5 * log_b + 0.05, log_b))

    params = Params(
        train_days=20,
        z_entry=2.0,
        z_exit=0.25,
        max_hold_days=4,
        ar1_phi_max=0.99,
        cost_bps_per_leg_side=3.0,
    )
    trades = run_pair(series, "A", "B", params)

    assert trades
    assert max(int(row["held_days"]) for row in trades) <= 4
    assert all(math.isclose(float(row["cost_bps"]), 12.0) for row in trades)
