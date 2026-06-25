"""Контракт closed-bar для v3-семейства (breakdown_retest_v3).

Live-parity страховка (CLAUDE_AUDIT_2026_06_22 §3): решение стратегии должно
зависеть ТОЛЬКО от закрытой истории + переданного решающего бара. Если в ленту
store попадает ещё не закрытый (формирующийся) бар ПОСЛЕ решающего, корректный
контракт обязан его отрезать (_closed_rows_before по signal_ts) и выдать ИДЕНТИЧНЫЙ
сигнал. Если кто-то сломает обрезку — этот тест упадёт ещё до live-подключения.

Переиспользует сценарий из test_breakdown_retest_v3 (слом поддержки + ретест).
"""
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
    rows, i, prev = _oscillation()
    for c in [99, 98, 97, 96, 96, 96, 96, 96]:
        rows.append(_row(i, prev, prev + 0.4, c - 0.4, c))
        prev = c
        i += 1
    return rows


def _entry_history():
    return [_row(70 + i, 99.0, 99.2, 98.8, 99.0) for i in range(40)]


def _cfg():
    return BreakdownRetestV3Config(
        min_touches=2, cooldown_bars=0, retest_band_atr=1.5, touch_into_atr=0.6,
        max_pierce_atr=1.0, reject_frac=0.3, atr_period=14, retest_vol_max_mult=0.0)


def _retest_bar(i=110):
    return _row(i, 99.4, 99.5, 98.7, 99.0)


def test_forming_bar_in_feed_does_not_change_decision():
    decision = _retest_bar(110)

    # baseline: чистая закрытая лента, сигнал есть
    s1 = BreakdownRetestV3Strategy(_cfg())
    sig1 = _call(s1, _Store(_structure_broken(), _entry_history() + [decision]), decision)
    assert sig1 is not None and sig1.side == "short"

    # та же лента + дикий ФОРМИРУЮЩИЙСЯ бар с ts ПОСЛЕ решающего:
    # корректный closed-bar контракт обязан его отрезать -> сигнал идентичен
    forming = _row(111, 99.0, 145.0, 55.0, 138.0)
    s2 = BreakdownRetestV3Strategy(_cfg())
    sig2 = _call(s2, _Store(_structure_broken(), _entry_history() + [decision] + [forming]), decision)
    assert sig2 is not None, "forming bar must not suppress a valid signal"
    assert sig2.side == sig1.side
    assert abs(sig2.entry - sig1.entry) < 1e-9, "entry must not be affected by a forming bar"
    assert abs(sig2.sl - sig1.sl) < 1e-9, "stop must not be affected by a forming bar"
    assert abs(sig2.tp - sig1.tp) < 1e-9, "target must not be affected by a forming bar"
