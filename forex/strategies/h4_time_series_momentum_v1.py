from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, ema
from forex.types import Candle, Signal


@dataclass(frozen=True)
class Config:
    short_lookback: int = 24
    long_lookback: int = 72
    ema_fast: int = 24
    ema_slow: int = 72
    atr_period: int = 14
    min_short_move_atr: float = 1.25
    min_long_move_atr: float = 1.75
    min_ema_gap_atr: float = 0.18
    max_signal_body_atr: float = 1.20
    stop_atr: float = 1.80
    reward_risk: float = 2.20
    cooldown_bars: int = 4


class H4TimeSeriesMomentumV1:
    """Causal H4 price persistence, deliberately distinct from break/retest.

    The signal is evaluated only after a completed H4 candle.  It requires
    short- and long-horizon returns to agree with the EMA direction and avoids
    entering a single oversized candle.  No level, retest, funding or future
    universe information is used.
    """

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown = 0

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        cfg = self.cfg
        minimum = max(cfg.long_lookback, cfg.ema_slow + 5, cfg.atr_period + 2)
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
        fast = ema(closes[-(cfg.ema_fast * 2) :], cfg.ema_fast)
        slow = ema(closes[-(cfg.ema_slow + 5) :], cfg.ema_slow)
        if not (a > 0 and fast == fast and slow == slow):
            return None

        short_move = current.c - closes[-1 - cfg.short_lookback]
        long_move = current.c - closes[-1 - cfg.long_lookback]
        body_atr = abs(current.c - current.o) / a
        gap_atr = abs(fast - slow) / a
        if body_atr > cfg.max_signal_body_atr or gap_atr < cfg.min_ema_gap_atr:
            return None

        long_ok = (
            short_move >= cfg.min_short_move_atr * a
            and long_move >= cfg.min_long_move_atr * a
            and current.c > fast > slow
        )
        short_ok = (
            short_move <= -cfg.min_short_move_atr * a
            and long_move <= -cfg.min_long_move_atr * a
            and current.c < fast < slow
        )
        if not (long_ok or short_ok):
            return None

        side = "long" if long_ok else "short"
        entry = current.c
        risk = cfg.stop_atr * a
        sl = entry - risk if side == "long" else entry + risk
        tp = entry + cfg.reward_risk * risk if side == "long" else entry - cfg.reward_risk * risk
        self._cooldown = cfg.cooldown_bars
        return Signal(
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason="fx_h4_time_series_momentum_v1",
        )
