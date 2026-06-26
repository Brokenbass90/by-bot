from strategies.alt_range_scalp_v1 import AltRangeScalpV1Config
from strategies.alt_range_scalp_v1 import _geometry_block_reason as ars1_geometry_block_reason
from strategies.alt_inplay_breakdown_v1 import AltInplayBreakdownV1Config
from strategies.alt_support_bounce_v1 import _geometry_block_reason as asb1_geometry_block_reason
from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Config, AltTrendlineTouchV1Strategy
from strategies.alt_trendline_touch_v1 import _geometry_block_reason as att1_geometry_block_reason
from strategies.elder_triple_screen_v2 import ElderTripleScreenV2Config
from strategies.impulse_volume_breakout_v1 import ImpulseVolumeBreakoutV1Strategy
from strategies.pump_fade_smart_v1 import PFS1Selector, PumpFadeSmartV1Strategy, _fetch_funding_pct


def test_asb1_blocks_bad_long_geometry() -> None:
    assert asb1_geometry_block_reason(
        entry=105.0,
        sl=99.0,
        tp=109.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("rr_too_low_")

    assert asb1_geometry_block_reason(
        entry=100.0,
        sl=99.99,
        tp=105.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("stop_too_tight_")


def test_att1_blocks_far_and_bad_geometry() -> None:
    assert att1_geometry_block_reason(
        side="long",
        entry=104.0,
        sl=97.8,
        tp=108.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("long_rr_too_low_")

    assert att1_geometry_block_reason(
        side="short",
        entry=96.0,
        sl=102.2,
        tp=92.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("short_rr_too_low_")


def test_att1_max_pivots_used_is_configurable() -> None:
    cfg = AltTrendlineTouchV1Config(min_pivots=2, max_pivots_used=5)
    strategy = AltTrendlineTouchV1Strategy(cfg)

    assert strategy.cfg.max_pivots_used == 5


def test_ars1_defaults_are_range_safe() -> None:
    cfg = AltRangeScalpV1Config()

    assert cfg.max_adx == 25.0
    assert cfg.trail_atr_mult > 0.0
    assert cfg.trail_activate_rr >= 1.0


def test_ars1_blocks_bad_geometry() -> None:
    assert ars1_geometry_block_reason(
        side="short",
        entry=100.0,
        sl=100.01,
        tp=95.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("short_stop_too_tight_")

    assert ars1_geometry_block_reason(
        side="long",
        entry=100.0,
        sl=98.0,
        tp=101.0,
        min_rr=1.0,
        min_stop_pct=0.001,
        max_stop_pct=0.20,
    ).startswith("long_rr_too_low_")


def test_ivb1_hot_reload_clears_armed_state(monkeypatch) -> None:
    strategy = ImpulseVolumeBreakoutV1Strategy()
    old_signature = strategy._armed_config_signature_value
    strategy._armed = {"side": "long", "armed_ts": 1, "breakout_level": 100.0, "atr": 1.0}

    monkeypatch.setenv("IVB1_MAX_ENTRY_DIST_ATR", "1.25")
    strategy._refresh_runtime_config()

    assert strategy.cfg.max_entry_dist_atr == 1.25
    assert strategy._armed is None
    assert strategy._armed_config_signature_value != old_signature


def test_pfs1_funding_fetch_uses_timestamp_when_available() -> None:
    class _Store:
        seen_ts = None

        def fetch_funding_rate(self, symbol, ts_ms=None):
            self.seen_ts = ts_ms
            return 0.001

    store = _Store()
    assert _fetch_funding_pct(store, "BTCUSDT", 123456) == 0.1
    assert store.seen_ts == 123456


def test_pfs1_selector_can_reset_all_cached_instances() -> None:
    selector = PFS1Selector()
    first = selector.get("BTCUSDT")
    selector.reset_all()

    assert selector.get("BTCUSDT") is not first


def test_ready_candidate_risk_guard_defaults_exist() -> None:
    pfs = PumpFadeSmartV1Strategy().cfg
    breakdown = AltInplayBreakdownV1Config()
    elder = ElderTripleScreenV2Config()

    assert pfs.min_stop_pct > 0
    assert pfs.max_stop_pct > pfs.min_stop_pct
    assert breakdown.min_rr >= 1.0
    assert breakdown.max_stop_pct > breakdown.min_stop_pct > 0
    assert elder.min_rr >= 1.0
    assert elder.max_entry_dist_atr > 0
