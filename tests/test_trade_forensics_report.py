from __future__ import annotations

import json

import scripts.trade_forensics_report as report
from scripts.trade_forensics_report import Trade, _cache_file_range, _load_live_events


def test_live_events_use_matching_fill_timestamp_and_price(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    rows = [
        {
            "event": "order_submitted",
            "entry_order_id": "oid-1",
            "ts": 1_700_000_000,
            "symbol": "DOGEUSDT",
            "side": "Buy",
            "strategy": "range",
            "entry_price": 0.10,
            "signal_reason": "range-long: support retest",
        },
        {
            "event": "entry_filled",
            "entry_order_id": "oid-1",
            "ts": 1_700_000_005,
            "symbol": "DOGEUSDT",
            "side": "Buy",
            "strategy": "range",
            "fill_price": 0.101,
            "qty": 10,
            "sl_price": 0.099,
            "tp_price": 0.105,
        },
        {
            "event": "close",
            "entry_order_id": "oid-1",
            "ts": 1_700_000_605,
            "symbol": "DOGEUSDT",
            "side": "Buy",
            "strategy": "range",
            "entry_price": 0.10,
            "exit_price": 0.105,
            "pnl": 0.04,
            "close_reason": "TP",
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    trades = _load_live_events(path, days=0)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_ts_ms == 1_700_000_005_000
    assert trade.exit_ts_ms == 1_700_000_605_000
    assert trade.entry_price == 0.101
    assert trade.qty == 10
    assert trade.sl_price == 0.099
    assert trade.tp_price == 0.105
    assert trade.reason == "range-long: support retest"


def test_cache_file_range_accepts_compact_utc_dates(tmp_path) -> None:
    path = tmp_path / "DOGEUSDT_1_20260617_20260618.json"

    start_ms, end_ms = _cache_file_range(path, "DOGEUSDT", "1") or (0, 0)

    assert start_ms == 1_781_654_400_000
    assert end_ms == 1_781_827_200_000


def test_analyze_trade_excludes_pre_entry_candles(tmp_path, monkeypatch) -> None:
    entry_ms = 1_700_000_000_000
    rows = [
        [entry_ms - 60_000, 100.0, 150.0, 50.0, 100.0, 1.0],
        [entry_ms, 100.0, 101.0, 99.0, 100.5, 1.0],
        [entry_ms + 60_000, 100.5, 102.0, 100.0, 101.0, 1.0],
    ]
    monkeypatch.setattr(report, "_load_symbol_candles", lambda *_args, **_kwargs: rows)
    trade = Trade(
        source="live:test",
        strategy="range",
        symbol="TESTUSDT",
        side="long",
        entry_ts_ms=entry_ms,
        exit_ts_ms=entry_ms + 60_000,
        entry_price=100.0,
        exit_price=101.0,
        qty=1.0,
        pnl=1.0,
        fees=0.0,
        outcome="tp",
        reason="test",
        sl_price=99.0,
        tp_price=102.0,
    )

    result = report.analyze_trade(trade, tmp_path, "1", 1)

    assert result.mfe_pct == 2.0
    assert result.mae_pct == -1.0
    assert result.candles == 2


def test_ambiguous_position_gone_uses_realized_pnl_not_sl_substring(tmp_path, monkeypatch) -> None:
    entry_ms = 1_700_000_000_000
    rows = [
        [entry_ms, 100.0, 101.0, 99.9, 100.8, 1.0],
        [entry_ms + 60_000, 100.8, 102.0, 100.5, 101.5, 1.0],
    ]
    monkeypatch.setattr(report, "_load_symbol_candles", lambda *_args, **_kwargs: rows)
    trade = Trade(
        source="live:test",
        strategy="range",
        symbol="TESTUSDT",
        side="long",
        entry_ts_ms=entry_ms,
        exit_ts_ms=entry_ms + 60_000,
        entry_price=100.0,
        exit_price=101.5,
        qty=1.0,
        pnl=1.5,
        fees=0.0,
        outcome="position_gone(tp/sl/manual)",
        reason="test",
        sl_price=99.0,
        tp_price=102.0,
    )

    result = report.analyze_trade(trade, tmp_path, "1", 1)

    assert result.verdict == "clean_win"
