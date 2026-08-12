from scripts.collect_bybit_orderbook_density import density_snapshot


def test_density_snapshot_keeps_no_wall_control_observation():
    book = {
        "bids": {99.0: 10.0, 98.0: 11.0, 97.0: 9.0},
        "asks": {101.0: 10.0, 102.0: 11.0, 103.0: 9.0},
    }
    row = density_snapshot(
        book,
        symbol="TESTUSDT",
        ts_ms=1,
        min_mult=10.0,
        max_dist_pct=5.0,
        top_n=5,
    )
    assert row is not None
    assert row["wall_count"] == 0
    assert row["walls"] == []
    assert row["order_capability"] is False


def test_density_snapshot_includes_matched_book_features_and_wall():
    book = {
        "bids": {99.0: 10.0, 98.0: 100.0, 97.0: 9.0},
        "asks": {101.0: 10.0, 102.0: 11.0, 103.0: 9.0},
    }
    row = density_snapshot(
        book,
        symbol="TESTUSDT",
        ts_ms=2,
        min_mult=4.0,
        max_dist_pct=5.0,
        top_n=5,
    )
    assert row is not None
    assert row["wall_count"] == 1
    assert row["walls"][0]["side"] == "bid"
    assert row["bid_depth_usd"] > row["ask_depth_usd"]
