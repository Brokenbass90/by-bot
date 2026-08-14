import json

from scripts.analyze_att1_lifecycle_readonly import reconstruct


def test_reconstructs_tp1_trail_and_net_r(tmp_path):
    path = tmp_path / "events.jsonl"
    rows = [
        {
            "event": "entry_filled", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT", "side": "Sell", "ts": 10, "fill_price": 100.0,
            "actual_risk_usd": 2.0, "post_fill_risk_allowed": True,
            "runner": {"runner_enabled": True, "initial_sl_price": 102.0},
        },
        {
            "event": "runner_tp", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT", "side": "Sell", "ts": 20, "price": 98.0, "tp_index": 1,
        },
        {
            "event": "runner_trailing_sl", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT", "side": "Sell", "ts": 25, "price": 97.0,
        },
        {
            "event": "close", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "symbol": "LTCUSDT", "side": "Sell", "ts": 30, "ts_utc": "utc",
            "exit_price": 97.5, "pnl": 3.0, "close_reason": "SL",
            "accounting_contaminated": False, "runner": {"tp_hit": [True, False]},
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = reconstruct(path)
    assert result["clean_closed"] == 1
    assert result["net_r"] == 1.5
    assert result["tp1_hits"] == 1 and result["tp2_hits"] == 0
    trade = result["trades"][0]
    assert trade["runner_event_mfe_lower_bound_r"] == 1.5
    assert trade["seconds_from_best_runner_observation_to_close"] == 5


def test_rejects_contaminated_trade(tmp_path):
    path = tmp_path / "events.jsonl"
    rows = [
        {
            "event": "entry_filled", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "ts": 10, "fill_price": 100.0, "actual_risk_usd": 2.0,
            "post_fill_risk_allowed": True, "runner": {"runner_enabled": True, "initial_sl_price": 102.0},
        },
        {
            "event": "close", "entry_order_id": "x", "strategy": "att1_trendline_touch",
            "ts": 20, "pnl": 1.0, "accounting_contaminated": True,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = reconstruct(path)
    assert result["clean_closed"] == 0
    assert result["rejected"][0]["reasons"] == ["accounting_not_explicitly_clean"]
