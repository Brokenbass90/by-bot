from bot.bybit_closed_pnl import (
    BYBIT_CLOSED_PNL_MAX_WINDOW_MS,
    aggregate_closed_pnl,
    closed_pnl_query_windows,
)


ENTRY_MS = 1_780_000_000_000


def test_query_windows_respect_bybit_seven_day_limit_without_gaps():
    end = ENTRY_MS + BYBIT_CLOSED_PNL_MAX_WINDOW_MS + 240_000

    windows = closed_pnl_query_windows(ENTRY_MS - 120_000, end)

    assert len(windows) == 2
    assert all(right - left <= BYBIT_CLOSED_PNL_MAX_WINDOW_MS for left, right in windows)
    assert windows[1][0] == windows[0][1] + 1
    assert windows[0][0] == ENTRY_MS - 120_000
    assert windows[-1][1] == end


def test_query_windows_reject_invalid_range():
    assert closed_pnl_query_windows(ENTRY_MS, ENTRY_MS - 1) == ()
    assert closed_pnl_query_windows(0, ENTRY_MS) == ()


def _row(
    order_id: str,
    *,
    updated_ms: int,
    size: str,
    pnl: str,
    side: str = "Buy",
    entry: str = "100.0",
    exit_price: str = "95.0",
    symbol: str = "BTCUSDT",
    exec_type: str = "Trade",
):
    return {
        "symbol": symbol,
        "orderId": order_id,
        "side": side,
        "execType": exec_type,
        "closedSize": size,
        "avgEntryPrice": entry,
        "avgExitPrice": exit_price,
        "closedPnl": pnl,
        "createdTime": str(updated_ms - 10),
        "updatedTime": str(updated_ms),
    }


def test_aggregates_partial_take_profits_and_final_exit():
    rows = [
        _row("final", updated_ms=ENTRY_MS + 30_000, size="0.4", pnl="-0.10", exit_price="99"),
        _row("tp2", updated_ms=ENTRY_MS + 20_000, size="0.3", pnl="0.80", exit_price="96"),
        _row("tp1", updated_ms=ENTRY_MS + 10_000, size="0.3", pnl="1.20", exit_price="94"),
    ]

    out = aggregate_closed_pnl(
        rows,
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is not None
    assert out.pnl == 1.9
    assert out.closed_size == 1.0
    assert out.latest_exit_price == 99.0
    assert [row["orderId"] for row in out.rows] == ["tp1", "tp2", "final"]


def test_waits_for_all_partial_rows_before_finalizing():
    out = aggregate_closed_pnl(
        [_row("final-visible-first", updated_ms=ENTRY_MS + 30_000, size="0.4", pnl="-0.10")],
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is None


def test_rejects_unbounded_lifecycle_without_expected_size():
    out = aggregate_closed_pnl(
        [_row("apparently-valid", updated_ms=ENTRY_MS + 30_000, size="1", pnl="4")],
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=None,
    )

    assert out is None


def test_excludes_prior_trade_other_side_price_symbol_and_non_trade_rows():
    valid = _row("valid", updated_ms=ENTRY_MS + 10_000, size="1", pnl="2")
    rows = [
        _row("prior", updated_ms=ENTRY_MS - 1, size="1", pnl="99"),
        _row("other-side", updated_ms=ENTRY_MS + 1, size="1", pnl="99", side="Sell"),
        _row("other-entry", updated_ms=ENTRY_MS + 2, size="1", pnl="99", entry="101"),
        _row("other-symbol", updated_ms=ENTRY_MS + 3, size="1", pnl="99", symbol="ETHUSDT"),
        _row("settlement", updated_ms=ENTRY_MS + 4, size="1", pnl="99", exec_type="SessionSettlePnL"),
        valid,
    ]

    out = aggregate_closed_pnl(
        rows,
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is not None
    assert out.pnl == 2.0
    assert [row["orderId"] for row in out.rows] == ["valid"]


def test_deduplicates_order_snapshots_and_stops_at_logical_position_size():
    stale = _row("tp", updated_ms=ENTRY_MS + 10_000, size="0.5", pnl="0.3")
    refreshed = _row("tp", updated_ms=ENTRY_MS + 11_000, size="0.5", pnl="0.5")
    final = _row("final", updated_ms=ENTRY_MS + 20_000, size="0.5", pnl="0.2")
    later_unrelated = _row("later", updated_ms=ENTRY_MS + 30_000, size="1", pnl="100")

    out = aggregate_closed_pnl(
        [later_unrelated, stale, final, refreshed],
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is not None
    assert out.pnl == 0.7
    assert [row["orderId"] for row in out.rows] == ["tp", "final"]


def test_buy_position_matches_sell_close_orders():
    out = aggregate_closed_pnl(
        [_row("long-close", updated_ms=ENTRY_MS + 10_000, size="1", pnl="1.5", side="Sell")],
        symbol="BTCUSDT",
        position_side="Buy",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is not None
    assert out.pnl == 1.5


def test_fee_alias_families_are_prioritized_without_double_counting():
    current = _row("current", updated_ms=ENTRY_MS + 10_000, size="0.25", pnl="1")
    current.update({
        "openFee": "0.10",
        "closeFee": "0.20",
        "cumEntryFee": "9",
        "cumExitFee": "9",
        "totalFee": "9",
        "fee": "9",
    })
    cumulative = _row("cumulative", updated_ms=ENTRY_MS + 20_000, size="0.25", pnl="1")
    cumulative.update({"cumEntryFee": "0.30", "cumExitFee": "0.40", "totalFee": "9", "fee": "9"})
    total = _row("total", updated_ms=ENTRY_MS + 30_000, size="0.25", pnl="1")
    total.update({"totalFee": "0.50", "fee": "9"})
    legacy = _row("legacy", updated_ms=ENTRY_MS + 40_000, size="0.25", pnl="1")
    legacy.update({"fee": "0.60"})

    out = aggregate_closed_pnl(
        [legacy, total, cumulative, current],
        symbol="BTCUSDT",
        position_side="Sell",
        entry_time_ms=ENTRY_MS,
        entry_price=100.0,
        expected_size=1.0,
    )

    assert out is not None
    assert out.fees == 2.1


def test_live_finalizer_sends_aggregate_to_all_accounting_sinks(monkeypatch):
    import smart_pump_reversal_bot as live
    from trade_state import TradeState

    rows = [
        _row("tp", updated_ms=ENTRY_MS + 10_000, size="0.4", pnl="1.25", exit_price="96"),
        _row("final", updated_ms=ENTRY_MS + 20_000, size="0.6", pnl="-0.20", exit_price="99"),
    ]

    class Client:
        def get_closed_pnl(self, symbol, start_ms, end_ms, limit):
            assert symbol == "BTCUSDT"
            assert limit == 100
            return rows

    class Wire:
        def __init__(self):
            self.outcomes = []

        def record_outcome(self, tr, symbol, pnl, exit_reason):
            self.outcomes.append((symbol, pnl, exit_reason))

    wire = Wire()
    live_events = []
    db_events = []
    ml_closes = []
    ai_reviews = []
    monkeypatch.setattr(live, "TRADE_CLIENT", Client())
    monkeypatch.setattr(live, "now_s", lambda: ENTRY_MS // 1000 + 30)
    monkeypatch.setattr(live, "tg_trade", lambda *args, **kwargs: None)
    monkeypatch.setattr(live, "log_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(live, "_get_meta", lambda symbol: {"tickSize": 0.01})
    monkeypatch.setattr(live, "_att1_wire", wire)
    monkeypatch.setattr(live, "BIG_LOSS_ALERT_USD", 0.0)
    monkeypatch.setattr(live, "TRADE_CHARTS_SEND_ON_CLOSE", False)
    monkeypatch.setattr(
        live,
        "_append_live_trade_event",
        lambda event, symbol, tr, **kwargs: live_events.append((event, symbol, kwargs)),
    )
    monkeypatch.setattr(
        live,
        "_db_log_event",
        lambda event, tr, symbol, **kwargs: db_events.append((event, symbol, kwargs)),
    )
    monkeypatch.setattr(
        live,
        "_db_log_ml_close",
        lambda tr, symbol, **kwargs: ml_closes.append((symbol, kwargs)),
    )
    monkeypatch.setattr(
        live,
        "_maybe_schedule_ai_trade_review",
        lambda tr, symbol, pnl, fees, exit_px: ai_reviews.append((symbol, pnl, fees, exit_px)),
    )

    tr = TradeState(
        symbol="BTCUSDT",
        side="Sell",
        strategy="att1_trendline_touch",
        qty=1.0,
        entry_ts=ENTRY_MS // 1000,
        avg=100.0,
        entry_price=100.0,
        status="OPEN",
    )
    # Non-runner/full-exit trades do not populate initial_qty; the finalizer
    # must still bound the lifecycle with the last exchange-confirmed qty.
    tr.initial_qty = 0.0
    tr.close_reason = "TRAIL"

    live._finalize_and_report_closed(tr, "BTCUSDT")

    assert tr.status == "CLOSED"
    assert live_events[0][2]["pnl"] == 1.05
    assert db_events[0][2]["pnl"] == 1.05
    assert wire.outcomes == [("BTCUSDT", 1.05, "TRAIL")]
    assert ml_closes[0][1]["pnl"] == 1.05
    assert ai_reviews == [("BTCUSDT", 1.05, 0.0, 99.0)]
