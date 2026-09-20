import json
import sys
from pathlib import Path

import pytest

from scripts import alpaca_protective_exit_manager as manager
from scripts.alpaca_protective_exit_manager import (
    _confirmed_fixed_stop,
    build_ratchet_plan,
    build_stop_replace_payload,
)


PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"


class _FakeBroker:
    instances = []
    current_price = 105.0
    existing_stop = 95.0

    def __init__(self, base_url, key, secret):
        self.base_url = base_url
        self.key = key
        self.secret = secret
        self.replace_payloads = []
        self.replaced_stop = None
        type(self).instances.append(self)

    def get_account(self):
        return {"trading_blocked": False}

    def get_clock(self):
        return {"is_open": True}

    def list_positions(self):
        return [_position(price=type(self).current_price)]

    def list_orders(self, *, status, limit):
        return [{
            **_stop(price=self.replaced_stop or type(self).existing_stop),
            "time_in_force": "day",
        }]

    def replace_order(self, order_id, payload):
        self.replace_payloads.append(payload)
        self.replaced_stop = float(payload["stop_price"])
        return {"id": "stop-2"}

    def get_order(self, order_id):
        return {**_stop(price=self.replaced_stop), "id": order_id, "time_in_force": "day"}


def _run_manager(monkeypatch, tmp_path: Path, *, base_url=PAPER_URL, apply=False, extra_env=None, seed_state=True):
    monkeypatch.setattr(manager, "ROOT", tmp_path)
    monkeypatch.setattr(manager, "AlpacaClient", _FakeBroker)
    _FakeBroker.instances = []
    _FakeBroker.current_price = 105.0
    _FakeBroker.existing_stop = 95.0
    for name in (
        "ALPACA_BASE_URL",
        "ALPACA_INTENDED_PAPER",
        "ALPACA_PROTECTIVE_EXIT_APPLY",
        "ALPACA_PROTECTIVE_EXIT_ACK",
        "ALPACA_ALLOW_NEW_ENTRIES",
        "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR",
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH",
        "ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH",
        "ALPACA_PROTECTIVE_EXIT_EXCLUDED_SYMBOLS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALPACA_BASE_URL", base_url)
    if apply:
        monkeypatch.setenv("ALPACA_PROTECTIVE_EXIT_ACK", "PROTECTIVE_EXITS_ONLY")
        monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    for name, value in (extra_env or {}).items():
        monkeypatch.setenv(name, str(value))
    if seed_state:
        runtime = Path((extra_env or {}).get(
            "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR",
            tmp_path / "runtime" / (
                "alpaca_paper_protective_exit" if base_url == PAPER_URL else "alpaca_live_v38"
            ),
        ))
        state_path = Path((extra_env or {}).get(
            "ALPACA_PROTECTIVE_EXIT_HWM_PATH",
            runtime / "protective_exit_hwm.json",
        ))
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{}")
    monkeypatch.setattr(sys, "argv", ["alpaca_protective_exit_manager.py"] + (["--apply"] if apply else []))
    return manager._main_unlocked()


def _position(price=105.0, entry=100.0, qty=0.5):
    return {"symbol": "SCHW", "current_price": str(price), "avg_entry_price": str(entry), "qty": str(qty)}


def _stop(price=95.0, qty=0.5):
    return {
        "id": "stop-1", "symbol": "SCHW", "side": "sell", "type": "stop",
        "status": "new", "stop_price": str(price), "qty": str(qty), "filled_qty": "0",
        "time_in_force": "gtc",
    }


def test_arms_and_only_raises_existing_broker_stop():
    plan, state = build_ratchet_plan(
        [_position()], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    row = plan[0]
    assert row["action"] == "replace_stop"
    assert row["target_stop"] == 101.32
    assert state["SCHW"]["hwm"] == 105.0


def test_high_water_mark_ratchets_but_never_lowers_stop():
    plan, _ = build_ratchet_plan(
        [_position(price=106.0)],
        [_stop(price=102.0)],
        {"SCHW": {"entry_price": 100.0, "hwm": 110.0}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["action"] == "replace_stop"
    assert plan[0]["target_stop"] == 105.89


def test_unarmed_position_and_missing_coverage_fail_closed():
    plan, _ = build_ratchet_plan(
        [_position(price=102.0)], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["reason"] == "trail_not_armed"

    plan, _ = build_ratchet_plan(
        [_position()], [], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["action"] == "blocked"
    assert plan[0]["reason"] == "expected_one_stop_found_0"


def test_excluded_symbols_are_not_managed():
    plan, state = build_ratchet_plan(
        [_position()], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
        excluded_symbols={"SCHW"},
    )
    assert plan == []
    assert state == {}


def test_fractional_stop_replace_preserves_existing_qty():
    payload = build_stop_replace_payload(105.0306)
    assert payload == {"stop_price": "105.03"}
    assert "qty" not in payload
    assert "time_in_force" not in payload


def test_stop_price_uses_four_decimals_below_one_dollar():
    assert build_stop_replace_payload(0.456789) == {"stop_price": "0.4567"}


def test_state_advances_accepted_floor_only_from_broker_observed_stop():
    plan, state = build_ratchet_plan(
        [_position(price=110.0)],
        [_stop(price=102.0)],
        {"SCHW": {"entry_price": 100.0, "hwm": 109.0, "accepted_stop_floor": 101.0,
                  "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["target_stop"] > 102.0
    assert state["SCHW"]["accepted_stop_floor"] == 102.0


def test_hwm_only_or_rejected_theoretical_raise_does_not_advance_accepted_floor():
    _, state = build_ratchet_plan(
        [_position(price=110.0)],
        [],
        {"SCHW": {"entry_price": 100.0, "hwm": 120.0, "accepted_stop_floor": 103.0,
                  "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert state["SCHW"]["hwm"] == 120.0
    assert state["SCHW"]["accepted_stop_floor"] == 103.0


def test_market_below_accepted_floor_escalates_instead_of_lowering_stop():
    plan, state = build_ratchet_plan(
        [_position(price=105.0)],
        [_stop(price=96.0)],
        {
            "SCHW": {
                "entry_price": 100.0,
                "hwm": 112.0,
                "accepted_stop_floor": 108.0,
                "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
            }
        },
        activate_gain_pct=3.5,
        trail_pct=3.5,
        min_lock_gain_pct=0.5,
        min_raise_bps=10,
        market_gap_bps=10,
    )
    assert plan[0]["action"] == "escalate_below_accepted_floor"
    assert plan[0]["reason"] == "market_below_broker_accepted_floor"
    assert state["SCHW"]["accepted_stop_floor"] == 108.0


def test_partial_qty_change_preserves_lifecycle_floor_but_new_entry_resets_it():
    previous = {"SCHW": {"entry_price": 100.0, "hwm": 110.0,
                         "accepted_stop_floor": 104.0,
                         "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}}
    _, same = build_ratchet_plan(
        [_position(price=106.0, entry=100.0, qty=0.25)], [], previous,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert same["SCHW"]["accepted_stop_floor"] == 104.0
    assert same["SCHW"]["lifecycle_first_seen_at_utc"] == "2026-08-10T13:30:00Z"

    _, changed = build_ratchet_plan(
        [_position(price=106.0, entry=101.0, qty=0.25)], [], previous,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert changed["SCHW"]["accepted_stop_floor"] == 0.0
    assert changed["SCHW"]["hwm"] == 106.0


def test_confirmed_stop_requires_fixed_sell_and_full_coverage():
    assert _confirmed_fixed_stop(_stop(price=104.0), symbol="SCHW", position_qty=0.5)
    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "type": "trailing_stop"},
        symbol="SCHW",
        position_qty=0.5,
    )

    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "qty": "0.25"},
        symbol="SCHW",
        position_qty=0.5,
    )
    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "qty": "0.75"},
        symbol="SCHW",
        position_qty=0.5,
    )


def test_ratchet_preserves_new_fill_identity_across_restart():
    identity = {"entry_order_id": "entry-schw", "account_id": "paper-account",
                "strategy_id": "ALPACA-BASELINE-26f7ff663dc98e87"}
    prior = {"SCHW": {**identity, "entry_price": 100.0, "hwm": 110.0,
                      "accepted_stop_floor": 102.0,
                      "lifecycle_first_seen_at_utc": "2026-09-18T14:00:00Z"}}
    _, after = build_ratchet_plan(
        [_position(price=109.0)], [_stop(price=102.0)], prior,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert {key: after["SCHW"].get(key) for key in identity} == identity
    assert after["SCHW"]["hwm"] == 110.0
    _, next_lifecycle = build_ratchet_plan(
        [_position(price=109.0, entry=101.0)], [], prior,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert "entry_order_id" not in next_lifecycle["SCHW"]


def test_paper_apply_replaces_stop_and_confirms_broker_readback(monkeypatch, tmp_path, capsys):
    assert _run_manager(monkeypatch, tmp_path, apply=True) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert _FakeBroker.instances[0].base_url == PAPER_URL
    assert _FakeBroker.instances[0].replace_payloads == [{"stop_price": "101.32"}]
    assert receipt["mode"] == "apply"
    assert receipt["results"] == [{
        "symbol": "SCHW",
        "status": "confirmed",
        "old_order_id": "stop-1",
        "new_order_id": "stop-2",
        "target_stop": 101.32,
        "confirmed_stop": 101.32,
        "confirmed_tif": "day",
    }]


def test_paper_restart_keeps_accepted_floor_and_high_water_mark(monkeypatch, tmp_path, capsys):
    assert _run_manager(monkeypatch, tmp_path, apply=True) == 0
    runtime = tmp_path / "runtime" / "alpaca_paper_protective_exit"
    first_state = json.loads((runtime / "protective_exit_hwm.json").read_text())
    assert first_state["SCHW"]["hwm"] == 105.0
    assert first_state["SCHW"]["accepted_stop_floor"] == 101.32

    _FakeBroker.current_price = 104.0
    _FakeBroker.existing_stop = 101.32
    # Keep the broker state across the process restart while retaining the fake
    # client's external boundary behavior.
    monkeypatch.setattr(manager, "AlpacaClient", _FakeBroker)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALPACA_BASE_URL", PAPER_URL)
    monkeypatch.setenv("ALPACA_PROTECTIVE_EXIT_ACK", "PROTECTIVE_EXITS_ONLY")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setattr(sys, "argv", ["alpaca_protective_exit_manager.py", "--apply"])
    assert manager._main_unlocked() == 0
    second_state = json.loads((runtime / "protective_exit_hwm.json").read_text())
    assert second_state["SCHW"]["hwm"] == 105.0
    assert second_state["SCHW"]["accepted_stop_floor"] == 101.32
    assert _FakeBroker.instances[-1].replace_payloads == []


def test_live_apply_preserves_live_default_runtime(monkeypatch, tmp_path):
    assert _run_manager(monkeypatch, tmp_path, base_url=LIVE_URL, apply=True) == 0
    assert (tmp_path / "runtime" / "alpaca_live_v38" / "protective_exit_hwm.json").is_file()
    assert not (tmp_path / "runtime" / "alpaca_paper_protective_exit").exists()


def test_intended_manager_refuses_missing_lifecycle_in_existing_state(monkeypatch, tmp_path, capsys):
    assert _run_manager(monkeypatch, tmp_path, apply=True,
                        extra_env={"ALPACA_INTENDED_PAPER": "1"}) == 7
    assert "intended_lifecycle_state_not_authoritative" in capsys.readouterr().err
    assert _FakeBroker.instances[0].replace_payloads == []
    state = tmp_path / "runtime/alpaca_paper_protective_exit/protective_exit_hwm.json"
    assert state.read_text() == "{}"


def test_intended_manager_cannot_run_against_live(monkeypatch, tmp_path):
    assert _run_manager(monkeypatch, tmp_path, base_url=LIVE_URL,
                        extra_env={"ALPACA_INTENDED_PAPER": "1"}) == 4
    assert _FakeBroker.instances == []


def test_intended_manager_restart_preserves_trusted_fill_state(monkeypatch, tmp_path):
    assert _run_manager(monkeypatch, tmp_path) == 0
    path = tmp_path / "runtime/alpaca_paper_protective_exit/protective_exit_hwm.json"
    state = json.loads(path.read_text())
    state["SCHW"].update({"entry_order_id": "entry-schw", "account_id": "paper-account",
                          "strategy_id": "ALPACA-BASELINE-26f7ff663dc98e87"})
    path.write_text(json.dumps(state))
    monkeypatch.setenv("ALPACA_INTENDED_PAPER", "1")
    monkeypatch.setattr(_FakeBroker, "get_account", lambda self: {"id": "paper-account"})
    assert manager._main_unlocked() == 0
    restored = json.loads(path.read_text())["SCHW"]
    for field in ("hwm", "accepted_stop_floor", "entry_order_id", "account_id", "strategy_id"):
        assert restored[field] == state["SCHW"][field]


@pytest.mark.parametrize("base_url", ["https://example.invalid", "http://paper-api.alpaca.markets"])
def test_unapproved_endpoint_is_rejected_before_authenticated_client(monkeypatch, tmp_path, capsys, base_url):
    assert _run_manager(monkeypatch, tmp_path, base_url=base_url, seed_state=False) == 4
    assert _FakeBroker.instances == []
    assert "error=invalid_alpaca_endpoint" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("base_url", "env", "expected_code", "expected_error"),
    [
        (base_url, env, code, error)
        for base_url in (PAPER_URL, LIVE_URL)
        for env, code, error in (
            ({"ALPACA_PROTECTIVE_EXIT_ACK": ""}, 3, "error=missing_protective_exit_ack"),
            ({"ALPACA_ALLOW_NEW_ENTRIES": "1"}, 5, "error=protective_manager_requires_new_entries_off"),
        )
    ],
)
def test_apply_keeps_ack_and_new_entry_guards(
    monkeypatch, tmp_path, capsys, base_url, env, expected_code, expected_error,
):
    assert _run_manager(
        monkeypatch, tmp_path, base_url=base_url, apply=True, extra_env=env,
    ) == expected_code
    assert _FakeBroker.instances == []
    assert expected_error in capsys.readouterr().err


def test_paper_default_runtime_is_isolated_and_explicit_paper_runtime_is_allowed(monkeypatch, tmp_path):
    assert _run_manager(monkeypatch, tmp_path) == 0
    default_runtime = tmp_path / "runtime" / "alpaca_paper_protective_exit"
    assert (default_runtime / "protective_exit_hwm.json").is_file()
    assert (default_runtime / "protective_exit_latest.json").is_file()

    explicit_runtime = tmp_path / "paper-receipts"
    assert _run_manager(
        monkeypatch,
        tmp_path,
        extra_env={"ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR": explicit_runtime},
    ) == 0
    assert (explicit_runtime / "protective_exit_hwm.json").is_file()
    assert (explicit_runtime / "protective_exit_latest.json").is_file()


@pytest.mark.parametrize("setting", [
    "ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR",
    "ALPACA_PROTECTIVE_EXIT_HWM_PATH",
    "ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH",
])
def test_paper_rejects_live_runtime_paths_including_symlink(monkeypatch, tmp_path, capsys, setting):
    live_runtime = tmp_path / "runtime" / "alpaca_live_v38"
    live_runtime.mkdir(parents=True)
    alias = tmp_path / "paper-alias"
    alias.symlink_to(live_runtime, target_is_directory=True)
    path = alias if setting.endswith("RUNTIME_DIR") else alias / (
        "protective_exit_hwm.json" if setting.endswith("HWM_PATH") else "protective_exit_latest.json"
    )
    assert _run_manager(monkeypatch, tmp_path, extra_env={setting: path}, seed_state=False) == 8
    assert _FakeBroker.instances == []
    assert "error=paper_runtime_overlaps_live_runtime" in capsys.readouterr().err
