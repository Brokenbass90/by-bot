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
