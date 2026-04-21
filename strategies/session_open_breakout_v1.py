"""
Session Open Breakout v1 (session_open_breakout_v1)
=====================================================
Enter in direction of the first impulse candle at session opens:
  - London open: 08:00 UTC (most reliable)
  - New York open: 13:30 UTC
  - Asia open: 00:00 UTC (optional, less reliable)

Edge: Institutional players open positions at session starts creating
      directional momentum in the first 15-30 minutes.

Signal logic:
  1. Wait for the first 15m candle to close after session open
  2. If that candle is bullish (close > open by body_min_atr) → long
     If bearish → short
  3. Optionally confirm with VWAP position
  4. SL: low/high of the trigger candle + buffer
  5. TP: RR × risk

Parameters (env vars):
  SOB1_SESSION_OPENS_UTC = "8,13"   # comma-separated session open hours
  SOB1_ENTRY_TF          = "15"     # entry timeframe minutes
  SOB1_BODY_MIN_ATR      = "0.3"    # min body size as fraction of ATR
  SOB1_SL_ATR            = "0.5"    # SL buffer in ATR beyond candle wick
  SOB1_RR                = "2.5"    # reward:risk ratio
  SOB1_ALLOW_LONGS       = "1"
  SOB1_ALLOW_SHORTS      = "1"
  SOB1_SESSION_WINDOW_M  = "45"     # only take signals within N min of open
  SOB1_VWAP_CONFIRM      = "0"      # require price above/below VWAP
  SOB1_RSI_MIN_LONG      = "0"      # optional RSI filter for longs (0=off)
  SOB1_RSI_MAX_SHORT     = "100"    # optional RSI filter for shorts (100=off)
  SOB1_SYMBOL_ALLOWLIST  = ""       # e.g. BTCUSDT,ETHUSDT
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

try:
    from strategies.signals import TradeSignal
except ImportError:
    from backtest.bt_types import TradeSignal  # type: ignore[no-redef]


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}

def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if not v:
        return default
    try: return float(v.strip())
    except: return default

def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try: return int(v.strip())
    except: return default

def _env_csv_ints(name: str, default: List[int]) -> List[int]:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return [int(x.strip()) for x in v.split(",") if x.strip()]
    except:
        return default

def _env_csv_set(name: str) -> set:
    raw = os.getenv(name, "") or ""
    return {p.strip().upper() for p in raw.split(",") if p.strip()}

def _atr(candles, period: int) -> float:
    if len(candles) < period + 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].get("high", candles[i].get("h", 0)) or 0)
        l = float(candles[i].get("low",  candles[i].get("l", 0)) or 0)
        pc = float(candles[i-1].get("close", candles[i-1].get("c", 0)) or 0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    last = trs[-period:]
    return sum(last) / max(1, len(last))

def _vwap(candles) -> float:
    """Simple session VWAP from available candles."""
    pv = 0.0
    vol = 0.0
    for c in candles:
        h = float(c.get("high", c.get("h", 0)) or 0)
        l = float(c.get("low",  c.get("l", 0)) or 0)
        cl = float(c.get("close", c.get("c", 0)) or 0)
        v = float(c.get("volume", c.get("v", 0)) or 0)
        tp = (h + l + cl) / 3.0
        pv += tp * v
        vol += v
    return pv / vol if vol > 0 else 0.0

def _rsi(candles, period: int = 14) -> float:
    if len(candles) < period + 2:
        return 50.0
    closes = [float(c.get("close", c.get("c", 0)) or 0) for c in candles]
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(0, d))
        losses.append(max(0, -d))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - (100.0 / (1 + rs))


@dataclass
class SessionOpenBreakoutConfig:
    session_opens_utc: List[int] = field(default_factory=lambda: [8, 13])
    entry_tf: str = "15"           # 15m candles for entry signal
    body_min_atr: float = 0.3      # min body / ATR to qualify as impulse
    sl_atr: float = 0.5            # SL buffer beyond candle wick in ATR units
    rr: float = 2.5
    allow_longs: bool = True
    allow_shorts: bool = True
    session_window_m: int = 45     # minutes after open to accept signals
    vwap_confirm: bool = False
    rsi_min_long: float = 0.0      # 0 = off
    rsi_max_short: float = 100.0   # 100 = off
    atr_period: int = 14


class SessionOpenBreakoutV1:
    """
    Session-open momentum breakout. Fires once per session open per symbol
    when the first qualifying 15m impulse candle appears after session start.
    """

    def __init__(self):
        p = "SOB1"
        cfg = SessionOpenBreakoutConfig()
        cfg.session_opens_utc = _env_csv_ints(f"{p}_SESSION_OPENS_UTC", cfg.session_opens_utc)
        cfg.entry_tf         = os.getenv(f"{p}_ENTRY_TF", cfg.entry_tf)
        cfg.body_min_atr     = _env_float(f"{p}_BODY_MIN_ATR", cfg.body_min_atr)
        cfg.sl_atr           = _env_float(f"{p}_SL_ATR", cfg.sl_atr)
        cfg.rr               = _env_float(f"{p}_RR", cfg.rr)
        cfg.allow_longs      = _env_bool(f"{p}_ALLOW_LONGS", cfg.allow_longs)
        cfg.allow_shorts     = _env_bool(f"{p}_ALLOW_SHORTS", cfg.allow_shorts)
        cfg.session_window_m = _env_int(f"{p}_SESSION_WINDOW_M", cfg.session_window_m)
        cfg.vwap_confirm     = _env_bool(f"{p}_VWAP_CONFIRM", cfg.vwap_confirm)
        cfg.rsi_min_long     = _env_float(f"{p}_RSI_MIN_LONG", cfg.rsi_min_long)
        cfg.rsi_max_short    = _env_float(f"{p}_RSI_MAX_SHORT", cfg.rsi_max_short)
        cfg.atr_period       = _env_int(f"{p}_ATR_PERIOD", cfg.atr_period)
        self.cfg = cfg
        self._allow = _env_csv_set(f"{p}_SYMBOL_ALLOWLIST")
        self._deny  = _env_csv_set(f"{p}_SYMBOL_DENYLIST")
        # Track which sessions we've already fired for (symbol → set of session keys)
        self._fired: dict = {}

    def _session_key(self, ts_ms: int) -> Optional[str]:
        """Return a session key like 'BTCUSDT_2026-04-05_08' if within window, else None."""
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        hour_utc = dt.hour
        minute_utc = dt.minute
        for session_hour in self.cfg.session_opens_utc:
            elapsed_m = (hour_utc - session_hour) * 60 + minute_utc
            if 0 <= elapsed_m <= self.cfg.session_window_m:
                date_str = dt.strftime("%Y-%m-%d")
                return f"{date_str}_{session_hour:02d}"
        return None

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        symbol = str(getattr(store, "symbol", "") or "").upper()

        # Allowlist / denylist
        if self._allow and symbol not in self._allow:
            return None
        if symbol in self._deny:
            return None

        # Are we in a session open window?
        sk = self._session_key(int(ts_ms))
        if sk is None:
            return None

        # Already fired this session for this symbol?
        fired_set = self._fired.setdefault(symbol, set())
        full_key = f"{symbol}_{sk}"
        if full_key in fired_set:
            return None

        # Get 15m candles (enough for ATR + RSI + VWAP)
        tf = self.cfg.entry_tf
        n_bars = max(60, self.cfg.atr_period + 20)
        candles = store.fetch_klines(symbol, tf, n_bars) or []
        if len(candles) < self.cfg.atr_period + 5:
            return None

        # Last closed candle is the session open impulse candle
        trigger = candles[-1]
        o = float(trigger.get("open",   trigger.get("o", 0)) or 0)
        h = float(trigger.get("high",   trigger.get("h", 0)) or 0)
        l = float(trigger.get("low",    trigger.get("l", 0)) or 0)
        c = float(trigger.get("close",  trigger.get("c", 0)) or 0)
        if not all([o, h, l, c]):
            return None

        atr = _atr(candles, self.cfg.atr_period)
        if atr <= 0:
            return None

        body = c - o  # positive = bullish, negative = bearish
        body_abs = abs(body)

        # Must be a meaningful impulse candle
        if body_abs < self.cfg.body_min_atr * atr:
            return None

        is_long  = body > 0 and self.cfg.allow_longs
        is_short = body < 0 and self.cfg.allow_shorts
        if not is_long and not is_short:
            return None

        # Optional VWAP confirm
        if self.cfg.vwap_confirm:
            vwap = _vwap(candles[-20:])
            if vwap > 0:
                if is_long  and c < vwap:
                    return None
                if is_short and c > vwap:
                    return None

        # Optional RSI filter
        if self.cfg.rsi_min_long > 0 or self.cfg.rsi_max_short < 100:
            rsi = _rsi(candles, self.cfg.atr_period)
            if is_long  and rsi < self.cfg.rsi_min_long:
                return None
            if is_short and rsi > self.cfg.rsi_max_short:
                return None

        # Build signal
        sl_buf = self.cfg.sl_atr * atr
        if is_long:
            entry = float(last_price)
            sl    = l - sl_buf
            risk  = entry - sl
            if risk <= 0:
                return None
            tp = entry + self.cfg.rr * risk
            side = "long"
            reason = f"sob1_london_long" if 8 in self.cfg.session_opens_utc and \
                      datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).hour == 8 \
                      else "sob1_session_long"
        else:
            entry = float(last_price)
            sl    = h + sl_buf
            risk  = sl - entry
            if risk <= 0:
                return None
            tp = entry - self.cfg.rr * risk
            side = "short"
            reason = "sob1_session_short"

        # Mark as fired for this session
        fired_set.add(full_key)

        return TradeSignal(
            strategy="session_open_breakout_v1",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=reason,
        )

    def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        return self.signal(store, ts_ms, last_price)
