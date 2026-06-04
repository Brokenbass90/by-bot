from scripts.equities_alpaca_paper_bridge import _live_order_guard_errors


def test_paper_orders_do_not_require_live_confirmation(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_LIVE_ACCOUNT_ROLE", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_CONFIRM", raising=False)

    assert _live_order_guard_errors(
        base_url="https://paper-api.alpaca.markets",
        send_orders=True,
        capital_override_usd=500,
    ) == []


def test_live_orders_require_role_confirmation_and_cap(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_LIVE_ACCOUNT_ROLE", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_CONFIRM", raising=False)

    errors = _live_order_guard_errors(
        base_url="https://api.alpaca.markets",
        send_orders=True,
        capital_override_usd=0,
    )

    assert len(errors) == 3


def test_live_orders_pass_with_monthly_role_and_bounded_cap(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_LIVE_ACCOUNT_ROLE", "monthly_v38")
    monkeypatch.setenv("ALPACA_LIVE_CONFIRM", "MONTHLY_V38_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_MAX_CAPITAL_USD", "500")

    assert _live_order_guard_errors(
        base_url="https://api.alpaca.markets",
        send_orders=True,
        capital_override_usd=500,
    ) == []
