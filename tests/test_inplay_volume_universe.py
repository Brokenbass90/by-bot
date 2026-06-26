from __future__ import annotations

from bot.inplay_volume_universe import score_inplay_volume


def _row(i: int, close: float, volume: float):
    return [i * 300_000, close, close * 1.001, close * 0.999, close, volume]


def test_score_inplay_volume_detects_relative_inflow():
    rows = [_row(i, 10.0, 10_000.0) for i in range(72)]
    rows += [_row(72 + i, 10.0 + i * 0.02, 80_000.0) for i in range(3)]

    score = score_inplay_volume(
        rows,
        recent_bars=3,
        baseline_bars=72,
        min_recent_quote_usd=500_000.0,
        min_inflow_mult=2.0,
        min_inflow_z=2.0,
    )

    assert score.ok
    assert score.reason == "ok"
    assert score.inflow_mult > 7.0
    assert score.score > 0.5


def test_score_inplay_volume_rejects_low_liquidity_spike():
    rows = [_row(i, 1.0, 100.0) for i in range(72)]
    rows += [_row(72 + i, 1.0, 1_000.0) for i in range(3)]

    score = score_inplay_volume(rows, min_recent_quote_usd=100_000.0)

    assert not score.ok
    assert score.reason == "recent_quote_too_low"


def test_score_inplay_volume_rejects_extreme_chase_move():
    rows = [_row(i, 10.0, 10_000.0) for i in range(72)]
    rows += [
        _row(72, 10.0, 100_000.0),
        _row(73, 11.5, 100_000.0),
        _row(74, 13.0, 100_000.0),
    ]

    score = score_inplay_volume(
        rows,
        recent_bars=3,
        baseline_bars=72,
        min_recent_quote_usd=500_000.0,
        max_abs_recent_return_pct=18.0,
    )

    assert not score.ok
    assert score.reason == "recent_move_too_extreme"
