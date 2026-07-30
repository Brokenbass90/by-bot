from scripts import restart_bybot_when_flat


def test_wait_until_flat_requires_consecutive_successful_checks(monkeypatch):
    responses = iter(
        [
            [{"symbol": "OPUSDT"}],
            [],
            RuntimeError("temporary API failure"),
            [],
            [],
        ]
    )
    calls = []

    def query():
        response = next(responses)
        calls.append(response)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(restart_bybot_when_flat.time, "sleep", lambda _seconds: None)

    restart_bybot_when_flat.wait_until_flat(query, confirmations=2, interval_sec=1)

    assert len(calls) == 5


def test_query_exchange_positions_fails_closed(monkeypatch):
    monkeypatch.setattr(
        restart_bybot_when_flat.portfolio_status,
        "_load_accounts",
        lambda: [{"name": "main"}, {"name": "arb"}],
    )

    def positions(account):
        if account["name"] == "arb":
            return [], "timeout"
        return [], None

    monkeypatch.setattr(restart_bybot_when_flat.portfolio_status, "_get_positions", positions)

    try:
        restart_bybot_when_flat.query_exchange_positions()
    except RuntimeError as exc:
        assert "arb: timeout" in str(exc)
    else:
        raise AssertionError("position query errors must block a restart")


def test_load_service_process_environment_uses_live_process_without_leaking(monkeypatch):
    monkeypatch.delenv("BYBIT_ACCOUNTS_JSON", raising=False)
    monkeypatch.delenv("TRADE_ACCOUNT_NAME", raising=False)
    payload = (
        b"IGNORED=value\0"
        b"BYBIT_ACCOUNTS_JSON=[{\"name\":\"main\",\"key\":\"secret-key\",\"secret\":\"secret-value\"}]\0"
        b"TRADE_ACCOUNT_NAME=main\0"
    )

    loaded = restart_bybot_when_flat.load_service_process_environment(
        "bybot.service",
        get_main_pid=lambda _service: 123,
        read_environ=lambda pid: payload if pid == 123 else b"",
    )

    assert loaded is True
    assert restart_bybot_when_flat.portfolio_status._load_accounts()[0]["name"] == "main"
    assert restart_bybot_when_flat.os.environ["TRADE_ACCOUNT_NAME"] == "main"
