from bot.fx_contracts import FxEvent, FxExecutionCosts, FxTradePlan
from bot.fx_harness_v2 import backtest_fx_plan_strategy, reprice_trades


BASE = FxExecutionCosts(1.0, 0.1, 0.2, 0.05, 0.2, 0.05, "base")
STRESS = FxExecutionCosts(2.0, 0.2, 0.5, 0.1, 0.5, 0.10, "stress")
STRESS_FEES_ONLY = FxExecutionCosts(1.0, 0.2, 0.5, 0.1, 0.5, 0.10, "stress_fees")


def _rows(n=20):
    return [[i * 3600, 100.0, 100.5, 99.5, 100.0, 1.0] for i in range(n)]


def _plan(ts, *, entry_type="market_next_open", limit=None, stop=99.0, rr=2.0, validity=2,
          sessions=(), max_hold=5):
    event = FxEvent(f"event-{ts}", "unit", "long", ts, 100.0, "horizontal", "unit")
    return FxTradePlan(
        event, entry_type, 100.0, stop, rr, max_hold, validity_bars=validity,
        limit_price=limit, max_entry_gap_atr=2.0,
        allowed_fill_sessions=tuple(sessions), metadata={"atr": 1.0},
    )


def test_market_signal_fills_only_on_next_open():
    rows = _rows()
    rows[4] = [4 * 3600, 101.0, 105.5, 100.5, 104.0, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0]) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3, context_bars=20)
    assert len(result.trades) == 1
    assert result.trades[0]["signal_ts"] == 3 * 3600
    assert result.trades[0]["entry_ts"] == 4 * 3600
    assert result.trades[0]["entry"] > 101.0  # executable ask, not MID open


def test_stop_gap_is_worse_than_minus_one_r():
    rows = _rows()
    rows[4] = [4 * 3600, 100.0, 100.4, 99.6, 100.0, 1.0]
    rows[5] = [5 * 3600, 98.0, 98.5, 97.5, 98.2, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0]) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades[0]["exit_reason"] == "SL_GAP"
    assert result.trades[0]["gross_r"] < -1.0


def test_limit_must_trade_or_is_unfilled():
    rows = _rows()

    def strategy(prefix):
        return _plan(prefix[-1][0], entry_type="limit", limit=99.2) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.unfilled == 1


def test_marketable_limit_uses_open_and_rejects_gap_through_stop():
    rows = _rows()
    # A resting buy limit is marketable at this open.  It must not pretend to
    # fill later at 100 after the market already gapped through its stop.
    rows[4] = [4 * 3600, 97.0, 100.5, 96.5, 99.5, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0], entry_type="limit", limit=100.0, validity=1) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.skipped_gap == 1


def test_intrabar_limit_fill_cannot_claim_earlier_same_bar_target():
    rows = _rows()
    # At H1 resolution the high may have happened before the later drop to the
    # limit.  The fill is valid, but a same-bar TP is unknowable and forbidden.
    rows[4] = [4 * 3600, 103.0, 104.0, 99.5, 100.5, 1.0]
    rows[5] = [5 * 3600, 100.5, 100.8, 99.8, 100.2, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0], entry_type="limit", limit=100.0) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert len(result.trades) == 1
    assert result.trades[0]["entry"] == 100.0
    assert result.trades[0]["exit_reason"] != "TP"


def test_stress_repricing_cannot_improve_net_r():
    rows = _rows()
    rows[4] = [4 * 3600, 100.0, 103.0, 99.8, 102.0, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0]) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    stressed = reprice_trades(result.trades, STRESS_FEES_ONLY)
    assert stressed[0]["r"] < result.trades[0]["r"]


def test_side_specific_swap_debit_and_credit_change_net_r():
    rows = _rows(80)
    signed = FxExecutionCosts(
        1.0, 0.1, 0.2, 0.05, 0.2, 0.0, "signed",
        financing_long_bps_per_day=-2.0,
        financing_short_bps_per_day=1.0,
    )
    long_trade = {
        "side": "long",
        "entry_type": "market_next_open",
        "risk_frac": 0.01,
        "duration_days": 2.0,
        "gross_r": 0.0,
        "synthetic_spread_bps": 1.0,
    }
    short_trade = {**long_trade, "side": "short"}
    repriced = reprice_trades([long_trade, short_trade], signed)
    assert repriced[0]["financing_cashflow_bps"] == -4.0
    assert repriced[1]["financing_cashflow_bps"] == 2.0
    assert repriced[1]["r"] > repriced[0]["r"]


def test_spread_change_requires_complete_barrier_rerun():
    rows = _rows()

    def strategy(prefix):
        return _plan(prefix[-1][0]) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    try:
        reprice_trades(result.trades, STRESS)
    except ValueError as exc:
        assert "rerunning fills" in str(exc)
    else:
        raise AssertionError("spread-only repricing must be rejected")


def test_buy_limit_requires_synthetic_ask_to_touch():
    rows = _rows()
    rows[4] = [4 * 3600, 100.2, 100.3, 99.998, 100.1, 1.0]

    def strategy(prefix):
        return _plan(prefix[-1][0], entry_type="limit", limit=100.0, validity=1) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.unfilled == 1


def test_duplicate_event_is_not_reentered():
    rows = _rows(30)
    fixed = _plan(3 * 3600)

    def strategy(prefix):
        return fixed if prefix[-1][0] >= 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3, cooldown_bars=1)
    assert len(result.trades) == 1
    assert result.duplicate_events > 0
    assert any(row["outcome"] == "duplicate_event" for row in result.signal_ledger)
    assert all(row["side"] == "long" for row in result.signal_ledger)


def test_fill_before_decision_timestamp_is_blocked():
    rows = _rows()

    def strategy(prefix):
        # The bar at t=3h cannot legitimately create a decision until t=5h.
        return _plan(5 * 3600) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.blocked_fill_window == 1


def test_open_trade_at_unknown_segment_end_is_censored_not_force_closed():
    rows = _rows(8)

    def strategy(prefix):
        return _plan(prefix[-1][0]) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.censored_trades == 1
    assert result.signal_ledger[0]["outcome"] == "censored_trade_at_segment_end"


def test_unexpired_limit_at_unknown_segment_end_is_censored():
    rows = _rows(6)

    def strategy(prefix):
        return _plan(
            prefix[-1][0], entry_type="limit", limit=99.2, validity=3
        ) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades == []
    assert result.unfilled == 0
    assert result.censored_orders == 1


def test_max_hold_one_means_exactly_the_fill_bar():
    rows = _rows()

    def strategy(prefix):
        return _plan(prefix[-1][0], max_hold=1) if prefix[-1][0] == 3 * 3600 else None

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert len(result.trades) == 1
    assert result.trades[0]["entry_ts"] == 4 * 3600
    assert result.trades[0]["exit_ts"] == 4 * 3600
    assert result.trades[0]["exit_reason"] == "TIME"


def test_short_stop_uses_synthetic_ask_not_mid_high():
    rows = _rows()
    rows[4] = [4 * 3600, 100.0, 100.997, 99.8, 100.5, 1.0]

    def strategy(prefix):
        if prefix[-1][0] != 3 * 3600:
            return None
        event = FxEvent("short-quote", "unit", "short", 3 * 3600, 100.0, "horizontal", "unit")
        return FxTradePlan(
            event, "market_next_open", 100.0, 101.0, 2.0, 5,
            metadata={"atr": 1.0}, max_entry_gap_atr=2.0,
        )

    result = backtest_fx_plan_strategy(rows, strategy, costs=BASE, warmup=3)
    assert result.trades[0]["exit_reason"] == "SL"
    assert result.trades[0]["entry"] < 100.0  # executable bid
