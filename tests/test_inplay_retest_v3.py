"""Tests for inplay_retest_v3 — the owner's retest-at-a-real-level approach.

We prove the logic that was WRONG in IVB1 is right here:
  - enters ON the retest-hold of a real (multi-touch) level, not after a reclaim;
  - stop is tight, just beyond the level;
  - tp1 sits before the next opposing level; runner beyond;
  - no level / no hold -> no trade.
"""
from strategies.inplay_retest_v3 import InplayRetestV3Config, InplayRetestV3Strategy


def _row(i, o, h, l, c, v):
    return [str(i * 3_600_000), str(o), str(h), str(l), str(c), str(v)]


class _Store:
    """Synthetic feed. structure_rows build real levels (repeated touches at
    100 support and 110 resistance); entry_rows end on the chosen trigger bar."""
    symbol = "TESTUSDT"

    def __init__(self, structure_rows, entry_rows):
        self._s = structure_rows
        self._e = entry_rows

    def fetch_klines(self, symbol, interval, limit):
        rows = self._s if str(interval) == "60" else self._e
        return rows[-limit:]


def _structure_with_levels():
    """~70 1h bars that repeatedly touch support=100 and resistance=110."""
    rows = []
    i = 0
    # oscillate between 100 (support) and 110 (resistance) several times -> >=2 touches each
    waypoints = [105, 110, 104, 100, 106, 110, 103, 100, 107, 110, 102, 100, 106]
    prev = 105.0
    for wp in waypoints:
        for _ in range(5):
            o = prev
            c = wp
            h = max(o, c) + 0.6
            l = min(o, c) - 0.6
            rows.append(_row(i, o, h, l, c, 100))
            prev = c
            i += 1
    return rows


def _cfg(**kw):
    base = dict(vol_mult=0.0, cooldown_bars=0, min_touches=2, retest_band_atr=1.5,
                touch_into_atr=0.8, max_pierce_atr=1.2, reject_frac=0.3,
                atr_period=14, use_sloped=False, channel_min_r2=2.0)
    base.update(kw)
    return InplayRetestV3Config(**base)


# detected levels in the fixture: support ~99.4, resistance ~110.6 (structure ATR ~1.77)
def _long_retest_bar(i, vol=100):
    # dips into the 99.4 support and closes back above it (held) — a real retest
    return _row(i, 100.1, 100.2, 99.45, 99.95, vol)


def _short_retest_bar(i, vol=100):
    # pokes up into the 110.6 resistance and closes back below it (rejected)
    return _row(i, 110.0, 110.55, 109.9, 110.1, vol)


def test_long_on_support_retest_hold():
    structure = _structure_with_levels()
    entry = [_row(i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]  # hovering above support
    entry.append(_long_retest_bar(40))
    sig = InplayRetestV3Strategy(_cfg()).maybe_signal(_Store(structure, entry), 1, 0, 0, 0, 0, 0)
    assert sig is not None, "should fire on a clean support retest-hold"
    assert sig.side == "long"
    # tight stop just BELOW the support level (not a far floating stop)
    assert sig.sl < 99.4
    assert sig.entry - sig.sl < 2.0  # tight relative to structure ATR (~1.77)
    # tp1 before the next opposing level, runner beyond, ladder valid
    assert sig.entry < sig.tps[0]
    assert sig.tps[1] >= sig.tps[0]
    assert sig.sl < sig.entry < sig.tp


def test_short_on_resistance_retest_hold():
    structure = _structure_with_levels()
    entry = [_row(i, 109.5, 109.7, 109.3, 109.5, 100) for i in range(40)]  # hovering below resistance
    entry.append(_short_retest_bar(40))
    sig = InplayRetestV3Strategy(_cfg()).maybe_signal(_Store(structure, entry), 1, 0, 0, 0, 0, 0)
    assert sig is not None, "should fire on a clean resistance retest-hold"
    assert sig.side == "short"
    assert sig.sl > 110.6
    assert sig.sl - sig.entry < 2.0
    assert sig.tp < sig.entry < sig.sl


def test_no_trade_when_price_far_from_any_level():
    structure = _structure_with_levels()
    # parked at 107, in the gap between 104.5 and 110.6 — the bar reaches no level
    entry = [_row(i, 107.0, 107.3, 106.7, 107.0, 100) for i in range(41)]
    s = InplayRetestV3Strategy(_cfg())
    sig = s.maybe_signal(_Store(structure, entry), 1, 0, 0, 0, 0, 0)
    assert sig is None
    assert s.last_no_signal_reason in {"no_retest_hold", "no_levels"}


def test_no_long_when_support_breaks_instead_of_holds():
    structure = _structure_with_levels()
    # bar slices clean through 99.4 and closes well below -> support did NOT hold
    entry = [_row(i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    entry.append(_row(40, 100.0, 100.1, 97.5, 97.8, 100))
    s = InplayRetestV3Strategy(_cfg(allow_short=False))  # isolate the long-hold failure
    sig = s.maybe_signal(_Store(structure, entry), 1, 0, 0, 0, 0, 0)
    assert sig is None
    assert s.last_no_signal_reason == "no_retest_hold"


def test_volume_filter_blocks_when_enabled_and_thin():
    structure = _structure_with_levels()
    entry = [_row(i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    entry.append(_long_retest_bar(40, vol=10))  # thin volume on the trigger bar
    s = InplayRetestV3Strategy(_cfg(vol_mult=1.5))
    sig = s.maybe_signal(_Store(structure, entry), 1, 0, 0, 0, 0, 0)
    assert sig is None
    assert s.last_no_signal_reason == "no_volume"
