"""
alt_volume_spike_momentum_v1 (VSM1) — Volume-Spike Momentum Scalper

STATUS: ❌ SHELVED — NOT VIABLE ON 5M BARS (2026-04-15 backtest verdict)
  Best 90-day sweep result: PF=0.21, WR=15%, -1.6% net (SL=0.8, spike=2.0x, body=0.50, qb=4, qra=0.8)
  Root cause: 5-minute volume spikes are mostly noise. The compression/spike pattern
  requires higher-timeframe context (15m or 1h) to achieve positive expectancy.
  Bug note: run_portfolio.py MIN_NOTIONAL_FILL_FRAC=0.40 kills all VSM1 trades by default
    (tight 0.5 ATR SL → huge risk-based qty >> notional cap → fill ratio <5%). Add
    MIN_NOTIONAL_FILL_FRAC=0 when backtesting this or any tight-SL strategy.
  Future work: redesign for 15m/1h bars with 8-12 bar compression windows.

CONCEPT:
  The strategy exploits the TRANSITION from quiet → active market.
  After 3-5 consecutive narrow/quiet bars (compression), a sudden volume
  spike + strong directional candle signals institutional/whale order flow.
  This typically produces 2-4 bars of continuation momentum.

  This is real market microstructure alpha, not pattern-matching:
  - Volume spikes precede directional moves because large orders must be
    executed over multiple fills, creating a visible volume signature.
  - The compression (quiet bars) indicates equilibrium before a breakout.
  - A strong body (≥45%) on the spike bar means the move is absorbing sellers/buyers.

ENTRY CONDITIONS:
  Long:
    1. Compression: last VSM1_QUIET_BARS bars each had range < VSM1_QUIET_RANGE_ATR × ATR
                    AND volume < VSM1_QUIET_VOL_MULT × 20-bar avg volume
    2. Spike: current bar volume ≥ VSM1_SPIKE_VOL_MULT × 20-bar avg volume
    3. Direction: bullish bar, close > open, body_frac ≥ VSM1_MIN_BODY_FRAC
    4. Candle: close in top VSM1_CLOSE_RANK of bar range (e.g. top 60%)
    5. RSI filter: RSI < VSM1_RSI_LONG_MAX (not overbought going in)
    6. ATR filter: VSM1_MIN_ATR_PCT ≤ ATR/price ≤ VSM1_MAX_ATR_PCT (not dead/crazy market)

  Short: symmetric

EXIT:
  TP: entry ± VSM1_TP_ATR × ATR (default 1.5 ATR = ~3R)
  SL: entry ∓ VSM1_SL_ATR × ATR (default 0.5 ATR)
  Time stop: VSM1_TIME_STOP_BARS bars (default 6 = 30 minutes)
  Trailing: activates after TP1 (50% at 1R), trail at VSM1_TRAIL_ATR × ATR

KEY DIFFERENCES FROM OTHER STRATEGIES:
  - Very tight SL (0.5 ATR) → small losers, fast cuts
  - Short time stop (30 min) → doesn't hold overnight
  - Volume compression is the MAIN filter (not price patterns)
  - Both sides: trades momentum regardless of regime
  - Expected: 400-600 trades/year on 8-symbol universe

ENV PREFIX: VSM1_
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip() == "1"


@dataclass
class VSM1Config:
    # Compression detection
    quiet_bars: int = 3          # consecutive narrow bars before spike
    quiet_range_atr: float = 0.8 # each quiet bar range < N × ATR (P41 on BTC 5m)
    quiet_vol_mult: float = 1.5  # each quiet bar vol < N × avg_vol (loose — range is main filter)

    # Spike detection
    spike_vol_mult: float = 1.5  # spike bar vol ≥ N × avg_vol (P82 on BTC 5m)
    min_body_frac: float = 0.40   # spike bar body must be ≥ N of range
    close_rank_min: float = 0.55  # close must be in top/bottom N% of range

    # RSI filter
    rsi_period: int = 14
    rsi_long_max: float = 60.0    # don't buy already overbought
    rsi_short_min: float = 40.0   # don't sell already oversold

    # ATR filter (market activity filter)
    atr_period: int = 14
    vol_avg_period: int = 20
    min_atr_pct: float = 0.05    # skip only truly dead markets (< 0.05% ATR on 5m)
    max_atr_pct: float = 4.00    # skip insane markets (> 4% ATR)

    # Exit
    sl_atr: float = 0.50         # tight SL = 0.5 ATR (fast cuts)
    tp1_atr: float = 1.00        # TP1 at 1 ATR (= 2R)
    tp1_frac: float = 0.50       # close 50% at TP1
    tp2_atr: float = 2.00        # TP2 at 2 ATR (= 4R)
    trail_atr: float = 0.60      # trailing stop after TP1 hit
    time_stop_bars: int = 6      # 6 bars = 30 minutes on 5m

    # Regime-aware: require at least VSM1_MIN_COMPRESSION_BARS quiet bars
    min_bars: int = 100          # minimum bars history needed

    # Direction filter
    allow_longs: bool = True
    allow_shorts: bool = True


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    n = len(closes)
    trs = []
    for i in range(n):
        h = highs[i]
        l_ = lows[i]
        prev_c = closes[i - 1] if i > 0 else closes[i]
        trs.append(max(h - l_, abs(h - prev_c), abs(l_ - prev_c)))
    atrs = []
    if len(trs) < period:
        return [trs[-1]] * n if trs else [0.0] * n
    atrs = [sum(trs[:period]) / period]
    for i in range(1, n):
        if i < period:
            atrs.append(sum(trs[:i + 1]) / (i + 1))
        else:
            atrs.append((atrs[-1] * (period - 1) + trs[i]) / period)
    return atrs


def _rsi(closes: List[float], period: int) -> List[float]:
    n = len(closes)
    if n < period + 1:
        return [50.0] * n
    gains, losses = [], []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsiv = []
    for i in range(n - 1):
        if i < period - 1:
            rsiv.append(50.0)
            continue
        if i == period - 1:
            rs = avg_gain / avg_loss if avg_loss > 1e-12 else 100.0
            rsiv.append(100 - 100 / (1 + rs))
            continue
        idx = i - period + 1
        avg_gain = (avg_gain * (period - 1) + gains[idx + period - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[idx + period - 1]) / period
        rs = avg_gain / avg_loss if avg_loss > 1e-12 else 100.0
        rsiv.append(100 - 100 / (1 + rs))
    rsiv.append(rsiv[-1] if rsiv else 50.0)
    return rsiv


class AltVolumeSpikeV1Strategy:
    """Volume-Spike Momentum Scalper."""

    def __init__(self) -> None:
        self.config = VSM1Config()
        self._load_env()
        self._last_no_signal_reason = ""
        self._last_ts: Optional[int] = None

    def _load_env(self) -> None:
        c = self.config
        c.quiet_bars = _env_int("VSM1_QUIET_BARS", c.quiet_bars)
        c.quiet_range_atr = _env_float("VSM1_QUIET_RANGE_ATR", c.quiet_range_atr)
        c.quiet_vol_mult = _env_float("VSM1_QUIET_VOL_MULT", c.quiet_vol_mult)
        c.spike_vol_mult = _env_float("VSM1_SPIKE_VOL_MULT", c.spike_vol_mult)
        c.min_body_frac = _env_float("VSM1_MIN_BODY_FRAC", c.min_body_frac)
        c.close_rank_min = _env_float("VSM1_CLOSE_RANK_MIN", c.close_rank_min)
        c.rsi_period = _env_int("VSM1_RSI_PERIOD", c.rsi_period)
        c.rsi_long_max = _env_float("VSM1_RSI_LONG_MAX", c.rsi_long_max)
        c.rsi_short_min = _env_float("VSM1_RSI_SHORT_MIN", c.rsi_short_min)
        c.atr_period = _env_int("VSM1_ATR_PERIOD", c.atr_period)
        c.vol_avg_period = _env_int("VSM1_VOL_AVG_PERIOD", c.vol_avg_period)
        c.min_atr_pct = _env_float("VSM1_MIN_ATR_PCT", c.min_atr_pct)
        c.max_atr_pct = _env_float("VSM1_MAX_ATR_PCT", c.max_atr_pct)
        c.sl_atr = _env_float("VSM1_SL_ATR", c.sl_atr)
        c.tp1_atr = _env_float("VSM1_TP1_ATR", c.tp1_atr)
        c.tp1_frac = _env_float("VSM1_TP1_FRAC", c.tp1_frac)
        c.tp2_atr = _env_float("VSM1_TP2_ATR", c.tp2_atr)
        c.trail_atr = _env_float("VSM1_TRAIL_ATR", c.trail_atr)
        c.time_stop_bars = _env_int("VSM1_TIME_STOP_BARS", c.time_stop_bars)
        c.allow_longs = _env_bool("VSM1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("VSM1_ALLOW_SHORTS", c.allow_shorts)

    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        cfg = self.config
        sym = getattr(store, "symbol", "?")

        # Fetch bars — rows are lists: [ts, open, high, low, close, volume, ...]
        # The store's fetch_klines already includes the current bar as rows[-1].
        # We do NOT append the current bar separately (avoids duplication).
        need = max(cfg.min_bars, cfg.quiet_bars + cfg.vol_avg_period + cfg.atr_period + 10)
        rows = store.fetch_klines(sym, "5", need)
        if not rows or len(rows) < need // 2:
            self._last_no_signal_reason = "insufficient_bars"
            return None

        # Duplicate-bar guard (same as ASM1 / ARF1 pattern)
        tf_ts = int(float(rows[-1][0]))
        if self._last_ts is None:
            self._last_ts = tf_ts
            self._last_no_signal_reason = "first_bar"
            return None
        if tf_ts == self._last_ts:
            self._last_no_signal_reason = "same_bar"
            return None
        self._last_ts = tf_ts

        # Build price series from klines (rows[-1] IS the current bar)
        closes = [float(b[4]) for b in rows]
        opens = [float(b[1]) for b in rows]
        highs = [float(b[2]) for b in rows]
        lows = [float(b[3]) for b in rows]
        volumes = [float(b[5]) if len(b) > 5 and b[5] not in (None, "", "nan") else 0.0
                   for b in rows]

        n = len(closes)
        if n < cfg.vol_avg_period + cfg.quiet_bars + 2:
            self._last_no_signal_reason = "insufficient_bars"
            return None

        # Override current bar with passed values if they differ (live accuracy)
        if abs(closes[-1] - c) / max(1e-12, closes[-1]) > 0.001:
            closes[-1] = c
            opens[-1] = o
            highs[-1] = h
            lows[-1] = l
        if v > 0:
            volumes[-1] = v

        # ATR
        atrs = _atr(highs, lows, closes, cfg.atr_period)
        atr_now = atrs[-1]
        if atr_now <= 0:
            self._last_no_signal_reason = "atr_zero"
            return None

        # ATR % filter
        price_now = closes[-1]
        atr_pct = (atr_now / price_now) * 100.0
        if atr_pct < cfg.min_atr_pct:
            self._last_no_signal_reason = f"atr_too_low:{atr_pct:.3f}"
            return None
        if atr_pct > cfg.max_atr_pct:
            self._last_no_signal_reason = f"atr_too_high:{atr_pct:.3f}"
            return None

        # RSI
        rsiv = _rsi(closes, cfg.rsi_period)
        rsi_now = rsiv[-1]

        # Volume average (excludes current bar)
        if n < cfg.vol_avg_period + 1:
            self._last_no_signal_reason = "insufficient_vol_history"
            return None
        vol_avg = sum(volumes[-(cfg.vol_avg_period + 1):-1]) / cfg.vol_avg_period
        if vol_avg <= 0:
            self._last_no_signal_reason = "zero_vol_avg"
            return None

        # Current bar properties
        curr_range = h - l
        curr_body = abs(c - o)
        body_frac = curr_body / curr_range if curr_range > 1e-12 else 0.0
        is_bullish = c > o
        # Close rank: where is close within the bar range?
        close_rank = (c - l) / curr_range if curr_range > 1e-12 else 0.5

        # Volume spike check (use volumes[-1] after override, not raw v)
        vol_current = volumes[-1]
        vol_mult_now = vol_current / vol_avg if vol_avg > 0 else 0.0
        if vol_mult_now < cfg.spike_vol_mult:
            self._last_no_signal_reason = f"vol_spike_weak:{vol_mult_now:.2f}x<{cfg.spike_vol_mult}"
            return None

        # Body fraction check
        if body_frac < cfg.min_body_frac:
            self._last_no_signal_reason = f"body_weak:{body_frac:.2f}<{cfg.min_body_frac}"
            return None

        # Compression check: previous quiet_bars must all be quiet
        need = cfg.quiet_bars
        if n < need + 2:  # need bars + current + at least 1 history
            self._last_no_signal_reason = "not_enough_bars_for_compression"
            return None

        compressed = True
        for i in range(n - 1 - need, n - 1):
            bar_range = highs[i] - lows[i]
            bar_vol = volumes[i]
            if bar_range > cfg.quiet_range_atr * atrs[i]:
                compressed = False
                break
            if bar_vol > cfg.quiet_vol_mult * vol_avg:
                compressed = False
                break

        if not compressed:
            self._last_no_signal_reason = "no_compression"
            return None

        # Direction logic
        if is_bullish and cfg.allow_longs:
            # Long: close in top portion of range
            if close_rank < cfg.close_rank_min:
                self._last_no_signal_reason = f"close_rank_low:{close_rank:.2f}<{cfg.close_rank_min}"
                return None
            if rsi_now > cfg.rsi_long_max:
                self._last_no_signal_reason = f"rsi_overbought:{rsi_now:.1f}>{cfg.rsi_long_max}"
                return None

            entry = c
            sl = entry - cfg.sl_atr * atr_now
            tp1 = entry + cfg.tp1_atr * atr_now
            tp2 = entry + cfg.tp2_atr * atr_now
            side = "long"

        elif not is_bullish and cfg.allow_shorts:
            # Short: close in bottom portion of range
            if close_rank > (1.0 - cfg.close_rank_min):
                self._last_no_signal_reason = f"close_rank_high:{close_rank:.2f}>{1-cfg.close_rank_min}"
                return None
            if rsi_now < cfg.rsi_short_min:
                self._last_no_signal_reason = f"rsi_oversold:{rsi_now:.1f}<{cfg.rsi_short_min}"
                return None

            entry = c
            sl = entry + cfg.sl_atr * atr_now
            tp1 = entry - cfg.tp1_atr * atr_now
            tp2 = entry - cfg.tp2_atr * atr_now
            side = "short"

        else:
            self._last_no_signal_reason = "direction_not_allowed"
            return None

        reason = (
            f"vsm1_{side}_compression vol={vol_mult_now:.1f}x "
            f"body={body_frac:.2f} atr_pct={atr_pct:.2f}% rsi={rsi_now:.1f}"
        )

        sig = TradeSignal(
            strategy="alt_volume_spike_momentum_v1",
            symbol=sym,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            reason=reason,
        )

        # Multi-TP runner
        sig.tps = [tp1, tp2]
        sig.tp_fracs = [cfg.tp1_frac, 1.0 - cfg.tp1_frac]
        sig.trailing_atr_mult = cfg.trail_atr
        sig.trailing_atr_period = cfg.atr_period
        sig.time_stop_bars = cfg.time_stop_bars

        self._last_no_signal_reason = ""
        return sig
