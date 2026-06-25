"""Tests for breakdown_retest_v3 — short on a broken-support retest (range hedge)."""
from strategies.breakdown_retest_v3 import BreakdownRetestV3Config, BreakdownRetestV3Strategy


def _row(i, o, h, l, c, v=100):
    return [str(i * 3_600_000), str(o), str(h), str(l), str(c), str(v)]


def _call(strategy, store, row):
    return strategy.maybe_signal(store, int(float(row[0])),
                                 float(row[1]), float(row[2]), float(row[3]),
                                 float(row[4]), float(row[5]))


class _Store:
    symbol = "TESTUSDT"

    def __init__(self, structure_rows, entry_rows):
        self._s = structure_rows
        self._e = entry_rows

    def fetch_klines(self, symbol, interval, limit):
        rows = self._s if str(interval) == "60" else self._e
        return rows[-limit:]


def _oscillation(start_i=0):
    rows, i, prev = [], start_i, 105.0
    for wp in [105, 110, 104, 100, 106, 110, 103, 100, 107, 110, 102, 100, 106]:
        for _ in range(5):
            o, c = prev, wp
            rows.append(_row(i, o, max(o, c) + 0.6, min(o, c) - 0.6, c))
            prev = c
            i += 1
    return rows, i, prev


def _structure_broken():
    """Levels at support 99.4 / resistance 110.6, then price BREAKS 100 and stays below."""
    rows, i, prev = _oscillation()
    for c in [99, 98, 97, 96, 96, 96, 96, 96]:
        rows.append(_row(i, prev, prev + 0.4, c - 0.4, c))
        prev = c
        i += 1
    return rows


def _structure_not_broken():
    rows, _i, _p = _oscillation()
    return rows  # latest close ~106, support 99.4 intact


def _entry_history():
    return [_row(70 + i, 99.0, 99.2, 98.8, 99.0) for i in range(40)]


def _cfg(**kw):
    base = dict(min_touches=2, cooldown_bars=0, retest_band_atr=1.5, touch_into_atr=0.6,
                max_pierce_atr=1.0, reject_frac=0.3, atr_period=14, retest_vol_max_mult=0.0)
    base.update(kw)
    return BreakdownRetestV3Config(**base)


# retest bar: pokes up to broken support 99.4 and closes back below it (rejected)
def _retest_bar(i=110):
    return _row(i, 99.4, 99.5, 98.7, 99.0)


def test_short_on_broken_support_retest():
    entry = _entry_history() + [_retest_bar()]
    sig = _call(BreakdownRetestV3Strategy(_cfg()), _Store(_structure_broken(), entry), _retest_bar())
    assert sig is not None, "should short the retest of a broken support"
    assert sig.side == "short"
    assert sig.sl > 99.4              # tight stop just ABOVE the (now resistance) level
    assert sig.sl - sig.entry < 2.0
    assert sig.tp < sig.entry < sig.sl


def test_no_trade_when_support_not_broken():
    entry = _entry_history() + [_retest_bar()]
    s = BreakdownRetestV3Strategy(_cfg())
    sig = _call(s, _Store(_structure_not_broken(), entry), _retest_bar())
    assert sig is None
    assert s.last_no_signal_reason == "no_broken_support_near_price"


def test_no_trade_when_retest_reclaims_level():
    # bar pokes up and CLOSES back above the broken level -> reclaimed, not a short
    reclaim = _row(110, 99.0, 100.2, 98.9, 99.8)
    entry = _entry_history() + [reclaim]
    s = BreakdownRetestV3Strategy(_cfg())
    sig = _call(s, _Store(_structure_broken(), entry), reclaim)
    assert sig is None
    assert s.last_no_signal_reason == "no_breakdown_retest"


def test_entry_distance_cap_rejects_far_close():
    # touches the level but closes far below it -> wide stop -> rejected
    far = _row(110, 99.4, 99.5, 97.0, 97.2)
    entry = _entry_history() + [far]
    s = BreakdownRetestV3Strategy(_cfg())
    sig = _call(s, _Store(_structure_broken(), entry), far)
    assert sig is None
    assert s.last_no_signal_reason == "entry_too_far_from_level"


def test_weak_retest_volume_filter_blocks_high_volume():
    hot = _row(110, 99.4, 99.5, 98.7, 99.0, 999)  # high-volume retest
    entry = _entry_history() + [hot]
    s = BreakdownRetestV3Strategy(_cfg(retest_vol_max_mult=1.5))
    sig = _call(s, _Store(_structure_broken(), entry), hot)
    assert sig is None
    assert s.last_no_signal_reason == "retest_volume_too_high"
