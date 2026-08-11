from scripts import check_alpaca_state_readonly as checker


def test_collect_uses_read_only_getters_and_labels_paper(monkeypatch):
    class Client:
        def __init__(self, base_url, _key, _secret):
            self.base_url = base_url

        def get_account(self):
            return {"status": "ACTIVE", "equity": "500", "cash": "350"}

        def list_positions(self):
            return [{"symbol": "ORCL", "qty": "-1", "current_price": "145"}]

        def list_orders(self, status="open", after=""):
            assert status in {"open", "all"}
            return [{"symbol": "ORCL", "side": "buy", "status": "new", "type": "stop"}]

        def submit_bracket_order(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

        def cancel_order(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

        def close_position(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

    monkeypatch.setattr(checker.bridge, "_load_env_file", lambda _path: None)
    monkeypatch.setattr(checker.bridge, "_refresh_runtime_paths", lambda: None)
    monkeypatch.setattr(
        checker.bridge,
        "_env",
        lambda key, default="": {
            "ALPACA_API_KEY_ID": "key",
            "ALPACA_API_SECRET_KEY": "secret",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        }.get(key, default),
    )
    monkeypatch.setattr(checker.bridge, "AlpacaClient", Client)

    result = checker.collect("ORCL")
    assert result["authority"] == "read_only_get_no_order_mutation"
    assert result["broker_mode"] == "PAPER"
    assert result["positions"][0]["side"] == "short"
    assert result["open_order_count"] == 1
    assert result["recent_order_count"] == 1
