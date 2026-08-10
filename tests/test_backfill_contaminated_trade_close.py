import argparse
import json
import sqlite3

from scripts.backfill_contaminated_trade_close import backfill


def _args(tmp_path, *, apply: bool):
    return argparse.Namespace(
        db=str(tmp_path / "trades.db"),
        events=str(tmp_path / "events.jsonl"),
        symbol="ADAUSDT",
        side="Sell",
        strategy="att1_trendline_touch",
        entry_ts=100,
        expected_qty=180.0,
        broker_qty=270.0,
        entry_price=0.1984,
        exit_price=0.1949,
        pnl=0.73928972,
        fees=0.05849218,
        reason="TRAILING_SL",
        apply=apply,
    )


def _db(path):
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE trade_events (
        id INTEGER PRIMARY KEY, ts INTEGER, event TEXT, exchange TEXT,
        symbol TEXT, side TEXT, strategy TEXT, qty REAL, entry_price REAL,
        exit_price REAL, tp_price REAL, sl_price REAL, pnl REAL, fees REAL,
        reason TEXT)"""
    )
    con.execute(
        """INSERT INTO trade_events
        (ts,event,exchange,symbol,side,strategy,qty,entry_price)
        VALUES (100,'ENTRY','Bybit','ADAUSDT','Sell','att1_trendline_touch',180,0.198)"""
    )
    con.commit()
    con.close()


def test_backfill_is_dry_run_by_default_and_idempotent(tmp_path):
    _db(tmp_path / "trades.db")
    assert backfill(_args(tmp_path, apply=False))["status"] == "WOULD_APPLY"
    with sqlite3.connect(tmp_path / "trades.db") as con:
        assert con.execute("SELECT count(*) FROM trade_events").fetchone()[0] == 1

    result = backfill(_args(tmp_path, apply=True))
    assert result["status"] == "APPLIED"
    with sqlite3.connect(tmp_path / "trades.db") as con:
        close = con.execute(
            "SELECT strategy,pnl,reason FROM trade_events WHERE event='CLOSE'"
        ).fetchone()
    assert close[0] == "att1_trendline_touch__contaminated"
    assert close[1] == 0.73928972
    assert "CONTAMINATED_QTY" in close[2]
    event = json.loads((tmp_path / "events.jsonl").read_text().strip())
    assert event["accounting_contaminated"] is True
    assert backfill(_args(tmp_path, apply=True))["status"] == "ALREADY_CLOSED"
