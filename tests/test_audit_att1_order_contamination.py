from scripts.audit_att1_order_contamination import audit_att1_contamination


def test_detects_extra_non_reduce_order_inside_att1_lifecycle() -> None:
    trades = [
        {
            "event": "entry_filled",
            "strategy": "att1_trendline_touch",
            "symbol": "ADAUSDT",
            "side": "Sell",
            "qty": 180,
            "entry_order_id": "entry-1",
            "ts": 100,
        },
        {
            "event": "close",
            "strategy": "att1_trendline_touch",
            "symbol": "ADAUSDT",
            "ts": 300,
        },
    ]
    orders = [
        {
            "symbol": "ADAUSDT",
            "side": "Sell",
            "qty": "180",
            "order_id": "entry-1",
            "reduce_only": False,
            "status": "placed",
            "ts": 100,
        },
        {
            "symbol": "ADAUSDT",
            "side": "Sell",
            "qty": "90",
            "order_id": "legacy-dca",
            "reduce_only": False,
            "status": "placed",
            "ts": 200,
        },
    ]

    result = audit_att1_contamination(trades, orders)

    assert result["contaminated_lifecycles"] == 1
    assert result["details"][0]["extra_non_reduce_orders"][0]["qty"] == "90"


def test_reduce_only_exit_is_not_contamination() -> None:
    trades = [
        {
            "event": "entry_filled",
            "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT",
            "side": "Sell",
            "entry_order_id": "entry-2",
            "ts": 100,
        },
        {
            "event": "close",
            "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT",
            "ts": 300,
        },
    ]
    orders = [
        {
            "symbol": "LTCUSDT",
            "side": "Sell",
            "order_id": "entry-2",
            "reduce_only": False,
            "status": "placed",
            "ts": 100,
        },
        {
            "symbol": "LTCUSDT",
            "side": "Sell",
            "order_id": "exit-2",
            "reduce_only": True,
            "status": "placed",
            "ts": 200,
        },
    ]

    result = audit_att1_contamination(trades, orders)

    assert result["contaminated_lifecycles"] == 0
