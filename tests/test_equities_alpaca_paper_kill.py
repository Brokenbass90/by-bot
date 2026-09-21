import json

import pytest

from scripts import equities_alpaca_paper_bridge as bridge


PAPER = "https://paper-api.alpaca.markets"


class FakeClient:
    def __init__(self, *, account_id="acct-1", positions=None, orders=None, is_open=True):
        self.account_id = account_id
        self.positions = positions or []
        self.orders = orders or []
        self.is_open = is_open
        self.cancelled = []
        self.closed = []
        self.requested_symbols = None

    def get_account(self):
        return {"id": self.account_id}

    def list_positions(self):
        return self.positions

    def list_orders(self, *, status="open", limit=100, symbols=None):
        assert status == "all" and limit == 500
        self.requested_symbols = symbols
        return self.orders

    def get_clock(self):
        return {"is_open": self.is_open}

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        for order in self.orders:
            if order.get("id") == order_id:
                order["status"] = "canceled"
        return {"id": order_id, "status": "canceled"}

    def get_order(self, order_id):
        return {"id": order_id, "status": "canceled"}

    def close_position(self, symbol):
        self.closed.append(symbol)
        return {"id": "close-" + symbol, "status": "accepted"}


def _proof():
    return {
        "account_id": "acct-1",
        "reason": "owner_kill",
        "positions": [{"symbol": "AAPL", "entry_order_id": "entry-aapl", "qty": "2", "avg_entry_price": "100"}],
    }


def _orders(*, entry_id="entry-aapl", entry_qty="2", entry_price="100", extra_buy=False):
    rows = [{"id": entry_id, "symbol": "AAPL", "side": "buy", "status": "filled", "filled_qty": entry_qty, "filled_avg_price": entry_price}]
    if extra_buy:
        rows.insert(0, {"id": "later-buy", "symbol": "AAPL", "side": "buy", "status": "filled", "filled_qty": "1", "filled_avg_price": "110"})
    return rows


def _position(qty="2", avg="100"):
    return {"symbol": "AAPL", "qty": qty, "avg_entry_price": avg, "side": "long"}


def test_paper_kill_dry_run_plans_only_owned_position_and_leaves_foreign_untouched(tmp_path):
    client = FakeClient(positions=[_position(), {"symbol": "AMZN", "qty": "1", "avg_entry_price": "200", "side": "long"}], orders=_orders())
    receipt = bridge.run_paper_owned_kill(
        proof=_proof(), client=client, base_url=PAPER, apply=False, state_dir=tmp_path
    )
    assert receipt["status"] == "dry_run_not_confirmed"
    assert client.requested_symbols == ["AAPL"]
    assert receipt["plan"] == [{"symbol": "AAPL", "action": "close_owned_position"}]
    assert client.cancelled == [] and client.closed == []


@pytest.mark.parametrize("proof_change", [{"account_id": "other"}, {"positions": [{"symbol": "AAPL", "entry_order_id": "wrong", "qty": "2", "avg_entry_price": "100"}]}])
def test_paper_kill_rejects_wrong_account_or_entry(proof_change, tmp_path):
    proof = _proof()
    proof.update(proof_change)
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=proof, client=FakeClient(positions=[_position()], orders=_orders()), base_url=PAPER, apply=False, state_dir=tmp_path)


@pytest.mark.parametrize("position", [_position(qty="3"), _position(avg="101")])
def test_paper_kill_rejects_qty_or_average_mismatch(position, tmp_path):
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=_proof(), client=FakeClient(positions=[position], orders=_orders()), base_url=PAPER, apply=False, state_dir=tmp_path)


def test_paper_kill_rejects_live_endpoint_and_later_buy(tmp_path):
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=_proof(), client=FakeClient(positions=[_position()], orders=_orders()), base_url="https://api.alpaca.markets", apply=False, state_dir=tmp_path)
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=_proof(), client=FakeClient(positions=[_position()], orders=_orders(extra_buy=True)), base_url=PAPER, apply=False, state_dir=tmp_path)


def test_paper_kill_rejects_invalid_number_and_unproven_same_symbol_buy(tmp_path, monkeypatch):
    bad = _proof()
    bad["positions"][0]["qty"] = "NaN"
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=bad, client=FakeClient(positions=[_position()], orders=_orders()), base_url=PAPER, apply=False, state_dir=tmp_path)
    monkeypatch.setenv("ALPACA_SEND_ORDERS", "1")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setenv("ALPACA_PAPER_KILL_ACK", "PAPER_OWNED_EXITS_ONLY")
    pending_buy = {"id": "foreign-buy", "symbol": "AAPL", "side": "buy", "status": "new"}
    with pytest.raises(bridge.PaperKillValidationError):
        bridge.run_paper_owned_kill(proof=_proof(), client=FakeClient(positions=[_position()], orders=_orders() + [pending_buy]), base_url=PAPER, apply=True, state_dir=tmp_path)


def test_paper_kill_closed_market_queues_receipt_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_SEND_ORDERS", "1")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setenv("ALPACA_PAPER_KILL_ACK", "PAPER_OWNED_EXITS_ONLY")
    client = FakeClient(positions=[_position()], orders=_orders(), is_open=False)
    receipt = bridge.run_paper_owned_kill(proof=_proof(), client=client, base_url=PAPER, apply=True, state_dir=tmp_path)
    assert receipt["status"] == "awaiting_regular_session"
    assert client.cancelled == [] and client.closed == []
    assert (tmp_path / ".paper-entry-halt.json").exists()


def test_paper_kill_apply_guards_cancel_and_pending_close_and_needs_fresh_flat(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_SEND_ORDERS", "1")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setenv("ALPACA_PAPER_KILL_ACK", "PAPER_OWNED_EXITS_ONLY")
    open_sell = {"id": "sell-1", "symbol": "AAPL", "side": "sell", "status": "new"}
    client = FakeClient(positions=[_position()], orders=_orders() + [open_sell])
    receipt = bridge.run_paper_owned_kill(proof=_proof(), client=client, base_url=PAPER, apply=True, state_dir=tmp_path)
    assert receipt["status"] == "not_confirmed"
    assert client.cancelled == ["sell-1"] and client.closed == ["AAPL"]
    # A later execution sees the pending close and does not submit another close.
    client.orders = _orders() + [{"id": "close-aapl", "symbol": "AAPL", "side": "sell", "type": "market", "status": "accepted"}]
    again = bridge.run_paper_owned_kill(proof=_proof(), client=client, base_url=PAPER, apply=True, state_dir=tmp_path)
    assert "pending_close" in again["status"] and client.closed == ["AAPL"]


def test_paper_kill_cancel_rejection_never_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_SEND_ORDERS", "1")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setenv("ALPACA_PAPER_KILL_ACK", "PAPER_OWNED_EXITS_ONLY")
    class RejectingClient(FakeClient):
        def cancel_order(self, order_id):
            raise RuntimeError("cancel rejected")
    client = RejectingClient(positions=[_position()], orders=_orders() + [{"id": "sell-1", "symbol": "AAPL", "side": "sell", "status": "new"}])
    with pytest.raises(RuntimeError, match="cancel rejected"):
        bridge.run_paper_owned_kill(proof=_proof(), client=client, base_url=PAPER, apply=True, state_dir=tmp_path)
    assert client.closed == []


def test_paper_halt_suppresses_bridge_entries_after_restart(tmp_path):
    (tmp_path / ".paper-entry-halt.json").write_text(json.dumps({"halted": True}), encoding="utf-8")
    assert bridge.paper_entry_halted(base_url=PAPER, state_dir=tmp_path)
    assert not bridge.paper_entry_halted(base_url="https://api.alpaca.markets", state_dir=tmp_path)
    (tmp_path / ".paper-entry-halt.json").write_text(json.dumps({"halted": "yes"}), encoding="utf-8")
    assert bridge.paper_entry_halted(base_url=PAPER, state_dir=tmp_path)


def test_list_orders_encodes_scoped_symbols_safely(monkeypatch):
    seen = {}
    class Response:
        def read(self):
            return b"[]"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
    def open_url(req, **_):
        seen["url"] = req.full_url
        return Response()
    monkeypatch.setattr(bridge.request, "urlopen", open_url)
    bridge.AlpacaClient(PAPER, "key", "secret").list_orders(status="all", limit=500, symbols=["BRK/B", "A B"])
    assert "symbols=BRK%2FB%2CA+B" in seen["url"]


def test_paper_kill_accepts_proven_terminal_partial_entry(tmp_path):
    rows=_orders()
    rows[0]['status']='canceled'
    receipt=bridge.run_paper_owned_kill(proof=_proof(),client=FakeClient(positions=[_position()],orders=rows),
        base_url=PAPER,apply=False,state_dir=tmp_path)
    assert receipt['status']=='dry_run_not_confirmed'
