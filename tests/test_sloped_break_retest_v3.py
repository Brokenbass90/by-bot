from __future__ import annotations

from strategies.sloped_break_retest_v2 import SlopedBreakRetestV2Config, SlopedBreakRetestV2Strategy
from strategies.sloped_break_retest_v3 import SlopedBreakRetestV3Strategy


def _row(idx: int, o: float, h: float, l: float, c: float, v: float = 100.0) -> list:
    return [str(idx * 14_400_000), str(o), str(h), str(l), str(c), str(v), "0"]


def _pending() -> dict:
    return {
        "side": "long",
        "line_level": 100.0,
        "slope_per_4h_bar": 0.0,
        "atr": 1.0,
        "visible_ts": 0,
        "created_trigger_ts": 0,
        "age": 0,
        "touched": False,
        "pivot_count": 3,
        "slope_pct_day": 1.0,
    }


def test_v3_records_touch_that_v2_rejects_without_same_bar_hold() -> None:
    cfg = SlopedBreakRetestV2Config(structure_lookback=2)
    v2 = SlopedBreakRetestV2Strategy(cfg)
    v3 = SlopedBreakRetestV3Strategy(cfg)
    v2._pending = _pending()
    v3._pending = _pending()
    rows = [
        _row(1, 100.4, 100.8, 100.1, 100.5),
        _row(2, 100.5, 100.8, 100.1, 100.4),
        _row(3, 100.4, 100.7, 100.0, 100.3),
        _row(4, 100.3, 100.6, 100.0, 100.2),
        _row(5, 100.2, 100.4, 99.8, 99.9),
    ]

    assert v2._process_trigger("BTCUSDT", rows) is None
    assert v2._pending is not None and v2._pending["touched"] is False
    assert v3._process_trigger("BTCUSDT", rows) is None
    assert v3._pending is not None and v3._pending["touched"] is True
    assert v3._pending["reclaimed"] is False


def test_v3_requires_reclaim_bar_then_later_bos_bar() -> None:
    cfg = SlopedBreakRetestV2Config(structure_lookback=2)
    strategy = SlopedBreakRetestV3Strategy(cfg)
    strategy._pending = _pending()
    rows = [
        _row(1, 100.4, 100.8, 100.1, 100.5),
        _row(2, 100.5, 100.8, 100.1, 100.4),
        _row(3, 100.4, 100.7, 100.0, 100.3),
        _row(4, 100.3, 100.6, 100.0, 100.2),
        _row(5, 100.2, 100.4, 99.8, 99.9),
    ]
    assert strategy._process_trigger("BTCUSDT", rows) is None

    rows.append(_row(6, 99.9, 100.7, 99.9, 100.4))
    assert strategy._process_trigger("BTCUSDT", rows) is None
    assert strategy._pending is not None and strategy._pending["reclaimed"] is True

    rows.append(_row(7, 100.4, 101.2, 100.2, 101.0))
    signal = strategy._process_trigger("BTCUSDT", rows)

    assert signal is not None
    assert signal.strategy == "sloped_break_retest_v3"
    assert signal.side == "long"
    assert signal.entry == 101.0
    assert signal.sl < 99.8
