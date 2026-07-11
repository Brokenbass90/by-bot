import pytest

from web.routes import ai_routes


@pytest.mark.parametrize(
    "action,params",
    [
        ("enable_sleeve", {"sleeve": "att1"}),
        ("disable_sleeve", {"sleeve": "att1"}),
        ("set_safe_mode", {}),
        ("clear_safe_mode", {}),
        ("reload_config", {}),
    ],
)
def test_unacknowledged_trading_controls_are_blocked(action, params):
    ok, reasons, _market = ai_routes._validate_command(action, params)

    assert not ok
    assert "effective-state acknowledgement" in reasons[0]


def test_blocked_control_does_not_write_fake_overlay(monkeypatch, tmp_path):
    overlay = tmp_path / "web_control_overlay.env"
    audit = tmp_path / "web_control_audit.jsonl"
    monkeypatch.setattr(ai_routes, "_OVERLAY_ENV", overlay)
    monkeypatch.setattr(ai_routes, "_AUDIT_LOG", audit)

    result = ai_routes.execute_command("enable_sleeve", {"sleeve": "att1"}, "owner@example.com")

    assert result.startswith("Blocked by command validator:")
    assert not overlay.exists()
    assert audit.exists()


@pytest.mark.parametrize("params", [None, [], "bad", 7])
def test_malformed_params_fail_closed(params):
    ok, reasons, market = ai_routes._validate_command("run_backtest", params)

    assert not ok and market == "unknown"
    assert reasons == ["params must be a JSON object"]


@pytest.mark.parametrize("days", [-1, 0, 29, 3651, "forever", True])
def test_backtest_days_are_bounded(days):
    ok, reasons, _market = ai_routes._validate_command(
        "run_backtest",
        {"sleeve": "att1", "symbols": ["BTCUSDT"], "days": days},
    )

    assert not ok
    assert any("days/period" in reason for reason in reasons)


def test_valid_backtest_goes_to_review_inbox_with_normalized_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(ai_routes, "_AUDIT_LOG", tmp_path / "audit.jsonl")

    result = ai_routes.execute_command(
        "run_backtest",
        {"sleeve": "ATT1", "symbols": "BTCUSDT, ETHUSDT", "period": "360d"},
        "owner@example.com",
    )

    inbox = tmp_path / "runtime" / "ai_operator" / "backtest_requests.jsonl"
    item = __import__("json").loads(inbox.read_text(encoding="utf-8"))
    assert "operator-review inbox" in result
    assert item["status"] == "operator_review_required"
    assert item["params"] == {"sleeve": "att1", "symbols": ["BTCUSDT", "ETHUSDT"], "days": 360}
