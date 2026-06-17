from scripts import portfolio_status


def _account():
    return {"name": "main", "key": "key", "secret": "secret", "base": "https://example.test"}


def test_position_query_failure_is_not_reported_as_flat(monkeypatch):
    monkeypatch.setattr(
        portfolio_status,
        "_bybit_get",
        lambda *_args, **_kwargs: {"retCode": -1, "error": "network timeout"},
    )

    positions, error = portfolio_status._get_positions(_account())

    assert positions == []
    assert error == "API err: network timeout"


def test_successful_empty_position_query_is_explicitly_flat(monkeypatch):
    monkeypatch.setattr(
        portfolio_status,
        "_bybit_get",
        lambda *_args, **_kwargs: {"retCode": 0, "result": {"list": []}},
    )

    positions, error = portfolio_status._get_positions(_account())

    assert positions == []
    assert error is None
