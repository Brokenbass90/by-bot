import json
import sys

import pytest

from scripts import equities_alpaca_paper_bridge as bridge


PAPER = "https://paper-api.alpaca.markets"


class FakeBroker:
    def __init__(self, *, entry_reads, stop):
        self.entry_reads = list(entry_reads)
        self.stop = dict(stop)
        self.cancelled = []

    def get_order(self, order_id):
        assert order_id in {"entry-1", "stop-1"}
        if order_id == "stop-1":
            return dict(self.stop)
        if not self.entry_reads:
            raise RuntimeError("entry_readback_exhausted")
        return dict(self.entry_reads.pop(0))

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"id": order_id, "status": "canceled"}


def _entry(status="filled", qty="0.4", avg="101.25", **extra):
    return {
        "id": "entry-1", "symbol": "SCHW", "side": "buy", "type": "market",
        "status": status, "filled_qty": qty, "filled_avg_price": avg,
        "filled_at": "2026-09-20T10:01:02Z", **extra,
    }


def _stop(status="new", qty="0.4", stop="95.25", tif="day", **extra):
    return {
        "id": "stop-1", "symbol": "SCHW", "side": "sell", "type": "stop",
        "status": status, "qty": qty, "filled_qty": "0", "stop_price": stop,
        "time_in_force": tif, **extra,
    }


def test_terminal_partial_fill_is_canceled_and_persisted_with_confirmed_floor(tmp_path):
    # Removing terminal readback or the broker-confirmed stop gate must fail this.
    broker = FakeBroker(
        entry_reads=[_entry("partially_filled", "0.2"), _entry("canceled", "0.4")],
        stop=_stop(),
    )
    ledger = tmp_path / "protective_exit_hwm.json"
    ledger.write_text(json.dumps({"FOREIGN": {"opaque": "preserve-me"}}))

    persisted = bridge._complete_intended_paper_simple_stop(
        client=broker, base_url=PAPER, state_dir=tmp_path, ledger_path=ledger,
        account_id="acct-1", entry_order=_entry("new", "0", ""),
        stop_order=_stop(), symbol="SCHW", requested_stop=95.25,
    )

    assert broker.cancelled == ["entry-1"]
    assert persisted["qty"] == 0.4
    assert persisted["entry_price"] == 101.25
    assert persisted["hwm"] == 101.25
    assert persisted["accepted_stop_floor"] == 95.25
    assert persisted["accepted_order_id"] == "stop-1"
    assert persisted["accepted_order_tif"] == "day"
    assert persisted["entry_order_id"] == "entry-1"
    assert persisted["lifecycle_first_seen_at_utc"] == "2026-09-20T10:01:02Z"
    assert persisted["account_id"] == "acct-1"
    assert persisted["strategy_id"] == "ALPACA-BASELINE-26f7ff663dc98e87"
    assert json.loads(ledger.read_text())["SCHW"] == persisted
    assert json.loads(ledger.read_text())["FOREIGN"] == {"opaque": "preserve-me"}


def test_ambiguous_entry_cancel_halts_durably_and_does_not_write_floor(tmp_path):
    # Treating a still-active entry as terminal would leave a growing fill unprotected.
    broker = FakeBroker(
        entry_reads=[_entry("partially_filled", "0.2"), _entry("partially_filled", "0.2")],
        stop=_stop(),
    )
    ledger = tmp_path / "protective_exit_hwm.json"

    with pytest.raises(bridge.IntendedPaperProtectionError, match="entry_not_terminal"):
        bridge._complete_intended_paper_simple_stop(
            client=broker, base_url=PAPER, state_dir=tmp_path, ledger_path=ledger,
            account_id="acct-1", entry_order=_entry("new", "0", ""),
            stop_order=_stop(), symbol="SCHW", requested_stop=95.25,
        )

    assert broker.cancelled == ["entry-1"]
    assert json.loads((tmp_path / ".paper-entry-halt.json").read_text())["halted"] is True
    assert not ledger.exists()


def test_rejected_stop_halts_and_identical_retry_preserves_higher_hwm_and_floor(tmp_path):
    # Resetting an identical lifecycle would lower the previously observed HWM/floor.
    ledger = tmp_path / "protective_exit_hwm.json"
    ledger.write_text(json.dumps({"SCHW": {
        "entry_order_id": "entry-1", "entry_price": 101.25, "qty": 0.4,
        "hwm": 110.0, "accepted_stop_floor": 99.0,
        "lifecycle_first_seen_at_utc": "2026-09-20T10:01:02Z",
        "account_id": "acct-1", "strategy_id": "ALPACA-BASELINE-26f7ff663dc98e87",
    }}))
    rejected = FakeBroker(entry_reads=[_entry()], stop=_stop("rejected"))
    with pytest.raises(bridge.IntendedPaperProtectionError, match="stop_not_accepted"):
        bridge._complete_intended_paper_simple_stop(
            client=rejected, base_url=PAPER, state_dir=tmp_path, ledger_path=ledger,
            account_id="acct-1", entry_order=_entry(), stop_order=_stop("rejected"),
            symbol="SCHW", requested_stop=95.25,
        )
    assert json.loads((tmp_path / ".paper-entry-halt.json").read_text())["halted"] is True

    accepted = FakeBroker(entry_reads=[_entry()], stop=_stop(stop="99.00"))
    persisted = bridge._complete_intended_paper_simple_stop(
        client=accepted, base_url=PAPER, state_dir=tmp_path, ledger_path=ledger,
        account_id="acct-1", entry_order=_entry(), stop_order=_stop(stop="99.00"), symbol="SCHW",
        requested_stop=95.25,
    )
    assert persisted["hwm"] == 110.0
    assert persisted["accepted_stop_floor"] == 99.0
    assert bridge._matching_protective_floor_record(
        "SCHW", {"avg_entry_price": "101.25"}, {"SCHW": persisted}
    )["accepted_stop_floor"] == 99.0


def test_intended_flag_rejects_live_endpoint_before_client_construction(tmp_path, monkeypatch, capsys):
    # Moving endpoint validation after client construction would make this network guard fail.
    picks = tmp_path / "picks.csv"
    picks.write_text(
        "month,ticker,entry_day,score,atr20_pct,momentum20_pct,momentum60_pct,pullback60_pct\n"
        "2026-09,SCHW,2026-09-20,1,2,3,4,-1\n"
    )
    monkeypatch.setenv("ALPACA_INTENDED_PAPER", "1")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setattr(sys, "argv", ["bridge", "--picks-csv", str(picks)])
    monkeypatch.setattr(
        bridge, "AlpacaClient", lambda *_args: (_ for _ in ()).throw(AssertionError("network"))
    )

    assert bridge._main_unlocked() == 8
    assert "intended_paper_requires_exact_paper_endpoint" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("entry", "stop", "error"),
    [
        (_entry(qty="NaN"), _stop(), "entry_terminal_without_positive_fill"),
        (_entry(id="other-entry"), _stop(), "entry_id_mismatch"),
        (_entry(side="sell"), _stop(), "entry_side_mismatch"),
        (_entry(symbol="OTHER"), _stop(), "entry_symbol_mismatch"),
        (_entry(), _stop(id="other-stop"), "stop_id_mismatch"),
        (_entry(), _stop(qty="NaN"), "stop_invalid_qty"),
        (_entry(), _stop(stop="Infinity"), "stop_invalid_price"),
        (_entry(filled_at="not-a-timestamp"), _stop(), "entry_invalid_broker_lifecycle_timestamp"),
    ],
)
def test_broker_readback_identity_finite_values_and_timestamp_are_required(tmp_path, entry, stop, error):
    # Removing any broker identity/finite/timestamp check must accept unsafe state here.
    broker = FakeBroker(entry_reads=[entry], stop=stop)
    with pytest.raises(bridge.IntendedPaperProtectionError, match=error):
        bridge._complete_intended_paper_simple_stop(
            client=broker, base_url=PAPER, state_dir=tmp_path,
            ledger_path=tmp_path / "floor.json", account_id="acct-1",
            entry_order=_entry(), stop_order=_stop(), symbol="SCHW", requested_stop=95.25,
        )
    assert bridge.paper_entry_halted(base_url=PAPER, state_dir=tmp_path)


def test_retry_with_stop_below_durable_floor_halts_instead_of_reporting_protected(tmp_path):
    # Dropping this comparison would label a lower broker stop as protected.
    ledger = tmp_path / "floor.json"
    ledger.write_text(json.dumps({"SCHW": {
        "entry_order_id": "entry-1", "entry_price": 101.25, "qty": 0.4,
        "hwm": 110.0, "accepted_stop_floor": 99.0,
        "lifecycle_first_seen_at_utc": "2026-09-20T10:01:02Z",
        "account_id": "acct-1", "strategy_id": "ALPACA-BASELINE-26f7ff663dc98e87",
    }}))
    with pytest.raises(bridge.IntendedPaperProtectionError, match="stop_below_durable_floor"):
        bridge._complete_intended_paper_simple_stop(
            client=FakeBroker(entry_reads=[_entry()], stop=_stop(stop="95.25")),
            base_url=PAPER, state_dir=tmp_path, ledger_path=ledger, account_id="acct-1",
            entry_order=_entry(), stop_order=_stop(stop="95.25"), symbol="SCHW", requested_stop=95.25,
        )


@pytest.mark.parametrize("complete_record", [False, True])
def test_unreconciled_existing_lifecycle_blocks_buy_before_submission(tmp_path, monkeypatch, capsys, complete_record):
    # Moving lifecycle validation below submit_market_buy_qty would fail this safety boundary.
    picks = tmp_path / "picks.csv"
    picks.write_text(
        "month,ticker,entry_day,score,atr20_pct,momentum20_pct,momentum60_pct,pullback60_pct,entry_price,stop_price,weight\n"
        "2026-09,SCHW,2026-09-20,1,2,3,4,-1,100,95,0.25\n"
    )
    ledger = tmp_path / "floor.json"
    ledger.write_text(json.dumps({"SCHW": {"entry_order_id": "missing-required-fields"}}))
    if complete_record:
        ledger.write_text(json.dumps({"SCHW": {
            "entry_order_id": "previous-entry", "entry_price": 100, "qty": 0.4,
            "hwm": 105, "accepted_stop_floor": 99,
            "lifecycle_first_seen_at_utc": "2026-09-18T13:31:02Z",
            "account_id": "acct-1", "strategy_id": bridge._INTENDED_PAPER_STRATEGY_ID,
        }}))

    class Client:
        buy_calls = 0
        def __init__(self, *_args): pass
        def get_account(self): return {"id": "acct-1", "buying_power": "1000", "cash": "1000"}
        def list_positions(self): return []
        def list_orders(self, **_kwargs): return []
        def get_clock(self): return {"is_open": True}
        def submit_market_buy_qty(self, *_args):
            type(self).buy_calls += 1
            raise AssertionError("buy must be blocked before submission")

    for key, value in {
        "ALPACA_INTENDED_PAPER": "1", "ALPACA_BASE_URL": PAPER,
        "ALPACA_API_KEY_ID": "key", "ALPACA_API_SECRET_KEY": "secret",
        "ALPACA_SEND_ORDERS": "1", "ALPACA_ALLOW_NEW_ENTRIES": "1",
        "ALPACA_BROKER_PROTECTION_ENABLE": "1", "ALPACA_BROKER_PROTECTION_REQUIRED": "1",
        "ALPACA_BROKER_PROTECTION_ORDER_CLASS": "simple_stop",
        "ALPACA_BROKER_PROTECTION_SIZE_MODE": "qty", "ALPACA_EARNINGS_FILTER": "0",
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH": str(ledger),
        "ALPACA_BRIDGE_LOCK_PATH": str(tmp_path / "lock"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["bridge", "--picks-csv", str(picks)])
    monkeypatch.setattr(bridge, "AlpacaClient", Client)

    assert bridge._main_unlocked() == 0
    assert Client.buy_calls == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    result = next(row for row in report["results"] if row["ticker"] == "SCHW")
    assert result["status"] == "not_confirmed_halted"
    assert result["error"] == ("existing_lifecycle_unreconciled" if complete_record else "existing_lifecycle_corrupt")
    assert bridge.paper_entry_halted(
        base_url=PAPER, state_dir=bridge._paper_kill_state_dir(PAPER, "key")
    )
