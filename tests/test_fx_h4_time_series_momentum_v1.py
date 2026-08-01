from __future__ import annotations

from forex.strategies.h4_time_series_momentum_v1 import Config, H4TimeSeriesMomentumV1
from forex.types import Candle


def _trend_rows(direction: int, count: int = 100) -> list[Candle]:
    rows = []
    price = 1.0
    for index in range(count):
        move = direction * 0.001
        opened = price
        price += move
        rows.append(Candle(index * 14_400, opened, max(opened, price) + 0.0004, min(opened, price) - 0.0004, price, 1.0))
    return rows


def test_momentum_side_follows_agreeing_horizons() -> None:
    cfg = Config(min_short_move_atr=0.2, min_long_move_atr=0.5, min_ema_gap_atr=0.02)
    long_rows = _trend_rows(1)
    short_rows = _trend_rows(-1)

    long_signal = H4TimeSeriesMomentumV1(cfg).maybe_signal(long_rows, len(long_rows) - 1)
    short_signal = H4TimeSeriesMomentumV1(cfg).maybe_signal(short_rows, len(short_rows) - 1)

    assert long_signal is not None and long_signal.side == "long"
    assert short_signal is not None and short_signal.side == "short"
    assert long_signal.sl < long_signal.entry < long_signal.tp
    assert short_signal.tp < short_signal.entry < short_signal.sl


def test_momentum_ignores_oversized_signal_candle() -> None:
    rows = _trend_rows(1)
    last = rows[-1]
    rows[-1] = Candle(last.ts, last.o, last.h + 0.02, last.l, last.c + 0.02, last.v)

    signal = H4TimeSeriesMomentumV1(Config(max_signal_body_atr=0.2)).maybe_signal(rows, len(rows) - 1)

    assert signal is None
