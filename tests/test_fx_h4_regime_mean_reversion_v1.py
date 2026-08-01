from __future__ import annotations

from forex.strategies.h4_regime_mean_reversion_v1 import Config, H4RegimeMeanReversionV1
from forex.types import Candle


def _flat_with_rejection(side: str) -> list[Candle]:
    rows = [Candle(i * 14_400, 1.0, 1.001, 0.999, 1.0, 1.0) for i in range(80)]
    ts = rows[-1].ts + 14_400
    if side == "long":
        rows.append(Candle(ts, 0.985, 0.992, 0.980, 0.990, 1.0))
    else:
        rows.append(Candle(ts, 1.015, 1.020, 1.008, 1.010, 1.0))
    return rows


def test_flat_regime_rejections_create_side_specific_signals() -> None:
    cfg = Config(entry_distance_atr=0.6, min_reward_risk=0.5, min_rejection_wick_atr=0.01)
    longs = _flat_with_rejection("long")
    shorts = _flat_with_rejection("short")

    long_signal = H4RegimeMeanReversionV1(cfg).maybe_signal(longs, len(longs) - 1)
    short_signal = H4RegimeMeanReversionV1(cfg).maybe_signal(shorts, len(shorts) - 1)

    assert long_signal is not None and long_signal.side == "long"
    assert short_signal is not None and short_signal.side == "short"


def test_trending_regime_is_rejected() -> None:
    rows = []
    price = 1.0
    for i in range(90):
        opened = price
        price += 0.002
        rows.append(Candle(i * 14_400, opened, price + 0.0005, opened - 0.0005, price, 1.0))

    signal = H4RegimeMeanReversionV1(Config(max_ema_slope_atr=0.05)).maybe_signal(rows, len(rows) - 1)

    assert signal is None
