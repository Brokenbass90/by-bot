"""Tests for spike_fade_v3 — fade pumps into resistance / reclaim dumps at support."""
from pathlib import Path

from strategies.spike_fade_v3 import SpikeFadeV3Config, SpikeFadeV3Strategy


def _row(i, o, h, l, c, v=100):
    return [str(i * 3_600_000), str(o), str(h), str(l), str(c), str(v)]


def _call(strategy, store, row):
    signal_ts = int(float(row[0])) + int(strategy.cfg.entry_tf) * 60_000
    return strategy.maybe_signal(store, signal_ts,
                                 float(row[1]), float(row[2]), float(row[3]),
                                 float(row[4]), float(row[5]))


class _Store:
    symbol = "TESTUSDT"

    def __init__(self, structure_rows, entry_rows):
        self._s, self._e = structure_rows, entry_rows

    def fetch_klines(self, symbol, interval, limit):
        rows = self._s if str(interval) == "60" else self._e
        return rows[-limit:]


def _structure():
    """Levels: support ~99.4, resistance ~110.6 (atr ~1.77)."""
    rows, i, prev = [], 0, 105.0
    for wp in [105, 110, 104, 100, 106, 110, 103, 100, 107, 110, 102, 100, 106]:
        for _ in range(5):
            o, c = prev, wp
            rows.append(_row(i, o, max(o, c) + 0.6, min(o, c) - 0.6, c))
            prev = c
            i += 1
    return rows


def _flat(n, px, start=70):
    return [_row(start + i, px, px + 0.3, px - 0.2, px) for i in range(n)]


def _row_ms(ts_ms, o, h, l, c, v=100):
    return [str(ts_ms), str(o), str(h), str(l), str(c), str(v)]


def _cfg(**kw):
    base = dict(min_touches=2, cooldown_bars=0, spike_lookback=6, spike_min_pct=3.0,
                tag_level_atr=0.7, pierce_atr=0.9, reject_frac=0.5, atr_period=14,
                vol_spike_mult=0.0)
    base.update(kw)
    return SpikeFadeV3Config(**base)


def test_pump_into_resistance_is_faded_short():
    # run-up in history, then a rejection bar tagging resistance 110.6 and closing back down
    hist = _flat(34, 104.0) + [
        _row(104, 104, 105.5, 104.0, 105.0), _row(105, 105, 107.0, 104.8, 106.5),
        _row(106, 106.5, 108.5, 106.0, 108.0), _row(107, 108, 110.0, 107.5, 109.5),
        _row(108, 109.5, 110.2, 109.0, 110.0),
    ]
    spike = _row(109, 110.0, 110.5, 108.0, 108.3)  # tags 110.6, closes low -> rejection
    sig = _call(SpikeFadeV3Strategy(_cfg()), _Store(_structure(), hist + [spike]), spike)
    assert sig is not None, "should fade the pump into resistance"
    assert sig.side == "short"
    assert sig.sl > 110.5            # stop above the spike high / level
    assert sig.tp < sig.entry < sig.sl


def test_dump_into_support_is_reclaimed_long():
    hist = _flat(34, 106.0) + [
        _row(104, 106, 106.2, 104.5, 105.0), _row(105, 105, 105.2, 103.5, 104.0),
        _row(106, 104, 104.2, 102.0, 102.5), _row(107, 102.5, 102.7, 100.5, 101.0),
        _row(108, 101, 101.2, 99.8, 100.0),
    ]
    spike = _row(109, 100.0, 101.5, 99.5, 101.2)  # flush to support 99.4, closes back up
    sig = _call(SpikeFadeV3Strategy(_cfg()), _Store(_structure(), hist + [spike]), spike)
    assert sig is not None, "should reclaim the dump at support"
    assert sig.side == "long"
    assert sig.sl < 99.5
    assert sig.sl < sig.entry < sig.tp


def test_no_fade_when_spike_hits_open_space_not_a_level():
    hist = _flat(38, 102.0)
    spike = _row(109, 102.0, 108.0, 101.8, 105.0)  # big move but high 108 tags no level
    s = SpikeFadeV3Strategy(_cfg())
    sig = _call(s, _Store(_structure(), hist + [spike]), spike)
    assert sig is None
    assert s.last_no_signal_reason == "no_spike_fade_setup"


def test_no_fade_without_rejection_close():
    hist = _flat(34, 104.0) + [
        _row(104, 104, 105.5, 104.0, 105.0), _row(105, 105, 107.0, 104.8, 106.5),
        _row(106, 106.5, 108.5, 106.0, 108.0), _row(107, 108, 110.0, 107.5, 109.5),
        _row(108, 109.5, 110.2, 109.0, 110.0),
    ]
    no_rej = _row(109, 110.0, 110.5, 109.8, 110.3)  # closes near the high -> no exhaustion
    s = SpikeFadeV3Strategy(_cfg())
    sig = _call(s, _Store(_structure(), hist + [no_rej]), no_rej)
    assert sig is None
    assert s.last_no_signal_reason == "no_spike_fade_setup"


def test_no_fade_when_move_too_small():
    hist = _flat(40, 109.0)  # already near resistance, no real pump
    small = _row(109, 109.0, 110.5, 108.8, 108.9)
    s = SpikeFadeV3Strategy(_cfg(spike_min_pct=4.0))
    sig = _call(s, _Store(_structure(), hist + [small]), small)
    assert sig is None
    assert s.last_no_signal_reason == "no_spike_fade_setup"


def test_forming_entry_bar_after_trigger_is_ignored():
    hist = _flat(34, 104.0) + [
        _row(104, 104, 105.5, 104.0, 105.0), _row(105, 105, 107.0, 104.8, 106.5),
        _row(106, 106.5, 108.5, 106.0, 108.0), _row(107, 108, 110.0, 107.5, 109.5),
        _row(108, 109.5, 110.2, 109.0, 110.0),
    ]
    spike = _row(109, 110.0, 110.5, 108.0, 108.3)
    forming_start = int(float(spike[0])) + int(SpikeFadeV3Config().entry_tf) * 60_000
    forming = _row_ms(forming_start, 120.0, 125.0, 119.0, 124.0, 10_000)

    sig = _call(SpikeFadeV3Strategy(_cfg()), _Store(_structure(), hist + [spike, forming]), spike)

    assert sig is not None
    assert sig.entry == float(spike[4])


def test_run_portfolio_supports_spike_fade_v3():
    source = (Path(__file__).resolve().parents[1] / "backtest" / "run_portfolio.py").read_text(encoding="utf-8")

    assert 'SpikeFadeV3Strategy = _import_strategy_class("spike_fade_v3", "SpikeFadeV3Strategy")' in source
    assert '"spike_fade_v3"' in source
    assert 'spike_fade_v3[sym].maybe_signal' in source
