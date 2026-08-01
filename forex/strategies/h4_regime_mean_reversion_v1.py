from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.types import Candle, Signal


@dataclass(frozen=True)
class Config:
    ema_period: int = 48
    slope_lookback: int = 12
    atr_period: int = 14
    max_ema_slope_atr: float = 0.22
    entry_distance_atr: float = 1.35
    min_rejection_wick_atr: float = 0.10
    stop_atr: float = 1.0
    min_reward_risk: float = 1.15
    cooldown_bars: int = 3


class H4RegimeMeanReversionV1:
    """Fade H4 excursions only while the causal EMA regime is flat."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        cfg = self.cfg
        minimum = cfg.ema_period + cfg.slope_lookback + 5
        if i < minimum:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        prefix = candles[: i + 1]
        closes = [bar.c for bar in prefix]
        highs = [bar.h for bar in prefix]
        lows = [bar.l for bar in prefix]
        current = prefix[-1]
        a = atr(highs, lows, closes, cfg.atr_period)
        center = ema(closes[-(cfg.ema_period + 5) :], cfg.ema_period)
        prior_center = ema(
            closes[: -cfg.slope_lookback][-(cfg.ema_period + 5) :],
            cfg.ema_period,
        )
        if not (a > 0 and center == center and prior_center == prior_center):
            return None
        if abs(center - prior_center) / a > cfg.max_ema_slope_atr:
            return None

        lower_wick = min(current.o, current.c) - current.l
        upper_wick = current.h - max(current.o, current.c)
        below = (center - current.c) / a
        above = (current.c - center) / a
        side = ""
        if below >= cfg.entry_distance_atr and current.c > current.o and lower_wick >= cfg.min_rejection_wick_atr * a:
            side = "long"
        elif above >= cfg.entry_distance_atr and current.c < current.o and upper_wick >= cfg.min_rejection_wick_atr * a:
            side = "short"
        if not side:
            return None

        entry = current.c
        risk = cfg.stop_atr * a
        target = center
        reward = target - entry if side == "long" else entry - target
        if reward <= 0 or reward / risk < cfg.min_reward_risk:
            return None
        sl = entry - risk if side == "long" else entry + risk
        self._cooldown = cfg.cooldown_bars
        return Signal(
            side=side,
            entry=entry,
            sl=sl,
            tp=target,
            reason="fx_h4_regime_mean_reversion_v1",
        )
