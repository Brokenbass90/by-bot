"""Offline integration evidence only; never a substitute for PAPER receipts."""
import json
import sys

from scripts import alpaca_protective_exit_manager as manager
from scripts import equities_alpaca_paper_bridge as bridge


def test_confirmed_fill_ratchet_restart_and_day_rearm_share_durable_floor(tmp_path, monkeypatch):
    class Broker:
        price = 110.0
        replacements = 0
        entry = {
            "id": "entry-1", "symbol": "SCHW", "side": "buy", "status": "filled",
            "filled_qty": "0.4", "filled_avg_price": "101.25",
            "filled_at": "2026-09-18T13:31:02Z",
        }
        stop = {
            "id": "stop-1", "symbol": "SCHW", "side": "sell", "type": "stop",
            "status": "new", "qty": "0.4", "filled_qty": "0",
            "stop_price": "95.25", "time_in_force": "day",
        }

        def get_account(self):
            return {"id": "paper-account", "trading_blocked": False}

        def get_clock(self):
            return {"is_open": True}

        def list_positions(self):
            return [{"symbol": "SCHW", "qty": "0.4", "avg_entry_price": "101.25",
                     "current_price": str(self.price), "side": "long"}]

        def list_orders(self, **kwargs):
            return [dict(self.stop)]

        def get_order(self, order_id):
            if order_id == "entry-1":
                return dict(self.entry)
            assert order_id == self.stop["id"]
            return dict(self.stop)

        def replace_order(self, order_id, payload):
            assert order_id == self.stop["id"]
            assert set(payload) == {"stop_price"}
            self.replacements += 1
            self.stop = {**self.stop, "id": "stop-2", **payload}
            return dict(self.stop)

    broker = Broker()
    state_path = tmp_path / "protective_exit_hwm.json"
    first = bridge._complete_intended_paper_simple_stop(
        client=broker, base_url=manager.PAPER_ALPACA_URL, state_dir=tmp_path,
        ledger_path=state_path, account_id="paper-account", entry_order=broker.entry,
        stop_order=broker.stop, symbol="SCHW", requested_stop=95.25,
    )
    assert first["hwm"] == 101.25
    for key, value in {
        "ALPACA_BASE_URL": manager.PAPER_ALPACA_URL,
        "ALPACA_API_KEY_ID": "fixture", "ALPACA_API_SECRET_KEY": "fixture",
        "ALPACA_INTENDED_PAPER": "1", "ALPACA_ALLOW_NEW_ENTRIES": "0",
        "ALPACA_PROTECTIVE_EXIT_ACK": "PROTECTIVE_EXITS_ONLY",
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH": str(state_path),
        "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR": str(tmp_path),
        "ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH": str(tmp_path / "receipt.json"),
        "ALPACA_PROTECTIVE_EXIT_EXCLUDED_SYMBOLS": "",
        "ALPACA_PROTECTIVE_TRAIL_ACTIVATE_GAIN_PCT": "3.5",
        "ALPACA_PROTECTIVE_TRAIL_PCT": "3.5",
        "ALPACA_PROTECTIVE_MIN_LOCK_GAIN_PCT": "0.5",
        "ALPACA_PROTECTIVE_MIN_RAISE_BPS": "10",
        "ALPACA_PROTECTIVE_MARKET_GAP_BPS": "10",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(manager, "AlpacaClient", lambda *args: broker)
    monkeypatch.setattr(sys, "argv", ["manager", "--apply"])
    assert manager._main_unlocked() == 0
    before = json.loads(state_path.read_text())["SCHW"]
    assert before["hwm"] == 110.0
    # Preserve the existing downward tick quantization (including float input).
    assert before["accepted_stop_floor"] == 106.14
    assert before["accepted_order_id"] == "stop-2"

    # A new invocation loads the file, not the prior in-memory bridge record.
    broker.price = 107.0
    assert manager._main_unlocked() == 0
    after = json.loads(state_path.read_text())["SCHW"]
    for key in ("entry_order_id", "account_id", "strategy_id", "entry_price", "qty",
                "hwm", "accepted_stop_floor", "accepted_order_id", "lifecycle_first_seen_at_utc"):
        assert after[key] == before[key]
    assert broker.replacements == 1

    # DAY expiry leaves no working stop: the bridge must reuse the raised floor.
    required = bridge._protected_rearm_stop_price(
        "SCHW", 95.25, broker.list_positions()[0], [], json.loads(state_path.read_text()),
    )
    assert required == 106.14
    assert bridge._persistent_exit_tif_for_qty("", 0.4) == "day"

    # A malformed current quote must not corrupt the proven durable lifecycle.
    saved = state_path.read_bytes()
    broker.price = float("nan")
    assert manager._main_unlocked() == 7
    assert state_path.read_bytes() == saved
    assert broker.replacements == 1
