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


def _call(strategy, store, row):
    # Bybit kline timestamps mark bar OPEN. Evaluate only after the configured
    # entry timeframe has fully closed.
    signal_ts = int(float(row[0])) + int(strategy.cfg.entry_tf) * 60_000
    return strategy.maybe_signal(
        store,
        signal_ts,
        float(row[1]),
        float(row[2]),
        float(row[3]),
        float(row[4]),
        float(row[5]),
    )


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


def _structure_with_levels(start_i=0):
    """~70 1h bars that repeatedly touch support=100 and resistance=110."""
    rows = []
    i = int(start_i)
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


def _structure_without_levels(start_i=0, n=48):
    """Enough closed history for ATR, but no repeated pivot cluster."""
    rows = []
    prev = 92.0
    for j in range(n):
        i = int(start_i) + j
        c = prev + 0.08
        rows.append(_row(i, prev, c + 0.20, prev - 0.20, c, 100))
        prev = c
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
    return _row(i, 99.7, 100.2, 99.3, 99.58, vol)


def _short_retest_bar(i, vol=100):
    # pokes up into the 110.6 resistance and closes back below it (rejected)
    return _row(i, 110.3, 110.7, 109.8, 110.42, vol)


def test_long_on_support_retest_hold():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]  # hovering above support
    trigger = _long_retest_bar(110)
    entry.append(trigger)
    sig = _call(InplayRetestV3Strategy(_cfg()), _Store(structure, entry), trigger)
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
    entry = [_row(70 + i, 109.5, 109.7, 109.3, 109.5, 100) for i in range(40)]  # hovering below resistance
    trigger = _short_retest_bar(110)
    entry.append(trigger)
    sig = _call(InplayRetestV3Strategy(_cfg()), _Store(structure, entry), trigger)
    assert sig is not None, "should fire on a clean resistance retest-hold"
    assert sig.side == "short"
    assert sig.sl > 110.6
    assert sig.sl - sig.entry < 2.0
    assert sig.tp < sig.entry < sig.sl


def test_no_trade_when_price_far_from_any_level():
    structure = _structure_with_levels()
    # parked at 107, in the gap between 104.5 and 110.6 — the bar reaches no level
    entry = [_row(70 + i, 107.0, 107.3, 106.7, 107.0, 100) for i in range(40)]
    trigger = _row(110, 107.0, 107.3, 106.7, 107.0, 100)
    entry.append(trigger)
    s = InplayRetestV3Strategy(_cfg())
    sig = _call(s, _Store(structure, entry), trigger)
    assert sig is None
    assert s.last_no_signal_reason in {"no_retest_hold", "no_levels"}


def test_no_long_when_support_breaks_instead_of_holds():
    structure = _structure_with_levels()
    # bar slices clean through 99.4 and closes well below -> support did NOT hold
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    trigger = _row(110, 100.0, 100.1, 97.5, 97.8, 100)
    entry.append(trigger)
    s = InplayRetestV3Strategy(_cfg(allow_short=False))  # isolate the long-hold failure
    sig = _call(s, _Store(structure, entry), trigger)
    assert sig is None
    assert s.last_no_signal_reason == "no_retest_hold"


def test_volume_filter_blocks_when_enabled_and_thin():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    trigger = _long_retest_bar(110, vol=10)  # thin volume on the trigger bar
    entry.append(trigger)
    s = InplayRetestV3Strategy(_cfg(vol_mult=1.5))
    sig = _call(s, _Store(structure, entry), trigger)
    assert sig is None
    assert s.last_no_signal_reason == "no_volume"


def test_levels_ignore_current_and_future_bars():
    history_without_levels = _structure_without_levels(start_i=0, n=48)
    future_levels_after_signal = _structure_with_levels(start_i=120)
    structure = history_without_levels + future_levels_after_signal
    entry = [_row(49 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(20)]
    trigger = _long_retest_bar(70)
    entry.append(trigger)

    s = InplayRetestV3Strategy(_cfg())
    sig = _call(s, _Store(structure, entry), trigger)

    assert sig is None
    assert s.last_no_signal_reason in {"no_levels", "no_retest_hold"}


def test_rr_guard_blocks_when_next_level_is_too_close():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    trigger = _long_retest_bar(110)
    entry.append(trigger)

    s = InplayRetestV3Strategy(_cfg(min_rr_tp1=20.0))
    sig = _call(s, _Store(structure, entry), trigger)

    assert sig is None
    assert s.last_no_signal_reason.startswith("tp1_rr_too_low_")


def test_stop_width_guards_block_bad_risk_geometry():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    trigger = _long_retest_bar(110)
    entry.append(trigger)

    too_tight = InplayRetestV3Strategy(_cfg(min_stop_pct=0.05))
    assert _call(too_tight, _Store(structure, entry), trigger) is None
    assert too_tight.last_no_signal_reason.startswith("stop_too_tight_")

    too_wide = InplayRetestV3Strategy(_cfg(max_stop_pct=0.005))
    assert _call(too_wide, _Store(structure, entry), trigger) is None
    assert too_wide.last_no_signal_reason.startswith("stop_too_wide_")


def test_entry_distance_cap_rejects_far_from_level_chase():
    # bar dips to touch support 99.4 but CLOSES far above it (a chase) -> rejected.
    # This is the guard against the net=-100/wide-stop blow-up: entry must be AT
    # the level so the stop is genuinely tight.
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    far_bar = _row(110, 99.5, 102.1, 99.45, 102.0, 100)  # touched 99.4, closed way up at 102.0
    entry.append(far_bar)
    s = InplayRetestV3Strategy(_cfg(retest_band_atr=10.0))  # isolate the stricter distance cap
    sig = _call(s, _Store(structure, entry), far_bar)
    assert sig is None
    assert s.last_no_signal_reason == "entry_too_far_from_level"


def test_forming_entry_bar_is_ignored():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    trigger = _long_retest_bar(110)
    forming = _row(111, 120.0, 125.0, 80.0, 90.0, 10_000)
    entry.extend([trigger, forming])

    sig = _call(InplayRetestV3Strategy(_cfg()), _Store(structure, entry), trigger)

    assert sig is not None
    assert sig.entry == float(trigger[4])


def test_cooldown_is_tied_to_entry_bar_time():
    structure = _structure_with_levels()
    entry = [_row(70 + i, 100.4, 100.6, 100.2, 100.4, 100) for i in range(40)]
    first = _long_retest_bar(110)
    entry.append(first)
    strategy = InplayRetestV3Strategy(_cfg(cooldown_bars=5))
    assert _call(strategy, _Store(structure, entry), first) is not None

    second = _long_retest_bar(111)
    entry.append(second)
    assert _call(strategy, _Store(structure, entry), second) is None
    assert strategy.last_no_signal_reason == "cooldown"
