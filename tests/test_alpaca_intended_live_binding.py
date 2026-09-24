import json

import pytest

from scripts import equities_alpaca_paper_bridge as bridge


LIVE = "https://api.alpaca.markets"
PAPER = "https://paper-api.alpaca.markets"


def _binding(**changes):
    value = {
        "schema_version": 1,
        "endpoint": LIVE,
        "strategy_id": bridge._INTENDED_PAPER_STRATEGY_ID,
        "account_id": "live-account-1",
        "enabled": False,
        "capital_usd": None,
        "max_positions": 4,
        "gross_exposure": 0.70,
        "maximum_weight": 0.60,
    }
    value.update(changes)
    return value


def _write_binding(tmp_path, monkeypatch, **changes):
    path = tmp_path / "intended-live-binding.json"
    path.write_text(json.dumps(_binding(**changes)))
    monkeypatch.setenv("ALPACA_INTENDED_LIVE_BINDING_PATH", str(path))
    return path


def test_disabled_null_capital_binding_is_valid_for_read_only(tmp_path, monkeypatch):
    expected = _binding()
    _write_binding(tmp_path, monkeypatch)

    assert bridge._load_intended_live_binding(base_url=LIVE, account_id="live-account-1", capital=0) == expected


@pytest.mark.parametrize(
    ("base_url", "binding_change", "error"),
    [
        ("https://paper-api.alpaca.markets", {}, "endpoint"),
        (LIVE, {"account_id": "other-account"}, "account"),
        (LIVE, {"capital_usd": float("inf")}, "capital"),
        (LIVE, {"max_positions": 3}, "max_positions"),
    ],
)
def test_binding_rejects_wrong_endpoint_or_pinned_fields(tmp_path, monkeypatch, base_url, binding_change, error):
    _write_binding(tmp_path, monkeypatch, **binding_change)

    with pytest.raises(bridge.IntendedPaperProtectionError, match=error):
        bridge._load_intended_live_binding(base_url=base_url, account_id="live-account-1")


def test_binding_rejects_account_and_capital_mismatch(tmp_path, monkeypatch):
    _write_binding(tmp_path, monkeypatch, enabled=True, capital_usd=123.45)

    with pytest.raises(bridge.IntendedPaperProtectionError, match="account"):
        bridge._load_intended_live_binding(base_url=LIVE, account_id="wrong")
    with pytest.raises(bridge.IntendedPaperProtectionError, match="capital"):
        bridge._load_intended_live_binding(base_url=LIVE, capital=123.46)


@pytest.mark.parametrize(
    ("binding_change", "missing_field", "error"),
    [
        ({"endpoint": "https://paper-api.alpaca.markets"}, None, "endpoint"),
        ({"account_id": 7}, None, "account"),
        ({"schema_version": 1.0}, None, "schema"),
        ({}, "endpoint", "endpoint"),
        ({}, "capital_usd", "capital"),
    ],
)
def test_binding_rejects_malformed_or_missing_required_document_fields(
    tmp_path, monkeypatch, binding_change, missing_field, error
):
    path = _write_binding(tmp_path, monkeypatch, **binding_change)
    if missing_field:
        document = json.loads(path.read_text())
        del document[missing_field]
        path.write_text(json.dumps(document))

    with pytest.raises(bridge.IntendedPaperProtectionError, match=error):
        bridge._load_intended_live_binding(base_url=LIVE)


@pytest.mark.parametrize("contents", ["{", "[]"])
def test_binding_rejects_missing_or_malformed_document(tmp_path, monkeypatch, contents):
    path = tmp_path / "intended-live-binding.json"
    path.write_text(contents)
    monkeypatch.setenv("ALPACA_INTENDED_LIVE_BINDING_PATH", str(path))

    with pytest.raises(bridge.IntendedPaperProtectionError, match="binding"):
        bridge._load_intended_live_binding(base_url=LIVE)


def test_enabled_binding_requires_ack_and_existing_live_guard(tmp_path, monkeypatch):
    _write_binding(tmp_path, monkeypatch, enabled=True, capital_usd=123.45)

    with pytest.raises(bridge.IntendedPaperProtectionError, match="ack"):
        bridge._load_intended_live_binding(base_url=LIVE, capital=123.45, require_enabled=True)

    monkeypatch.setenv("ALPACA_INTENDED_LIVE_ACK", "INTENDED_LIVE_CANARY")
    with pytest.raises(bridge.IntendedPaperProtectionError, match="live_guard"):
        bridge._load_intended_live_binding(base_url=LIVE, capital=123.45, require_enabled=True)


def test_require_enabled_rejects_disabled_binding(tmp_path, monkeypatch):
    _write_binding(tmp_path, monkeypatch)

    with pytest.raises(bridge.IntendedPaperProtectionError, match="disabled"):
        bridge._load_intended_live_binding(base_url=LIVE, capital=0, require_enabled=True)


def test_enabled_binding_with_explicit_configured_capital_is_valid(tmp_path, monkeypatch):
    expected = _binding(enabled=True, capital_usd=123.45)
    _write_binding(tmp_path, monkeypatch, enabled=True, capital_usd=123.45)
    monkeypatch.setenv("ALPACA_INTENDED_LIVE_ACK", "INTENDED_LIVE_CANARY")
    monkeypatch.setenv("ALPACA_LIVE_ACCOUNT_ROLE", "monthly_v38")
    monkeypatch.setenv("ALPACA_LIVE_CONFIRM", "MONTHLY_V38_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_MAX_CAPITAL_USD", "123.45")

    assert bridge._load_intended_live_binding(
        base_url=LIVE, account_id="live-account-1", capital=123.45, require_enabled=True
    ) == expected


def _enable_live_binding(tmp_path, monkeypatch, **changes):
    binding_changes = {"enabled": True, "capital_usd": 123.45}
    binding_changes.update(changes)
    _write_binding(tmp_path, monkeypatch, **binding_changes)
    monkeypatch.setenv("ALPACA_INTENDED_LIVE_ACK", "INTENDED_LIVE_CANARY")
    monkeypatch.setenv("ALPACA_LIVE_ACCOUNT_ROLE", "monthly_v38")
    monkeypatch.setenv("ALPACA_LIVE_CONFIRM", "MONTHLY_V38_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_MAX_CAPITAL_USD", "123.45")


def test_intended_lifecycle_mode_is_exactly_one_of_paper_or_explicit_live(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_INTENDED_PAPER", "1")
    assert bridge._intended_lifecycle_enabled(PAPER)
    with pytest.raises(bridge.IntendedPaperProtectionError, match="paper"):
        bridge._intended_lifecycle_enabled(LIVE)

    _enable_live_binding(tmp_path, monkeypatch)
    monkeypatch.delenv("ALPACA_INTENDED_PAPER")
    monkeypatch.setenv("ALPACA_INTENDED_LIVE", "1")
    assert bridge._intended_lifecycle_enabled(
        LIVE, require_enabled=True, account_id="live-account-1", capital=123.45
    )

    monkeypatch.setenv("ALPACA_INTENDED_PAPER", "1")
    with pytest.raises(bridge.IntendedPaperProtectionError, match="mutually"):
        bridge._intended_lifecycle_enabled(LIVE)


@pytest.mark.parametrize(
    ("binding_change", "account_id", "capital", "env_change", "error"),
    [
        ({"enabled": False, "capital_usd": None}, "live-account-1", 0, {}, "disabled"),
        ({}, "wrong-account", 123.45, {}, "account"),
        ({}, "live-account-1", 123.46, {}, "capital"),
        ({}, "live-account-1", 123.45, {"ALPACA_INTENDED_LIVE_ACK": "wrong"}, "ack"),
    ],
)
def test_live_mode_rejects_unbound_before_lifecycle(
    tmp_path, monkeypatch, binding_change, account_id, capital, env_change, error
):
    _enable_live_binding(tmp_path, monkeypatch, **binding_change)
    for key, value in env_change.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ALPACA_INTENDED_LIVE", "1")

    with pytest.raises(bridge.IntendedPaperProtectionError, match=error):
        bridge._intended_lifecycle_enabled(LIVE, require_enabled=True, account_id=account_id, capital=capital)


def test_validated_live_fill_uses_the_existing_floor_contract(tmp_path, monkeypatch):
    _enable_live_binding(tmp_path, monkeypatch)

    class Broker:
        def get_order(self, order_id):
            if order_id == "entry-1":
                return {"id": "entry-1", "symbol": "SCHW", "side": "buy", "status": "filled",
                        "filled_qty": "0.4", "filled_avg_price": "101.25", "filled_at": "2026-09-20T10:01:02Z"}
            return {"id": "stop-1", "symbol": "SCHW", "side": "sell", "type": "stop", "status": "new",
                    "qty": "0.4", "filled_qty": "0", "stop_price": "95.25", "time_in_force": "day"}

    record = bridge._complete_intended_paper_simple_stop(
        client=Broker(), base_url=LIVE, state_dir=tmp_path, ledger_path=tmp_path / "floor.json",
        account_id="live-account-1", entry_order={"id": "entry-1"}, stop_order={"id": "stop-1"},
        symbol="SCHW", requested_stop=95.25, intended_live=True, capital=123.45,
    )
    assert record["accepted_stop_floor"] == 95.25


def test_intended_live_halt_suppresses_entries_without_affecting_legacy_live(tmp_path, monkeypatch):
    (tmp_path / ".paper-entry-halt.json").write_text(json.dumps({"halted": True}))

    assert not bridge.paper_entry_halted(base_url=LIVE, state_dir=tmp_path)
    monkeypatch.setenv("ALPACA_INTENDED_LIVE", "1")
    assert bridge.paper_entry_halted(base_url=LIVE, state_dir=tmp_path)
