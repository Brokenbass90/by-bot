"""Tests for the crypto efficiency backtester (R-math + store cursor)."""

from backtest.crypto_efficiency_backtest import _metrics, BacktestStore


def test_metrics_R_math():
    # 2 wins (+3R, +2R), 2 losses (-1R, -1R) over 30 days
    Rs = [3.0, -1.0, 2.0, -1.0]
    start = 0; end = 30 * 86400000
    m = _metrics(Rs, start, end)
    assert m["trades"] == 4
    assert m["win_pct"] == 50.0
    assert m["avg_win_R"] == 2.5
    assert m["avg_loss_R"] == -1.0
    assert m["expectancy_R"] == 0.75          # (3-1+2-1)/4
    assert m["profit_factor"] == 2.5          # 5 / 2
    assert m["trades_per_30d"] == 4.0


def test_metrics_empty():
    assert _metrics([], 0, 1)["trades"] == 0


def test_store_cursor_only_returns_past_bars():
    # build a fake store by injecting data directly
    s = BacktestStore.__new__(BacktestStore)
    s.symbol = "X"
    s._data = {"5": [[100, 1, 1, 1, 1, 0], [200, 2, 2, 2, 2, 0], [300, 3, 3, 3, 3, 0]]}
    s._ts = {"5": [100, 200, 300]}
    s._cursor_ts = 0
    s.set_cursor(200)
    rows = s.fetch_klines("X", "5", 10)
    assert [r[0] for r in rows] == [100, 200]   # no look-ahead past cursor
    assert s.fetch_klines("X", "5", 1)[0][0] == 200
