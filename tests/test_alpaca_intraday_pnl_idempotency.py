from __future__ import annotations

import json

import pytest

from scripts import equities_alpaca_intraday_bridge as intraday


def _configure_paths(tmp_path, monkeypatch) -> tuple:
    equity_path = tmp_path / "intraday_equity_log.json"
    ledger_path = tmp_path / "intraday_exit_ledger.json"
    monkeypatch.setattr(intraday, "EQUITY_LOG_FILE", equity_path)
    monkeypatch.setenv("INTRADAY_EXIT_LEDGER_FILE", str(ledger_path))
    return equity_path, ledger_path


def _daily_total(path) -> float:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sum(float(row["pnl_usd"]) for row in rows)


def test_same_exit_order_is_booked_only_once(tmp_path, monkeypatch) -> None:
    equity_path, ledger_path = _configure_paths(tmp_path, monkeypatch)

    assert intraday._record_daily_pnl(2.5, "alpaca_order:exit-123") is True
    assert intraday._record_daily_pnl(2.5, "alpaca_order:exit-123") is False

    assert _daily_total(equity_path) == pytest.approx(2.5)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert list(ledger["events"]) == ["alpaca_order:exit-123"]
    assert not ledger_path.with_suffix(".json.tmp").exists()
    assert not equity_path.with_suffix(".json.tmp").exists()


def test_distinct_exit_orders_with_same_pnl_are_both_booked(tmp_path, monkeypatch) -> None:
    equity_path, _ = _configure_paths(tmp_path, monkeypatch)

    intraday._record_daily_pnl(1.25, "alpaca_order:exit-a")
    intraday._record_daily_pnl(1.25, "alpaca_order:exit-b")

    assert _daily_total(equity_path) == pytest.approx(2.5)


def test_confirmed_fill_date_is_used_instead_of_reconciliation_date(
    tmp_path, monkeypatch
) -> None:
    equity_path, ledger_path = _configure_paths(tmp_path, monkeypatch)

    intraday._record_daily_pnl(
        1.5,
        "alpaca_order:historical-exit",
        {"filled_at": "2026-07-06T15:31:00Z"},
        "2026-07-06",
    )

    rows = json.loads(equity_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert rows == [{"date": "2026-07-06", "pnl_usd": 1.5}]
    assert ledger["events"]["alpaca_order:historical-exit"]["date"] == "2026-07-06"


def test_existing_equity_log_is_preserved_as_ledger_baseline(tmp_path, monkeypatch) -> None:
    equity_path, _ = _configure_paths(tmp_path, monkeypatch)
    equity_path.write_text(
        json.dumps([{"date": "2026-07-09", "pnl_usd": 3.0}]),
        encoding="utf-8",
    )

    intraday._record_daily_pnl(-1.0, "alpaca_order:new-exit")
    intraday._record_daily_pnl(-1.0, "alpaca_order:new-exit")

    assert _daily_total(equity_path) == pytest.approx(2.0)


def test_missing_order_id_uses_deterministic_position_fill_fallback() -> None:
    position = intraday.PositionState(
        symbol="AAPL",
        side="long",
        entry_price=200.0,
        sl_price=198.0,
        tp_price=204.0,
        qty=0.5,
        entry_ts=1_700_000_000,
        alpaca_order_id="entry-42",
    )
    confirmed = {
        "order_id": "",
        "filled_at": "2026-07-10T15:30:00Z",
        "exit_price": 202.0,
        "qty": 0.5,
        "pnl_usd": 1.0,
    }

    first = intraday._exit_pnl_event_id(position, confirmed)
    second = intraday._exit_pnl_event_id(position, dict(confirmed))

    assert first == second
    assert first.startswith("fallback:")


def test_replay_recovers_crash_after_ledger_commit_without_double_booking(
    tmp_path, monkeypatch
) -> None:
    equity_path, ledger_path = _configure_paths(tmp_path, monkeypatch)
    original_save = intraday._save_equity_log
    calls = 0

    def crash_once(log):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated crash before equity projection")
        original_save(log)

    monkeypatch.setattr(intraday, "_save_equity_log", crash_once)
    with pytest.raises(RuntimeError, match="simulated crash"):
        intraday._record_daily_pnl(-0.75, "alpaca_order:exit-crash")

    assert ledger_path.exists()
    assert not equity_path.exists()
    assert intraday._record_daily_pnl(-0.75, "alpaca_order:exit-crash") is False
    assert _daily_total(equity_path) == pytest.approx(-0.75)
