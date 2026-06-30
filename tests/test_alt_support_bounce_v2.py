import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategies.alt_support_bounce_v2 import AltSupportBounceV2Config, AltSupportBounceV2Strategy


def _row(i, o, h, l, c, v=100.0):
    return [i * 3_600_000, o, h, l, c, v]


class _Store:
    symbol = "TESTUSDT"
    def __init__(self, rows):
        self.rows = rows
    def fetch_klines(self, symbol, interval, limit):
        assert symbol == self.symbol
        return self.rows[-limit:]


def _cfg(**kw):
    base = dict(lookback=40, atr_period=14, pivot_left=1, pivot_right=1,
                min_touches=2, level_tol_atr=0.6, max_entry_dist_atr=1.2,
                require_close_up=True, min_lower_wick_frac=0.15,
                vol_avg_period=10, vol_mult=1.2, flat_slope_atr=0.05,
                sl_atr_mult=0.6, tp1_rr=1.0, tp2_rr=2.0, min_rr=0.8,
                cooldown_bars=0, config_refresh_bars=9999)
    base.update(kw)
    return AltSupportBounceV2Config(**base)


def _flat_channel(n=40, lo=100.0, hi=108.0, vol=100.0):
    """Zigzag between a ~lo support and ~hi resistance => flat regime, repeated touches."""
    rows = []
    for i in range(n):
        if i % 2 == 0:  # touch support
            rows.append(_row(i, lo + 2, lo + 3, lo, lo + 1, vol))
        else:           # touch resistance
            rows.append(_row(i, hi - 3, hi, hi - 2, hi - 1, vol))
    return rows


def test_bounce_long_signal_fires():
    rows = _flat_channel()
    strat = AltSupportBounceV2Strategy(_cfg())
    s = _Store(rows)
    # warm-up call establishes the closed-bar baseline
    assert strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0) is None
    # append trigger bar: tags support ~100, closes up with lower wick, high volume
    trig = _row(len(rows), 101.0, 104.5, 99.8, 104.0, 600.0)
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "long"
    assert sig.sl < sig.entry < sig.tp
    assert "asb2_bounce" in sig.reason


def test_no_signal_without_volume():
    rows = _flat_channel()
    strat = AltSupportBounceV2Strategy(_cfg())
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 101.0, 104.5, 99.8, 104.0, 100.0)  # weak volume
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    assert sig is None
    assert strat.last_no_signal_reason == "weak_volume"


def test_no_signal_when_not_tagging_support():
    rows = _flat_channel()
    strat = AltSupportBounceV2Strategy(_cfg())
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 106.0, 107.0, 105.5, 106.5, 600.0)  # up near resistance, not support
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    assert sig is None
    assert strat.last_no_signal_reason in ("not_tagging_support", "entry_too_far", "no_support")


def test_descending_regime_can_be_disabled():
    # build a descending channel; with allow_descending False -> blocked
    rows = []
    for i in range(40):
        mid = 200 - i * 1.5
        if i % 2 == 0:
            rows.append(_row(i, mid + 2, mid + 3, mid, mid + 1, 100))
        else:
            rows.append(_row(i, mid + 5, mid + 8, mid + 4, mid + 7, 100))
    strat = AltSupportBounceV2Strategy(_cfg(allow_descending=False))
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    last_mid = 200 - 40 * 1.5
    trig = _row(40, last_mid + 1, last_mid + 4, last_mid - 0.2, last_mid + 3.5, 600)
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    assert sig is None
    assert "regime_blocked" in strat.last_no_signal_reason


def test_adaptive_mode_runs_and_fires():
    rows = _flat_channel()
    strat = AltSupportBounceV2Strategy(_cfg(adaptive=True))
    s = _Store(rows)
    assert strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0) is None  # warm-up
    trig = _row(len(rows), 101.0, 104.5, 99.8, 104.0, 600.0)
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    # adaptive flat-regime tightens params but fresh support exists -> should fire
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "long"


def test_max_age_config_accepted_and_runs():
    # freshness logic itself is unit-tested in market_context; here just ensure the
    # strategy accepts max_age_bars and still fires on a fresh, in-range support.
    rows = _flat_channel()
    strat = AltSupportBounceV2Strategy(_cfg(max_age_bars=5))
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 101.0, 104.5, 99.8, 104.0, 600.0)  # fresh support tag
    s.rows = rows + [trig]
    sig = strat.maybe_signal(s, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])
    assert sig is not None, strat.last_no_signal_reason
