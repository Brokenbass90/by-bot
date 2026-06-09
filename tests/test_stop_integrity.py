"""Tests for scripts.stop_integrity_watchdog.analyze_orders (Opus 2026-06-08)."""
import importlib.util
spec = importlib.util.spec_from_file_location("siw", "scripts/stop_integrity_watchdog.py")
siw = importlib.util.module_from_spec(spec); spec.loader.exec_module(siw)


def test_detects_compression_bug():
    events = [
        {"event": "order_submitted", "entry_order_id": "A", "symbol": "ETHUSDT",
         "strategy": "alt_inplay_breakdown_v1", "request_sl": 1557.0, "request_price": 1511.0},
        {"event": "entry_filled", "entry_order_id": "A", "sl_price": 1519.0, "fill_price": 1514.0},
    ]
    r = siw.analyze_orders(events)
    assert r["verdict"] == "compression_detected"
    assert r["flagged_count"] == 1
    assert r["flagged"][0]["symbol"] == "ETHUSDT"


def test_healthy_stop_passes():
    # requested ~3% short stop, actual ~3% -> NOT compressed (fix working)
    events = [
        {"event": "order_submitted", "entry_order_id": "B", "symbol": "ETHUSDT",
         "strategy": "alt_inplay_breakdown_v1", "request_sl": 1557.0, "request_price": 1511.0},
        {"event": "entry_filled", "entry_order_id": "B", "sl_price": 1560.0, "fill_price": 1513.0},
    ]
    r = siw.analyze_orders(events)
    assert r["verdict"] == "ok"
    assert r["flagged_count"] == 0


def test_ignores_tiny_requested_stop():
    # genuinely tight scalp (requested 0.3%) -> not flagged (below min_requested_pct)
    events = [
        {"event": "order_submitted", "entry_order_id": "C", "symbol": "X",
         "request_sl": 100.3, "request_price": 100.0},
        {"event": "entry_filled", "entry_order_id": "C", "sl_price": 100.15, "fill_price": 100.0},
    ]
    r = siw.analyze_orders(events)
    assert r["verdict"] == "no_data"  # nothing met the min_requested threshold


def test_no_data():
    assert siw.analyze_orders([])["verdict"] == "no_data"


def test_missing_request_is_not_silent():
    events = [
        {"event": "entry_filled", "entry_order_id": "D", "symbol": "BTCUSDT",
         "strategy": "att1_trendline_touch", "sl_price": 99.0, "fill_price": 100.0},
    ]
    r = siw.analyze_orders(events)
    assert r["verdict"] == "missing_request"
    assert r["missing_request_count"] == 1
