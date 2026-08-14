from __future__ import annotations

from strategies.sloped_break_retest_v2 import (
    SlopedBreakRetestV2Config,
    SlopedBreakRetestV2Strategy,
    confirmed_pivots,
    identify_breakout,
)


def _row(idx: int, o: float, h: float, l: float, c: float, v: float = 100.0) -> list:
    return [str(idx * 14_400_000), str(o), str(h), str(l), str(c), str(v), "0"]


def test_confirmed_pivots_never_uses_unconfirmed_right_edge() -> None:
    values = [1, 2, 1, 2, 1, 5]

    pivots = confirmed_pivots(values, mode="high", left=1, right=1)

    assert pivots == [(1, 2), (3, 2)]


def test_identify_descending_resistance_break_from_confirmed_pivots() -> None:
    rows = []
    for idx in range(40):
        line = 113.0 - 0.3 * idx
        close = line - 2.0
        rows.append(_row(idx, close - 0.2, close + 0.4, close - 0.6, close))
    for idx, high in ((10, 110.0), (20, 107.0), (30, 104.0)):
        close = high - 1.0
        rows[idx] = _row(idx, close - 0.2, high, close - 0.8, close)
    rows[-2] = _row(38, 100.4, 101.8, 100.0, 101.4)
    rows[-1] = _row(39, 100.5, 102.8, 100.3, 102.5, 150.0)
    cfg = SlopedBreakRetestV2Config(
        breakout_volume_multiple=1.2,
        max_fit_error_atr=0.5,
        post_fit_break_tolerance_atr=0.2,
    )

    candidate = identify_breakout(rows, cfg)

    assert candidate is not None
    assert candidate["side"] == "long"
    assert candidate["pivot_count"] >= 3
    assert candidate["slope_per_4h_bar"] < 0


def test_retest_requires_a_later_structure_break() -> None:
    cfg = SlopedBreakRetestV2Config(structure_lookback=2)
    strategy = SlopedBreakRetestV2Strategy(cfg)
    strategy._pending = {
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
    rows = [
        _row(1, 100.5, 101.0, 100.2, 100.6),
        _row(2, 100.6, 100.9, 100.1, 100.4),
        _row(3, 100.4, 100.8, 100.1, 100.5),
        _row(4, 100.5, 100.9, 100.2, 100.6),
        _row(5, 100.4, 100.7, 99.9, 100.2),
    ]

    assert strategy._process_trigger("BTCUSDT", rows) is None
    assert strategy._pending is not None
    assert strategy._pending["touched"] is True

    rows.append(_row(6, 100.2, 101.4, 100.1, 101.2))
    signal = strategy._process_trigger("BTCUSDT", rows)

    assert signal is not None
    assert signal.side == "long"
    assert signal.entry == 101.2
    assert signal.sl < 99.9
    assert "4h_break_15m_retest_bos" in signal.reason


def test_environment_is_resolved_once(monkeypatch) -> None:
    monkeypatch.setenv("SLBR2_ALLOW_LONGS", "0")
    strategy = SlopedBreakRetestV2Strategy()
    monkeypatch.setenv("SLBR2_ALLOW_LONGS", "1")

    assert strategy.cfg.allow_longs is False
