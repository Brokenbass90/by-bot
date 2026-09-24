import json

import pytest

from scripts import equities_alpaca_paper_bridge as bridge


LIVE = "https://api.alpaca.markets"


def _enable_live_binding(tmp_path, monkeypatch):
    path = tmp_path / "binding.json"
    path.write_text(json.dumps({
        "schema_version": 1, "endpoint": LIVE,
        "strategy_id": bridge._INTENDED_PAPER_STRATEGY_ID,
        "account_id": "live-account-1", "enabled": True, "capital_usd": 123.45,
        "max_positions": 4, "gross_exposure": .70, "maximum_weight": .60,
    }))
    for key, value in {
        "ALPACA_INTENDED_LIVE_BINDING_PATH": str(path),
        "ALPACA_INTENDED_LIVE_ACK": "INTENDED_LIVE_CANARY",
        "ALPACA_LIVE_ACCOUNT_ROLE": "monthly_v38",
        "ALPACA_LIVE_CONFIRM": "MONTHLY_V38_LIVE",
        "ALPACA_LIVE_MAX_CAPITAL_USD": "123.45",
        "ALPACA_INTENDED_LIVE_KILL_ACK": "INTENDED_OWNED_EXITS_ONLY",
        "ALPACA_SEND_ORDERS": "1", "ALPACA_ALLOW_NEW_ENTRIES": "0",
    }.items():
        monkeypatch.setenv(key, value)


class Broker:
    def get_account(self): return {"id": "live-account-1"}
    def list_positions(self): return [{"symbol": "SCHW", "qty": "0.4", "avg_entry_price": "101.25"}, {"symbol": "FOREIGN", "qty": "1", "avg_entry_price": "7"}]
    def list_orders(self, **_kwargs): return [{"id": "entry-1", "symbol": "SCHW", "side": "buy", "status": "filled", "filled_qty": "0.4", "filled_avg_price": "101.25"}]


def _proof():
    return {"reason": "unprotected_after_reconcile", "account_id": "live-account-1", "positions": [{"symbol": "SCHW", "entry_order_id": "entry-1", "qty": "0.4", "avg_entry_price": "101.25"}]}


def test_old_paper_kill_rejects_live_endpoint():
    with pytest.raises(bridge.PaperKillValidationError, match="paper"):
        bridge._validated_paper_kill_scope(proof=_proof(), client=Broker(), base_url=LIVE)


def test_explicit_live_kill_requires_bound_account_and_returns_exact_owned_scope(tmp_path, monkeypatch):
    _enable_live_binding(tmp_path, monkeypatch)

    receipt = bridge.run_paper_owned_kill(
        proof=_proof(), client=Broker(), base_url=LIVE, apply=False, state_dir=tmp_path, intended_live=True
    )

    assert receipt["scope_symbols"] == ["SCHW"]
    assert receipt["present_symbols"] == ["SCHW"]


def test_explicit_live_kill_rejects_missing_kill_ack_before_writes(tmp_path, monkeypatch):
    _enable_live_binding(tmp_path, monkeypatch)
    monkeypatch.delenv("ALPACA_INTENDED_LIVE_KILL_ACK")

    with pytest.raises(bridge.PaperKillValidationError, match="kill_ack"):
        bridge.run_paper_owned_kill(
            proof=_proof(), client=Broker(), base_url=LIVE, apply=True, state_dir=tmp_path, intended_live=True
        )
    assert not (tmp_path / ".paper-entry-halt.json").exists()
