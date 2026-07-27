from __future__ import annotations

import json

from web.routes.data_routes import _merge_live_event_record, _normalise_trade


def test_normalise_trade_decodes_immutable_signal_geometry() -> None:
    geometry = {
        "schema_version": "position_geometry_v1",
        "available": True,
        "primary_level": 101.25,
        "primary_role": "trendline",
        "sloped_lines": [
            {
                "projection_at_signal": 101.25,
                "slope_pct_per_day": -0.8,
            }
        ],
    }

    trade = _normalise_trade(
        {
            "symbol": "BTCUSDT",
            "entry_price": "100.5",
            "signal_geometry": json.dumps(geometry),
        }
    )

    assert trade["entry"] == 100.5
    assert trade["signal_geometry"] == geometry


def test_normalise_trade_keeps_invalid_geometry_honest() -> None:
    trade = _normalise_trade(
        {
            "symbol": "ETHUSDT",
            "entry_price": "2500",
            "signal_geometry": "{not-json",
        }
    )

    assert trade["signal_geometry"] == "{not-json"


def test_empty_close_geometry_does_not_erase_entry_snapshot() -> None:
    exact = {
        "schema_version": "position_geometry_v1",
        "available": True,
        "primary_level": 101.25,
    }
    record = {}

    _merge_live_event_record(record, {"event": "order_submitted", "signal_geometry": exact})
    _merge_live_event_record(record, {"event": "close", "signal_geometry": {}, "pnl": 1.0})

    assert record["event"] == "close"
    assert record["pnl"] == 1.0
    assert record["signal_geometry"] == exact
