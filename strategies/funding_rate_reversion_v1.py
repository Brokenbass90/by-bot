"""
Funding Rate Reversion v1 — Bybit Perpetuals Edge
==================================================
Edge rationale:
  Bybit perpetual futures pay/receive funding every 8 hours (00:00, 08:00, 16:00 UTC).
  When funding rate is extreme (|rate| > threshold):
    • Positive extreme (+0.06%+) → longs are overpaying → market is overextended long
      → Mean reversion SHORT: market tends to sell off or stall after funding
    • Negative extreme (-0.06%+) → shorts are overpaying → oversold condition
      → Mean reversion LONG: snapback rally likely after funding

  This is a Bybit-specific edge not available on spot exchanges.
  Typical duration: 1-6 hours (1-72 5m bars). Fast reversal then exit.

Entry conditions (confluence required):
  1. Funding rate extreme at last 8h window (|rate| ≥ FR_THRESHOLD)
  2. Price extended from EMA (EMA_FAST): price > EMA * (1 + EXT_PCT) for short
  3. RSI confirms overbought/oversold (RSI ≥ RSI_OB for short, ≤ RSI_OS for long)
  4. No cooldown from recent trade
  5. Within trading session (session_utc_start → session_utc_end)

Exit:
  • Fixed SL: SL_ATR_MULT × ATR14 from entry
  • TP: TP_ATR_MULT × ATR14 from entry (mean reversion target)
  • Time stop: TIME_STOP_BARS_5M bars after entry

Funding rate source:
  • Injected via store.funding_rate (float, e.g. 0.0008 = 0.08%)
  • OR via environment variable FR_LATEST_{SYMBOL} for testing
  • See scripts/funding_rate_fetcher.py for live data injection

Config env vars:
  FR_THRESHOLD=0.0006         # 0.06% default (bybit typical extreme)
  FR_EMA_PERIOD=55            # trend EMA period
  FR_EXT_PCT=0.005            # price extension from EMA (0.5%)
  FR_RSI_PERIOD=14
  FR_RSI_OB=65.0              # RSI overbought threshold for shorts
  FR_RSI_OS=35.0              # RSI oversold threshold for longs
  FR_SL_ATR_MULT=1.5
  FR_TP_ATR_MULT=2.5
  FR_TIME_STOP_BARS_5M=72     # 6 hours max hold
  FR_COOLDOWN_BARS=24         # 2h cooldown between trades
  FR_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT
  FR_MIN_VOLUME_USDT=1000000  # min bar volume for liquid market check
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .signals import TradeSignal


# ── Helpers ────────────────────────────────────────────────────────────────────
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


def _env_csv_set(name: str, default: str = "") -> set:
    raw = os.getenv(name, default) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return sum(trs) / float(period) if trs else float("nan")


def _rsi(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period + 1:
        return float("nan")
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses < 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


# ── Config ─────────────────────────────────────────────────────────────────────
@dataclass
class FundingRateReversionConfig:
    fr_threshold: float = 0.0006        # |funding rate| trigger (0.06%)
    ema_period: int = 55                # trend EMA
    ext_pct: float = 0.005             # price extension from EMA (0.5%)
    rsi_period: int = 14
    rsi_ob: float = 65.0               # overbought → short candidate
    rsi_os: float = 35.0               # oversold → long candidate
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    time_stop_bars: int = 72           # 6h max hold at 5m bars
    cooldown_bars: int = 24            # 2h cooldown
    session_utc_start: int = 0         # 24h market, no session filter by default
    session_utc_end: int = 24
    min_volume_usdt: float = 1_000_000 # min bar volume filter
    allow_longs: bool = True
    allow_shorts: bool = True


# ── Strategy ───────────────────────────────────────────────────────────────────
class FundingRateReversionV1:
    """
    Funding rate mean reversion strategy for Bybit perpetual futures.
    Works on 5m bars. Reads funding rate from store.funding_rate or env.
    """

    name = "funding_rate_reversion_v1"

    def __init__(self, cfg: Optional[FundingRateReversionConfig] = None) -> None:
        self.cfg = cfg or FundingRateReversionConfig()
        self._reload_config()

        self._closes: List[float] = []
        self._highs:  List[float] = []
        self._lows:   List[float] = []
        self._vols:   List[float] = []
        self._cooldown: int = 0
        self._last_funding_rate: float = 0.0  # cached from store
        self._last_funding_ts: int = 0

    def _reload_config(self) -> None:
        c = self.cfg
        c.fr_threshold    = _env_float("FR_THRESHOLD",          c.fr_threshold)
        c.ema_period      = _env_int("FR_EMA_PERIOD",           c.ema_period)
        c.ext_pct         = _env_float("FR_EXT_PCT",            c.ext_pct)
        c.rsi_period      = _env_int("FR_RSI_PERIOD",           c.rsi_period)
        c.rsi_ob          = _env_float("FR_RSI_OB",             c.rsi_ob)
        c.rsi_os          = _env_float("FR_RSI_OS",             c.rsi_os)
        c.sl_atr_mult     = _env_float("FR_SL_ATR_MULT",        c.sl_atr_mult)
        c.tp_atr_mult     = _env_float("FR_TP_ATR_MULT",        c.tp_atr_mult)
        c.time_stop_bars  = _env_int("FR_TIME_STOP_BARS_5M",    c.time_stop_bars)
        c.cooldown_bars   = _env_int("FR_COOLDOWN_BARS",        c.cooldown_bars)
        c.min_volume_usdt = _env_float("FR_MIN_VOLUME_USDT",    c.min_volume_usdt)
        c.allow_longs     = os.getenv("FR_ALLOW_LONGS", "1").strip() in {"1","true","yes"}
        c.allow_shorts    = os.getenv("FR_ALLOW_SHORTS", "1").strip() in {"1","true","yes"}

        self._allow = _env_csv_set(
            "FR_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT"
        )

    def _in_session(self, ts_ms: int) -> bool:
        h = ((ts_ms // 1000) // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def _get_funding_rate(self, store, symbol: str) -> Optional[float]:
        """
        Try to get funding rate from:
        1. store.funding_rate (injected by live bot's funding fetcher)
        2. Environment variable FR_LATEST_{SYMBOL} (for testing/override)
        Returns None if unavailable.
        """
        # Priority 1: store attribute
        fr = getattr(store, "funding_rate", None)
        if fr is not None:
            try:
                return float(fr)
            except Exception:
                pass
        # Priority 2: env var override (useful for testing)
        env_key = f"FR_LATEST_{symbol.upper()}"
        env_val = os.getenv(env_key, "")
        if env_val:
            try:
                return float(env_val)
            except Exception:
                pass
        return None

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
        _ = o
        sym = str(getattr(store, "symbol", "")).upper()

        # ── Guards ─────────────────────────────────────────────────────────────
        if self._allow and sym not in self._allow:
            return None
        if not self._in_session(ts_ms):
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # Accumulate bars
        self._closes.append(float(c))
        self._highs.append(float(h))
        self._lows.append(float(l))
        self._vols.append(float(v))

        min_bars = max(self.cfg.ema_period + 5, self.cfg.rsi_period + 5)
        if len(self._closes) < min_bars:
            return None

        # ── Funding rate check ─────────────────────────────────────────────────
        funding_rate = self._get_funding_rate(store, sym)
        if funding_rate is None:
            return None   # No funding data — skip

        abs_fr = abs(funding_rate)
        if abs_fr < self.cfg.fr_threshold:
            return None   # Funding not extreme enough

        # ── Indicators ────────────────────────────────────────────────────────
        ema_val = _ema(self._closes[-(self.cfg.ema_period * 2):], self.cfg.ema_period)
        atr_val = _atr(self._highs, self._lows, self._closes, 14)
        rsi_val = _rsi(self._closes, self.cfg.rsi_period)
        vol_usdt = float(v) * c

        if not (math.isfinite(ema_val) and math.isfinite(atr_val)
                and math.isfinite(rsi_val) and atr_val > 0):
            return None

        # Volume filter
        if self.cfg.min_volume_usdt > 0 and vol_usdt < self.cfg.min_volume_usdt:
            return None

        # ── Signal logic ───────────────────────────────────────────────────────
        # SHORT signal: extreme positive funding + price extended above EMA + RSI overbought
        if (self.cfg.allow_shorts
                and funding_rate >= self.cfg.fr_threshold
                and c > ema_val * (1.0 + self.cfg.ext_pct)
                and rsi_val >= self.cfg.rsi_ob):

            entry = c
            sl    = entry + self.cfg.sl_atr_mult * atr_val
            tp    = entry - self.cfg.tp_atr_mult * atr_val
            if tp <= 0:
                return None

            self._cooldown = self.cfg.cooldown_bars
            reason = (
                f"funding_short|FR={funding_rate*100:.4f}%"
                f"|RSI={rsi_val:.1f}|ext={(c/ema_val-1)*100:.2f}%"
            )
            return TradeSignal(
                strategy=self.name,
                symbol=sym,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=0.0,
                trailing_atr_mult=0.0,
                time_stop_bars=self.cfg.time_stop_bars,
                reason=reason,
            )

        # LONG signal: extreme negative funding + price below EMA + RSI oversold
        if (self.cfg.allow_longs
                and funding_rate <= -self.cfg.fr_threshold
                and c < ema_val * (1.0 - self.cfg.ext_pct)
                and rsi_val <= self.cfg.rsi_os):

            entry = c
            sl    = entry - self.cfg.sl_atr_mult * atr_val
            tp    = entry + self.cfg.tp_atr_mult * atr_val
            if sl <= 0:
                return None

            self._cooldown = self.cfg.cooldown_bars
            reason = (
                f"funding_long|FR={funding_rate*100:.4f}%"
                f"|RSI={rsi_val:.1f}|ext={(c/ema_val-1)*100:.2f}%"
            )
            return TradeSignal(
                strategy=self.name,
                symbol=sym,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=0.0,
                trailing_atr_mult=0.0,
                time_stop_bars=self.cfg.time_stop_bars,
                reason=reason,
            )

        return None
