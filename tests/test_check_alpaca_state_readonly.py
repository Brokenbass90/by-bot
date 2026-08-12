import subprocess
import sys

from scripts import check_alpaca_state_readonly as checker


def test_collect_uses_read_only_getters_and_labels_paper(monkeypatch):
    loaded = []

    class Client:
        def __init__(self, base_url, _key, _secret):
            self.base_url = base_url

        def get_account(self):
            return {"status": "ACTIVE", "equity": "500", "cash": "350"}

        def list_positions(self):
            return [{"symbol": "ORCL", "qty": "-1", "current_price": "145"}]

        def list_orders(self, status="open", after=""):
            assert status in {"open", "all"}
            return [{
                "symbol": "ORCL",
                "side": "buy",
                "status": "new",
                "type": "stop",
                "time_in_force": "day",
            }]

        def submit_bracket_order(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

        def cancel_order(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

        def close_position(self, *args, **kwargs):
            raise AssertionError("mutation method must not be called")

    monkeypatch.setattr(checker.bridge, "_load_env_file", loaded.append)
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

    result = checker.collect("ORCL", "/tmp/alpaca-paper.env")
    assert result["authority"] == "read_only_get_no_order_mutation"
    assert result["configured_env_file"] == "/tmp/alpaca-paper.env"
    assert result["broker_mode"] == "PAPER"
    assert result["positions"][0]["side"] == "short"
    assert result["open_order_count"] == 1
    assert result["recent_order_count"] == 1
    assert result["open_orders"][0]["time_in_force"] == "day"
    assert [str(path) for path in loaded] == ["/tmp/alpaca-paper.env"]


def test_collect_defaults_to_live_v38_env(monkeypatch):
    loaded = []

    class Client:
        def __init__(self, _base_url, _key, _secret):
            pass

        def get_account(self):
            return {"status": "ACTIVE", "equity": "485", "cash": "390"}

        def list_positions(self):
            return []

        def list_orders(self, status="open", after=""):
            return []

    monkeypatch.setattr(checker.bridge, "_load_env_file", loaded.append)
    monkeypatch.setattr(checker.bridge, "_refresh_runtime_paths", lambda: None)
    monkeypatch.setattr(
        checker.bridge,
        "_env",
        lambda key, default="": {
            "ALPACA_API_KEY_ID": "key",
            "ALPACA_API_SECRET_KEY": "secret",
            "ALPACA_BASE_URL": "https://api.alpaca.markets",
        }.get(key, default),
    )
    monkeypatch.setattr(checker.bridge, "AlpacaClient", Client)

    result = checker.collect()

    assert result["broker_mode"] == "LIVE"
    assert loaded == [checker.DEFAULT_LIVE_ENV_FILE]


def test_cli_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, str(checker.__file__), "--help"],
        cwd=checker.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "protected Alpaca" in completed.stdout
    assert "live v38 file" in completed.stdout
