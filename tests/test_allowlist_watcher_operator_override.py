import os

from bot.allowlist_watcher import AllowlistWatcher


def test_operator_override_protects_att1_allowlist_from_dynamic_overlay(tmp_path, monkeypatch):
    override = tmp_path / "att1_canary.env"
    override.write_text(
        "ATT1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT\n"
        "ATT1_RISK_MULT=0.10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ALLOW_OPERATOR_LIVE_OVERRIDES", "1")
    monkeypatch.setenv("OPERATOR_LIVE_OVERRIDE_ENV", str(override))
    monkeypatch.setenv("ATT1_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_SYMBOL_ALLOWLIST": "1000BONKUSDT,ADAUSDT,NEARUSDT,WLDUSDT,XLMUSDT"},
        silent=True,
        source="dynamic_allowlist_latest.env",
    )

    assert os.environ["ATT1_SYMBOL_ALLOWLIST"] == "BTCUSDT,ETHUSDT,SOLUSDT"


def test_operator_override_protects_att1_risk_from_auto_apply(tmp_path, monkeypatch):
    override = tmp_path / "att1_canary.env"
    override.write_text("ATT1_RISK_MULT=0.10\n", encoding="utf-8")
    monkeypatch.setenv("ALLOW_OPERATOR_LIVE_OVERRIDES", "1")
    monkeypatch.setenv("OPERATOR_LIVE_OVERRIDE_ENV", str(override))
    monkeypatch.setenv("ALLOW_AUTO_APPLY_OVERRIDES", "1")
    monkeypatch.setenv("ALLOW_AUTO_APPLY_HOT_RELOAD", "1")
    monkeypatch.setenv("ATT1_RISK_MULT", "0.10")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RISK_MULT": "0.70"},
        silent=True,
        source="auto_apply_params.env",
    )

    assert os.environ["ATT1_RISK_MULT"] == "0.10"


def test_auto_apply_is_ignored_when_startup_auto_apply_is_disabled(monkeypatch):
    monkeypatch.setenv("ALLOW_AUTO_APPLY_OVERRIDES", "0")
    monkeypatch.setenv("ALLOW_AUTO_APPLY_HOT_RELOAD", "1")
    monkeypatch.setenv("ATT1_RISK_MULT", "0.10")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RISK_MULT": "0.70"},
        silent=True,
        source="auto_apply_params.env",
    )

    assert os.environ["ATT1_RISK_MULT"] == "0.10"
    assert all(path.name != "auto_apply_params.env" for path in watcher._files)


def test_auto_apply_requires_separate_runtime_authorization(monkeypatch):
    monkeypatch.setenv("ALLOW_AUTO_APPLY_OVERRIDES", "1")
    monkeypatch.setenv("ALLOW_AUTO_APPLY_HOT_RELOAD", "0")
    monkeypatch.setenv("ATT1_RISK_MULT", "0.10")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RISK_MULT": "0.70"},
        silent=True,
        source="auto_apply_params.env",
    )

    assert os.environ["ATT1_RISK_MULT"] == "0.10"
    assert all(path.name != "auto_apply_params.env" for path in watcher._files)


def test_auto_apply_can_hot_reload_only_with_both_authorizations(monkeypatch):
    monkeypatch.setenv("ALLOW_OPERATOR_LIVE_OVERRIDES", "0")
    monkeypatch.setenv("ALLOW_AUTO_APPLY_OVERRIDES", "1")
    monkeypatch.setenv("ALLOW_AUTO_APPLY_HOT_RELOAD", "1")
    monkeypatch.setenv("ATT1_RISK_MULT", "0.10")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RISK_MULT": "0.20"},
        silent=True,
        source="auto_apply_params.env",
    )

    assert os.environ["ATT1_RISK_MULT"] == "0.20"
    assert any(path.name == "auto_apply_params.env" for path in watcher._files)


def test_dynamic_overlay_still_updates_non_override_vars(tmp_path, monkeypatch):
    override = tmp_path / "att1_canary.env"
    override.write_text("ATT1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT\n", encoding="utf-8")
    monkeypatch.setenv("ALLOW_OPERATOR_LIVE_OVERRIDES", "1")
    monkeypatch.setenv("OPERATOR_LIVE_OVERRIDE_ENV", str(override))
    monkeypatch.setenv("ARF1_SYMBOL_ALLOWLIST", "LINKUSDT")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ARF1_SYMBOL_ALLOWLIST": "BNBUSDT,DOGEUSDT,LINKUSDT"},
        silent=True,
        source="dynamic_allowlist_latest.env",
    )

    assert os.environ["ARF1_SYMBOL_ALLOWLIST"] == "BNBUSDT,DOGEUSDT,LINKUSDT"


def test_dynamic_overlay_updates_when_operator_override_disabled(tmp_path, monkeypatch):
    override = tmp_path / "att1_canary.env"
    override.write_text("ATT1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT\n", encoding="utf-8")
    monkeypatch.setenv("ALLOW_OPERATOR_LIVE_OVERRIDES", "0")
    monkeypatch.setenv("OPERATOR_LIVE_OVERRIDE_ENV", str(override))
    monkeypatch.setenv("ATT1_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_SYMBOL_ALLOWLIST": "ADAUSDT,NEARUSDT"},
        silent=True,
        source="dynamic_allowlist_latest.env",
    )

    assert os.environ["ATT1_SYMBOL_ALLOWLIST"] == "ADAUSDT,NEARUSDT"


def test_dynamic_overlay_cannot_change_strategy_params_by_default(monkeypatch):
    monkeypatch.setenv("ALLOW_DYNAMIC_PARAM_HOT_RELOAD", "0")
    monkeypatch.setenv("ATT1_RSI_SHORT_MIN", "45")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RSI_SHORT_MIN": "80"},
        silent=True,
        source="dynamic_allowlist_latest.env",
    )

    assert os.environ["ATT1_RSI_SHORT_MIN"] == "45"


def test_dynamic_overlay_param_reload_requires_explicit_authorization(monkeypatch):
    monkeypatch.setenv("ALLOW_DYNAMIC_PARAM_HOT_RELOAD", "1")
    monkeypatch.setenv("ATT1_RSI_SHORT_MIN", "45")

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._apply(
        {"ATT1_RSI_SHORT_MIN": "50"},
        silent=True,
        source="dynamic_allowlist_latest.env",
    )

    assert os.environ["ATT1_RSI_SHORT_MIN"] == "50"
