import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategies.alt_channel_bounce_v1 import AltChannelBounceV1Config, AltChannelBounceV1Strategy


def _row(i, o, h, l, c, v=100.0):
    return [i * 3_600_000, o, h, l, c, v]


class _Store:
    symbol = "TESTUSDT"
    def __init__(self, rows): self.rows = rows
    def fetch_klines(self, symbol, interval, limit):
        assert symbol == self.symbol
        return self.rows[-limit:]


def _cfg(**kw):
    base = dict(lookback=40, atr_period=14, pivot_left=1, pivot_right=1,
                edge_pos=0.3, min_width_atr=0.5, vol_avg_period=10, vol_mult=1.2,
                min_lower_wick_frac=0.15, min_upper_wick_frac=0.15,
                flat_slope_atr=0.06, sl_atr_mult=0.6, target_frac=0.85,
                min_rr=0.8, cooldown_bars=0, config_refresh_bars=9999)
    base.update(kw)
    return AltChannelBounceV1Config(**base)


def _flat(n=40, lo=100.0, hi=110.0, vol=100.0):
    rows = []
    for i in range(n):
        if i % 2 == 0:
            rows.append(_row(i, lo + 2, lo + 3, lo, lo + 1, vol))
        else:
            rows.append(_row(i, hi - 3, hi, hi - 2, hi - 1, vol))
    return rows


def _fire(strat, store, trig):
    store.rows = store.rows + [trig]
    return strat.maybe_signal(store, trig[0], trig[1], trig[2], trig[3], trig[4], trig[5])


def test_long_off_lower_edge():
    rows = _flat()
    strat = AltChannelBounceV1Strategy(_cfg())
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)  # warm up
    trig = _row(len(rows), 100.2, 101.2, 99.8, 101.0, 600.0)  # at lower edge, reject up
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "long"
    assert sig.sl < sig.entry < sig.tp


def test_short_off_upper_edge():
    rows = _flat()
    strat = AltChannelBounceV1Strategy(_cfg())
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 109.8, 110.2, 108.8, 109.0, 600.0)  # at upper edge, reject down
    sig = _fire(strat, s, trig)
    assert sig is not None, strat.last_no_signal_reason
    assert sig.side == "short"
    assert sig.tp < sig.entry < sig.sl


def test_middle_no_signal():
    rows = _flat()
    strat = AltChannelBounceV1Strategy(_cfg())
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 104.8, 105.5, 104.5, 105.0, 600.0)  # mid channel
    sig = _fire(strat, s, trig)
    assert sig is None
    assert "not_at_edge" in strat.last_no_signal_reason


def test_long_disabled():
    rows = _flat()
    strat = AltChannelBounceV1Strategy(_cfg(allow_long=False))
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)
    trig = _row(len(rows), 100.2, 101.2, 99.8, 101.0, 600.0)
    sig = _fire(strat, s, trig)
    assert sig is None  # long suppressed; lower edge but allow_long False -> not_at_edge/None


def test_adaptive_mode_runs():
    rows = _flat()
    strat = AltChannelBounceV1Strategy(_cfg(adaptive=True))
    s = _Store(rows)
    strat.maybe_signal(s, rows[-1][0], 0, 0, 0, 0, 0)  # warm-up, must not crash
    trig = _row(len(rows), 100.2, 101.2, 99.8, 101.0, 600.0)
    sig = _fire(strat, s, trig)
    # adaptive path runs; flat regime -> long off lower edge expected
    assert sig is None or sig.side == "long"
