import csv
from datetime import date, timedelta
from pathlib import Path

from backtest.alpaca_exact_parity_contract import DailyBar
from backtest.alpaca_honest_portfolio import select_v38_successor
from scripts import alpaca_adaptive_paper as adaptive_paper
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP


def _frozen_history() -> dict[str, list[DailyBar]]:
    start = date(2025, 1, 1)
    history: dict[str, list[DailyBar]] = {}
    for n, symbol in enumerate(("SPY", "UNH", "CVX", "CAT", "AAPL", "JPM")):
        rows = []
        for i in range(220):
            base = 100.0 + n * 30.0 + i * (0.80 + n * 0.006)
            close = base * 0.975 if i in (209, 219) and symbol != "SPY" else base
            rows.append(DailyBar(start + timedelta(days=i), close - 0.2, close + 1.0, close - 1.0, close))
        history[symbol] = rows
    return history


def test_intended_prepare_matches_direct_canonical_selection_and_stops_at_signal_close():
    history = _frozen_history()
    signal = history["SPY"][209].session_date
    expected_history = {symbol: [bar for bar in rows if bar.session_date <= signal] for symbol, rows in history.items()}
    expected = select_v38_successor(expected_history, sectors=SECTOR_MAP, clusters=adaptive_paper._frozen_clusters(), top_n=4, maximum_weight=0.60)
    report = adaptive_paper.prepare_intended_report(history, signal_session=signal, entry_session=history["SPY"][210].session_date)
    assert [pick["symbol"] for pick in report["picks"]] == [pick.symbol for pick in expected]
    assert report["picks"]
    assert [pick["weight"] for pick in report["picks"]] == [pick.weight for pick in expected]
    assert all(pick["stop_price"] == pick["signal_close"] - 2.0 * pick["atr20"] for pick in report["picks"])


def test_intended_prepare_never_reads_future_bar_at_or_after_cutoff():
    history = _frozen_history()
    signal = history["SPY"][209].session_date
    baseline = adaptive_paper.prepare_intended_report(history, signal_session=signal, entry_session=history["SPY"][210].session_date)
    history["UNH"][-1] = DailyBar(history["UNH"][-1].session_date, 1, 2, 1, 1_000_000)
    after = adaptive_paper.prepare_intended_report(history, signal_session=signal, entry_session=history["SPY"][210].session_date)
    assert after["picks"] == baseline["picks"]


def test_intended_bridge_csv_keeps_frozen_weight_rawscore_and_signal_close_stop(tmp_path: Path):
    report = {"entry_session": "2026-09-30", "picks": [{"symbol": "UNH", "rawscore": 0.42, "weight": 0.60, "atr20_pct": 1.2, "signal_close": 100.0, "stop_price": 96.0}]}
    csv_path = tmp_path / "frozen.csv"
    adaptive_paper.write_intended_bridge_picks_csv(report, csv_path)
    row = next(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
    assert (float(row["score"]), float(row["base_score"]), float(row["entry_price"]), float(row["stop_price"])) == (0.60, 0.42, 100.0, 96.0)


def test_intended_paper_env_is_frozen_and_never_exports_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "must-not-be-exported")
    env = adaptive_paper.build_intended_bridge_env({}, picks_csv=tmp_path / "picks.csv", capital=1_000.0)
    assert env["ALPACA_BASE_URL"] == "https://paper-api.alpaca.markets"
    assert env["ALPACA_SEND_ORDERS"] == "0" and env["ALPACA_ALLOW_NEW_ENTRIES"] == "0"
    assert env["MONTHLY_WEIGHTED_SIZING"] == "1" and env["MONTHLY_ATR_SIZING"] == "0"
    assert env["ALPACA_ENTRY_RELATIVE_STOP_ENABLE"] == "1" and env["ALPACA_BROKER_PROTECTION_TIF"] == "day"
    assert env["ALPACA_PROTECTIVE_TRAIL_ACTIVATE_GAIN_PCT"] == "3.5"
    assert env["ALPACA_PROTECTIVE_TRAIL_PCT"] == "3.5" and env["ALPACA_PROTECTIVE_MIN_LOCK_GAIN_PCT"] == "0.5"
    assert env["MONTHLY_TRAIL_REENTRY_BLOCK_DAYS"] == "21"
    assert "ALPACA_API_SECRET_KEY" not in env
