from __future__ import annotations

from research_lab.fx_smart_grid_v1 import (
    aggregate_h1,
    efficiency,
    roundtrip_cost_bps,
)


def test_aggregate_h1_keeps_only_complete_twelve_bar_hours() -> None:
    rows = []
    for i in range(13):
        ts = i * 300
        rows.append([ts, 1.0, 1.1 + i / 1000, 0.9, 1.0 + i / 1000, 1.0])

    result = aggregate_h1(rows)

    assert len(result) == 1
    assert result[0][0] == 0
    assert result[0][1] == 1.0
    assert result[0][4] == rows[11][4]


def test_efficiency_distinguishes_trend_from_back_and_forth() -> None:
    assert efficiency([1, 2, 3, 4, 5]) == 1.0
    assert efficiency([1, 2, 1, 2, 1]) == 0.0


def test_stress_cost_is_stricter_than_base() -> None:
    contract = {
        "research_arms": {"stress": {"commission_bps_per_side": 0.4}},
        "instruments": {"EURUSD": {"spread_pips_base": 0.9}},
    }

    base = roundtrip_cost_bps("EURUSD", 1.10, contract, "base")
    stress = roundtrip_cost_bps("EURUSD", 1.10, contract, "stress")

    assert base > 0
    assert stress > base
