"""Tests for the red-month hedge pairing tool."""
import datetime as dt

from backtest.hedge_pairing import hedge_report, combine_streams, format_hedge_summary


def _t(month, day, pnl, regime):
    ts = int(dt.datetime(2026, month, day).timestamp() * 1000)
    return {"exit_ts_ms": ts, "pnl": pnl, "regime": regime}


def test_hedge_covers_primary_red_bear_month():
    # primary (range) bleeds in a bear month; hedge (breakdown) is green there
    primary = [_t(2, 5, 6.0, "bull_trend"), _t(3, 5, -4.0, "bear_chop")]
    hedge = [_t(3, 6, 5.0, "bear_chop")]
    rep = hedge_report(primary, hedge)
    assert rep["primary_verdict"] == "FAIL"          # red bear month 2026-03
    assert "2026-03" in rep["red_bear_primary"]
    assert rep["combined_verdict"] == "PASS"          # hedge turned it green
    assert "2026-03" in rep["covered_red_bear_months"]
    assert rep["improved"] is True


def test_hedge_that_does_not_cover_leaves_month_red():
    primary = [_t(2, 5, 6.0, "bull_trend"), _t(3, 5, -4.0, "bear_chop")]
    hedge = [_t(3, 6, 1.0, "bear_chop")]  # too small to flip the month
    rep = hedge_report(primary, hedge)
    assert rep["combined_verdict"] == "FAIL"
    assert "2026-03" in rep["uncovered_red_bear_months"]
    assert rep["improved"] is False


def test_hedge_drag_flags_months_made_red_by_hedge():
    # primary green in a (non-bear) month, hedge loses enough to turn it red
    primary = [_t(5, 5, 2.0, "bull_trend")]
    hedge = [_t(5, 6, -5.0, "bull_trend")]
    rep = hedge_report(primary, hedge)
    assert "2026-05" in rep["hedge_drag_months"]


def test_combine_streams_concatenates():
    a = [_t(1, 1, 1.0, "x")]
    b = [_t(1, 2, 2.0, "y")]
    assert len(combine_streams(a, b)) == 2


def test_explicit_bear_months_path_and_summary_text():
    primary = [_t(6, 4, -3.0, "")]  # no regime label -> use explicit bear months
    hedge = [_t(6, 5, 4.0, "")]
    rep = hedge_report(primary, hedge, bear_months={"2026-06"})
    assert rep["primary_verdict"] == "FAIL" and rep["combined_verdict"] == "PASS"
    txt = format_hedge_summary(rep)
    assert "HEDGE HELPS" in txt
