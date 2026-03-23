"""
alt_inplay_breakdown_v1 — Shorts-only breakdown strategy

A dedicated short-selling engine built on the same InPlayBreakoutStrategy
engine as inplay_breakout, but configured for downside breakdowns only.

Key differences from inplay_breakout:
- env_prefix = "BREAKDOWN" (uses BREAKDOWN_* env vars)
- Defaults: allow_longs=False, allow_shorts=True
- Regime filter enabled by default: only enters shorts when 4H EMA is bearish
- Controlled via BREAKDOWN_* env vars (independent of BREAKOUT_* params)

Typical env config:
    ENABLE_BREAKDOWN_TRADING=1
    BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ATOMUSDT
    BREAKDOWN_ALLOW_LONGS=0
    BREAKDOWN_ALLOW_SHORTS=1
    BREAKDOWN_REGIME_MODE=ema
    BREAKDOWN_REGIME_TF=4h
    BREAKDOWN_REGIME_EMA_FAST=21
    BREAKDOWN_REGIME_EMA_SLOW=55
    BREAKDOWN_LOOKBACK_H=72
    BREAKDOWN_RR=2.5
    BREAKDOWN_SL_ATR=1.8
    BREAKDOWN_RISK_MULT=0.10
    BREAKDOWN_MAX_OPEN_TRADES=1
"""
from __future__ import annotations

import os
from typing import Optional

from strategies.inplay_breakout import InPlayBreakoutWrapper, InPlayBreakoutConfig


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


class AltInplayBreakdownV1Strategy:
    """
    Shorts-only breakdown wrapper.  Uses InPlayBreakoutWrapper with
    env_prefix='BREAKDOWN' so its parameters are fully independent from
    the existing BREAKOUT_* longs strategy.

    The strategy name reported in trades is 'alt_inplay_breakdown_v1'.
    """

    STRATEGY_NAME = "alt_inplay_breakdown_v1"

    def __init__(self) -> None:
        # Build default config: shorts only, regime filter on
        cfg = InPlayBreakoutConfig()
        cfg.allow_longs = False
        cfg.allow_shorts = True
        cfg.regime_mode = "ema"   # default regime filter — overridable via BREAKDOWN_REGIME_MODE=off

        self._wrapper = InPlayBreakoutWrapper(cfg=cfg, env_prefix="BREAKDOWN")

    @property
    def last_no_signal_reason(self) -> str:
        return self._wrapper.last_no_signal_reason

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        sig = self._wrapper.signal(store, ts_ms, last_price)
        if sig is not None:
            sig.strategy = self.STRATEGY_NAME
        return sig

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        sig = await self._wrapper.maybe_signal(store, ts_ms, last_price)
        if sig is not None:
            sig.strategy = self.STRATEGY_NAME
        return sig
