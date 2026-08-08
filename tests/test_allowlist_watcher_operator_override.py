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


def test_tg_live_only_suppresses_inactive_shadow_sleeves(monkeypatch):
    sent = []
    monkeypatch.setenv("ALLOWLIST_WATCHER_TG_MODE", "live_only")
    monkeypatch.setenv("ASM1_RISK_MULT", "0")
    monkeypatch.setenv("FLAT_RISK_MULT", "0")
    monkeypatch.setattr("bot.allowlist_watcher._tg", lambda token, chat, msg: sent.append(msg))

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._tg_token = "test"
    watcher._tg_chat = "test"
    watcher._send_tg_digest(
        {
            "ASM1_SYMBOL_ALLOWLIST": ("XAGUSDT", "XAUUSDT"),
            "ARF1_SYMBOL_ALLOWLIST": ("LTCUSDT", ""),
        },
        {},
        source="dynamic_allowlist_latest.env",
    )

    assert sent == []


def test_tg_live_only_keeps_live_sleeve_and_filters_shadow(monkeypatch):
    sent = []
    monkeypatch.setenv("ALLOWLIST_WATCHER_TG_MODE", "live_only")
    monkeypatch.setenv("ATT1_RISK_MULT", "0.10")
    monkeypatch.setenv("ASM1_RISK_MULT", "0")
    monkeypatch.setattr("bot.allowlist_watcher._tg", lambda token, chat, msg: sent.append(msg))

    watcher = AllowlistWatcher(poll_interval=999)
    watcher._tg_token = "test"
    watcher._tg_chat = "test"
    watcher._send_tg_digest(
        {
            "ATT1_SYMBOL_ALLOWLIST": ("BTCUSDT", "BTCUSDT,ETHUSDT"),
            "ASM1_SYMBOL_ALLOWLIST": ("XAGUSDT", "XAUUSDT"),
        },
        {},
        source="dynamic_allowlist_latest.env",
    )

    assert len(sent) == 1
    assert "ATT1" in sent[0]
    assert "ETHUSDT" in sent[0]
    assert "ASM1" not in sent[0]


def test_tg_modes_all_and_off(monkeypatch):
    sent = []
    monkeypatch.setattr("bot.allowlist_watcher._tg", lambda token, chat, msg: sent.append(msg))
    watcher = AllowlistWatcher(poll_interval=999)
    watcher._tg_token = "test"
    watcher._tg_chat = "test"

    monkeypatch.setenv("ALLOWLIST_WATCHER_TG_MODE", "all")
    watcher._send_tg_digest(
        {"ASM1_SYMBOL_ALLOWLIST": ("XAGUSDT", "XAUUSDT")},
        {},
        source="dynamic_allowlist_latest.env",
    )
    assert len(sent) == 1

    monkeypatch.setenv("ALLOWLIST_WATCHER_TG_MODE", "off")
    watcher._send_tg_digest(
        {"ATT1_SYMBOL_ALLOWLIST": ("BTCUSDT", "ETHUSDT")},
        {},
        source="dynamic_allowlist_latest.env",
    )
    assert len(sent) == 1
