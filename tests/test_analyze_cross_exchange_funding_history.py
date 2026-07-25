from __future__ import annotations

from scripts.analyze_cross_exchange_funding_history import DAY_MS, walk_forward


def _row(venue: str, symbol: str, day: int, rate: float) -> dict:
    return {
        "venue": venue,
        "symbol": symbol,
        "funding_time_ms": (day + 1) * DAY_MS,
        "funding_rate": rate,
    }


def test_walk_forward_fixes_direction_and_charges_cost_once_per_block() -> None:
    rows: list[dict] = []
    for day in range(10):
        for symbol, diff in (("AAAUSDT", 0.002), ("BBBUSDT", -0.001)):
            rows.append(_row("bybit", symbol, day, diff))
            rows.append(_row("mexc", symbol, day, 0.0))

    result = walk_forward(
        rows,
        train_days=4,
        oos_days=3,
        top_k=2,
        round_trip_cost_bps=(0.0, 8.0),
    )

    first = result["blocks"][0]
    routes = {row["symbol"]: row["collection_route"] for row in first["selected"]}
    assert routes == {
        "AAAUSDT": "short_bybit_long_mexc",
        "BBBUSDT": "short_mexc_long_bybit",
    }
    # Each block has three daily observations.  AAA earns 60 bps and BBB 30
    # bps, so the equal-weight basket earns 45 bps before one 8 bps round trip.
    assert first["basket_gross_bps"] == 45.0
    assert first["basket_net_bps_by_round_trip_cost"]["8"] == 37.0


def test_walk_forward_does_not_peek_when_oos_sign_reverses() -> None:
    rows: list[dict] = []
    for day in range(8):
        diff = 0.001 if day < 4 else -0.001
        rows.append(_row("bybit", "AAAUSDT", day, diff))
        rows.append(_row("mexc", "AAAUSDT", day, 0.0))

    result = walk_forward(
        rows,
        train_days=4,
        oos_days=3,
        top_k=1,
        round_trip_cost_bps=(0.0,),
    )

    first = result["blocks"][0]
    assert first["selected"][0]["collection_route"] == "short_bybit_long_mexc"
    assert first["basket_gross_bps"] == -30.0
