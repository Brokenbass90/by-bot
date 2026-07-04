"""Offline units for the orderbook density collector (pure functions only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.collect_bybit_orderbook_density import apply_orderbook_message, build_parser, extract_densities


def _snapshot(symbol="BTCUSDT", bids=None, asks=None):
    return {
        "topic": f"orderbook.50.{symbol}",
        "type": "snapshot",
        "data": {"s": symbol,
                 "b": [[str(p), str(s)] for p, s in (bids or [])],
                 "a": [[str(p), str(s)] for p, s in (asks or [])]},
    }


def test_snapshot_then_delta_updates_and_deletes():
    book = {"bids": {}, "asks": {}}
    sym = apply_orderbook_message(book, _snapshot(
        bids=[(100.0, 1.0), (99.5, 2.0)], asks=[(100.5, 1.5), (101.0, 3.0)]))
    assert sym == "BTCUSDT"
    assert book["bids"][100.0] == 1.0 and book["asks"][101.0] == 3.0

    delta = {"topic": "orderbook.50.BTCUSDT", "type": "delta",
             "data": {"s": "BTCUSDT", "b": [["100.0", "0"], ["99.0", "5.0"]], "a": []}}
    apply_orderbook_message(book, delta)
    assert 100.0 not in book["bids"]          # size 0 deletes
    assert book["bids"][99.0] == 5.0          # new level added
    assert book["asks"][100.5] == 1.5         # untouched side intact

    # a fresh snapshot must RESET the book
    apply_orderbook_message(book, _snapshot(bids=[(98.0, 1.0)], asks=[(98.5, 1.0)]))
    assert set(book["bids"]) == {98.0} and set(book["asks"]) == {98.5}


def test_non_orderbook_message_ignored():
    book = {"bids": {1.0: 1.0}, "asks": {2.0: 1.0}}
    assert apply_orderbook_message(book, {"topic": "allLiquidation.BTCUSDT", "data": {}}) is None
    assert book["bids"] == {1.0: 1.0}


def test_extract_densities_finds_walls_near_mid_only():
    # median bid size = 1.0; wall of 10 at 99.8 (0.15% from mid) -> density
    # equally big wall at 90.0 (>3% away) -> ignored
    book = {
        "bids": {99.8: 10.0, 99.7: 1.0, 99.6: 1.0, 99.5: 1.0, 90.0: 10.0},
        "asks": {100.1: 1.0, 100.2: 1.0, 100.3: 1.2},
    }
    dens = extract_densities(book, symbol="ETHUSDT", ts_ms=123, min_mult=4.0, max_dist_pct=3.0)
    assert len(dens) == 1
    d = dens[0]
    assert d["side"] == "bid" and d["price"] == 99.8
    assert d["mult_vs_median"] >= 4.0
    assert d["size_usd"] == round(10.0 * 99.8, 2)
    assert d["dist_pct"] < 0.5


def test_extract_densities_empty_or_crossed_book():
    assert extract_densities({"bids": {}, "asks": {}}, symbol="X", ts_ms=1) == []
    crossed = {"bids": {101.0: 1.0}, "asks": {100.0: 1.0}}
    assert extract_densities(crossed, symbol="X", ts_ms=1) == []


def test_top_n_caps_output():
    bids = {99.0 - i * 0.01: 10.0 for i in range(10)}   # 10 walls
    bids.update({95.0 - i * 0.01: 1.0 for i in range(20)})  # median floor
    book = {"bids": bids, "asks": {100.0: 1.0, 100.1: 1.0}}
    dens = extract_densities(book, symbol="X", ts_ms=1, min_mult=4.0, max_dist_pct=10.0, top_n=3)
    assert len([d for d in dens if d["side"] == "bid"]) == 3


def test_parser_help_formats_percent_sign():
    help_text = build_parser().format_help()
    assert "within this % of mid" in help_text
