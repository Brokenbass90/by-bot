import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.strategy_breaker import breaker_state, recent_close_stats, _parse_expiry


def _make_db(tmp_path, rows, strategy="alt_trendline_touch_v1"):
    """rows: list of (pnl, ts_offset_sec_from_now). Negative offset = in the past."""
    db = str(tmp_path / "trades.db")
    now = int(time.time())
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE trade_events (event TEXT, strategy TEXT, pnl REAL, ts INTEGER)"
    )
    for pnl, off in rows:
        con.execute(
            "INSERT INTO trade_events (event, strategy, pnl, ts) VALUES (?,?,?,?)",
            ("CLOSE", strategy, pnl, now + off),
        )
    # noise: another strategy + a non-close event must be ignored
    con.execute("INSERT INTO trade_events VALUES ('CLOSE','other',-99.0,?)", (now,))
    con.execute("INSERT INTO trade_events VALUES ('OPEN',?, -99.0,?)", (strategy, now))
    con.commit()
    con.close()
    return db


def test_stats_aggregate_and_streak(tmp_path):
    db = _make_db(tmp_path, [(1.0, -100), (-0.5, -90), (-0.4, -80), (2.0, -70), (-0.3, -60)])
    s = recent_close_stats(db, "alt_trendline_touch_v1", 30)
    assert s["trades"] == 5
    assert s["wins"] == 2
    assert abs(s["net_pnl"] - 1.8) < 1e-9
    assert s["max_consec_losses"] == 2  # the -0.5,-0.4 run


def test_full_risk_when_profitable(tmp_path):
    db = _make_db(tmp_path, [(1.0, -i * 100) for i in range(8)])
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6, hard_net_pnl=-4.5, soft_net_pnl=-2.0)
    assert st["blocked"] is False
    assert st["risk_mult"] == 1.0


def test_soft_cut(tmp_path):
    # net = -2.5 over 8 trades -> below soft -2.0 but above hard -4.5
    rows = [(-0.5, -i * 100) for i in range(5)] + [(0.0, -900 - i * 100) for i in range(3)]
    db = _make_db(tmp_path, rows)
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6,
                       soft_net_pnl=-2.0, soft_mult=0.5, hard_net_pnl=-4.5,
                       max_consec_losses=99)
    assert st["blocked"] is False
    assert st["risk_mult"] == 0.5


def test_hard_block_on_net(tmp_path):
    db = _make_db(tmp_path, [(-1.0, -i * 100) for i in range(8)])  # net -8
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6, hard_net_pnl=-4.5,
                       max_consec_losses=99)
    assert st["blocked"] is True
    assert st["risk_mult"] == 0.0
    assert "hard" in st["reason"]


def test_consecutive_loss_kill_small_sample(tmp_path):
    # only 3 trades but all losses -> streak kill even below min_trades
    db = _make_db(tmp_path, [(-0.2, -300), (-0.2, -200), (-0.2, -100)])
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6, max_consec_losses=3)
    assert st["blocked"] is True
    assert "consecutive" in st["reason"]


def test_min_trades_gate_blocks_pnl_rule(tmp_path):
    # net very negative but too few trades -> no pnl block (streak off)
    db = _make_db(tmp_path, [(-3.0, -100)])
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6, hard_net_pnl=-4.5,
                       max_consec_losses=None)
    assert st["blocked"] is False


def test_expiry_blocks_regardless(tmp_path):
    db = _make_db(tmp_path, [(5.0, -100)])  # profitable
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6,
                       expiry_utc="2000-01-01")
    assert st["expired"] is True
    assert st["blocked"] is True
    assert st["risk_mult"] == 0.0


def test_expiry_future_ok(tmp_path):
    db = _make_db(tmp_path, [(1.0, -i * 100) for i in range(8)])
    st = breaker_state(db, "alt_trendline_touch_v1", min_trades=6,
                       expiry_utc="2099-01-01")
    assert st["expired"] is False
    assert st["blocked"] is False


def test_parse_expiry_formats():
    assert _parse_expiry("2026-07-15") is not None
    assert _parse_expiry("2026-07-15T12:30:00") is not None
    assert _parse_expiry("2026-07-15 12:30:00 UTC") is not None
    assert _parse_expiry("") is None
    assert _parse_expiry(None) is None
    assert _parse_expiry("garbage") is None


def test_lookback_excludes_old(tmp_path):
    # old loss outside window must be excluded
    db = _make_db(tmp_path, [(-10.0, -40 * 86400), (1.0, -100), (1.0, -200)])
    s = recent_close_stats(db, "alt_trendline_touch_v1", 30)
    assert s["trades"] == 2
    assert abs(s["net_pnl"] - 2.0) < 1e-9


def test_missing_db_is_safe(tmp_path):
    st = breaker_state(str(tmp_path / "nope.db"), "alt_trendline_touch_v1")
    assert st["blocked"] is False
    assert st["trades"] == 0
