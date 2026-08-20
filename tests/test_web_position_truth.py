from web.routes.position_routes import reconcile_position_truth


def test_flat_broker_and_bot_are_confirmed():
    truth = reconcile_position_truth([], [], fetched_at_utc="2026-08-20T00:00:00Z")
    assert truth["status"] == "CONFIRMED"
    assert truth["broker_count"] == truth["bot_count"] == 0


def test_qty_or_stop_conflict_is_explicit():
    truth = reconcile_position_truth(
        [{"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001, "exchange_sl": 70_000}],
        [{"symbol": "BTCUSDT", "side": "Sell", "size": "0.002", "stopLoss": "0"}],
        fetched_at_utc="2026-08-20T00:00:00Z",
    )
    assert truth["status"] == "CONFLICT"
    assert any(issue.startswith("qty:") for issue in truth["issues"])
    assert any(issue.startswith("broker_sl_missing:") for issue in truth["issues"])


def test_broker_only_position_never_becomes_confirmed():
    truth = reconcile_position_truth(
        [],
        [{"symbol": "ETHUSDT", "side": "Buy", "size": "0.1", "stopLoss": "1000"}],
        fetched_at_utc="2026-08-20T00:00:00Z",
    )
    assert truth["status"] == "CONFLICT"
    assert truth["issues"] == ["broker_only:ETHUSDT buy"]
