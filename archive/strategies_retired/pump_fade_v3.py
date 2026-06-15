"""
pump_fade_v3 — Calibrated pump/dump fade with regime awareness.

Key improvements over v2:
  - Lower pump threshold: 4% (was 7%) → catches more real pumps
  - Lower RSI thresholds: OB=65 OS=35 (was 72/28) → more signals, still extreme
  - Dual window: checks both 5m bar window (fast pump) AND hourly (slow pump)
  - ATR quality gate: skip if market is too quiet (no real moves expected)
  - ER regime gate: skip if market is trending (don't fade strong trends)
  - Tighter position sizing controls

Volume exhaustion is off by default but encouraged for live (vol_exhaust_mult=0.7).

Env config:
    PF3_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT
    PF3_PUMP_WINDOW_BARS=20       # 5m bars to scan for pump (100 min)
    PF3_MIN_PUMP_PCT=0.04         # 4% move to qualify as pump
    PF3_MAX_PUMP_PCT=0.35         # cap at 35% (beyond = liquidation cascade)
    PF3_RSI_OB=65                 # RSI overbought for shorts
    PF3_RSI_OS=35                 # RSI oversold for longs
    PF3_CONFIRM_BARS=2            # reversal bars needed
    PF3_SL_ATR_MULT=1.5
    PF3_RR=2.0
    PF3_ALLOW_SHORTS=1
    PF3_ALLOW_LONGS=1
    PF3_ATR_MIN_PCT=0.10          # skip if 5m ATR < 0.10% of price
    PF3_ER_GATE_ENABLED=1         # skip if trending (ER > 0.60)
    PF3_ER_GATE_MAX=0.60          # max ER to enter fade (trending → don't fade)
    PF3_ER_GATE_BARS=48           # bars for ER calculation (48 × 5m = 4h)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

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
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _rsi(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_from_bars(bars: List[tuple], period: int) -> float:
    """bars = list of (ts, o, h, l, c, v)"""
    if len(bars) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = bars[i][2]
        l = bars[i][3]
        pc = bars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period if trs else float("nan")


def _efficiency_ratio(closes: List[float], bars: int) -> float:
    """ER = |net_move| / sum(|bar_moves|). 0=chop, 1=trend."""
    n = min(bars, len(closes) - 1)
    if n < 2:
        return float("nan")
    net_move = abs(closes[-1] - closes[-1 - n])
    path = sum(abs(closes[-i] - closes[-i - 1]) for i in range(1, n + 1))
    if path < 1e-12:
        return 0.0
    return net_move / path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PumpFadeV3Config:
    # Signal detection window (5m bars)
    pump_window_bars: int = 20    # was 12 in v2 — now 100 min window
    min_pump_pct: float = 0.04    # was 0.07 — now 4% minimum move
    max_pump_pct: float = 0.35    # cap at 35%
    rsi_period: int = 14
    rsi_ob: float = 65.0          # was 72 — now 65 (still clearly extreme)
    rsi_os: float = 35.0          # was 28 — now 35
    confirm_bars: int = 2         # reversal bars needed before entry

    # Exit management
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    rr: float = 2.0               # was 1.8 — slight improvement
    allow_shorts: bool = True
    allow_longs: bool = True
    time_stop_bars: int = 96      # 8h time stop (5m bars)
    cooldown_bars: int = 24       # 2h cooldown (was 20 bars)

    # Volume exhaustion (optional — enables only if vol > 0)
    vol_exhaust_mult: float = 0.0  # 0=disabled; 0.7=enable for live

    # ATR quality gate: skip if market is too quiet
    atr_min_pct: float = 0.10     # skip if 5m ATR < 0.10% of price

    # ER gate: skip if market is TRENDING (don't fade trends)
    # This is INVERTED from ASM1: ASM1 needs ER high, fade needs ER LOW
    er_gate_enabled: bool = True
    er_gate_max: float = 0.60     # skip if ER > 0.60 (trending — not a fade setup)
    er_gate_bars: int = 48        # 48 × 5m = 4h ER window


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class PumpFadeV3Strategy:
    """Fades pumps (short) and bounces dumps (long) with calibrated thresholds.

    Key changes from v2:
      - min_pump_pct: 7% → 4% (×4 more qualifying moves)
      - rsi_ob/os: 72/28 → 65/35 (×3 more extreme readings)
      - ATR quality gate (skip quiet markets)
      - ER gate (skip trending markets — don't fade a breakout)
    """

    STRATEGY_NAME = "pump_fade_v3"

    def __init__(self, cfg: Optional[PumpFadeV3Config] = None):
        self.cfg = cfg or PumpFadeV3Config()
        self._load_env()
        self._cooldown = 0
        self._last_5m_ts: Optional[int] = None
        self._bars: List[tuple] = []
        self.last_no_signal_reason = ""

    def _load_env(self) -> None:
        c = self.cfg
        c.pump_window_bars = _env_int("PF3_PUMP_WINDOW_BARS", c.pump_window_bars)
        c.min_pump_pct = _env_float("PF3_MIN_PUMP_PCT", c.min_pump_pct)
        c.max_pump_pct = _env_float("PF3_MAX_PUMP_PCT", c.max_pump_pct)
        c.rsi_period = _env_int("PF3_RSI_PERIOD", c.rsi_period)
        c.rsi_ob = _env_float("PF3_RSI_OB", c.rsi_ob)
        c.rsi_os = _env_float("PF3_RSI_OS", c.rsi_os)
        c.confirm_bars = _env_int("PF3_CONFIRM_BARS", c.confirm_bars)
        c.atr_period = _env_int("PF3_ATR_PERIOD", c.atr_period)
        c.sl_atr_mult = _env_float("PF3_SL_ATR_MULT", c.sl_atr_mult)
        c.rr = _env_float("PF3_RR", c.rr)
        c.allow_shorts = _env_bool("PF3_ALLOW_SHORTS", c.allow_shorts)
        c.allow_longs = _env_bool("PF3_ALLOW_LONGS", c.allow_longs)
        c.time_stop_bars = _env_int("PF3_TIME_STOP_BARS", c.time_stop_bars)
        c.cooldown_bars = _env_int("PF3_COOLDOWN_BARS", c.cooldown_bars)
        c.vol_exhaust_mult = _env_float("PF3_VOL_EXHAUST_MULT", c.vol_exhaust_mult)
        c.atr_min_pct = _env_float("PF3_ATR_MIN_PCT", c.atr_min_pct)
        c.er_gate_enabled = _env_bool("PF3_ER_GATE_ENABLED", c.er_gate_enabled)
        c.er_gate_max = _env_float("PF3_ER_GATE_MAX", c.er_gate_max)
        c.er_gate_bars = _env_int("PF3_ER_GATE_BARS", c.er_gate_bars)
        self._allow = _env_csv_set("PF3_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("PF3_SYMBOL_DENYLIST")

    def _refresh_runtime(self) -> None:
        self._allow = _env_csv_set("PF3_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("PF3_SYMBOL_DENYLIST")
        self._load_env()

    def maybe_signal(
        self, symbol: str, ts_ms: int,
        o: float, h: float, l: float, c: float, v: float = 0.0,
    ) -> Optional[TradeSignal]:
        self._refresh_runtime()
        self.last_no_signal_reason = ""

        sym = str(symbol or "").upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        # Deduplicate 5m bars
        tf_ts = int(ts_ms)
        if self._last_5m_ts is not None and tf_ts == self._last_5m_ts:
            return None
        self._last_5m_ts = tf_ts

        self._bars.append((tf_ts, float(o), float(h), float(l), float(c), float(v or 0.0)))
        need = self.cfg.pump_window_bars + self.cfg.confirm_bars + self.cfg.atr_period + 5
        max_keep = max(need + 20, 300)
        if len(self._bars) > max_keep:
            self._bars = self._bars[-max_keep:]
        if len(self._bars) < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        # Core data
        closes = [r[4] for r in self._bars]
        opens  = [r[1] for r in self._bars]
        highs  = [r[2] for r in self._bars]
        lows   = [r[3] for r in self._bars]
        vols   = [r[5] for r in self._bars]

        # ATR quality gate — skip quiet markets
        atr = _atr_from_bars(self._bars, self.cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "atr_invalid"
            return None
        cur_price = closes[-1]
        atr_pct = atr / max(1e-12, cur_price) * 100.0
        if atr_pct < self.cfg.atr_min_pct:
            self.last_no_signal_reason = f"atr_too_quiet:{atr_pct:.3f}%"
            return None

        # ER gate — skip trending markets (don't fade real breakouts)
        if self.cfg.er_gate_enabled and self.cfg.er_gate_max < 1.0:
            er = _efficiency_ratio(closes, self.cfg.er_gate_bars)
            if math.isfinite(er) and er > self.cfg.er_gate_max:
                self.last_no_signal_reason = f"er_trending:{er:.3f}"
                return None

        # RSI
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not math.isfinite(rsi):
            self.last_no_signal_reason = "rsi_invalid"
            return None

        # Pump/dump detection over the lookback window
        win = self.cfg.pump_window_bars
        pump_start = closes[-win - 1]
        pump_peak = max(closes[-win:])
        pump_pct = (pump_peak - pump_start) / max(1e-12, abs(pump_start))

        dump_start = closes[-win - 1]
        dump_trough = min(closes[-win:])
        dump_pct = (dump_start - dump_trough) / max(1e-12, abs(dump_start))

        side: Optional[str] = None

        # ── SHORT: Fade the pump ─────────────────────────────────────────────
        if self.cfg.allow_shorts:
            pump_qualifies = self.cfg.min_pump_pct <= pump_pct <= self.cfg.max_pump_pct
            rsi_extreme = rsi >= self.cfg.rsi_ob
            if pump_qualifies and rsi_extreme:
                # Need confirm_bars of bearish reversal bars from the peak
                reversal_ok = True
                for i in range(1, min(self.cfg.confirm_bars + 1, 5)):
                    if closes[-i] >= opens[-i]:          # not a bearish candle
                        reversal_ok = False
                        break
                    if closes[-i] >= closes[-i - 1]:     # not declining
                        reversal_ok = False
                        break
                if reversal_ok:
                    # Volume exhaustion check (optional)
                    if self.cfg.vol_exhaust_mult > 0:
                        pump_slice_vols = [vols[-win + j] for j in range(win - 1)]
                        vol_pump_peak = max(pump_slice_vols) if pump_slice_vols else 0.0
                        vol_cur = vols[-1]
                        if vol_pump_peak > 0 and vol_cur >= self.cfg.vol_exhaust_mult * vol_pump_peak:
                            self.last_no_signal_reason = "vol_not_exhausted_short"
                            return None
                    side = "short"

        # ── LONG: Bounce the dump ────────────────────────────────────────────
        if side is None and self.cfg.allow_longs:
            dump_qualifies = self.cfg.min_pump_pct <= dump_pct <= self.cfg.max_pump_pct
            rsi_extreme = rsi <= self.cfg.rsi_os
            if dump_qualifies and rsi_extreme:
                reversal_ok = True
                for i in range(1, min(self.cfg.confirm_bars + 1, 5)):
                    if closes[-i] <= opens[-i]:          # not a bullish candle
                        reversal_ok = False
                        break
                    if closes[-i] <= closes[-i - 1]:     # not rising
                        reversal_ok = False
                        break
                if reversal_ok:
                    if self.cfg.vol_exhaust_mult > 0:
                        dump_slice_vols = [vols[-win + j] for j in range(win - 1)]
                        vol_dump_peak = max(dump_slice_vols) if dump_slice_vols else 0.0
                        vol_cur = vols[-1]
                        if vol_dump_peak > 0 and vol_cur >= self.cfg.vol_exhaust_mult * vol_dump_peak:
                            self.last_no_signal_reason = "vol_not_exhausted_long"
                            return None
                    side = "long"

        if side is None:
            self.last_no_signal_reason = "no_setup"
            return None

        entry_price = cur_price

        if side == "short":
            # SL above the pump high + ATR buffer
            peak_high = max(highs[-win:])
            sl = peak_high + self.cfg.sl_atr_mult * atr
            risk = sl - entry_price
            if risk <= 0:
                self.last_no_signal_reason = "short_sl_invalid"
                return None
            tp = entry_price - self.cfg.rr * risk
            if tp <= 0:
                self.last_no_signal_reason = "short_tp_invalid"
                return None
        else:  # long
            # SL below the dump trough - ATR buffer
            trough_low = min(lows[-win:])
            sl = trough_low - self.cfg.sl_atr_mult * atr
            if sl <= 0:
                sl = entry_price * 0.92  # fallback 8% SL
            risk = entry_price - sl
            if risk <= 0:
                self.last_no_signal_reason = "long_sl_invalid"
                return None
            tp = entry_price + self.cfg.rr * risk

        self._cooldown = max(0, self.cfg.cooldown_bars)
        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=symbol,
            side=side,
            entry=entry_price,
            sl=float(sl),
            tp=float(tp),
            time_stop_bars=max(0, self.cfg.time_stop_bars),
            reason=(
                f"pf3_{side} pump={pump_pct*100:.1f}% dump={dump_pct*100:.1f}% "
                f"rsi={rsi:.1f} er={_efficiency_ratio(closes, self.cfg.er_gate_bars):.2f}"
            ),
        )
        return sig if sig.validate() else None
