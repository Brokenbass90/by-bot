import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.volume_exit import volume_fade_exit
from backtest.portfolio_engine import volume_exit_settings_from_env


def _row(ts, o, h, l, c, v):
    return [ts, o, h, l, c, v]


def _series(vols, prices=None):
    rows = []
    for i, v in enumerate(vols):
        p = (prices[i] if prices else 100 + i)
        rows.append(_row(i, p, p + 1, p - 1, p, v))
    return rows


def test_not_enough_bars():
    r = volume_fade_exit(_series([100, 100, 100]), side="long")
    assert r["exit"] is False and r["reason"] == "not_enough_bars"


def test_no_prior_impulse_blocks_exit():
    # flat chop, no real volume thrust -> must NOT exit (the key real-data fix)
    vols = [100] * 17 + [90, 80, 70, 60]
    prices = list(range(100, 117)) + [117, 117, 117, 117]
    r = volume_fade_exit(_series(vols, prices), side="long")
    assert r["exit"] is False
    assert r["reason"] == "no_prior_impulse"
    assert r["impulse_present"] is False


def test_volume_alive_no_exit():
    # real impulse but volume still high & price advancing -> hold
    vols = [100] * 15 + [300, 350, 400, 420, 450, 480]
    prices = list(range(100, 121))
    r = volume_fade_exit(_series(vols, prices), side="long")
    assert r["exit"] is False
    assert r["impulse_present"] is True
    assert r["reason"] in ("volume_alive", "volume_fading_but_price_advancing")


def test_baseline_fade_with_stall_exits_long():
    vols = [100] * 17 + [400, 60, 50, 40]   # clear impulse then collapse
    prices = list(range(100, 117)) + [117, 117, 117, 117]  # stall at top
    r = volume_fade_exit(_series(vols, prices), side="long", require_stall=True)
    assert r["exit"] is True
    assert r["impulse_present"] is True
    assert r["vol_ratio"] < 0.7
    assert r["stalled"] is True


def test_fading_but_advancing_blocks_when_stall_required():
    vols = [100] * 17 + [400, 60, 50, 40]
    prices = list(range(100, 121))  # new highs each bar
    r = volume_fade_exit(_series(vols, prices), side="long", require_stall=True)
    assert r["exit"] is False
    assert r["reason"] == "volume_fading_but_price_advancing"


def test_fading_advancing_exits_when_stall_not_required():
    vols = [100] * 17 + [400, 60, 50, 40]
    prices = list(range(100, 121))
    r = volume_fade_exit(_series(vols, prices), side="long", require_stall=False)
    assert r["exit"] is True


def test_short_side_stall_on_no_new_low():
    vols = [100] * 17 + [400, 60, 50, 40]
    prices = list(range(120, 103, -1)) + [103, 103, 103, 103]
    r = volume_fade_exit(_series(vols, prices), side="short", require_stall=True)
    assert r["exit"] is True
    assert r["stalled"] is True


def test_peak_fade_triggers():
    vols = [100] * 17 + [400, 60, 55, 50]
    prices = list(range(100, 117)) + [117, 117, 117, 117]
    r = volume_fade_exit(_series(vols, prices), side="long", fade_ratio=0.0,
                         peak_fade_ratio=0.45, require_stall=True)
    assert r["exit"] is True
    assert "peak" in r["reason"]


def test_impulse_gate_tunable():
    # peak only 1.5x baseline; default min_impulse_mult=2.0 blocks, lower allows
    vols = [100] * 17 + [150, 40, 35, 30]
    prices = list(range(100, 117)) + [117, 117, 117, 117]
    assert volume_fade_exit(_series(vols, prices), side="long")["reason"] == "no_prior_impulse"
    r = volume_fade_exit(_series(vols, prices), side="long", min_impulse_mult=1.3)
    assert r["exit"] is True


def test_zero_volume_safe():
    rows = [_row(i, 100, 101, 99, 100, 0) for i in range(20)]
    r = volume_fade_exit(rows, side="long")
    assert r["exit"] is False


def test_bad_side():
    r = volume_fade_exit(_series([100] * 20), side="sideways")
    assert r["exit"] is False and r["reason"] == "bad_side"


def test_portfolio_volume_exit_settings_resolve_once(monkeypatch):
    monkeypatch.setenv("VOLUME_EXIT_ENABLE", "1")
    monkeypatch.setenv("VOLUME_EXIT_STRATEGIES", "alt_trendline_touch_v1")
    monkeypatch.setenv("VOLUME_EXIT_BASELINE_WINDOW", "24")
    monkeypatch.setenv("VOLUME_EXIT_IMPULSE_WINDOW", "4")
    monkeypatch.setenv("VOLUME_EXIT_REQUIRE_BE_ARMED", "1")

    settings = volume_exit_settings_from_env()

    assert settings["enable"] is True
    assert settings["strategies"] == {"alt_trendline_touch_v1"}
    assert settings["baseline_window"] == 24
    assert settings["impulse_window"] == 4
    assert settings["require_be_armed"] is True
    assert settings["bars"] == 34
