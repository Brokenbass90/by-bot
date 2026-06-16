"""Tests for monthly analysis + bear-month failure rule."""

from backtest.monthly_analysis import monthly_breakdown, verdict, format_table

MS = 86400000


def _t(month, day, pnl, regime):
    import datetime as dt
    ts = int(dt.datetime(2026, month, day).timestamp() * 1000)
    return {"exit_ts_ms": ts, "pnl": pnl, "regime": regime}


def test_breakdown_groups_by_month_and_flags_bear():
    trades = [_t(5, 3, 2.0, "bull_trend"), _t(5, 10, -1.0, "bull_trend"),
              _t(6, 4, -3.0, "bear_chop"), _t(6, 9, -1.0, "bear_chop")]
    b = monthly_breakdown(trades)
    assert b["2026-05"]["pnl"] == 1.0 and b["2026-05"]["is_bear_month"] is False
    assert b["2026-06"]["pnl"] == -4.0 and b["2026-06"]["is_bear_month"] is True
    assert b["2026-06"]["red"] is True


def test_verdict_fails_on_red_bear_month():
    trades = [_t(5, 3, 5.0, "bull_trend"), _t(6, 4, -3.0, "bear_chop")]
    v = verdict(monthly_breakdown(trades))
    assert v["verdict"] == "FAIL"
    assert "2026-06" in v["red_bear_months"]


def test_verdict_pass_when_bear_month_green():
    trades = [_t(5, 3, 5.0, "bull_trend"), _t(6, 4, 2.0, "bear_chop")]
    v = verdict(monthly_breakdown(trades))
    assert v["verdict"] == "PASS"
    assert v["red_bear_months"] == []
    assert "2026-06" in v["bear_months"]


def test_overall_negative_fails_even_without_bear():
    trades = [_t(5, 3, 1.0, "bull_trend"), _t(5, 10, -5.0, "bull_trend")]
    assert verdict(monthly_breakdown(trades))["verdict"] == "FAIL"


def test_table_marks_red_bear():
    trades = [_t(6, 4, -3.0, "bear_chop")]
    txt = format_table(monthly_breakdown(trades))
    assert "RED BEAR" in txt


def test_explicit_bear_months_override_missing_trade_regime():
    trades = [_t(6, 4, -3.0, "")]
    b = monthly_breakdown(trades, bear_months={"2026-06"})
    assert b["2026-06"]["is_bear_month"] is True
    assert b["2026-06"]["bear_source"] == "explicit"
    assert verdict(b)["verdict"] == "FAIL"
