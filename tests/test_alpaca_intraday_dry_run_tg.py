from scripts import equities_alpaca_intraday_bridge as bridge


def test_dry_run_telegram_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTRADAY_DRY_RUN_TG_ENABLE", raising=False)

    assert bridge._dry_run_tg_enabled() is False


def test_dry_run_telegram_can_be_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("INTRADAY_DRY_RUN_TG_ENABLE", "1")

    assert bridge._dry_run_tg_enabled() is True
