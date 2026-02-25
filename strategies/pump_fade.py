#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from .signals import TradeSignal


def ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e




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
    if v is None or not str(v).strip():
        return default
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "on"}


def _env_float_list(name: str, default: List[float]) -> List[float]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return list(default)
    out: List[float] = []
    for part in str(raw).split(","):
        s = part.strip()
        if not s:
            continue
        try:
            out.append(float(s))
        except Exception:
            return list(default)
    return out or list(default)


def _env_csv_set(name: str) -> set[str]:
    raw = os.getenv(name, "") or ""
    return {p.strip().upper() for p in str(raw).split(",") if p.strip()}


def _atr_last(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        hi = highs[i]
        lo = lows[i]
        pc = closes[i - 1]
        tr = max(hi - lo, abs(hi - pc), abs(lo - pc))
        trs.append(max(0.0, tr))
    return sum(trs) / float(period) if trs else float("nan")


def rsi(values: List[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        ch = values[i] - values[i - 1]
        if ch > 0:
            gains += ch
        else:
            losses -= ch
    if gains == 0 and losses == 0:
        return 50.0
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class PumpFadeConfig:
    interval_min: int = 5
    pump_window_min: int = 60  # lookback window to detect the pump
    pump_threshold_pct: float = 0.08  # +8% within the window
    rsi_overbought: float = 75.0
    ema_period: int = 9
    peak_lookback_min: int = 30

    stop_buffer_pct: float = 0.0025  # +0.25% above peak for shorts
    rr: float = 1.6

    cooldown_bars: int = 24  # don't re-enter for N bars after a trade
    entry_max_drop_pct: float = 0.08  # reject entries too late from pump peak
    entry_min_drop_pct: float = 0.005  # reject ultra-early entries before actual pullback
    reversal_body_min_frac: float = 0.45  # candle body / candle range
    confirm_bars: int = 2  # require N bearish confirmation bars
    time_stop_bars: int = 48
    trailing_atr_mult: float = 1.4
    trailing_atr_period: int = 14
    partial_rs: Optional[List[float]] = None
    partial_fracs: Optional[List[float]] = None
    spike_only: bool = False
    spike_threshold_pct: float = 0.10
    spike_last_leg_bars: int = 6
    spike_last_leg_min_pct: float = 0.025
    use_exhaustion_filter: bool = True
    exhaustion_body_to_wick_max: float = 0.35
    exhaustion_vol_drop_ratio: float = 0.75
    strong_pump_threshold_pct: float = 0.12
    strong_entry_min_drop_pct: float = 0.002
    rsi_override_enable: bool = True
    rsi_override_pump_pct: float = 0.14
    rsi_override_leg_pct: float = 0.040
    # PF v3: peak -> loss of momentum -> short re-entry
    v3_enable: bool = False
    v3_pump_threshold_pct: float = 0.09
    v3_peak_recent_bars: int = 14
    v3_min_drop_pct: float = 0.006
    v3_max_drop_pct: float = 0.085
    v3_rsi_peak_min: float = 74.0
    v3_rsi_reentry_max: float = 60.0
    v3_reversal_bars: int = 2
    v3_reversal_body_min_frac: float = 0.30
    v3_peak_vol_mult: float = 1.20
    v3_vol_fade_ratio: float = 0.80
    v3_rr: float = 1.7
    v3_sl_buffer_pct: float = 0.0020


class PumpFadeStrategy:
    """Shorts a *sharp pump* after first meaningful reversal.

    This is intentionally conservative and designed for backtesting.
    You can harden it later (VWAP filters, liquidity filters, etc.).
    """

    def __init__(self, cfg: Optional[PumpFadeConfig] = None):
        self.cfg = cfg or PumpFadeConfig()
        self._allow = _env_csv_set("PF_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("PF_SYMBOL_DENYLIST")

        # Optional env overrides for fast parameter sweeps in portfolio backtests
        self.cfg.interval_min = _env_int("PF_INTERVAL_MIN", self.cfg.interval_min)
        self.cfg.pump_window_min = _env_int("PF_PUMP_WINDOW_MIN", self.cfg.pump_window_min)
        self.cfg.pump_threshold_pct = _env_float("PF_PUMP_THRESHOLD_PCT", self.cfg.pump_threshold_pct)
        self.cfg.rsi_overbought = _env_float("PF_RSI_OVERBOUGHT", self.cfg.rsi_overbought)
        self.cfg.ema_period = _env_int("PF_EMA_PERIOD", self.cfg.ema_period)
        self.cfg.peak_lookback_min = _env_int("PF_PEAK_LOOKBACK_MIN", self.cfg.peak_lookback_min)
        self.cfg.stop_buffer_pct = _env_float("PF_STOP_BUFFER_PCT", self.cfg.stop_buffer_pct)
        self.cfg.rr = _env_float("PF_RR", self.cfg.rr)
        self.cfg.cooldown_bars = _env_int("PF_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.entry_max_drop_pct = _env_float("PF_ENTRY_MAX_DROP_PCT", self.cfg.entry_max_drop_pct)
        self.cfg.entry_min_drop_pct = _env_float("PF_ENTRY_MIN_DROP_PCT", self.cfg.entry_min_drop_pct)
        self.cfg.reversal_body_min_frac = _env_float("PF_REVERSAL_BODY_MIN_FRAC", self.cfg.reversal_body_min_frac)
        self.cfg.confirm_bars = _env_int("PF_CONFIRM_BARS", self.cfg.confirm_bars)
        self.cfg.time_stop_bars = _env_int("PF_TIME_STOP_BARS", self.cfg.time_stop_bars)
        self.cfg.trailing_atr_mult = _env_float("PF_TRAIL_ATR_MULT", self.cfg.trailing_atr_mult)
        self.cfg.trailing_atr_period = _env_int("PF_TRAIL_ATR_PERIOD", self.cfg.trailing_atr_period)
        self.cfg.partial_rs = _env_float_list("PF_PARTIAL_RS", [0.9, 1.8, 3.0])
        self.cfg.partial_fracs = _env_float_list("PF_PARTIAL_FRACS", [0.40, 0.30, 0.30])
        self.cfg.spike_only = _env_bool("PF_SPIKE_ONLY", self.cfg.spike_only)
        self.cfg.spike_threshold_pct = _env_float("PF_SPIKE_THRESHOLD_PCT", self.cfg.spike_threshold_pct)
        self.cfg.spike_last_leg_bars = _env_int("PF_SPIKE_LAST_LEG_BARS", self.cfg.spike_last_leg_bars)
        self.cfg.spike_last_leg_min_pct = _env_float("PF_SPIKE_LAST_LEG_MIN_PCT", self.cfg.spike_last_leg_min_pct)
        self.cfg.use_exhaustion_filter = _env_bool("PF_USE_EXHAUSTION_FILTER", self.cfg.use_exhaustion_filter)
        self.cfg.exhaustion_body_to_wick_max = _env_float(
            "PF_EXHAUSTION_BODY_TO_WICK_MAX", self.cfg.exhaustion_body_to_wick_max
        )
        self.cfg.exhaustion_vol_drop_ratio = _env_float(
            "PF_EXHAUSTION_VOL_DROP_RATIO", self.cfg.exhaustion_vol_drop_ratio
        )
        self.cfg.strong_pump_threshold_pct = _env_float(
            "PF_STRONG_PUMP_THRESHOLD_PCT", self.cfg.strong_pump_threshold_pct
        )
        self.cfg.strong_entry_min_drop_pct = _env_float(
            "PF_STRONG_ENTRY_MIN_DROP_PCT", self.cfg.strong_entry_min_drop_pct
        )
        self.cfg.rsi_override_enable = _env_bool("PF_RSI_OVERRIDE_ENABLE", self.cfg.rsi_override_enable)
        self.cfg.rsi_override_pump_pct = _env_float("PF_RSI_OVERRIDE_PUMP_PCT", self.cfg.rsi_override_pump_pct)
        self.cfg.rsi_override_leg_pct = _env_float("PF_RSI_OVERRIDE_LEG_PCT", self.cfg.rsi_override_leg_pct)
        self.cfg.v3_enable = _env_bool("PF_V3_ENABLE", self.cfg.v3_enable)
        self.cfg.v3_pump_threshold_pct = _env_float("PF_V3_PUMP_THRESHOLD_PCT", self.cfg.v3_pump_threshold_pct)
        self.cfg.v3_peak_recent_bars = _env_int("PF_V3_PEAK_RECENT_BARS", self.cfg.v3_peak_recent_bars)
        self.cfg.v3_min_drop_pct = _env_float("PF_V3_MIN_DROP_PCT", self.cfg.v3_min_drop_pct)
        self.cfg.v3_max_drop_pct = _env_float("PF_V3_MAX_DROP_PCT", self.cfg.v3_max_drop_pct)
        self.cfg.v3_rsi_peak_min = _env_float("PF_V3_RSI_PEAK_MIN", self.cfg.v3_rsi_peak_min)
        self.cfg.v3_rsi_reentry_max = _env_float("PF_V3_RSI_REENTRY_MAX", self.cfg.v3_rsi_reentry_max)
        self.cfg.v3_reversal_bars = _env_int("PF_V3_REVERSAL_BARS", self.cfg.v3_reversal_bars)
        self.cfg.v3_reversal_body_min_frac = _env_float(
            "PF_V3_REVERSAL_BODY_MIN_FRAC", self.cfg.v3_reversal_body_min_frac
        )
        self.cfg.v3_peak_vol_mult = _env_float("PF_V3_PEAK_VOL_MULT", self.cfg.v3_peak_vol_mult)
        self.cfg.v3_vol_fade_ratio = _env_float("PF_V3_VOL_FADE_RATIO", self.cfg.v3_vol_fade_ratio)
        self.cfg.v3_rr = _env_float("PF_V3_RR", self.cfg.v3_rr)
        self.cfg.v3_sl_buffer_pct = _env_float("PF_V3_SL_BUFFER_PCT", self.cfg.v3_sl_buffer_pct)

        if not self.cfg.partial_rs:
            self.cfg.partial_rs = [self.cfg.rr]
        if len(self.cfg.partial_fracs or []) != len(self.cfg.partial_rs):
            self.cfg.partial_fracs = [1.0 / float(len(self.cfg.partial_rs))] * len(self.cfg.partial_rs)

        fr_sum = sum(self.cfg.partial_fracs or [])
        if fr_sum > 1.000001:
            self.cfg.partial_fracs = [x / fr_sum for x in (self.cfg.partial_fracs or [1.0])]

        self._opens: List[float] = []
        self._closes: List[float] = []
        self._highs: List[float] = []
        self._lows: List[float] = []
        self._volumes: List[float] = []
        self._cooldown: int = 0
        self._pumped_flag: bool = False
        self._skip_reasons: Dict[str, int] = {}
        self._signals_emitted: int = 0

    def _emit_short_signal(self, symbol: str, *, entry: float, peak_high: float, stop_buffer_pct: float, rr: float, move_pct: float) -> Optional[TradeSignal]:
        sl = peak_high * (1.0 + float(stop_buffer_pct))
        if sl <= entry:
            self._mark_skip("INVALID_SL_LEVEL", reset_pumped=True)
            return None
        risk = (sl - entry)
        if risk <= 0:
            self._mark_skip("NON_POSITIVE_RISK", reset_pumped=True)
            return None

        tps: List[float] = []
        for r in (self.cfg.partial_rs or [rr]):
            tpv = entry - float(r) * risk
            if tpv > 0:
                tps.append(float(tpv))
        if not tps:
            self._mark_skip("NO_VALID_TPS", reset_pumped=True)
            return None
        tps = sorted(set(tps), reverse=True)
        tp = float(tps[-1])

        atr_now = _atr_last(self._highs, self._lows, self._closes, max(5, int(self.cfg.trailing_atr_period)))
        trail_mult = float(self.cfg.trailing_atr_mult) if math.isfinite(atr_now) and atr_now > 0 else 0.0

        self._cooldown = self.cfg.cooldown_bars
        self._pumped_flag = False

        sig = TradeSignal(
            strategy="pump_fade",
            symbol=symbol,
            side="short",
            entry=entry,
            sl=sl,
            tp=tp,
            tps=tps,
            tp_fracs=self.cfg.partial_fracs,
            trailing_atr_mult=trail_mult,
            trailing_atr_period=max(5, int(self.cfg.trailing_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars)),
            reason=f"pump {move_pct*100:.1f}%/{self.cfg.pump_window_min}m fade",
        )
        if sig.validate():
            self._signals_emitted += 1
            return sig
        self._mark_skip("INVALID_SIGNAL_OBJECT")
        return None

    def _on_bar_v3(self, symbol: str, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        bars_in_window = max(4, int(self.cfg.pump_window_min / self.cfg.interval_min))
        if len(self._closes) < bars_in_window + 8:
            self._mark_skip("V3_HISTORY_SHORT")
            return None

        closes_w = self._closes[-bars_in_window:]
        highs_w = self._highs[-bars_in_window:]
        vols_w = self._volumes[-bars_in_window:]
        base = self._closes[-bars_in_window - 1]
        if base <= 0:
            self._mark_skip("V3_INVALID_BASE_PRICE")
            return None

        peak_high = max(highs_w)
        peak_idx = highs_w.index(peak_high)
        peak_age = bars_in_window - 1 - peak_idx
        if peak_age > max(2, int(self.cfg.v3_peak_recent_bars)):
            self._mark_skip("V3_PEAK_TOO_OLD")
            return None
        move_pct = (peak_high / base) - 1.0
        if move_pct < float(self.cfg.v3_pump_threshold_pct):
            self._mark_skip("V3_NO_PUMP")
            return None

        if peak_high <= 0:
            self._mark_skip("V3_INVALID_PEAK")
            return None
        peak_drop = (peak_high - c) / peak_high
        if peak_drop < float(self.cfg.v3_min_drop_pct):
            self._mark_skip("V3_ENTRY_TOO_EARLY")
            return None
        if peak_drop > float(self.cfg.v3_max_drop_pct):
            self._mark_skip("V3_ENTRY_TOO_LATE")
            return None

        ema_now = ema(self._closes[-(self.cfg.ema_period * 4):], self.cfg.ema_period)
        if not (math.isfinite(ema_now) and c < ema_now):
            self._mark_skip("V3_EMA_NOT_BEARISH")
            return None

        rsi_now = rsi(self._closes, 14)
        if not math.isfinite(rsi_now):
            self._mark_skip("V3_RSI_NAN")
            return None

        # RSI at/near peak should be overheated. If exact index is not enough history, fallback to max recent RSI.
        rsi_peak = float("nan")
        try:
            abs_peak_idx = len(self._closes) - bars_in_window + peak_idx
            if abs_peak_idx >= 15:
                rsi_peak = rsi(self._closes[:abs_peak_idx + 1], 14)
        except Exception:
            rsi_peak = float("nan")
        if not math.isfinite(rsi_peak):
            vals: List[float] = []
            for i in range(max(15, len(self._closes) - 10), len(self._closes) + 1):
                rv = rsi(self._closes[:i], 14)
                if math.isfinite(rv):
                    vals.append(float(rv))
            rsi_peak = max(vals) if vals else float("nan")

        if not (math.isfinite(rsi_peak) and rsi_peak >= float(self.cfg.v3_rsi_peak_min)):
            self._mark_skip("V3_RSI_PEAK_LOW")
            return None
        if rsi_now > float(self.cfg.v3_rsi_reentry_max):
            self._mark_skip("V3_RSI_REENTRY_HIGH")
            return None

        # Reversal bars: bearish closes with meaningful body.
        rev_n = max(1, int(self.cfg.v3_reversal_bars))
        if len(self._opens) < rev_n + 1 or len(self._closes) < rev_n + 1:
            self._mark_skip("V3_REV_HISTORY_SHORT")
            return None
        for i in range(1, rev_n + 1):
            oi = self._opens[-i]
            ci = self._closes[-i]
            hi = self._highs[-i]
            li = self._lows[-i]
            rng = max(1e-12, hi - li)
            body_frac = abs(ci - oi) / rng
            if not (ci < oi and body_frac >= float(self.cfg.v3_reversal_body_min_frac)):
                self._mark_skip("V3_REVERSAL_FAIL")
                return None

        # Peak volume climax then fade.
        vol_avg = sum(vols_w) / float(len(vols_w)) if vols_w else 0.0
        peak_vol = vols_w[peak_idx] if peak_idx < len(vols_w) else 0.0
        if vol_avg > 0 and peak_vol < vol_avg * float(self.cfg.v3_peak_vol_mult):
            self._mark_skip("V3_PEAK_VOL_WEAK")
            return None
        if peak_vol > 0 and self._volumes[-1] > peak_vol * float(self.cfg.v3_vol_fade_ratio):
            self._mark_skip("V3_VOL_NOT_FADED")
            return None

        return self._emit_short_signal(
            symbol,
            entry=float(c),
            peak_high=float(peak_high),
            stop_buffer_pct=float(self.cfg.v3_sl_buffer_pct),
            rr=float(self.cfg.v3_rr),
            move_pct=float(move_pct),
        )

    def _mark_skip(self, reason: str, *, reset_pumped: bool = False) -> None:
        key = str(reason or "UNKNOWN").strip().upper()
        if not key:
            key = "UNKNOWN"
        self._skip_reasons[key] = int(self._skip_reasons.get(key, 0)) + 1
        if reset_pumped:
            self._pumped_flag = False

    def skip_reason_stats(self) -> Dict[str, int]:
        return dict(self._skip_reasons)

    def signals_emitted(self) -> int:
        return int(self._signals_emitted)

    def on_bar(self, symbol: str, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        sym_u = str(symbol or "").upper()
        if self._allow and sym_u not in self._allow:
            self._mark_skip("ALLOWLIST_REJECT")
            return None
        if sym_u in self._deny:
            self._mark_skip("DENYLIST_REJECT")
            return None

        self._opens.append(o)
        self._closes.append(c)
        self._highs.append(h)
        self._lows.append(l)
        self._volumes.append(max(0.0, float(v or 0.0)))

        if self.cfg.v3_enable:
            return self._on_bar_v3(symbol, o, h, l, c, v)

        if self._cooldown > 0:
            self._cooldown -= 1
            self._mark_skip("COOLDOWN_ACTIVE")
            return None

        # need enough history
        bars_in_window = max(1, int(self.cfg.pump_window_min / self.cfg.interval_min))
        if len(self._closes) < bars_in_window + 2:
            self._mark_skip("HISTORY_SHORT")
            return None

        base = self._closes[-bars_in_window - 1]
        if base <= 0:
            self._mark_skip("INVALID_BASE_PRICE")
            return None
        window_high = max(self._highs[-bars_in_window:]) if len(self._highs) >= bars_in_window else c
        move_ref = max(c, window_high)
        move_pct = (move_ref / base) - 1.0
        leg_bars = max(1, int(self.cfg.spike_last_leg_bars))
        if len(self._closes) > leg_bars and len(self._highs) > leg_bars:
            leg_base = self._closes[-leg_bars - 1]
            leg_peak = max(self._highs[-leg_bars:])
            leg_ref = max(c, leg_peak)
            leg_pct = ((leg_ref / leg_base) - 1.0) if leg_base > 0 else 0.0
        else:
            leg_pct = 0.0

        # Pump detection
        if move_pct >= self.cfg.pump_threshold_pct:
            self._pumped_flag = True

        if not self._pumped_flag:
            self._mark_skip("NO_PUMP_DETECTED")
            return None

        if self.cfg.spike_only:
            if not (move_pct >= self.cfg.spike_threshold_pct and leg_pct >= self.cfg.spike_last_leg_min_pct):
                self._mark_skip("SPIKE_ONLY_GATE")
                return None

        # Reversal confirmation: pump + overbought + near peak + bearish confirmation
        ema_now = ema(self._closes[-(self.cfg.ema_period * 4):], self.cfg.ema_period)
        rsi_now = rsi(self._closes, 14)

        peak_bars = max(2, int(self.cfg.peak_lookback_min / self.cfg.interval_min))
        peak_high = max(self._highs[-peak_bars:])

        # if price already collapsed too far, skip (avoid late entries)
        if peak_high <= 0:
            self._mark_skip("INVALID_PEAK_HIGH", reset_pumped=True)
            return None
        peak_drop = (peak_high - c) / peak_high
        if peak_drop > self.cfg.entry_max_drop_pct:
            self._mark_skip("ENTRY_TOO_LATE", reset_pumped=True)
            return None
        min_drop_needed = float(self.cfg.entry_min_drop_pct)
        if move_pct >= float(self.cfg.strong_pump_threshold_pct):
            min_drop_needed = min(min_drop_needed, float(self.cfg.strong_entry_min_drop_pct))
        if peak_drop < min_drop_needed:
            self._mark_skip("ENTRY_TOO_EARLY")
            return None

        rsi_ok = bool(rsi_now >= self.cfg.rsi_overbought)
        rsi_override = bool(
            self.cfg.rsi_override_enable
            and move_pct >= float(self.cfg.rsi_override_pump_pct)
            and leg_pct >= float(self.cfg.rsi_override_leg_pct)
        )
        if not (rsi_ok or rsi_override):
            self._mark_skip("RSI_NOT_OVERBOUGHT")
            return None

        # Exhaustion filter (custom-indicators aligned):
        # accept reversal only when the latest bar shows either:
        # - weak body vs upper wick (buyers exhausted), or
        # - visible volume fade vs previous bar.
        if self.cfg.use_exhaustion_filter and len(self._opens) >= 2 and len(self._volumes) >= 2:
            o1, c1, h1 = self._opens[-1], self._closes[-1], self._highs[-1]
            body = abs(c1 - o1)
            upper_wick = max(0.0, h1 - max(o1, c1))
            weak_body = upper_wick > 0 and body <= self.cfg.exhaustion_body_to_wick_max * upper_wick

            v_prev = max(1e-12, self._volumes[-2])
            v_now = self._volumes[-1]
            vol_fade = v_now <= (v_prev * self.cfg.exhaustion_vol_drop_ratio)

            if not (weak_body or vol_fade):
                self._mark_skip("EXHAUSTION_NOT_CONFIRMED")
                return None

        # Reversal trigger.
        # 1) close under EMA
        # 2) last N bars are bearish with meaningful body
        # 3) close structure is non-increasing across confirmations
        confirm_n = max(1, int(self.cfg.confirm_bars))
        if len(self._closes) < confirm_n + 1 or len(self._opens) < confirm_n:
            self._mark_skip("CONFIRM_HISTORY_SHORT")
            return None
        if not (math.isfinite(ema_now) and c < ema_now):
            self._mark_skip("EMA_REVERSAL_NOT_CONFIRMED")
            return None

        bearish_ok = True
        for i in range(1, confirm_n + 1):
            oi = self._opens[-i]
            ci = self._closes[-i]
            hi = self._highs[-i]
            li = self._lows[-i]
            rng = max(1e-12, hi - li)
            body_frac = abs(ci - oi) / rng
            if not (ci < oi and body_frac >= self.cfg.reversal_body_min_frac):
                bearish_ok = False
                break
            if i > 1 and self._closes[-i] < self._closes[-(i - 1)]:
                bearish_ok = False
                break
        if not bearish_ok:
            self._mark_skip("BEARISH_CONFIRM_FAIL")
            return None

        sig = self._emit_short_signal(
            symbol,
            entry=float(c),
            peak_high=float(peak_high),
            stop_buffer_pct=float(self.cfg.stop_buffer_pct),
            rr=float(self.cfg.rr),
            move_pct=float(move_pct),
        )
        if sig is not None:
            sig.reason = f"pump {move_pct*100:.1f}%/{self.cfg.pump_window_min}m leg={leg_pct*100:.1f}% then reversal;confirm={confirm_n}"
        return sig

        return None

    # Backwards-compatibility: backtest.run_month calls `maybe_signal(symbol, ts_ms, o, h, l, c, v)`.
    # We keep `on_bar(symbol, o, h, l, c)` as the canonical method.
    def maybe_signal(
        self,
        symbol: str,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = ts_ms
        return self.on_bar(symbol, o, h, l, c, v)
