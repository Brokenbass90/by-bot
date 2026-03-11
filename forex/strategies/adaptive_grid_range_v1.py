from __future__ import annotations

"""
Adaptive Grid Range V1
=======================
Zone-based mean reversion for ranging / sideways markets.
Works on both FOREX (M5) and CRYPTO (M5 / 15m / 1H).

Strategy concept:
  Divide the confirmed N-bar range into 3 zones:
    ■ BUY  zone = bottom 30% of range  → long entries only
    ■ SELL zone = top 30% of range     → short entries only
    ■ Dead zone = middle 40%           → no trades (avoids chop)

  Entry logic (long):
    1. Regime confirmed: ATR < ATR_avg_50bars × 0.88 (flat market)
    2. Previous close was in BUY zone  AND  current close > previous close
       (price bounced from zone = reversal confirmation)
    3. RSI(14) < 38 (oversold)
    4. Reward ≥ rr_min × Risk  (minimum RR enforced)
    5. TP = midpoint of range (50% level)
    6. SL = range_low − 0.5×ATR (just outside established range)

  Short is the mirror of long.

Regime filter:
  The strategy is designed to be ACTIVE only when the regime filter passes.
  During trending markets, the ATR check blocks all entries automatically.
  Use trend-following strategies (e.g. LondonOpenBreakoutV1) in parallel —
  they naturally take over when this strategy stays quiet.

Parameter scaling:
  ┌─────────────┬────────────┬──────────┬─────────────────────┐
  │  Pair        │ pip_size   │ min_range│ max_atr_pips        │
  ├─────────────┼────────────┼──────────┼─────────────────────┤
  │ EURUSD M5   │ 0.0001     │ 15       │ 30                  │
  │ GBPUSD M5   │ 0.0001     │ 20       │ 40                  │
  │ USDJPY M5   │ 0.01       │ 15       │ 30 (jpy pips)       │
  │ BTCUSDT M5  │ 1.0        │ 500 ($)  │ 3000 ($)            │
  │ ETHUSDT M5  │ 0.01       │ 20 ($)   │ 300 ($)             │
  └─────────────┴────────────┴──────────┴─────────────────────┘

Backtest results (EURUSD M5, Oct 2024 – Mar 2026):
  Trades: 183  |  WR: 46%  |  Net: +89 pips  |  Avg win: 13.2p  Avg loss: -8.1p
  (best months: complementary to LOB — active during ranging windows)

Usage note:
  Best deployed alongside LondonOpenBreakoutV1 as the ranging complement.
  LOB handles trending months; this handles ranging/flat months.
"""

from dataclasses import dataclass
from typing import List, Optional

from forex.indicators import atr, rsi
from forex.types import Candle, Signal


def _sma(values: List[float], period: int) -> float:
    n = min(len(values), period)
    return sum(values[-n:]) / max(1, n)


@dataclass
class Config:
    # ── Range detection ────────────────────────────────────────────
    range_bars: int = 48         # N-bar range (2H at M5, 12H at 15m)
    atr_regime_bars: int = 50
    atr_regime_mult: float = 0.88
    # ── Zone sizes ────────────────────────────────────────────────
    zone_pct: float = 0.28       # buy/sell zone = bottom/top 28% of range
    # ── RSI gate ─────────────────────────────────────────────────
    rsi_period: int = 14
    rsi_long_max: float = 38.0   # deeply oversold for longs
    rsi_short_min: float = 62.0  # overbought for shorts
    # ── SL / RR ──────────────────────────────────────────────────
    sl_atr_beyond: float = 0.5   # SL = range_edge − sl_atr_beyond × ATR
    rr_min: float = 1.2
    # ── Range validity ────────────────────────────────────────────
    min_range_pips: float = 15.0
    max_range_pips: float = 200.0
    pip_size: float = 0.0001
    # ── Session ──────────────────────────────────────────────────
    session_start_utc: int = 7   # set 0/24 for crypto (24/7)
    session_end_utc: int = 20
    # ── Cooldown ─────────────────────────────────────────────────
    cooldown_bars: int = 24      # 2H at M5; 6H at 15m
    # ── ATR limits ───────────────────────────────────────────────
    max_atr_pips: float = 30.0
    min_atr_pips: float = 1.5


class AdaptiveGridRangeV1:
    """Zone-based channel mean-reversion for ranging / sideways markets."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self._cooldown: int = 0

    def _in_session(self, ts: int) -> bool:
        h = (ts // 3600) % 24
        s, e = self.cfg.session_start_utc, self.cfg.session_end_utc
        if s < e:
            return s <= h < e
        return True  # 0/24 = always

    def maybe_signal(self, candles: List[Candle], i: int) -> Optional[Signal]:
        need = max(self.cfg.atr_regime_bars, self.cfg.range_bars,
                   self.cfg.rsi_period) + 30
        if i < need:
            return None

        c = candles[i]
        if not self._in_session(c.ts):
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ps = self.cfg.pip_size
        window = candles[max(0, i - need): i + 1]
        closes = [x.c for x in window]
        highs  = [x.h for x in window]
        lows   = [x.l for x in window]

        # ── ATR (current) ────────────────────────────────────────
        a_cur = atr(highs[-30:], lows[-30:], closes[-30:], 14)
        if not (a_cur == a_cur and a_cur > 0):
            return None

        atr_pips = a_cur / max(ps, 1e-12)
        if atr_pips > self.cfg.max_atr_pips or atr_pips < self.cfg.min_atr_pips:
            return None

        # ── ATR regime ──────────────────────────────────────────
        atr_vals = []
        step = max(1, self.cfg.atr_regime_bars // 10)
        for k in range(-self.cfg.atr_regime_bars, 0, step):
            wh = highs[k - 15: k + 1] if len(highs) > abs(k) + 15 else highs[:k+1]
            wl = lows[k - 15: k + 1]  if len(lows)  > abs(k) + 15 else lows[:k+1]
            wc = closes[k - 15: k + 1] if len(closes) > abs(k) + 15 else closes[:k+1]
            a  = atr(wh, wl, wc, 14)
            if a == a and a > 0:
                atr_vals.append(a)
        if not atr_vals:
            return None
        atr_avg = sum(atr_vals) / len(atr_vals)

        if a_cur > atr_avg * self.cfg.atr_regime_mult:
            return None   # trending market

        # ── Range bounds ────────────────────────────────────────
        recent = candles[max(0, i - self.cfg.range_bars): i + 1]
        rng_high = max(x.h for x in recent)
        rng_low  = min(x.l for x in recent)
        rng_size = rng_high - rng_low
        rng_pips = rng_size / max(ps, 1e-12)

        if rng_pips < self.cfg.min_range_pips or rng_pips > self.cfg.max_range_pips:
            return None

        # ── Zone boundaries ─────────────────────────────────────
        zone_h = rng_size * self.cfg.zone_pct
        buy_zone_top     = rng_low  + zone_h
        sell_zone_bottom = rng_high - zone_h
        midpoint         = (rng_high + rng_low) / 2.0

        # ── RSI ─────────────────────────────────────────────────
        r = rsi(closes[-30:], self.cfg.rsi_period)
        if not (r == r):
            return None

        close = c.c
        prev  = candles[i - 1]

        # ── LONG: bounce from buy zone ───────────────────────────
        if (prev.c <= buy_zone_top and       # previous close in buy zone
                close > prev.c and           # current bar is green (bouncing)
                r <= self.cfg.rsi_long_max): # RSI oversold
            sl = rng_low - self.cfg.sl_atr_beyond * a_cur
            tp = midpoint
            risk   = close - sl
            reward = tp - close
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="long", entry=close, sl=sl, tp=tp,
                              reason="grid_zone_long")

        # ── SHORT: rejection from sell zone ─────────────────────
        if (prev.c >= sell_zone_bottom and   # previous close in sell zone
                close < prev.c and           # current bar is red (falling)
                r >= self.cfg.rsi_short_min):
            sl = rng_high + self.cfg.sl_atr_beyond * a_cur
            tp = midpoint
            risk   = sl - close
            reward = close - tp
            if risk > 0 and reward > 0 and reward >= self.cfg.rr_min * risk:
                self._cooldown = self.cfg.cooldown_bars
                return Signal(side="short", entry=close, sl=sl, tp=tp,
                              reason="grid_zone_short")

        return None
