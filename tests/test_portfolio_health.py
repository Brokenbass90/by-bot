import sqlite3
import time

from bot import portfolio_health
from bot.edge_monitor import HealthReport


def test_sleeve_r_multiples_from_db_uses_actual_stop_risk(tmp_path):
    db = tmp_path / "trades.db"
    now = int(time.time())
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE trade_events ("
            "ts INT, event TEXT, strategy TEXT, qty REAL, entry_price REAL, sl_price REAL, pnl REAL)"
        )
        con.execute(
            "INSERT INTO trade_events VALUES (?,?,?,?,?,?,?)",
            (now, "CLOSE", "att1_trendline_touch", 10.0, 100.0, 99.0, 20.0),
        )
        con.execute(
            "INSERT INTO trade_events VALUES (?,?,?,?,?,?,?)",
            (now, "CLOSE", "att1_trendline_touch", 10.0, 100.0, 99.0, -5.0),
        )
        con.execute(
            "INSERT INTO trade_events VALUES (?,?,?,?,?,?,?)",
            (now, "CLOSE", "att1_trendline_touch", 10.0, 100.0, 100.0, 99.0),
        )
        con.execute(
            "INSERT INTO trade_events VALUES (?,?,?,?,?,?,?)",
            (now, "OPEN", "att1_trendline_touch", 10.0, 100.0, 99.0, -99.0),
        )

    rs = portfolio_health.sleeve_r_multiples_from_db(str(db), lookback_days=1)

    assert rs == {"att1_trendline_touch": [2.0, -0.5]}


def test_build_report_includes_risk_multiplier():
    rep = HealthReport(
        sleeve="range",
        status="degraded",
        n=25,
        live_expectancy_R=-0.01,
        baseline_expectancy_R=0.05,
        ratio=-0.2,
        win_rate=0.42,
        drawdown_R=2.0,
        worst_losing_streak=3,
        reason="edge_decay_ratio_-0.20",
    )

    out = portfolio_health.build_report({"range": rep})

    assert out["sleeves"]["range"]["risk_mult"] == 0.5
    assert out["degraded_sleeves"] == ["range"]
    assert out["halted_sleeves"] == []
