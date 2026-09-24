import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backtest.alpaca_exact_parity_contract import DailyBar
from scripts import alpaca_adaptive_paper as adaptive_paper


def _history():
    start = date(2026, 1, 1)
    rows = [start + timedelta(days=index) for index in range((date(2026, 10, 1) - start).days + 1)]
    result = {}
    for offset, symbol in enumerate(("SPY", "UNH", "CVX", "CAT", "AAPL", "JPM")):
        result[symbol] = [
            DailyBar(day, 100 + offset + index, 102 + offset + index, 99 + offset + index, 101 + offset + index)
            for index, day in enumerate(rows)
        ]
    return result


class CalendarClient:
    def __init__(self, timestamp, rows):
        self.timestamp = timestamp
        self.rows = rows
        self.requests = []

    def get_clock(self):
        return {"timestamp": self.timestamp}

    def _request(self, method, path):
        self.requests.append((method, path))
        return self.rows


SEPT_OCT = [
    {"date": "2026-08-31", "open": "09:30", "close": "16:00"},
    {"date": "2026-09-29", "open": "09:30", "close": "16:00"},
    {"date": "2026-09-30", "open": "09:30", "close": "16:00"},
    {"date": "2026-10-01", "open": "09:30", "close": "16:00"},
]


def test_waits_before_month_close_without_loading_or_replacing_selection(tmp_path, monkeypatch):
    client = CalendarClient("2026-09-30T19:59:00Z", SEPT_OCT)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: pytest.fail("must not prepare before close"))

    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )

    assert result["status"] == "WAITING_FOR_MONTH_CLOSE"
    assert not (tmp_path / "latest_selection.json").exists()
    assert not (tmp_path / "cycles").exists()


@pytest.mark.parametrize("timestamp", ["2026-09-30T20:00:00Z", "2026-10-01T13:30:00Z"])
def test_month_close_stages_immutable_next_open_cycle(tmp_path, monkeypatch, timestamp):
    client = CalendarClient(timestamp, SEPT_OCT)
    history = _history()
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: history)

    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )

    assert result["status"] == "PREPARED"
    assert result["signal_session"] == "2026-09-30"
    assert result["entry_session"] == "2026-10-01"
    report = json.loads((tmp_path / "cycles" / "2026-10-01" / "latest_selection.json").read_text())
    assert report["capital_usd"] == 487.42
    assert report["monthly_schedule"]["calendar_sha256"]
    assert not (tmp_path / "latest_selection.json").exists()


def test_weekend_month_boundary_uses_next_calendar_session(tmp_path, monkeypatch):
    client = CalendarClient("2026-08-29T18:00:00Z", [
        {"date": "2026-08-28", "open": "09:30", "close": "16:00"},
        {"date": "2026-09-01", "open": "09:30", "close": "16:00"},
    ])
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: _history())

    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-09-01"
    )

    assert (result["signal_session"], result["entry_session"]) == ("2026-08-28", "2026-09-01")


def test_first_entry_guard_does_not_backfill_old_month(tmp_path, monkeypatch):
    client = CalendarClient("2026-08-29T18:00:00Z", [
        {"date": "2026-08-28", "open": "09:30", "close": "16:00"},
        {"date": "2026-09-01", "open": "09:30", "close": "16:00"},
    ])
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: pytest.fail("old cycle must not prepare"))

    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )

    assert result["status"] == "WAITING_FOR_FIRST_ENTRY_SESSION"


def test_cycle_is_stable_and_future_cache_bar_is_not_used(tmp_path, monkeypatch):
    client = CalendarClient("2026-09-30T20:00:00Z", SEPT_OCT)
    history = _history()
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: history)
    first = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )
    report_path = tmp_path / "cycles" / "2026-10-01" / "latest_selection.json"
    frozen = report_path.read_bytes()
    history["UNH"][-1] = DailyBar(date(2026, 10, 1), 1, 2, 1, 1_000_000)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: pytest.fail("frozen cycle must not reload"))

    repeated = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )

    assert first["status"] == "PREPARED" and repeated["status"] == "ALREADY_PREPARED"
    assert report_path.read_bytes() == frozen
    with pytest.raises(ValueError, match="capital"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, tmp_path / "cache", 400.0, client, first_entry_session="2026-10-01"
        )
    monkeypatch.setattr(adaptive_paper, "_frozen_source_hashes", lambda: {"changed": True})
    with pytest.raises(ValueError, match="conflict"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
        )


def test_cycle_resume_ignores_calendar_rows_outside_frozen_signal_and_entry(tmp_path, monkeypatch):
    client = CalendarClient("2026-09-30T20:00:00Z", SEPT_OCT)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: _history())
    first = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )
    report_path = tmp_path / "cycles" / "2026-10-01" / "latest_selection.json"
    picks_path = tmp_path / "cycles" / "2026-10-01" / "current_cycle_picks.csv"
    frozen = (report_path.read_bytes(), picks_path.read_bytes())
    client.rows = [
        {"date": "2026-08-03", "open": "09:30", "close": "16:00"},
        *SEPT_OCT,
        {"date": "2026-11-02", "open": "09:30", "close": "16:00"},
    ]
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: pytest.fail("frozen cycle must not reload"))

    resumed = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )

    assert first["status"] == "PREPARED" and resumed["status"] == "ALREADY_PREPARED"
    assert (report_path.read_bytes(), picks_path.read_bytes()) == frozen


def test_cycle_resume_rejects_corrupted_frozen_csv(tmp_path, monkeypatch):
    client = CalendarClient("2026-09-30T20:00:00Z", SEPT_OCT)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: _history())
    adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )
    (tmp_path / "cycles" / "2026-10-01" / "current_cycle_picks.csv").write_text("tampered\\n")
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: pytest.fail("frozen cycle must not reload"))

    with pytest.raises(ValueError, match="picks"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
        )


def test_interrupted_staging_leaves_only_partial_evidence_and_can_retry(tmp_path, monkeypatch):
    client = CalendarClient("2026-09-30T20:00:00Z", SEPT_OCT)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda _: _history())
    original_write = adaptive_paper._atomic_write_private_json

    def crash_before_publication(path, payload):
        raise OSError("interrupted before cycle publication")

    monkeypatch.setattr(adaptive_paper, "_atomic_write_private_json", crash_before_publication)
    with pytest.raises(OSError, match="before cycle publication"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
        )
    cycles = tmp_path / "cycles"
    assert not (cycles / "2026-10-01").exists()
    assert any(path.name.startswith(".2026-10-01.partial-") for path in cycles.iterdir())
    monkeypatch.setattr(adaptive_paper, "_atomic_write_private_json", original_write)

    assert adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, tmp_path / "cache", 487.42, client, first_entry_session="2026-10-01"
    )["status"] == "PREPARED"
