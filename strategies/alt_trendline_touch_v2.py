"""
alt_trendline_touch_v2 (ATT2) — Улучшенная версия ATT1.

Ключевые улучшения по сравнению с v1:
─────────────────────────────────────────────────────────────────────────────
1. WEIGHTED LEAST SQUARES для пивотов
   Пивоты ближе к текущему бару получают экспоненциально больший вес.
   decay_half_life = 10 баров → пивот 20 баров назад весит в 4 раза меньше
   свежего. Это делает тренд-линию более актуальной и снижает ложные
   отклонения из-за старых "гуляющих" пивотов.

2. АДАПТИВНЫЙ R² ПОРОГ
   Вместо жёсткого 0.70: threshold = 0.88 - 0.11*(n_pivots-2),
   capped в [0.50, 0.88]. Для 2 пивотов — всегда принимаем (нельзя
   вычислить R² по 2 точкам), для 3 — 0.77, для 4 — 0.66, для 5+ — 0.55.
   Больше пивотов → выше требование к их коллинеарности.

3. VOLUME CONFIRMATION (опционально)
   ATT2_VOLUME_CONFIRM=1 — touch-бар должен иметь объём ≥ 0.8×MA20(volume).
   Слабый тач на мёртвом объёме = ненадёжный отбой. Default=0 (off).

4. РЕЖИМ-АДАПТИВНЫЕ RSI ДИАПАЗОНЫ
   Читает ATT2_REGIME из env (или override). Автоматически сдвигает:
   - bear_trend/bear_chop: RSI_LONG_MAX -= 5, RSI_SHORT_MIN -= 5 (шортить легче)
   - bull_trend/bull_chop: RSI_LONG_MAX += 5 (лонги разрешены при более высоком RSI)

5. SIGNAL QUALITY SCORE
   Каждый сигнал получает score ∈ [0,1] на основе:
   R² линии × (1 - slope_extreme_factor) × touch_precision × rr_quality
   Передаётся в reason= строке для future AI gate.

6. LINE PROJECTION CHECK
   Если текущая цена слишком далеко ушла от линии (> max_line_dist_atr),
   скипаем — линия потеряла актуальность.

Формат env переменных: ATT2_* (совместим с ATT1 через rename)
Можно использовать ATT1_ переменные задав ATT2_USE_ATT1_ENV=1.
─────────────────────────────────────────────────────────────────────────────

Exit plan (наследуется от v1, refinements):
  TP1: tp1_rr × risk (partial: tp1_frac)
  TP2: tp2_rr × risk (remainder)
  Trailing: arms at trail_activate_rr×risk, trails at trail_atr_mult×ATR
  Break-even: arms at be_trigger_rr×risk
  Time stop: time_stop_bars_5m
  Cooldown: cooldown_bars_5m

Environment variables (ATT2_ prefix, или ATT1_ если ATT2_USE_ATT1_ENV=1):
  ATT2_SYMBOL_ALLOWLIST     csv    торгуемые символы
  ATT2_SIGNAL_TF            str    таймфрейм сигнала [60]
  ATT2_SIGNAL_LOOKBACK      int    баров истории [120]
  ATT2_ATR_PERIOD           int    период ATR [14]
  ATT2_RSI_PERIOD           int    период RSI [14]
  ATT2_PIVOT_LEFT           int    баров слева от пивота [2]
  ATT2_PIVOT_RIGHT          int    баров справа от пивота [2]
  ATT2_MIN_PIVOTS           int    мин. пивотов для линии [2]
  ATT2_MAX_PIVOT_AGE        int    макс. баров с последнего пивота [24]
  ATT2_MAX_SLOPE_PCT        float  макс. наклон линии %/день [4.0]
  ATT2_MIN_SLOPE_PCT        float  мин. наклон линии %/день [0.02]
  ATT2_LONG_MAX_NEG_SLOPE   float  допустимый отрицательный наклон поддержки [0.6]
  ATT2_SHORT_MAX_POS_SLOPE  float  допустимый положительный наклон сопротивления [0.6]
  ATT2_TOUCH_ATR            float  допуск касания в ATR [0.40]
  ATT2_REJECT_ATR           float  мин. дистанция закрытия от линии [0.10]
  ATT2_MIN_BODY_FRAC        float  мин. тело свечи / диапазон [0.18]
  ATT2_RSI_LONG_MAX         float  макс. RSI для лонга [58.0]
  ATT2_RSI_SHORT_MIN        float  мин. RSI для шорта [42.0]
  ATT2_REGIME               str    текущий режим (bull_trend|bull_chop|bear_chop|bear_trend) []
  ATT2_VOLUME_CONFIRM       bool   требовать объём ≥ 0.8×MA20 [0]
  ATT2_VOLUME_MA_PERIOD     int    период MA объёма [20]
  ATT2_VOLUME_RATIO_MIN     float  мин. отношение объёма touch-бара к MA [0.80]
  ATT2_MAX_LINE_DIST_ATR    float  макс. дистанция от линии до цены в ATR [3.0]
  ATT2_DECAY_HALF_LIFE      int    полупериод затухания веса пивотов [10]
  ATT2_SL_ATR_MULT          float  буфер SL от линии [1.0]
  ATT2_TP1_RR               float  TP1 R-кратное [1.20]
  ATT2_TP2_RR               float  TP2 R-кратное [2.80]
  ATT2_TP1_FRAC             float  доля закрытия на TP1 [0.55]
  ATT2_BE_TRIGGER_RR        float  порог переноса SL в безубыток [1.00]
  ATT2_BE_LOCK_RR           float  смещение SL за точку входа при BE [0.02]
  ATT2_TRAIL_ATR_MULT       float  трейлинг в ATR единицах [1.40]
  ATT2_TRAIL_ACTIVATE_RR    float  порог активации трейлинга [1.00]
  ATT2_TIME_STOP_BARS_5M    int    тайм-стоп в 5m барах [2016]
  ATT2_COOLDOWN_BARS_5M     int    кулдаун после сделки [96]
  ATT2_ALLOW_LONGS          bool   разрешить лонги [1]
  ATT2_ALLOW_SHORTS         bool   разрешить шорты [1]
  ATT2_USE_ATT1_ENV         bool   читать ATT1_ env как fallback [0]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .signals import TradeSignal


# ─────────────────────────────────────────────────────────────────────────────
# Env helpers
# ─────────────────────────────────────────────────────────────────────────────

def _env_float(name: str, default: float, fallback: Optional[str] = None) -> float:
    for n in ([name, fallback] if fallback else [name]):
        if not n:
            continue
        v = os.getenv(n)
        if v is not None and str(v).strip():
            try:
                return float(str(v).strip())
            except Exception:
                pass
    return default


def _env_int(name: str, default: int, fallback: Optional[str] = None) -> int:
    for n in ([name, fallback] if fallback else [name]):
        if not n:
            continue
        v = os.getenv(n)
        if v is not None and str(v).strip():
            try:
                return int(str(v).strip())
            except Exception:
                pass
    return default


def _env_bool(name: str, default: bool, fallback: Optional[str] = None) -> bool:
    for n in ([name, fallback] if fallback else [name]):
        if not n:
            continue
        v = os.getenv(n)
        if v is not None:
            return str(v).strip().lower() in {"1", "true", "yes", "on"}
    return default


def _env_str(name: str, default: str, fallback: Optional[str] = None) -> str:
    for n in ([name, fallback] if fallback else [name]):
        if not n:
            continue
        v = os.getenv(n)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _env_csv_set(name: str, default_csv: str = "", fallback: Optional[str] = None) -> set:
    for n in ([name, fallback] if fallback else [name]):
        if not n:
            continue
        raw = os.getenv(n)
        if raw is not None and raw.strip():
            return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}
    raw = default_csv
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


# ─────────────────────────────────────────────────────────────────────────────
# Математические утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _atr(rows: List[list], period: int) -> float:
    """Average True Range по последним `period` барам."""
    if len(rows) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = float(rows[i][2])
        l = float(rows[i][3])
        pc = float(rows[i - 1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period if trs else float("nan")


def _rsi(values: List[float], period: int) -> float:
    """Wilder RSI по последним period+1 значениям."""
    if len(values) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_g = gains / period
    avg_l = losses / period
    if avg_l < 1e-12:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _vol_ma(volumes: List[float], period: int) -> float:
    """Простое среднее объёма за последние period баров (исключая текущий)."""
    if len(volumes) < period + 1:
        return float("nan")
    return sum(volumes[-period - 1:-1]) / period


def _find_swing_lows(lows: List[float], left: int, right: int) -> List[Tuple[int, float]]:
    """Пивотные минимумы: low[i] ≤ всем соседям, хоть одна строгая неравенство."""
    n = len(lows)
    pivots: List[Tuple[int, float]] = []
    for i in range(left, n - right):
        v = lows[i]
        if (all(v <= lows[i - k] for k in range(1, left + 1)) and
                all(v <= lows[i + k] for k in range(1, right + 1)) and
                (any(v < lows[i - k] for k in range(1, left + 1)) or
                 any(v < lows[i + k] for k in range(1, right + 1)))):
            pivots.append((i, v))
    return pivots


def _find_swing_highs(highs: List[float], left: int, right: int) -> List[Tuple[int, float]]:
    """Пивотные максимумы: high[i] ≥ всем соседям, хоть одна строгая неравенство."""
    n = len(highs)
    pivots: List[Tuple[int, float]] = []
    for i in range(left, n - right):
        v = highs[i]
        if (all(v >= highs[i - k] for k in range(1, left + 1)) and
                all(v >= highs[i + k] for k in range(1, right + 1)) and
                (any(v > highs[i - k] for k in range(1, left + 1)) or
                 any(v > highs[i + k] for k in range(1, right + 1)))):
            pivots.append((i, v))
    return pivots


def _weighted_linreg(
    points: List[Tuple[int, float]],
    decay_half_life: float,
    n_total: int,
) -> Tuple[float, float, float]:
    """
    Взвешенная линейная регрессия через пивотные точки.

    Вес пивота = exp(-ln(2) / half_life * (n_total - 1 - pivot_idx)).
    Чем свежее пивот (ближе к n_total-1), тем больший вес.

    Returns (slope, intercept, weighted_r2).
    """
    if len(points) < 2:
        return float("nan"), float("nan"), float("nan")

    decay_rate = math.log(2.0) / max(1.0, decay_half_life)
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    ws = [math.exp(-decay_rate * max(0.0, n_total - 1 - p[0])) for p in points]

    W = sum(ws)
    if W <= 1e-12:
        return float("nan"), float("nan"), float("nan")

    Wx = sum(w * x for w, x in zip(ws, xs))
    Wy = sum(w * y for w, y in zip(ws, ys))
    Wxx = sum(w * x * x for w, x, y in zip(ws, xs, ys))
    Wxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))

    denom = W * Wxx - Wx * Wx
    if abs(denom) < 1e-18:
        # Вертикальная линия или константа — нет смысла
        return float("nan"), float("nan"), float("nan")

    slope = (W * Wxy - Wx * Wy) / denom
    intercept = (Wy - slope * Wx) / W

    # Взвешенный R²
    y_mean = Wy / W
    ss_tot = sum(w * (y - y_mean) ** 2 for w, y in zip(ws, ys))
    ss_res = sum(w * (y - (slope * x + intercept)) ** 2 for w, x, y in zip(ws, xs, ys))
    if ss_tot < 1e-18:
        r2 = 1.0  # идеально плоская линия, все на ней
    else:
        r2 = max(0.0, 1.0 - ss_res / ss_tot)

    return slope, intercept, r2


def _adaptive_r2_threshold(n_pivots: int) -> float:
    """
    Адаптивный порог R²: больше пивотов → строже требование коллинеарности.
    2 пивота → 0.0 (нельзя вычислить, всегда принимаем)
    3 пивота → 0.77
    4 пивота → 0.66
    5+ пивотов → 0.55
    """
    if n_pivots <= 2:
        return 0.0
    return max(0.50, 0.88 - 0.11 * (n_pivots - 2))


def _slope_pct_per_day(slope: float, price: float, bars_per_day: int = 24) -> float:
    """Наклон в % от цены в сутки (при bars_per_day часовых барах)."""
    if price <= 1e-12:
        return float("inf")
    return abs(slope * bars_per_day / price) * 100.0


def _signal_quality(r2: float, slope_pct: float, max_slope: float,
                    touch_precision: float, rr_ratio: float) -> float:
    """
    Качество сигнала ∈ [0, 1]:
      r2_score          — чем выше R², тем лучше линия
      slope_score       — prefer умеренный наклон, штраф за экстремальный
      touch_score       — насколько точно low/high коснулся линии (1=идеал, 0=грань допуска)
      rr_score          — reward-to-risk quality (capped at 3)
    """
    r2_score = float(r2)
    slope_norm = min(1.0, slope_pct / max(0.01, max_slope))
    slope_score = 1.0 - 0.5 * slope_norm  # штраф за слишком крутую линию
    touch_score = max(0.0, 1.0 - touch_precision)  # 0 = самый край допуска, 1 = точное касание
    rr_score = min(1.0, rr_ratio / 3.0)
    return r2_score * 0.35 + slope_score * 0.20 + touch_score * 0.25 + rr_score * 0.20


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ATT2Config:
    # Env prefix — ATT2_, с fallback на ATT1_ если use_att1_env=True
    use_att1_env: bool = False

    # Allowlist / denylist
    allow: set = field(default_factory=set)
    deny: set = field(default_factory=set)

    # Signal timeframe
    signal_tf: str = "60"
    signal_lookback: int = 120
    atr_period: int = 14
    rsi_period: int = 14

    # Pivot detection
    pivot_left: int = 2
    pivot_right: int = 2
    min_pivots: int = 2
    max_pivot_age: int = 24

    # Weighted regression
    decay_half_life: float = 10.0   # баров

    # Slope constraints (%/day)
    min_slope_pct: float = 0.02
    max_slope_pct: float = 4.0
    long_max_neg_slope: float = 0.6   # разрешённый отрицат. наклон поддержки
    short_max_pos_slope: float = 0.6  # разрешённый положит. наклон сопротивления

    # Touch & rejection
    touch_atr: float = 0.40
    reject_atr: float = 0.10
    min_body_frac: float = 0.18
    max_line_dist_atr: float = 3.0   # макс. дистанция от линии до текущей цены

    # RSI filters (базовые, корректируются режимом)
    rsi_long_max: float = 58.0
    rsi_short_min: float = 42.0

    # Regime adaptation
    regime: str = ""  # пусто = без адаптации

    # Volume confirmation
    volume_confirm: bool = False
    volume_ma_period: int = 20
    volume_ratio_min: float = 0.80

    # Exit
    sl_atr_mult: float = 1.0
    tp1_rr: float = 1.20
    tp2_rr: float = 2.80
    tp1_frac: float = 0.55
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.02
    trail_atr_mult: float = 1.40
    trail_activate_rr: float = 1.00
    time_stop_bars_5m: int = 2016
    cooldown_bars_5m: int = 96

    # Direction gates
    allow_longs: bool = True
    allow_shorts: bool = True

    @classmethod
    def from_env(cls) -> "ATT2Config":
        use_att1 = _env_bool("ATT2_USE_ATT1_ENV", False)
        fb = lambda n: f"ATT1_{n}" if use_att1 else None  # noqa: E731

        cfg = cls()
        cfg.use_att1_env = use_att1
        cfg.allow = _env_csv_set("ATT2_SYMBOL_ALLOWLIST", "", fb("SYMBOL_ALLOWLIST"))
        cfg.deny = _env_csv_set("ATT2_SYMBOL_DENYLIST", "")
        cfg.signal_tf = _env_str("ATT2_SIGNAL_TF", "60", fb("SIGNAL_TF"))
        cfg.signal_lookback = _env_int("ATT2_SIGNAL_LOOKBACK", 120, fb("SIGNAL_LOOKBACK"))
        cfg.atr_period = _env_int("ATT2_ATR_PERIOD", 14, fb("ATR_PERIOD"))
        cfg.rsi_period = _env_int("ATT2_RSI_PERIOD", 14, fb("RSI_PERIOD"))
        cfg.pivot_left = _env_int("ATT2_PIVOT_LEFT", 2, fb("PIVOT_LEFT"))
        cfg.pivot_right = _env_int("ATT2_PIVOT_RIGHT", 2, fb("PIVOT_RIGHT"))
        cfg.min_pivots = _env_int("ATT2_MIN_PIVOTS", 2, fb("MIN_PIVOTS"))
        cfg.max_pivot_age = _env_int("ATT2_MAX_PIVOT_AGE", 24, fb("MAX_PIVOT_AGE"))
        cfg.decay_half_life = _env_float("ATT2_DECAY_HALF_LIFE", 10.0)
        cfg.min_slope_pct = _env_float("ATT2_MIN_SLOPE_PCT", 0.02, fb("MIN_SLOPE_PCT"))
        cfg.max_slope_pct = _env_float("ATT2_MAX_SLOPE_PCT", 4.0, fb("MAX_SLOPE_PCT"))
        cfg.long_max_neg_slope = _env_float("ATT2_LONG_MAX_NEG_SLOPE", 0.6, fb("LONG_MAX_NEG_SLOPE"))
        cfg.short_max_pos_slope = _env_float("ATT2_SHORT_MAX_POS_SLOPE", 0.6, fb("SHORT_MAX_POS_SLOPE"))
        cfg.touch_atr = _env_float("ATT2_TOUCH_ATR", 0.40, fb("TOUCH_ATR"))
        cfg.reject_atr = _env_float("ATT2_REJECT_ATR", 0.10, fb("REJECT_ATR"))
        cfg.min_body_frac = _env_float("ATT2_MIN_BODY_FRAC", 0.18, fb("MIN_BODY_FRAC"))
        cfg.max_line_dist_atr = _env_float("ATT2_MAX_LINE_DIST_ATR", 3.0)
        cfg.rsi_long_max = _env_float("ATT2_RSI_LONG_MAX", 58.0, fb("RSI_LONG_MAX"))
        cfg.rsi_short_min = _env_float("ATT2_RSI_SHORT_MIN", 42.0, fb("RSI_SHORT_MIN"))
        cfg.regime = _env_str("ATT2_REGIME", "")
        cfg.volume_confirm = _env_bool("ATT2_VOLUME_CONFIRM", False)
        cfg.volume_ma_period = _env_int("ATT2_VOLUME_MA_PERIOD", 20)
        cfg.volume_ratio_min = _env_float("ATT2_VOLUME_RATIO_MIN", 0.80)
        cfg.sl_atr_mult = _env_float("ATT2_SL_ATR_MULT", 1.0, fb("SL_ATR_MULT"))
        cfg.tp1_rr = _env_float("ATT2_TP1_RR", 1.20, fb("TP1_RR"))
        cfg.tp2_rr = _env_float("ATT2_TP2_RR", 2.80, fb("TP2_RR"))
        cfg.tp1_frac = _env_float("ATT2_TP1_FRAC", 0.55, fb("TP1_FRAC"))
        cfg.be_trigger_rr = _env_float("ATT2_BE_TRIGGER_RR", 1.00, fb("BE_TRIGGER_RR"))
        cfg.be_lock_rr = _env_float("ATT2_BE_LOCK_RR", 0.02, fb("BE_LOCK_RR"))
        cfg.trail_atr_mult = _env_float("ATT2_TRAIL_ATR_MULT", 1.40, fb("TRAIL_ATR_MULT"))
        cfg.trail_activate_rr = _env_float("ATT2_TRAIL_ACTIVATE_RR", 1.00, fb("TRAIL_ACTIVATE_RR"))
        cfg.time_stop_bars_5m = _env_int("ATT2_TIME_STOP_BARS_5M", 2016, fb("TIME_STOP_BARS_5M"))
        cfg.cooldown_bars_5m = _env_int("ATT2_COOLDOWN_BARS_5M", 96, fb("COOLDOWN_BARS_5M"))
        cfg.allow_longs = _env_bool("ATT2_ALLOW_LONGS", True, fb("ALLOW_LONGS"))
        cfg.allow_shorts = _env_bool("ATT2_ALLOW_SHORTS", True, fb("ALLOW_SHORTS"))
        return cfg

    def effective_rsi_long_max(self) -> float:
        """RSI порог для лонгов с учётом режима."""
        base = self.rsi_long_max
        r = self.regime.lower()
        if "bear" in r:
            return base - 5.0
        if "bull_trend" in r:
            return base + 5.0
        return base

    def effective_rsi_short_min(self) -> float:
        """RSI порог для шортов с учётом режима."""
        base = self.rsi_short_min
        r = self.regime.lower()
        if "bear" in r:
            return base - 5.0  # шортить разрешено при более низком RSI
        if "bull_trend" in r:
            return base + 5.0  # шортить сложнее в бычьем тренде
        return base


# ─────────────────────────────────────────────────────────────────────────────
# Стратегия
# ─────────────────────────────────────────────────────────────────────────────

class AltTrendlineTouchV2Strategy:
    """
    ATT2 — улучшенный тренд-линейный отбой.
    Совместим с runner'ом бота: реализует maybe_signal(store, ts_ms, o, h, l, c, v).
    """

    NAME = "alt_trendline_touch_v2"

    def __init__(self, cfg: Optional[ATT2Config] = None) -> None:
        self.cfg: ATT2Config = cfg or ATT2Config.from_env()
        self._cooldown: int = 0
        self._last_tf_ts: Optional[int] = None
        self._last_no_signal_reason: str = ""
        # Кэш последнего обновления конфига
        self._cfg_refresh_bar: int = 0

    # ── Диагностика ─────────────────────────────────────────────────────────

    def _ns(self, reason: str) -> None:
        """Записывает причину отсутствия сигнала."""
        self._last_no_signal_reason = reason

    @property
    def last_no_signal_reason(self) -> str:
        return self._last_no_signal_reason

    def _refresh_config(self) -> None:
        """Горячее обновление конфига из env каждые 50 баров."""
        self.cfg = ATT2Config.from_env()

    # ── Trendline detection ──────────────────────────────────────────────────

    def _check_long_tl(
        self,
        lows: List[float],
        closes: List[float],
        opens: List[float],
        highs: List[float],
        volumes: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float, float]]:
        """
        Проверяет поддерживающую трендлинию для лонга.
        Returns (tl_level, slope, quality_score) or None.
        """
        c = self.cfg
        n = len(lows)

        pivots = _find_swing_lows(lows, c.pivot_left, c.pivot_right)
        if len(pivots) < c.min_pivots:
            self._ns("long_pivots_short")
            return None

        # Берём min_pivots последних, но не более 5
        recent = pivots[-min(5, max(c.min_pivots, 3)):]
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        # Проверка актуальности линии
        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            self._ns("long_pivot_stale")
            return None

        slope, intercept, r2 = _weighted_linreg(recent, c.decay_half_life, n)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            self._ns("long_line_invalid")
            return None

        # Адаптивный R² порог
        r2_threshold = _adaptive_r2_threshold(len(recent))
        if r2 < r2_threshold and len(recent) > 2:
            self._ns(f"long_r2_low_{r2:.3f}<{r2_threshold:.3f}")
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = _slope_pct_per_day(slope, price_ref)

        # Ограничения наклона
        if slope_pct < c.min_slope_pct:
            self._ns(f"long_slope_flat_{slope_pct:.3f}")
            return None
        if slope_pct > c.max_slope_pct:
            self._ns(f"long_slope_steep_{slope_pct:.3f}")
            return None
        long_slope_floor = -price_ref * c.long_max_neg_slope / 100.0 / 24.0
        if slope < long_slope_floor:
            self._ns("long_slope_direction")
            return None

        tl_now = slope * (n - 1) + intercept

        # Проверка что линия ещё близко к цене
        line_dist = abs(closes[-1] - tl_now)
        if line_dist > c.max_line_dist_atr * atr:
            self._ns(f"long_line_far_{line_dist / atr:.2f}atr")
            return None

        # Touch & rejection
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        touched = cur_low <= tl_now + c.touch_atr * atr
        reclaimed = cur_close >= tl_now + c.reject_atr * atr
        bullish = cur_close > cur_open
        body_ok = body_frac >= c.min_body_frac
        rsi_ok = rsi <= c.effective_rsi_long_max()

        if not touched:
            self._ns(f"long_no_touch_dist={(cur_low - tl_now) / atr:.2f}atr")
            return None
        if not reclaimed:
            self._ns("long_no_reject")
            return None
        if not bullish:
            self._ns("long_not_bullish")
            return None
        if not body_ok:
            self._ns(f"long_body_weak_{body_frac:.2f}")
            return None
        if not rsi_ok:
            self._ns(f"long_rsi_high_{rsi:.1f}")
            return None

        # Опциональная проверка объёма
        if c.volume_confirm and len(volumes) > c.volume_ma_period + 1:
            vol_ma = _vol_ma(volumes, c.volume_ma_period)
            if math.isfinite(vol_ma) and vol_ma > 0:
                vol_ratio = volumes[-1] / vol_ma
                if vol_ratio < c.volume_ratio_min:
                    self._ns(f"long_vol_weak_{vol_ratio:.2f}")
                    return None

        # Качество touch: насколько точно low коснулся линии
        touch_precision = abs(cur_low - tl_now) / max(1e-12, c.touch_atr * atr)
        quality = _signal_quality(r2, slope_pct, c.max_slope_pct, touch_precision,
                                  c.tp2_rr)  # rr_ratio = TP2_RR как прокси
        return (tl_now, slope, quality)

    def _check_short_tl(
        self,
        highs: List[float],
        closes: List[float],
        opens: List[float],
        lows: List[float],
        volumes: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float, float]]:
        """
        Проверяет сопротивляющуюся трендлинию для шорта.
        Returns (tl_level, slope, quality_score) or None.
        """
        c = self.cfg
        n = len(highs)

        pivots = _find_swing_highs(highs, c.pivot_left, c.pivot_right)
        if len(pivots) < c.min_pivots:
            self._ns("short_pivots_short")
            return None

        recent = pivots[-min(5, max(c.min_pivots, 3)):]
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            self._ns("short_pivot_stale")
            return None

        slope, intercept, r2 = _weighted_linreg(recent, c.decay_half_life, n)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            self._ns("short_line_invalid")
            return None

        r2_threshold = _adaptive_r2_threshold(len(recent))
        if r2 < r2_threshold and len(recent) > 2:
            self._ns(f"short_r2_low_{r2:.3f}<{r2_threshold:.3f}")
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = _slope_pct_per_day(slope, price_ref)

        if slope_pct < c.min_slope_pct:
            self._ns(f"short_slope_flat_{slope_pct:.3f}")
            return None
        if slope_pct > c.max_slope_pct:
            self._ns(f"short_slope_steep_{slope_pct:.3f}")
            return None
        short_slope_ceil = price_ref * c.short_max_pos_slope / 100.0 / 24.0
        if slope > short_slope_ceil:
            self._ns("short_slope_direction")
            return None

        tl_now = slope * (n - 1) + intercept

        line_dist = abs(closes[-1] - tl_now)
        if line_dist > c.max_line_dist_atr * atr:
            self._ns(f"short_line_far_{line_dist / atr:.2f}atr")
            return None

        cur_high = highs[-1]
        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_low = lows[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        touched = cur_high >= tl_now - c.touch_atr * atr
        rejected = cur_close <= tl_now - c.reject_atr * atr
        bearish = cur_close < cur_open
        body_ok = body_frac >= c.min_body_frac
        rsi_ok = rsi >= c.effective_rsi_short_min()

        if not touched:
            self._ns(f"short_no_touch_dist={(tl_now - cur_high) / atr:.2f}atr")
            return None
        if not rejected:
            self._ns("short_no_reject")
            return None
        if not bearish:
            self._ns("short_not_bearish")
            return None
        if not body_ok:
            self._ns(f"short_body_weak_{body_frac:.2f}")
            return None
        if not rsi_ok:
            self._ns(f"short_rsi_low_{rsi:.1f}")
            return None

        if c.volume_confirm and len(volumes) > c.volume_ma_period + 1:
            vol_ma = _vol_ma(volumes, c.volume_ma_period)
            if math.isfinite(vol_ma) and vol_ma > 0:
                vol_ratio = volumes[-1] / vol_ma
                if vol_ratio < c.volume_ratio_min:
                    self._ns(f"short_vol_weak_{vol_ratio:.2f}")
                    return None

        touch_precision = abs(cur_high - tl_now) / max(1e-12, c.touch_atr * atr)
        quality = _signal_quality(r2, slope_pct, c.max_slope_pct, touch_precision, c.tp2_rr)
        return (tl_now, slope, quality)

    # ── Runner interface ─────────────────────────────────────────────────────

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
        """Основной метод: вызывается ботом на каждом тике."""
        _ = (o, h, l, c, v)
        self._last_no_signal_reason = ""

        # Горячее обновление конфига
        self._cfg_refresh_bar += 1
        if self._cfg_refresh_bar >= 50:
            self._cfg_refresh_bar = 0
            self._refresh_config()

        cfg = self.cfg
        sym = str(getattr(store, "symbol", "")).upper()

        # Allowlist / denylist
        if cfg.allow and sym not in cfg.allow:
            self._ns("symbol_not_allowed")
            return None
        if sym in cfg.deny:
            self._ns("symbol_denied")
            return None

        # Cooldown
        if self._cooldown > 0:
            self._cooldown -= 1
            self._ns("cooldown")
            return None

        # Загрузка истории
        rows = store.fetch_klines(store.symbol, cfg.signal_tf, cfg.signal_lookback) or []
        if len(rows) < cfg.signal_lookback:
            self._ns(f"history_short_{len(rows)}")
            return None

        # Дедупликация по таймфрейму
        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            self._ns("first_bar")
            return None
        if tf_ts == self._last_tf_ts:
            self._ns("same_bar")
            return None
        self._last_tf_ts = tf_ts

        # Данные
        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        volumes = [float(r[5]) for r in rows] if len(rows[0]) > 5 else []

        cur = closes[-1]
        if cur <= 0:
            self._ns("price_zero")
            return None

        atr_val = _atr(rows, cfg.atr_period)
        rsi_val = _rsi(closes, cfg.rsi_period)
        if not (math.isfinite(atr_val) and math.isfinite(rsi_val)) or atr_val <= 0:
            self._ns("indicators_nan")
            return None

        # ── LONG ────────────────────────────────────────────────────────────
        if cfg.allow_longs:
            result = self._check_long_tl(lows, closes, opens, highs, volumes, atr_val, rsi_val)
            if result is not None:
                tl_level, slope, quality = result
                sl = tl_level - cfg.sl_atr_mult * atr_val
                risk = cur - sl
                if risk > 0:
                    tp1 = cur + cfg.tp1_rr * risk
                    tp2 = cur + cfg.tp2_rr * risk
                    slope_pct_fmt = slope * 24 / max(1e-12, cur) * 100
                    sig = TradeSignal(
                        strategy=self.NAME,
                        symbol=store.symbol,
                        side="long",
                        entry=float(cur),
                        sl=float(sl),
                        tp=float(tp2),
                        tps=[float(tp1), float(tp2)],
                        tp_fracs=[
                            min(0.90, max(0.10, cfg.tp1_frac)),
                            max(0.05, 1.0 - min(0.90, max(0.10, cfg.tp1_frac))),
                        ],
                        be_trigger_rr=max(0.0, cfg.be_trigger_rr),
                        be_lock_rr=max(0.0, cfg.be_lock_rr),
                        trailing_atr_mult=max(0.0, cfg.trail_atr_mult),
                        trailing_atr_period=cfg.atr_period,
                        trail_activate_rr=max(0.0, cfg.trail_activate_rr),
                        time_stop_bars=max(0, cfg.time_stop_bars_5m),
                        reason=(
                            f"att2_long tl={tl_level:.4f} "
                            f"slope={slope_pct_fmt:.3f}%/d "
                            f"rsi={rsi_val:.1f} "
                            f"q={quality:.2f} "
                            f"regime={cfg.regime}"
                        ),
                    )
                    if sig.validate():
                        self._cooldown = max(0, cfg.cooldown_bars_5m)
                        return sig
                self._ns("long_risk_zero")

        # ── SHORT ────────────────────────────────────────────────────────────
        if cfg.allow_shorts:
            result = self._check_short_tl(highs, closes, opens, lows, volumes, atr_val, rsi_val)
            if result is not None:
                tl_level, slope, quality = result
                sl = tl_level + cfg.sl_atr_mult * atr_val
                risk = sl - cur
                if risk > 0:
                    tp1 = cur - cfg.tp1_rr * risk
                    tp2 = cur - cfg.tp2_rr * risk
                    if tp2 > 0:
                        slope_pct_fmt = slope * 24 / max(1e-12, cur) * 100
                        sig = TradeSignal(
                            strategy=self.NAME,
                            symbol=store.symbol,
                            side="short",
                            entry=float(cur),
                            sl=float(sl),
                            tp=float(tp2),
                            tps=[float(tp1), float(tp2)],
                            tp_fracs=[
                                min(0.90, max(0.10, cfg.tp1_frac)),
                                max(0.05, 1.0 - min(0.90, max(0.10, cfg.tp1_frac))),
                            ],
                            be_trigger_rr=max(0.0, cfg.be_trigger_rr),
                            be_lock_rr=max(0.0, cfg.be_lock_rr),
                            trailing_atr_mult=max(0.0, cfg.trail_atr_mult),
                            trailing_atr_period=cfg.atr_period,
                            trail_activate_rr=max(0.0, cfg.trail_activate_rr),
                            time_stop_bars=max(0, cfg.time_stop_bars_5m),
                            reason=(
                                f"att2_short tl={tl_level:.4f} "
                                f"slope={slope_pct_fmt:.3f}%/d "
                                f"rsi={rsi_val:.1f} "
                                f"q={quality:.2f} "
                                f"regime={cfg.regime}"
                            ),
                        )
                        if sig.validate():
                            self._cooldown = max(0, cfg.cooldown_bars_5m)
                            return sig
                self._ns("short_risk_zero")

        if not self._last_no_signal_reason:
            self._ns("no_setup")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random
    random.seed(42)
    print("=== ATT2 Smoke Test ===")

    # Тест weighted_linreg
    pts = [(0, 100.0), (5, 102.0), (10, 104.0), (15, 105.5)]  # ~восходящая
    s, i, r2 = _weighted_linreg(pts, decay_half_life=5.0, n_total=20)
    print(f"WLS slope={s:.4f} intercept={i:.2f} R²={r2:.4f}")
    assert r2 > 0.95, f"R² слишком низкий: {r2}"

    # Тест adaptive R²
    assert _adaptive_r2_threshold(2) == 0.0
    assert abs(_adaptive_r2_threshold(3) - 0.77) < 0.01
    assert abs(_adaptive_r2_threshold(4) - 0.66) < 0.01
    print(f"R² thresholds: 2piv={_adaptive_r2_threshold(2):.2f} "
          f"3piv={_adaptive_r2_threshold(3):.2f} "
          f"4piv={_adaptive_r2_threshold(4):.2f}")

    # Тест адаптивного RSI
    cfg = ATT2Config()
    cfg.rsi_long_max = 58.0
    cfg.regime = "bear_chop"
    assert cfg.effective_rsi_long_max() == 53.0, f"Got {cfg.effective_rsi_long_max()}"
    cfg.regime = "bull_trend"
    assert cfg.effective_rsi_long_max() == 63.0
    print("Adaptive RSI: bear_chop=53.0 ✓  bull_trend=63.0 ✓")

    # Тест quality score
    q = _signal_quality(r2=0.9, slope_pct=1.0, max_slope=4.0, touch_precision=0.2, rr_ratio=2.5)
    assert 0.5 < q < 1.0, f"Unexpected quality: {q}"
    print(f"Signal quality score: {q:.3f} ✓")

    print("\n✅ Все тесты прошли")
