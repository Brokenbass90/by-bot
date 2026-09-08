import json
from pathlib import Path

import pytest

from scripts import run_att1_lifecycle_zero_risk as runner
from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_session import LifecycleSession


ROOT = Path(__file__).resolve().parents[1]


def test_public_lifecycle_runner_entrypoint_exists():
    assert (ROOT / "scripts" / "run_att1_lifecycle_zero_risk.py").is_file()


def test_config_is_exact_default_off_and_has_no_authority(tmp_path):
    cache = tmp_path / "l1-cache"
    cache.mkdir()
    config = {
        "schema_id": "att1_lifecycle_public_config_v1",
        "enabled": False,
        "authority": {
            "money_authority": False,
            "orders_allowed": False,
            "private_api_allowed": False,
            "promotion_authority": False,
        },
        "profile_sha256": "a" * 64,
        "runtime_dir": str(tmp_path / "runtime"),
        "l1_cache_dir": str(cache),
        "public_base_url": "https://api.bybit.com",
        "poll_seconds": 1,
        "max_response_bytes": 5_000_000,
        "min_free_bytes": 536_870_912,
        "scenario_taker_fee_rate": "0.001",
        "max_book_participation": "0.05",
        "epoch_id": "att1-public-lifecycle-20260908-v1",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    assert runner.load_config(path) == config
    config["authority"]["orders_allowed"] = True
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(runner.RunnerViolation, match="authority"):
        runner.load_config(path)
    config["authority"] = {key: 0 for key in runner.AUTHORITY}
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(runner.RunnerViolation, match="authority"):
        runner.load_config(path)
    path.write_text('{"schema_id":"x","schema_id":"x"}', encoding="utf-8")
    with pytest.raises(runner.RunnerViolation, match="config unreadable"):
        runner.load_config(path)


def test_public_transport_is_allowlisted_get_only_and_rejects_ambiguous_json():
    calls = []

    def transport(endpoint, params, *, timeout_seconds, headers):
        calls.append((endpoint, params, timeout_seconds, headers))
        return b'{"retCode":0,"result":{"category":"linear","symbol":"BTCUSDT","list":[]}}'

    response = runner.request_public(
        transport,
        "/v5/market/kline",
        {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 2},
        symbol="BTCUSDT",
        max_response_bytes=5_000_000,
    )
    assert response["result"]["symbol"] == "BTCUSDT"
    assert calls == [
        ("https://api.bybit.com/v5/market/kline", {"category": "linear", "symbol": "BTCUSDT", "interval": "60", "limit": 2}, 10, {})
    ]
    with pytest.raises(runner.RunnerViolation, match="allowlist"):
        runner.request_public(transport, "/v5/order/create", {"category": "linear", "symbol": "BTCUSDT"}, symbol="BTCUSDT", max_response_bytes=5_000_000)
    with pytest.raises(runner.RunnerViolation, match="duplicate"):
        runner.decode_public_json(b'{"retCode":0,"retCode":0}', 100)
    with pytest.raises(runner.RunnerViolation, match="retCode"):
        runner.decode_public_json(b'{"retCode":true,"result":{}}', 100)


def test_endpoint_specific_public_envelopes_accept_orderbook_and_funding_rows():
    def orderbook(_endpoint, _params, **_kwargs):
        return b'{"retCode":0,"result":{"s":"BTCUSDT","b":[["99","1"]],"a":[["100","1"]],"ts":1,"u":2,"seq":3,"cts":1}}'
    assert runner.request_public(orderbook, "/v5/market/orderbook", {"category":"linear","symbol":"BTCUSDT","limit":1}, symbol="BTCUSDT", max_response_bytes=1000)["result"]["s"] == "BTCUSDT"
    def funding(_endpoint, _params, **_kwargs):
        return b'{"retCode":0,"result":{"category":"linear","list":[{"symbol":"BTCUSDT","fundingRate":"0.001","fundingRateTimestamp":"1"}]}}'
    assert runner.request_public(funding, "/v5/market/funding/history", {"category":"linear","symbol":"BTCUSDT","limit":1}, symbol="BTCUSDT", max_response_bytes=1000)["result"]["list"]


def test_short_ioc_simulation_uses_only_fresh_post_submit_bid_levels_once():
    snapshot = {
        "ts": 10_100,
        "cts": 10_000,
        "u": 5,
        "seq": 9,
        "b": [["99", "1"], ["98", "1"]],
        "a": [["100", "1"]],
    }
    fills = runner.simulate_ioc_fills(
        snapshot,
        decision_id="d" * 64,
        order_id="research-order:" + "d" * 64,
        kind="ENTRY_FILL",
        requested_qty="0.1",
        qty_step="0.01",
        submit_ms=10_000,
        received_ms=10_200,
        source_sha256="a" * 64,
    )
    assert [(row["qty"], row["price"], row["fee_amount"]) for row in fills] == [
        ("0.05", "99", "0.00495"), ("0.05", "98", "0.0049")
    ]
    assert all(row["exchange_ms"] == 10_000 and row["received_ms"] == 10_200 for row in fills)
    assert len({row["execution_id"] for row in fills}) == 2
    assert runner.simulate_ioc_fills(
        {**snapshot, "cts": 9_999}, decision_id="d" * 64, order_id="research-order:" + "d" * 64,
        kind="ENTRY_FILL", requested_qty="0.1", qty_step="0.01", submit_ms=10_000,
        received_ms=10_200, source_sha256="a" * 64,
    ) == []
    with pytest.raises(runner.RunnerViolation, match="crossed"):
        runner.simulate_ioc_fills({**snapshot, "a": [["98", "1"]]}, decision_id="d" * 64, order_id="research-order:" + "d" * 64, kind="ENTRY_FILL", requested_qty="0.1", qty_step="0.01", submit_ms=10_000, received_ms=10_200, source_sha256="a" * 64)


def test_persistence_precedes_normalized_restart_identical_verification(tmp_path):
    profile = build_profile(ROOT)
    t = 1_800 * 3_600_000
    intent = {
        "signal": {
            "schema_id": "att1_lifecycle_signal_v1", "symbol": "BTCUSDT", "side": "short",
            "stream": "EXECUTION_FORWARD", "bar_close_ms": t, "source_available_ms": t + 10,
            "signal_ready_ms": t + 20, "entry": "100", "sl": "110", "tps": ["88", "75"],
            "tp_fracs": ["0.55", "0.45"], "be_trigger_rr": "0", "be_lock_rr": "0.02",
            "trailing_atr_mult": "0", "trailing_atr_period": 14, "trail_activate_rr": "1",
            "time_stop_bars_5m": 4032, "source_sha256": "a" * 64, "data_sha256": "b" * 64,
            "profile_sha256": profile["profile_sha256"],
        },
        "instrument": {
            "symbol": "BTCUSDT", "tick_size": "0.01", "qty_step": "0.01", "min_order_qty": "0.01",
            "min_notional": "1", "max_market_qty": "10", "observed_ms": t + 10, "source_sha256": "c" * 64,
        },
        "book_state": {"active_decision_id": None, "last_admitted_bar_ms": None, "last_terminal_ms": None},
        "book": "ATT1_TEST", "submit_ms": t + 30,
    }
    path = tmp_path / "BTCUSDT.jsonl"
    session = LifecycleSession(path, profile, intent=intent)
    runner.persist_events(session, [{
        "schema_id": "att1_lifecycle_event_v1", "event_id": "ack", "kind": "ENTRY_ACK",
        "exchange_ms": t + 31, "received_ms": t + 32, "source_sha256": "a" * 64,
    }])
    before = path.read_bytes()
    verified = runner.verify_state([path], profile)
    assert path.read_bytes() == before
    assert verified["authority"] == runner.AUTHORITY
    assert verified["sessions"][0]["held_qty"] == "0"
    assert len(verified["state_sha256"]) == 64
    assert runner.verify_state([], profile)["sessions"] == []


def test_preflight_reconciles_pinned_profile_without_network_or_runtime_mutation(tmp_path):
    profile = build_profile(ROOT)
    cache = tmp_path / "l1"
    cache.mkdir()
    runtime = tmp_path / "new-runtime"
    config = {
        "schema_id": "att1_lifecycle_public_config_v1", "enabled": False,
        "authority": runner.AUTHORITY, "profile_sha256": profile["profile_sha256"],
        "runtime_dir": str(runtime), "l1_cache_dir": str(cache), "public_base_url": "https://api.bybit.com",
        "poll_seconds": 1, "max_response_bytes": 5_000_000, "min_free_bytes": 536_870_912,
        "scenario_taker_fee_rate": "0.001", "max_book_participation": "0.05",
        "epoch_id": "att1-public-lifecycle-20260908-v1",
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert runner.preflight(path, root=ROOT)["profile_sha256"] == profile["profile_sha256"]
    assert runner.main(["--config", str(path), "--preflight"]) == 0
    assert not runtime.exists()


def test_run_authorization_requires_exact_ack_and_enabled_config():
    disabled = {"enabled": False}
    with pytest.raises(runner.RunnerViolation, match="ack"):
        runner.require_run_authorization(disabled, None)
    with pytest.raises(runner.RunnerViolation, match="disabled"):
        runner.require_run_authorization(disabled, "ATT1_PUBLIC_LIFECYCLE")
    runner.require_run_authorization({"enabled": True}, "ATT1_PUBLIC_LIFECYCLE")


def test_heartbeat_is_atomic_and_never_claims_market_or_account_parity(tmp_path):
    path = tmp_path / "heartbeat.json"
    runner.write_heartbeat(path, {"status": "IDLE", "epoch_id": "att1-public-lifecycle-20260908-v1"})
    heartbeat = json.loads(path.read_text(encoding="utf-8"))
    assert heartbeat["authority"] == runner.AUTHORITY
    assert heartbeat["continuous_market_path_verified"] is False
    assert heartbeat["execution_parity"] is False
    assert heartbeat["actual_account_costs_verified"] is False
    assert heartbeat["promotion_pass"] is False
    assert path.stat().st_mode & 0o777 == 0o600


def test_instrument_envelope_validates_each_symbol_in_list():
    def transport(*_args,**_kwargs):
        return b'{"retCode":0,"result":{"category":"linear","list":[{"symbol":"BTCUSDT"}],"nextPageCursor":""}}'
    assert runner.request_public(transport,'/v5/market/instruments-info',{'category':'linear','symbol':'BTCUSDT'},symbol='BTCUSDT',max_response_bytes=1000)['result']['list']


def test_public_decimal_rejects_unbounded_exponent_before_fraction_allocation():
    with pytest.raises(runner.RunnerViolation):runner._decimal('1e999999999','rate')
