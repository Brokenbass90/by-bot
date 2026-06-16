from scripts.collect_bybit_liquidations import normalize_liquidation, normalize_ws_message


def test_normalize_sell_order_side_means_long_liquidation():
    ev = normalize_liquidation(
        {"T": 1700000000000, "s": "BTCUSDT", "S": "Sell", "v": "0.5", "p": "40000"},
        recv_ts_ms=1700000000100,
    )
    assert ev["symbol"] == "BTCUSDT"
    assert ev["side"] == "long"
    assert ev["usd"] == 20000
    assert ev["order_side"] == "Sell"


def test_normalize_buy_order_side_means_short_liquidation():
    ev = normalize_liquidation(
        {"T": 1700000000000, "s": "ETHUSDT", "S": "Buy", "v": "2", "p": "2500"},
        recv_ts_ms=1700000000100,
    )
    assert ev["side"] == "short"
    assert ev["usd"] == 5000


def test_ws_message_normalizes_list_payload_and_topic_symbol_fallback():
    events = normalize_ws_message(
        {
            "topic": "allLiquidation.SOLUSDT",
            "ts": 1700000000200,
            "data": [{"T": 1700000000000, "S": "Sell", "v": "10", "p": "100"}],
        }
    )
    assert events == [
        {
            "ts_ms": 1700000000000,
            "symbol": "SOLUSDT",
            "side": "long",
            "usd": 1000.0,
            "qty": 10.0,
            "price": 100.0,
            "order_side": "Sell",
            "recv_ts_ms": 1700000000200,
        }
    ]


def test_bad_liquidation_event_is_ignored():
    assert normalize_liquidation({"s": "BTCUSDT", "S": "Sell", "v": "0", "p": "40000"}) is None
