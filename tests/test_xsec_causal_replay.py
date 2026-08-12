import pandas as pd

from research_lab.xsec_causal_replay import metrics, vol_target


def test_metrics_and_vol_target_are_deterministic():
    rows = [
        {"price_return": 0.01, "funding_cashflow": 0.001, "cost": 0.0015, "net_return": 0.0095}
        for _ in range(12)
    ]
    targeted = vol_target(rows)
    assert targeted[0]["leverage"] == 0.5
    assert len(targeted) == 12
    result = metrics([row["net_return"] for row in targeted])
    assert result["n"] == 12
    assert result["total_pct"] > 0


def test_period_dates_are_utc_compatible():
    index = pd.to_datetime(["2024-01-01", "2024-01-04"], utc=True)
    assert str(index.tz) == "UTC"
