import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backtest.alpaca_exact_parity_contract import DailyBar
from scripts import alpaca_adaptive_paper as adaptive_paper


ROWS = [
    {"date": "2026-09-30", "open": "09:30", "close": "16:00"},
    {"date": "2026-10-01", "open": "09:30", "close": "16:00"},
]


class Client:
    def __init__(self, timestamp):
        self.timestamp = timestamp
    def get_clock(self): return {"timestamp": self.timestamp}
    def _request(self, method, path): return ROWS


def history():
    days = [date(2026, 1, 1) + timedelta(days=n) for n in range(274)]
    return {symbol: [DailyBar(day, 100, 102, 99, 101) for day in days]
            for symbol in ("SPY", "AAPL")}


def source_cache(tmp_path):
    cache = tmp_path / "source"
    cache.mkdir()
    timestamp = int(datetime(2026, 9, 30, 20, tzinfo=timezone.utc).timestamp())
    for symbol in ("SPY", "AAPL"):
        (cache / f"{symbol}_M5.csv").write_text(f"ts,o,h,l,c,v\n{timestamp},1,1,1,1,1\n")
    return cache


def test_refresh_does_not_start_before_completed_month_close(tmp_path, monkeypatch):
    child = lambda *args, **kwargs: pytest.fail("refresh must wait for close")
    monkeypatch.setattr(adaptive_paper.subprocess, "run", child)

    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, source_cache(tmp_path), 487.42, Client("2026-09-30T19:59:00Z"), refresh_cache=True
    )

    assert result["status"] == "WAITING_FOR_MONTH_CLOSE"


def test_refresh_uses_public_fetch_argv_and_scrubbed_environment(tmp_path, monkeypatch):
    cache = source_cache(tmp_path)
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "must-not-pass")
    monkeypatch.setenv("TG_TOKEN", "must-not-pass")
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda path: history())

    def run(argv, **kwargs):
        assert argv[1] == str(adaptive_paper.ROOT / "scripts/fetch_equities_yfinance.py")
        assert argv[argv.index("--tickers") + 1] == "AAPL,SPY"
        assert argv[argv.index("--period") + 1] == "730d"
        assert argv[argv.index("--interval") + 1] == "60m"
        destination = Path(argv[argv.index("--out-dir") + 1])
        assert destination.name.startswith(".2026-10-01.partial-")
        assert not any(key.startswith("ALPACA_") or key.startswith("TG_") for key in kwargs["env"])
        (destination / "SPY_M5.csv").write_text((cache / "SPY_M5.csv").read_text())
        (destination / "AAPL_M5.csv").write_text((cache / "AAPL_M5.csv").read_text())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(adaptive_paper.subprocess, "run", run)
    result = adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
    )

    receipt = json.loads((tmp_path / "inputs" / "2026-10-01" / "fetch_receipt.json").read_text())
    assert result["status"] == "PREPARED"
    assert receipt["status"] == "completed"
    assert sorted(receipt["source_file_sha256"]) == ["AAPL_M5.csv", "SPY_M5.csv"]


@pytest.mark.parametrize("missing_spy", [False, True])
def test_failed_or_missing_spy_refresh_preserves_partial_without_cycle(tmp_path, monkeypatch, missing_spy):
    cache = source_cache(tmp_path)
    def run(argv, **kwargs):
        destination = Path(argv[argv.index("--out-dir") + 1])
        (destination / "AAPL_M5.csv").write_text("partial")
        if not missing_spy:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(adaptive_paper.subprocess, "run", run)

    with pytest.raises(ValueError, match="refresh"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
        )
    assert not (tmp_path / "cycles" / "2026-10-01").exists()
    partials = list((tmp_path / "inputs").glob(".2026-10-01.partial-*"))
    assert len(partials) == 1 and (partials[0] / "AAPL_M5.csv").exists()


def test_refresh_rejects_spy_without_completed_signal_bar(tmp_path, monkeypatch):
    cache = source_cache(tmp_path)
    def run(argv, **kwargs):
        destination = Path(argv[argv.index("--out-dir") + 1])
        (destination / "AAPL_M5.csv").write_text((cache / "AAPL_M5.csv").read_text())
        (destination / "SPY_M5.csv").write_text("ts,o,h,l,c,v\n1,1,1,1,1,1\n")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(adaptive_paper.subprocess, "run", run)

    with pytest.raises(ValueError, match="signal_spy_missing"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
        )
    assert not (tmp_path / "cycles" / "2026-10-01").exists()


def test_existing_frozen_cycle_never_refetches(tmp_path, monkeypatch):
    cache = source_cache(tmp_path)
    monkeypatch.setattr(adaptive_paper, "_load_intended_hourly_history", lambda path: history())
    def first_run(argv, **kwargs):
        destination = Path(argv[argv.index("--out-dir") + 1])
        for symbol in ("SPY", "AAPL"):
            (destination / f"{symbol}_M5.csv").write_text((cache / f"{symbol}_M5.csv").read_text())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(adaptive_paper.subprocess, "run", first_run)
    assert adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
    )["status"] == "PREPARED"
    monkeypatch.setattr(adaptive_paper.subprocess, "run", lambda *args, **kwargs: pytest.fail("must not refetch"))

    assert adaptive_paper.prepare_intended_monthly_cycle(
        tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
    )["status"] == "ALREADY_PREPARED"


def test_refresh_rejects_incomplete_requested_symbol_set(tmp_path, monkeypatch):
    cache = source_cache(tmp_path)
    def run(argv, **kwargs):
        destination = Path(argv[argv.index("--out-dir") + 1])
        (destination / "SPY_M5.csv").write_text((cache / "SPY_M5.csv").read_text())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(adaptive_paper.subprocess, "run", run)

    with pytest.raises(ValueError, match="incomplete"):
        adaptive_paper.prepare_intended_monthly_cycle(
            tmp_path, cache, 487.42, Client("2026-09-30T20:00:00Z"), refresh_cache=True
        )


@pytest.mark.parametrize("live", [False, True])
def test_failed_monthly_preparation_runs_existing_active_cycle_maintenance_only(tmp_path, monkeypatch, live):
    from scripts import equities_alpaca_paper_bridge as bridge
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    report = {
        "entry_session": "2026-10-01", "signal_session": "2026-09-30", "capital_usd": 487.42,
        "mode": "intended_prepare_only", "target_gross_exposure": .7, "maximum_weight": .6,
        "max_positions": 4, "picks": [], "selector_source_hashes": adaptive_paper._frozen_source_hashes(),
    }
    (runtime / "latest_selection.json").write_text(json.dumps(report))
    adaptive_paper.write_intended_bridge_picks_csv(report, runtime / "current_cycle_picks.csv")
    (runtime / "foreign_owners.json").write_text(json.dumps({"account_id": "paper-1", "owners": {}}))
    for key, value in {"ALPACA_BASE_URL": "https://paper-api.alpaca.markets", "ALPACA_API_KEY_ID": "fixture",
                       "ALPACA_API_SECRET_KEY": "fixture", "ALPACA_BRIDGE_LOCK_PATH": str(runtime / "account.lock")}.items():
        monkeypatch.setenv(key, value)
    if live:
        binding = {"selector_source_hashes": adaptive_paper._frozen_source_hashes(),
                   "runtime_dir": str(runtime.resolve()), "account_lock_path": str(runtime / "account.lock")}
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        monkeypatch.setattr(bridge, "_load_intended_live_binding", lambda **kw: binding)
    monkeypatch.setattr(adaptive_paper, "validate_intended_live_schedule", lambda *a: (_ for _ in ()).throw(OSError("calendar offline")))
    monkeypatch.setattr(adaptive_paper, "prepare_intended_monthly_cycle", lambda *a, **k: (_ for _ in ()).throw(ValueError("refresh unavailable")))
    calls = []
    def run(command, **kwargs):
        calls.append(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(adaptive_paper.subprocess, "run", run)
    class OpenBroker:
        def get_account(self): return {"id": "paper-1", "status": "ACTIVE", "trading_blocked": False}
        def get_clock(self): return {"is_open": True, "timestamp": "2026-10-02T14:00:00Z"}
        def list_positions(self): return []
        def list_orders(self, **kwargs): return []

    assert adaptive_paper.run_intended_cycle(runtime, capital=487.42, send_orders=True,
        client=OpenBroker(), monthly=True, live=live, cache_dir=tmp_path / "source") == 0
    assert len(calls) == 2
    assert all(env["ALPACA_ALLOW_NEW_ENTRIES"] == "0" and env["ALPACA_INTENDED_MONTHLY"] == "0" for env in calls)
    receipt = json.loads((runtime / "latest_intended_run.json").read_text())
    assert receipt["data_blocked"]["maintenance_only"] is True


def test_reserved_entry_intent_requires_exact_filled_broker_match(tmp_path):
    journal = tmp_path / "monthly_reentry_block.json"
    intent = {"account_id": "paper-1", "strategy_id": "strategy", "symbol": "CRM",
              "entry_session": "2026-10-01", "notional": 100, "status": "reserved"}
    journal.write_text(json.dumps({"symbols": {}, "entry_intents": {"intent-1": intent}}))
    class Orders:
        def get_order_by_client_id(self, client_id):
            return {"client_order_id": client_id, "symbol": "CRM", "side": "buy", "status": "filled",
                    "filled_qty": "1", "filled_avg_price": "100"}
    positions = [{"symbol": "CRM", "qty": "1", "avg_entry_price": "100"}]
    assert adaptive_paper._reserved_monthly_entry_positions(journal_path=journal, client=Orders(),
        account_id="paper-1", positions=positions, strategy_id="strategy") == {"CRM"}
    intent["status"] = "complete"
    journal.write_text(json.dumps({"symbols": {}, "entry_intents": {"intent-1": intent}}))
    assert adaptive_paper._reserved_monthly_entry_positions(journal_path=journal, client=Orders(),
        account_id="paper-1", positions=positions, strategy_id="strategy") == set()


def test_consumed_not_submitted_intent_does_not_grant_ownership_or_corrupt_journal(tmp_path):
    journal = tmp_path / "blocks.json"
    journal.write_text(json.dumps({"entry_intents": {"id": {"account_id":"a", "strategy_id":"s",
        "symbol":"X", "entry_session":"2026-10-01", "notional":40, "status":"not_submitted"}}}))
    assert adaptive_paper._reserved_monthly_entry_positions(journal_path=journal, client=None,
        account_id="a", positions=[{"symbol":"X"}], strategy_id="s") == set()
