"""
strategies/liquidation_cascade_entry_v1.py — Liquidation Cascade Entry v1
==========================================================================
Edge: When a rapid cascade of liquidations fires (large market-driven stop hunts),
price briefly overshoots fair value. We enter a counter-trend position as the panic
exhausts itself.

LOGIC:
  LONG (buy the panic dip):
    - Price dropped > LC_DROP_PCT % in last LC_LOOKBACK_BARS × 5m bars
    - RSI(14) dropped below LC_RSI_OVERSOLD (≤ 25 indicates true panic)
    - Volume spike: last bar volume ≥ LC_VOL_SPIKE_X × avg volume (capitulation candle)
    - Price is ≥ LC_BELOW_EMA_PCT % below EMA(LC_EMA_PERIOD)
    - Optional: only enter if OI (open interest) dropped → confirms long liquidations hit

  SHORT (fade the squeeze):
    - Price rallied > LC_DROP_PCT % in last LC_LOOKBACK_BARS × 5m bars
    - RSI(14) > LC_RSI_OVERBOUGHT (≥ 75 = shorts being squeezed)
    - Volume spike AND price ≥ LC_BELOW_EMA_PCT % ABOVE EMA
    - Controlled via LC_ALLOW_SHORTS env var

EXIT:
    - SL = LC_SL_ATR_MULT × ATR(14) (tight, cascade can resume)
    - TP = LC_TP_ATR_MULT × ATR(14)
    - Time stop = LC_TIME_STOP_BARS_5M bars (≈ 4h default = 48 bars)
    - Breakeven at LC_BE_PCT % profit
    - Cooldown = LC_COOLDOWN_BARS after any signal (prevents re-entry during sustained move)

WHY IT WORKS:
    Liquidation cascades on Bybit perpetuals create predictable overshoots because:
    1. Liquidation engines are mechanical — they dump at market regardless of level
    2. After the cascade, no more forced sellers → price snaps back
    3. Edge window is SHORT (minutes), so intraday timeframe (5m) is ideal
    4. Most effective on high-OI alt coins (AVAX, SOL, BNB) where small cascades = big moves

CONFIG (env vars):
    LC_ALLOW_LONGS=1             Enable long entries (default: 1)
    LC_ALLOW_SHORTS=0            Enable short entries (default: 0, shorts are riskier)
    LC_LOOKBACK_BARS=6           How many 5m bars to look back for the cascade (30 min)
    LC_DROP_PCT=3.0              Minimum % drop/rally to qualify as cascade (3%)
    LC_EMA_PERIOD=55             EMA period for dislocation check
    LC_BELOW_EMA_PCT=2.0         Must be ≥ this % below/above EMA
    LC_RSI_OVERSOLD=28.0         RSI threshold for longs
    LC_RSI_OVERBOUGHT=72.0       RSI threshold for shorts
    LC_VOL_SPIKE_X=2.5           Volume of entry bar vs avg (N bars) must be ≥ this
    LC_VOL_AVG_BARS=20           Bars to average volume over
    LC_SL_ATR_MULT=1.2           SL tightness (cascades: tight stop, fast TP)
    LC_TP_ATR_MULT=2.0           TP target
    LC_BE_PCT=0.8                Move to breakeven after 0.8% profit
    LC_TIME_STOP_BARS_5M=48      Max hold = 48 × 5min = 4 hours
    LC_COOLDOWN_BARS=12          Cooldown after signal = 1 hour (12 × 5min)
    LC_MIN_VOLUME_USDT=2000000   Min bar volume in USDT (filter thin coins)
    LC_ATR_PERIOD=14             ATR lookback

AUTORESEARCH:
    nohup python3 scripts/run_strategy_autoresearch.py \
        --spec configs/autoresearch/liquidation_cascade_v1_grid.json \
        > /tmp/lc_v1.log 2>&1 &
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# ── shared types (match the pattern used by other strategies in this repo) ──
try:
    from .signals import TradeSignal  # package import (backtest / live)
except ImportError:
    try:
        from strategies.signals import TradeSignal  # absolute import fallback
    except ImportError:
        try:
            from backtest.engine import TradeSignal  # legacy engine fallback
        except ImportError:
            from typing import Any
            TradeSignal = Any  # type: ignore[assignment,misc]

try:
    from backtest.engine import KlineStore
except ImportError:
    from typing import Any
    KlineStore = Any  # type: ignore[assignment,misc]


# ── Config ──────────────────────────────────────────────────────────────────

@dataclass
class LiquidationCascadeConfig:
    allow_longs:         bool  = field(default_factory=lambda: os.getenv("LC_ALLOW_LONGS", "1") == "1")
    allow_shorts:        bool  = field(default_factory=lambda: os.getenv("LC_ALLOW_SHORTS", "0") == "1")
    lookback_bars:       int   = field(default_factory=lambda: int(os.getenv("LC_LOOKBACK_BARS", "6")))
    drop_pct:            float = field(default_factory=lambda: float(os.getenv("LC_DROP_PCT", "3.0")))
    ema_period:          int   = field(default_factory=lambda: int(os.getenv("LC_EMA_PERIOD", "55")))
    below_ema_pct:       float = field(default_factory=lambda: float(os.getenv("LC_BELOW_EMA_PCT", "2.0")))
    rsi_oversold:        float = field(default_factory=lambda: float(os.getenv("LC_RSI_OVERSOLD", "28.0")))
    rsi_overbought:      float = field(default_factory=lambda: float(os.getenv("LC_RSI_OVERBOUGHT", "72.0")))
    vol_spike_x:         float = field(default_factory=lambda: float(os.getenv("LC_VOL_SPIKE_X", "2.5")))
    vol_avg_bars:        int   = field(default_factory=lambda: int(os.getenv("LC_VOL_AVG_BARS", "20")))
    sl_atr_mult:         float = field(default_factory=lambda: float(os.getenv("LC_SL_ATR_MULT", "1.2")))
    tp_atr_mult:         float = field(default_factory=lambda: float(os.getenv("LC_TP_ATR_MULT", "2.0")))
    be_pct:              float = field(default_factory=lambda: float(os.getenv("LC_BE_PCT", "0.8")))
    time_stop_bars:      int   = field(default_factory=lambda: int(os.getenv("LC_TIME_STOP_BARS_5M", "48")))
    cooldown_bars:       int   = field(default_factory=lambda: int(os.getenv("LC_COOLDOWN_BARS", "12")))
    min_volume_usdt:     float = field(default_factory=lambda: float(os.getenv("LC_MIN_VOLUME_USDT", "2000000")))
    atr_period:          int   = field(default_factory=lambda: int(os.getenv("LC_ATR_PERIOD", "14")))


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ema(values: list, period: int) -> float:
    if len(values) < period:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
    return e


def _rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = float(closes[i]) - float(closes[i - 1])
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(candles: list, period: int = 14) -> float:
    """candles: list of objects with .h .l .c attributes"""
    if len(candles) < period + 1:
        return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h)
        l = float(candles[i].l)
        pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / len(recent)


# ── Strategy ─────────────────────────────────────────────────────────────────

class LiquidationCascadeEntryV1:
    """
    Counter-trend entry after liquidation cascade exhaustion.
    Compatible with run_portfolio.py backtest (KlineStore) and live bot integration.
    """

    def __init__(self) -> None:
        self.cfg = LiquidationCascadeConfig()
        self._last_signal_bar: int = -9999  # bar index of last signal (cooldown)

    def _reload_cfg(self) -> None:
        """Re-read env vars each call (allows live parameter tweaks)."""
        self.cfg = LiquidationCascadeConfig()

    def maybe_signal(
        self,
        store: KlineStore,
        ts_ms: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> Optional[TradeSignal]:
        self._reload_cfg()
        cfg = self.cfg

        # ── 1. Gather candles ────────────────────────────────────────────────
        try:
            i = int(getattr(store, "i5", getattr(store, "i", None)))
            candles = store.c5
        except (AttributeError, TypeError):
            return None

        min_bars = max(cfg.lookback_bars, cfg.ema_period, cfg.vol_avg_bars, cfg.atr_period) + 5
        if i < min_bars:
            return None

        # ── 2. Cooldown ──────────────────────────────────────────────────────
        if i - self._last_signal_bar < cfg.cooldown_bars:
            return None

        # ── 3. Volume filter ─────────────────────────────────────────────────
        bar_vol_usdt = volume * close
        if bar_vol_usdt < cfg.min_volume_usdt:
            return None

        # ── 4. ATR ──────────────────────────────────────────────────────────
        atr = _atr(candles[i - cfg.atr_period - 1: i + 1], cfg.atr_period)
        if not atr or atr != atr:  # nan guard
            return None

        # ── 5. EMA for dislocation check ─────────────────────────────────────
        ema_src = [float(candles[j].c) for j in range(i - cfg.ema_period + 1, i + 1)]
        ema = _ema(ema_src, cfg.ema_period)
        if not ema or ema != ema:
            return None

        # ── 6. RSI ──────────────────────────────────────────────────────────
        rsi_period = 14
        rsi_src = [float(candles[j].c) for j in range(i - rsi_period - 1, i + 1)]
        rsi = _rsi(rsi_src, rsi_period)
        if rsi != rsi:
            return None

        # ── 7. Cascade detection (price move over lookback) ──────────────────
        lookback_start = candles[i - cfg.lookback_bars]
        cascade_high = max(float(candles[j].h) for j in range(i - cfg.lookback_bars, i + 1))
        cascade_low  = min(float(candles[j].l) for j in range(i - cfg.lookback_bars, i + 1))
        lookback_open = float(lookback_start.o)

        drop_pct_actual   = (lookback_open - close) / lookback_open * 100.0   # positive = dropped
        rally_pct_actual  = (close - lookback_open) / lookback_open * 100.0   # positive = rallied

        # ── 8. Volume spike check ────────────────────────────────────────────
        avg_vol = sum(
            float(candles[j].v) * float(candles[j].c)
            for j in range(i - cfg.vol_avg_bars, i)
        ) / cfg.vol_avg_bars
        vol_spike = bar_vol_usdt / avg_vol if avg_vol > 0 else 0.0

        # ── 9. Entry conditions ───────────────────────────────────────────────
        direction: Optional[str] = None
        entry_reason = ""

        if cfg.allow_longs:
            dislocation_below = (ema - close) / ema * 100.0  # positive = below EMA
            if (
                drop_pct_actual >= cfg.drop_pct
                and rsi <= cfg.rsi_oversold
                and vol_spike >= cfg.vol_spike_x
                and dislocation_below >= cfg.below_ema_pct
            ):
                direction = "long"
                entry_reason = (
                    f"LC_LONG drop={drop_pct_actual:.1f}% RSI={rsi:.1f} "
                    f"vol_x={vol_spike:.1f} ema_dis={dislocation_below:.1f}%"
                )

        if direction is None and cfg.allow_shorts:
            dislocation_above = (close - ema) / ema * 100.0  # positive = above EMA
            if (
                rally_pct_actual >= cfg.drop_pct
                and rsi >= cfg.rsi_overbought
                and vol_spike >= cfg.vol_spike_x
                and dislocation_above >= cfg.below_ema_pct
            ):
                direction = "short"
                entry_reason = (
                    f"LC_SHORT rally={rally_pct_actual:.1f}% RSI={rsi:.1f} "
                    f"vol_x={vol_spike:.1f} ema_dis={dislocation_above:.1f}%"
                )

        if direction is None:
            return None

        # ── 10. Build signal ──────────────────────────────────────────────────
        self._last_signal_bar = i

        # Get symbol from store (same pattern as funding_rate_reversion_v1)
        symbol = str(getattr(store, "symbol", "") or "").upper()

        sl_dist = atr * cfg.sl_atr_mult
        tp_dist = atr * cfg.tp_atr_mult

        if direction == "long":
            sl_price = close - sl_dist
            tp_price = close + tp_dist
        else:
            sl_price = close + sl_dist
            tp_price = close - tp_dist

        be_trigger_rr = cfg.be_pct / (sl_dist / close * 100.0) if sl_dist > 0 else 0.0

        try:
            return TradeSignal(
                strategy="liquidation_cascade_entry_v1",
                symbol=symbol,
                side=direction,           # TradeSignal uses "side", not "direction"
                entry=close,
                sl=sl_price,
                tp=tp_price,
                be_trigger_rr=be_trigger_rr,
                trailing_atr_mult=0.0,
                time_stop_bars=cfg.time_stop_bars,
                reason=entry_reason,
            )
        except Exception:
            return None
