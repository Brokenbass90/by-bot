from research_lab.pairs_statarb_v2 import fit_ols, summarize


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
