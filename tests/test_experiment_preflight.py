from types import SimpleNamespace

import pytest

from research_lab import experiment_preflight as preflight


def test_autoresearch_spec_requires_preflight():
    with pytest.raises(preflight.PreflightError, match="no experiment_preflight"):
        preflight.assert_autoresearch_spec_preflight({"grid": {"KNOB": [1, 2]}})


def test_autoresearch_spec_requires_every_varied_knob(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "assert_handle_differentiates",
        lambda *args, **kwargs: [1.0, 2.0],
    )
    spec = {
        "grid": {"KNOB_A": [1, 2], "KNOB_B": [3, 4]},
        "experiment_preflight": [
            {"module": "fake", "env": "KNOB_A", "cfg_field": "a", "values": [1, 2]}
        ],
    }

    with pytest.raises(preflight.PreflightError, match="KNOB_B"):
        preflight.assert_autoresearch_spec_preflight(spec)


def test_autoresearch_spec_returns_receipt_for_verified_grid(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_strategy_class",
        lambda module: lambda: SimpleNamespace(cfg=SimpleNamespace(a=float(__import__("os").environ["KNOB_A"]))),
    )
    spec = {
        "grid": {"KNOB_A": [1, 2]},
        "experiment_preflight": [
            {"module": "fake", "env": "KNOB_A", "cfg_field": "a", "values": [1, 2]}
        ],
    }

    receipt = preflight.assert_autoresearch_spec_preflight(spec)

    assert receipt == [
        {
            "module": "fake",
            "env": "KNOB_A",
            "cfg_field": "a",
            "resolved": [1.0, 2.0],
            "status": "pass",
        }
    ]


def test_params_backed_handle_must_resolve_distinct_values(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_strategy_class",
        lambda module: lambda: SimpleNamespace(
            params={"ALLOW_LONGS": __import__("os").environ["FAKE_ALLOW_LONGS"]}
        ),
    )

    resolved = preflight.assert_param_handle_differentiates(
        "fake", "FAKE_ALLOW_LONGS", "ALLOW_LONGS", [0, 1], quiet=True
    )

    assert resolved == [0.0, 1.0]


def test_params_backed_handle_rejects_unwired_env(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_strategy_class",
        lambda module: lambda: SimpleNamespace(params={"ALLOW_LONGS": 1}),
    )

    with pytest.raises(preflight.PreflightError, match="handle unread"):
        preflight.assert_param_handle_differentiates(
            "fake", "FAKE_ALLOW_LONGS", "ALLOW_LONGS", [0, 1], quiet=True
        )


def test_symbol_handle_resolves_distinct_normalized_universes(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_strategy_class",
        lambda module: lambda: SimpleNamespace(
            cfg=SimpleNamespace(symbol_allowlist=__import__("os").environ["FAKE_UNIVERSE"])
        ),
    )

    resolved = preflight.assert_symbol_handle_differentiates(
        "fake",
        "FAKE_UNIVERSE",
        "symbol_allowlist",
        ["btcusdt,ETHUSDT", "SOLUSDT"],
        quiet=True,
    )

    assert resolved == [("BTCUSDT", "ETHUSDT"), ("SOLUSDT",)]


def test_symbol_handle_rejects_unwired_env(monkeypatch):
    monkeypatch.setattr(
        preflight,
        "_strategy_class",
        lambda module: lambda: SimpleNamespace(
            cfg=SimpleNamespace(symbol_allowlist="BTCUSDT")
        ),
    )

    with pytest.raises(preflight.PreflightError, match="universe handle unread"):
        preflight.assert_symbol_handle_differentiates(
            "fake",
            "FAKE_UNIVERSE",
            "symbol_allowlist",
            ["BTCUSDT", "ETHUSDT"],
            quiet=True,
        )


def test_callable_engine_preflight_proves_volume_exit_handle():
    spec = {
        "grid": {"VOLUME_EXIT_ENABLE": [0, 1]},
        "experiment_preflight": [
            {
                "module": "backtest.portfolio_engine",
                "callable": "volume_exit_settings_from_env",
                "env": "VOLUME_EXIT_ENABLE",
                "cfg_field": "enable",
                "values": [0, 1],
            }
        ],
    }

    receipt = preflight.assert_autoresearch_spec_preflight(spec)

    assert receipt[0]["resolved"] == [0.0, 1.0]
    assert receipt[0]["callable"] == "volume_exit_settings_from_env"
