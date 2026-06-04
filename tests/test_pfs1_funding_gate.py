from strategies.pump_fade_smart_v1 import PFS1Config, PumpFadeSmartV1Strategy


def test_pfs1_research_can_require_funding_data(monkeypatch):
    monkeypatch.setenv("PFS1_REQUIRE_FUNDING_DATA", "1")

    strategy = PumpFadeSmartV1Strategy()

    assert strategy.cfg.require_funding_data is True


def test_pfs1_live_default_keeps_funding_optional(monkeypatch):
    monkeypatch.delenv("PFS1_REQUIRE_FUNDING_DATA", raising=False)

    assert PFS1Config().require_funding_data is False
