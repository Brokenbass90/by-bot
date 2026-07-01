import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategies.inplay_retest_v4 import InplayRetestV4Config, InplayRetestV4Strategy


def _row(i, o, h, l, c, v=100.0):
    return [i * 3_600_000, o, h, l, c, v]


class _Store:
    symbol = "TESTUSDT"
    def __init__(self, rows): self.rows = rows
    def fetch_klines(self, symbol, interval, limit):
        assert symbol == self.symbol
        return self.rows[-limit:]


def _cfg(**kw):
    base = dict(lookback=40, atr_period=14, pivot_left=1, pivot_right=1, min_touches=2,
                tol_atr=0.5, entry_band_atr=0.6, max_age_bars=60, min_wick_frac=0.15,
                vol_avg_period=10, vol_mult=1.2, sl_atr_buffer=0.5, tp_rr=2.5, tp1_rr=1.5,
                min_stop_pct=0.0005, cooldown_bars=0, config_refresh_bars=9999,
                enable_setup_b=False)
    base.update(kw); return InplayRetestV4Config(**base)


def _flat(n=40, lo=100.0, hi=110.0):
    rows = []
    for i in range(n):
        if i % 2 == 0:
            rows.append(_row(i, lo + 2, lo + 3, lo, lo + 1))
        else:
            rows.append(_row(i, hi - 3, hi, hi - 2, hi - 1))
    return rows


def _fire(strat, s, trig):
    s.rows = s.rows + [trig]
    return strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])


def test_long_retest_off_support_asymmetric_rr():
    s = _Store(_flat()); strat = InplayRetestV4Strategy(_cfg())
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)  # at support, reject up, vol
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "long" and sig.sl < sig.entry < sig.tp
    # asymmetric R:R: reward (tp-entry) ~2.5x risk (entry-sl)
    rr = (sig.tp - sig.entry) / (sig.entry - sig.sl)
    assert rr > 2.0


def test_short_retest_off_resistance():
    s = _Store(_flat()); strat = InplayRetestV4Strategy(_cfg())
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 109.8, 110.1, 109.0, 109.2, 600.0)  # at resistance, reject down
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "short" and sig.tp < sig.entry < sig.sl


def test_no_entry_when_far_from_level():
    s = _Store(_flat()); strat = InplayRetestV4Strategy(_cfg(entry_band_atr=0.2))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 105.0, 105.5, 104.5, 105.0, 600.0)  # mid, far in tight band
    sig = _fire(strat, s, trig)
    assert sig is None and strat.last_no_signal_reason == "no_setup"


def test_no_entry_without_volume():
    s = _Store(_flat()); strat = InplayRetestV4Strategy(_cfg())
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 100.0)  # weak volume
    sig = _fire(strat, s, trig)
    assert sig is None


def test_adaptive_runs():
    s = _Store(_flat()); strat = InplayRetestV4Strategy(_cfg(adaptive=True))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is None or sig.side in ("long", "short")


def test_retest_quality_gate_can_pass():
    s = _Store(_flat())
    strat = InplayRetestV4Strategy(_cfg(use_retest_quality=True, retest_min_quality=0.10))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert "quality=" in sig.reason


def test_retest_quality_gate_can_block():
    s = _Store(_flat())
    strat = InplayRetestV4Strategy(_cfg(use_retest_quality=True, retest_min_quality=1.01))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is None
    assert strat.last_no_signal_reason.startswith("quality=")


def test_range_gate_can_be_enabled_without_crash():
    s = _Store(_flat(n=80))
    strat = InplayRetestV4Strategy(_cfg(use_range_filter=True, range_require_all=False))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(80, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is None or sig.side in ("long", "short")


def test_level_entry_builds_limit_order_at_level():
    s = _Store(_flat())
    strat = InplayRetestV4Strategy(_cfg(use_level_entry=True, level_entry_validity_bars=3))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "long"
    assert getattr(sig, "entry_order_type") == "limit"
    assert getattr(sig, "limit_validity_bars") == 3
    assert getattr(sig, "entry_plan_reason") == "limit_at_level"
    assert sig.entry < trig[4]  # limit at/near the level, not late bar-close chase


def test_level_entry_blocks_late_chase():
    s = _Store(_flat())
    strat = InplayRetestV4Strategy(_cfg(use_level_entry=True, level_entry_max_chase_atr=0.01))
    strat.maybe_signal(s, s.rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(40, 100.2, 101.0, 99.9, 100.8, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is None
    assert strat.last_no_signal_reason.startswith("level_entry:would_chase")
