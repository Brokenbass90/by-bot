"""
scalper_sweep_v2 (SS2) — Strict liquidity-sweep + reverse strategy.

Полный rewrite SC1.sweep mode. Главные отличия:

  • **Sweep depth filter**: проникновение за pivot должно быть ≥ 0.3 ATR
    (не марginal break of a few ticks). True stop-hunt = decisive penetration.
  • **Reverse confirmation**: reverse close должен быть ≥ 0.4 ATR обратно
    в противоположную сторону от sweep extreme.
  • **Volume z ≥ 3.0** на sweep candle (true stop-hunt = volume spike)
  • **HTF reverse alignment**: 1H EMA21 ДОЛЖНА быть В сторону reverse
    (sweep + reverse = HTF trend wins; we trade with HTF)
  • **No early exits**: TP1 1.8R, TP2 3.5R (sweep moves are larger)

Дизайн-цель: PF ≥ 1.6, DD ≤ 6%, 15-30 трейдов/мес — exotic setup,
редкий но качественный.

Env vars (префикс SS2_)
-----------------------
  SS2_SYMBOL_ALLOWLIST           csv     BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT
  SS2_SIGNAL_TF                  str     5
  SS2_MACRO_TF                   str     60
  SS2_SIGNAL_LOOKBACK            int     200
  SS2_ATR_PERIOD                 int     14
  SS2_SWEEP_LOOKBACK             int     30
  SS2_MIN_SWEEP_DEPTH_ATR        float   0.30
  SS2_MIN_REVERSE_DEPTH_ATR      float   0.40
  SS2_VOL_Z_MIN                  float   3.00
  SS2_MACRO_EMA_PERIOD           int     21
  SS2_MIN_MACRO_SLOPE_PCT        float   0.20
  SS2_MACRO_SLOPE_BARS           int     8
  SS2_MIN_ATR_PCT                float   0.25
  SS2_MAX_ATR_PCT                float   3.00
  SS2_SL_ATR_BUFFER              float   0.30
  SS2_TP1_RR                     float   1.80
  SS2_TP2_RR                     float   3.50
  SS2_TP1_FRAC                   float   0.50
  SS2_BE_TRIGGER_RR              float   1.00
  SS2_TIME_STOP_BARS_5M          int     60
  SS2_COOLDOWN_BARS_5M           int     36
  SS2_ALLOW_LONGS                bool    1
  SS2_ALLOW_SHORTS               bool    1

Author: Claude Opus, 2026-06-03. Rewrite of SC1.sweep — depth + HTF alignment.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return values[:]
    k = 2.0 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs[-period:]) / period


def _vol_zscore(volumes: List[float], baseline_period: int = 40, recent_n: int = 1) -> float:
    if len(volumes) < baseline_period + recent_n:
        return 0.0
    base = volumes[-baseline_period - recent_n:-recent_n]
    recent = volumes[-recent_n:]
    if not base:
        return 0.0
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    return ((sum(recent) / len(recent)) - mean) / std


def _slope_pct_per_bar(values: List[float], lookback: int, price_ref: float) -> float:
    if lookback <= 0 or len(values) < lookback + 1 or price_ref <= 0:
        return 0.0
    return ((values[-1] - values[-lookback - 1]) / price_ref) * 100.0 / lookback


@dataclass
class SS2Config:
    signal_tf: str = "5"
    macro_tf: str = "60"
    signal_lookback: int = 200
    atr_period: int = 14
    sweep_lookback: int = 30
    min_sweep_depth_atr: float = 0.30
    min_reverse_depth_atr: float = 0.40
    vol_z_min: float = 3.00
    macro_ema_period: int = 21
    min_macro_slope_pct: float = 0.20
    macro_slope_bars: int = 8
    min_atr_pct: float = 0.25
    max_atr_pct: float = 3.00
    sl_atr_buffer: float = 0.30
    tp1_rr: float = 1.80
    tp2_rr: float = 3.50
    tp1_frac: float = 0.50
    be_trigger_rr: float = 1.00
    time_stop_bars_5m: int = 60
    cooldown_bars_5m: int = 36
    allow_longs: bool = True
    allow_shorts: bool = True


class ScalperSweepV2Strategy:
    """Strict liquidity sweep with depth filter + HTF reverse alignment."""

    def __init__(self) -> None:
        self.cfg = SS2Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self.last_no_signal_reason: str = ""
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = str(reason or "unknown")

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("SS2_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("SS2_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("SS2_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("SS2_ATR_PERIOD", c.atr_period)
        c.sweep_lookback = _env_int("SS2_SWEEP_LOOKBACK", c.sweep_lookback)
        c.min_sweep_depth_atr = _env_float("SS2_MIN_SWEEP_DEPTH_ATR", c.min_sweep_depth_atr)
        c.min_reverse_depth_atr = _env_float("SS2_MIN_REVERSE_DEPTH_ATR", c.min_reverse_depth_atr)
        c.vol_z_min = _env_float("SS2_VOL_Z_MIN", c.vol_z_min)
        c.macro_ema_period = _env_int("SS2_MACRO_EMA_PERIOD", c.macro_ema_period)
        c.min_macro_slope_pct = _env_float("SS2_MIN_MACRO_SLOPE_PCT", c.min_macro_slope_pct)
        c.macro_slope_bars = _env_int("SS2_MACRO_SLOPE_BARS", c.macro_slope_bars)
        c.min_atr_pct = _env_float("SS2_MIN_ATR_PCT", c.min_atr_pct)
        c.max_atr_pct = _env_float("SS2_MAX_ATR_PCT", c.max_atr_pct)
        c.sl_atr_buffer = _env_float("SS2_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("SS2_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("SS2_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("SS2_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("SS2_BE_TRIGGER_RR", c.be_trigger_rr)
        c.time_stop_bars_5m = _env_int("SS2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("SS2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("SS2_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("SS2_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set("SS2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT")
        self._deny = _env_csv_set("SS2_SYMBOL_DENYLIST")

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, cl: float, v: float = 0.0) -> Optional[TradeSignal]:
        self.last_no_signal_reason = ""
        symbol = getattr(store, "symbol", "")
        c = self.cfg

        if self._allow and symbol.upper() not in self._allow:
            self._no_signal("symbol_not_allowed"); return None
        if self._deny and symbol.upper() in self._deny:
            self._no_signal("symbol_denied"); return None
        if not c.allow_shorts and not c.allow_longs:
            self._no_signal("both_sides_disabled"); return None
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar"); return None
        if self._cooldown > 0:
            self._cooldown -= 1; self._no_signal("cooldown"); return None

        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
            rows_macro = store.fetch_klines(symbol, c.macro_tf, 80) or []
        except Exception:
            self._no_signal("history_short"); return None

        if len(rows_5m) < c.sweep_lookback + 30 or len(rows_macro) < c.macro_ema_period + c.macro_slope_bars + 5:
            self._no_signal("history_short"); return None

        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]
        closes_macro = [float(r[4]) for r in rows_macro]

        atr = _atr(highs5, lows5, closes5, c.atr_period)
        price = closes5[-1]
        if atr <= 0 or price <= 0:
            self._no_signal("atr_invalid"); return None
        atr_pct = (atr / price) * 100.0
        if atr_pct < c.min_atr_pct:
            self._no_signal(f"atr_too_low={atr_pct:.3f}"); return None
        if atr_pct > c.max_atr_pct:
            self._no_signal(f"atr_too_high={atr_pct:.3f}"); return None

        vol_z = _vol_zscore(volumes5, baseline_period=40, recent_n=1)
        if vol_z < c.vol_z_min:
            self._no_signal(f"vol_z_low={vol_z:.2f}"); return None

        macro_ema = _ema_series(closes_macro, c.macro_ema_period)
        macro_slope = _slope_pct_per_bar(macro_ema, c.macro_slope_bars, price)

        prior_highs = highs5[-c.sweep_lookback - 1:-1]
        prior_lows = lows5[-c.sweep_lookback - 1:-1]
        if not prior_highs or not prior_lows:
            self._no_signal("history_short"); return None
        prior_max_high = max(prior_highs)
        prior_min_low = min(prior_lows)
        cur_high = highs5[-1]
        cur_low = lows5[-1]
        cur_close = closes5[-1]

        # LONG sweep: low spiked below prior_min_low by ≥ depth, close back above by ≥ reverse_depth
        if c.allow_longs and macro_slope >= c.min_macro_slope_pct:
            sweep_depth = prior_min_low - cur_low
            reverse_depth = cur_close - prior_min_low
            if sweep_depth >= c.min_sweep_depth_atr * atr and reverse_depth >= c.min_reverse_depth_atr * atr:
                sl = cur_low - c.sl_atr_buffer * atr
                entry = cur_close
                risk = entry - sl
                if risk > 0:
                    tp1 = entry + c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="scalper_sweep_v2",
                        symbol=symbol, side="long", entry=entry, sl=sl, tp=tp1,
                        reason=(f"ss2_sweep_long pivot={prior_min_low:.6f} sweep={sweep_depth/atr:.2f}atr "
                                f"reverse={reverse_depth/atr:.2f}atr vol_z={vol_z:.2f} macro_slope={macro_slope:.3f}"),
                    )

        # SHORT sweep: high spiked above prior_max_high by ≥ depth, close back below
        if c.allow_shorts and macro_slope <= -c.min_macro_slope_pct:
            sweep_depth = cur_high - prior_max_high
            reverse_depth = prior_max_high - cur_close
            if sweep_depth >= c.min_sweep_depth_atr * atr and reverse_depth >= c.min_reverse_depth_atr * atr:
                sl = cur_high + c.sl_atr_buffer * atr
                entry = cur_close
                risk = sl - entry
                if risk > 0:
                    tp1 = entry - c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="scalper_sweep_v2",
                        symbol=symbol, side="short", entry=entry, sl=sl, tp=tp1,
                        reason=(f"ss2_sweep_short pivot={prior_max_high:.6f} sweep={sweep_depth/atr:.2f}atr "
                                f"reverse={reverse_depth/atr:.2f}atr vol_z={vol_z:.2f} macro_slope={macro_slope:.3f}"),
                    )

        self._no_signal("no_setup")
        return None


class SS2Selector:
    def __init__(self):
        self._strategies: dict[str, ScalperSweepV2Strategy] = {}

    def get(self, symbol: str) -> ScalperSweepV2Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ScalperSweepV2Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
