"""alt_bear_regime_continuation_v1 — short trend-follow для bear / dead market.

ПОЛЬЗОВАТЕЛЬСКАЯ ИДЕЯ:
  «Когда медвежка — открываем шорт в продолжение тренда, ловим маленькие
   корректировки в pullback к EMA. Когда рынок развернётся в бычку —
   автоматически отключаемся и ждём.»

Логика:

Регим-gate (КРИТИЧНО):
  Активна ТОЛЬКО если regime ∈ {bear_chop, bear_trend}.
  В bull-режимах signal() сразу возвращает None.

Trend confirmation:
  • EMA20 на 1H ниже EMA50 (downtrend на хайтайме)
  • close < EMA20 на 5m (текущая цена ниже краткосрочной EMA)
  • НЕ требуем strong slope — работаем и в chop с слегка нисходящим bias

Pullback entry (SHORT):
  • Был ралли вверх в течение N последних 5m баров (3-6)
  • Текущая свеча показывает rejection: upper_wick ≥ body_floor × 1.2
  • RSI(14) на 5m в зоне 50-70 (overbought отскок, готов идти вниз)
  • close в нижней половине свечи (closer to lows)
  • Объём НЕ должен быть сильно выше среднего (это pullback, не breakdown)

Exit:
  • SL = swing_high recent + sl_pad×ATR (короткий стоп)
  • TP = entry - rr × risk (default RR=1.6 — short hold, мелкие движения)
  • Time stop = TIME_STOP_BARS_5M (default 96 = 8h)
  • Breakeven после TP1 (0.7R)

Symbol allowlist:
  По умолчанию топ ALT'ы (где медвежка наиболее видима): SOLUSDT, ADAUSDT, DOTUSDT, LINKUSDT, AVAXUSDT, SUIUSDT
  Не торгуем BTC/ETH (для них есть btc_eth_midterm).

Env vars (BRC1_):
  BRC1_HTF                   ("60")  — таймфрейм для тренд-фильтра
  BRC1_EMA_FAST              (20)
  BRC1_EMA_SLOW              (50)
  BRC1_PULLBACK_BARS         (4)     — количество восходящих 5m баров для pullback
  BRC1_PULLBACK_MIN_PCT      (0.4)   — pullback должен быть ≥ N% от ATR
  BRC1_RSI_PERIOD            (14)
  BRC1_RSI_MIN               (50)
  BRC1_RSI_MAX               (70)
  BRC1_MIN_REJECT_WICK_RATIO (1.2)
  BRC1_MAX_VOL_MULT          (1.6)   — pullback не должен быть с большим объёмом
  BRC1_VOL_AVG_BARS          (20)
  BRC1_SL_PAD_ATR            (0.20)
  BRC1_RR                    (1.6)
  BRC1_TP1_RR                (0.7)
  BRC1_TP1_FRAC              (0.50)
  BRC1_TIME_STOP_BARS_5M     (96)
  BRC1_COOLDOWN_BARS_5M      (36)    — 3h cooldown per symbol
  BRC1_ATR_PERIOD            (14)
  BRC1_SYMBOL_ALLOWLIST      (SOLUSDT,ADAUSDT,DOTUSDT,LINKUSDT,AVAXUSDT,SUIUSDT)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from .signals import TradeSignal
except ImportError:
    from strategies.signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip(): return default
    try: return float(str(raw).strip())
    except: return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip(): return default
    try: return int(float(str(raw).strip()))
    except: return default


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or default_csv
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _candles_5m(store, symbol: str) -> list:
    if hasattr(store, "c5"):
        return getattr(store, "c5") or []
    if hasattr(store, "candles"):
        return store.candles(symbol)
    return getattr(store, "rows", [])


def _atr(candles: list, period: int) -> float:
    if len(candles) < period + 1: return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h); l = float(candles[i].l); pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / float(len(recent)) if recent else float("nan")


def _ema(values: list[float], period: int) -> float:
    if len(values) < period or period <= 0: return float("nan")
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
    return e


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) < period + 1: return float("nan")
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass
class BRC1Config:
    htf: str = field(default_factory=lambda: _env_str("BRC1_HTF", "60"))
    ema_fast: int = field(default_factory=lambda: _env_int("BRC1_EMA_FAST", 20))
    ema_slow: int = field(default_factory=lambda: _env_int("BRC1_EMA_SLOW", 50))
    pullback_bars: int = field(default_factory=lambda: _env_int("BRC1_PULLBACK_BARS", 4))
    pullback_min_pct: float = field(default_factory=lambda: _env_float("BRC1_PULLBACK_MIN_PCT", 0.4))
    rsi_period: int = field(default_factory=lambda: _env_int("BRC1_RSI_PERIOD", 14))
    rsi_min: float = field(default_factory=lambda: _env_float("BRC1_RSI_MIN", 50))
    rsi_max: float = field(default_factory=lambda: _env_float("BRC1_RSI_MAX", 70))
    min_reject_wick_ratio: float = field(default_factory=lambda: _env_float("BRC1_MIN_REJECT_WICK_RATIO", 1.2))
    max_vol_mult: float = field(default_factory=lambda: _env_float("BRC1_MAX_VOL_MULT", 1.6))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("BRC1_VOL_AVG_BARS", 20))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("BRC1_SL_PAD_ATR", 0.20))
    rr: float = field(default_factory=lambda: _env_float("BRC1_RR", 1.6))
    tp1_rr: float = field(default_factory=lambda: _env_float("BRC1_TP1_RR", 0.7))
    tp1_frac: float = field(default_factory=lambda: _env_float("BRC1_TP1_FRAC", 0.50))
    time_stop_bars: int = field(default_factory=lambda: _env_int("BRC1_TIME_STOP_BARS_5M", 96))
    cooldown_bars: int = field(default_factory=lambda: _env_int("BRC1_COOLDOWN_BARS_5M", 36))
    atr_period: int = field(default_factory=lambda: _env_int("BRC1_ATR_PERIOD", 14))
    symbol_allowlist: set[str] = field(
        default_factory=lambda: _env_csv_set("BRC1_SYMBOL_ALLOWLIST", "SOLUSDT,ADAUSDT,DOTUSDT,LINKUSDT,AVAXUSDT,SUIUSDT")
    )


class AltBearRegimeContinuationV1Strategy:
    NAME = "alt_bear_regime_continuation_v1"

    def __init__(self):
        self.cfg = BRC1Config()
        self._last_signal_i: dict[str, int] = {}
        self._htf_downtrend_cache: dict[tuple[str, str, int, int, int], bool] = {}
        self.last_no_signal_reason = ""

    def signal(self, store, symbol: str, i: int, regime: Optional[str] = None) -> Optional[TradeSignal]:
        cfg = self.cfg

        # ── HARD REGIME GATE — only bear regimes ─────────────────────────────
        if regime is None or regime.upper() not in {"BEAR_CHOP", "BEAR_TREND"}:
            self.last_no_signal_reason = f"regime_not_bear:{regime}"
            return None

        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            self.last_no_signal_reason = "symbol_blocked"
            return None

        candles = _candles_5m(store, symbol)
        need = max(cfg.atr_period + 5, cfg.rsi_period + 5, cfg.vol_avg_bars + 2, cfg.pullback_bars + 5)
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        # Per-symbol cooldown
        last_i = self._last_signal_i.get(symbol, -10**9)
        if i - last_i < cfg.cooldown_bars:
            self.last_no_signal_reason = f"cooldown:{symbol}"
            return None

        atr = _atr(candles[max(0, i - cfg.atr_period - 2): i + 1], cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "bad_atr"
            return None

        # ── HTF trend filter — EMA20 < EMA50 на 1H (downtrend) ───────────────
        htf_rows = []
        htf_ok_cached = None
        try:
            htf_min = max(5, int(float(str(cfg.htf))))
            htf_bucket = max(0, i // max(1, htf_min // 5))
        except Exception:
            htf_bucket = i
        htf_cache_key = (symbol.upper(), str(cfg.htf), int(htf_bucket), int(cfg.ema_fast), int(cfg.ema_slow))
        if htf_cache_key in self._htf_downtrend_cache:
            htf_ok_cached = self._htf_downtrend_cache[htf_cache_key]
        else:
            htf_rows = store.fetch_klines(symbol, cfg.htf, max(cfg.ema_slow + 10, 80)) if hasattr(store, "fetch_klines") else []
            if htf_rows and len(htf_rows) >= cfg.ema_slow + 5:
                htf_closes = [float(r[4]) for r in htf_rows]  # bybit kline format
                ema_fast_htf = _ema(htf_closes, cfg.ema_fast)
                ema_slow_htf = _ema(htf_closes, cfg.ema_slow)
                if math.isfinite(ema_fast_htf) and math.isfinite(ema_slow_htf):
                    htf_ok_cached = bool(ema_fast_htf < ema_slow_htf)
                    self._htf_downtrend_cache[htf_cache_key] = htf_ok_cached
        if htf_ok_cached is not None:
            if not htf_ok_cached:
                self.last_no_signal_reason = "htf_not_downtrend"
                return None
        elif htf_rows and len(htf_rows) >= cfg.ema_slow + 5:
            # Defensive fallback for malformed HTF rows: fail closed instead of
            # silently treating an unusable high-timeframe filter as permissive.
            self.last_no_signal_reason = "bad_htf"
            return None
        # Если нет HTF данных — fallback на 5m EMA
        else:
            closes_5m = [float(x.c) for x in candles[max(0, i - cfg.ema_slow - 5): i + 1]]
            ema_fast_5m = _ema(closes_5m, cfg.ema_fast)
            ema_slow_5m = _ema(closes_5m, cfg.ema_slow)
            if not (math.isfinite(ema_fast_5m) and math.isfinite(ema_slow_5m) and ema_fast_5m < ema_slow_5m):
                self.last_no_signal_reason = "5m_not_downtrend"
                return None

        # ── 5m close < 5m EMA20 (current below local trend) ──────────────────
        closes_5m = [float(x.c) for x in candles[max(0, i - cfg.ema_fast - 5): i + 1]]
        ema_fast_5m_now = _ema(closes_5m, cfg.ema_fast)
        if not math.isfinite(ema_fast_5m_now):
            self.last_no_signal_reason = "bad_ema"
            return None

        cur = candles[i]
        o, h, l, c, v = float(cur.o), float(cur.h), float(cur.l), float(cur.c), float(cur.v)

        # Pullback detection — было N восходящих свечей перед текущей?
        recent = candles[i - cfg.pullback_bars: i]
        if not recent:
            self.last_no_signal_reason = "no_recent"
            return None
        rally_size = (max(float(x.h) for x in recent) - min(float(x.l) for x in recent))
        if rally_size < cfg.pullback_min_pct * atr:
            self.last_no_signal_reason = "no_pullback"
            return None

        # Текущая свеча уже выше локальной EMA20 (это и есть pullback к EMA)?
        # Логика: цена упала с пика, оттолкнулась от EMA20 снизу, или сейчас на ней
        if c > ema_fast_5m_now * 1.005:  # выше EMA на > 0.5% — слишком далеко
            self.last_no_signal_reason = "too_far_from_ema"
            return None

        # RSI зона 50-70 (overbought minor pullback)
        rsi_closes = [float(x.c) for x in candles[max(0, i - cfg.rsi_period - 2): i + 1]]
        rsi = _rsi(rsi_closes, cfg.rsi_period)
        if not math.isfinite(rsi):
            self.last_no_signal_reason = "bad_rsi"
            return None
        if not (cfg.rsi_min <= rsi <= cfg.rsi_max):
            self.last_no_signal_reason = f"rsi_out_of_zone:{rsi:.1f}"
            return None

        # Rejection: upper wick > body * ratio
        body = abs(c - o)
        body_floor = max(body, 0.05 * atr)
        upper_wick = h - max(o, c)
        if upper_wick < cfg.min_reject_wick_ratio * body_floor:
            self.last_no_signal_reason = "no_rejection_wick"
            return None

        # Close in lower half of bar
        bar_range = max(h - l, 1e-9)
        close_pos = (c - l) / bar_range
        if close_pos > 0.55:
            self.last_no_signal_reason = "close_too_high"
            return None

        # Volume должен быть умеренным (не breakdown spike)
        avg_vol = sum(float(candles[j].v) * float(candles[j].c) for j in range(i - cfg.vol_avg_bars, i)) / float(cfg.vol_avg_bars)
        cur_vol = v * c
        if avg_vol > 0 and cur_vol > cfg.max_vol_mult * avg_vol:
            self.last_no_signal_reason = "volume_too_high"
            return None

        # ── ENTRY SHORT ──────────────────────────────────────────────────────
        sl = max(h, max(float(x.h) for x in recent)) + cfg.sl_pad_atr * atr
        risk = sl - c
        if risk <= 0:
            self.last_no_signal_reason = "bad_risk"
            return None
        tp = c - cfg.rr * risk

        self._last_signal_i[symbol] = i
        sig = TradeSignal(
            strategy=self.NAME,
            symbol=symbol,
            side="short",
            entry=c,
            sl=sl,
            tp=tp,
            time_stop_bars=cfg.time_stop_bars,
            reason=f"BRC1_SHORT regime={regime} rsi={rsi:.1f} pullback={cfg.pullback_bars}b vol_ratio={cur_vol/max(avg_vol,1e-9):.2f}",
        )
        if hasattr(sig, "tps") and cfg.tp1_frac > 0:
            tp1 = c - cfg.tp1_rr * risk
            sig.tps = [float(tp1), float(tp)]
            sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
        return sig
