from strategies.alt_range_scalp_v1 import AltRangeScalpV1Config
from strategies.alt_range_scalp_v1 import _geometry_block_reason as ars1_geometry_block_reason
from strategies.alt_support_bounce_v1 import _geometry_block_reason as asb1_geometry_block_reason
from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Config, AltTrendlineTouchV1Strategy
from strategies.alt_trendline_touch_v1 import _geometry_block_reason as att1_geometry_block_reason


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
