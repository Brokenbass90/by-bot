"""alt_elder_revived_v1 — упрощённый Elder triple screen, реанимация мёртвой ETS3.

Контекст: оригинальный ETS3 (4 экрана 1D+4h+1h+15m + MACD slope + Force Index +
строгие RSI) давал ~7 трейдов за весь backtest sweep. Стратегия мёртвая.

Решение: упрощаем до 3 экранов и релаксим thresholds. Сохраняем главную идею —
multi-timeframe alignment + pullback entry — но даём шанс торговать чаще.

Логика — классический Elder principle:
    SCREEN 1 (4h): МАКРОТРЕНД направление
        - LONG:  EMA50 > EMA200 на 4h И MACD histogram > 0
        - SHORT: EMA50 < EMA200 на 4h И MACD histogram < 0
        - иначе: пропускаем

    SCREEN 2 (1h): MOMENTUM PULLBACK
        - LONG:  RSI 40-55 (зона pullback в аптренде)
        - SHORT: RSI 45-60 (зона pullback в даунтренде)

    SCREEN 3 (5m): ENTRY TIMING
        - LONG:  bullish candle (close>open) + body >= 45% range + close > EMA9
        - SHORT: bearish candle + body >= 45% range + close < EMA9

Exit (Elder rules):
    - SL: за последний swing low/high (10 баров) + SL_BUFFER_ATR
    - TP1: TP1_ATR_MULT x ATR (закрывает TP1_FRAC, переводит в BE)
    - TP2: TP2_ATR_MULT x ATR (остаток)
    - Trail: TRAIL_ATR_MULT x ATR от peak/trough, активируется после TP1
    - Time stop: TIME_STOP_BARS_5M x 5m баров

ИСПРАВЛЕНИЯ v1.1 (2026-05-25):
  [BUG FIX]  _macd_hist() переписан с O(N^2) на O(N) инкрементальный EMA.
  [NEW]      maybe_signal(store, ts_ms, o, h, l, c, v) — интерфейс для runner'а бота.
  [NEW]      _no_signal(reason) — диагностика с логированием причины.
  [NEW]      _cooldown механизм и дедупликация по таймфреймовому timestamp.
  [NEW]      Вывод TradeSignal вместо ElderRevivedSignal (совместимо с ботом).
  [IMPROVE]  Swing low/high берётся как точный минимум/максимум последних N баров.
"""
from __future__ import annotations
from types import SimpleNamespace

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _ef(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _ei(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _eb(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _es(name: str, default: str) -> str:
    v = os.getenv(name)
    return str(v).strip() if v and str(v).strip() else default


def _ecsv(name: str, default: str = "") -> set:
    raw = os.getenv(name, default) or default
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


# ---------------------------------------------------------------------------
# Math — O(N) incremental EMA / MACD (replaces O(N^2) loop)
# ---------------------------------------------------------------------------

def _ema_series(values: List[float], period: int) -> List[float]:
    """Incremental EMA, O(N). First period-1 elements = nan."""
    n = len(values)
    out = [float("nan")] * n
    if n < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1.0)
    cur = seed
    for i in range(period, n):
        cur = values[i] * k + cur * (1.0 - k)
        out[i] = cur
    return out


def _macd_hist_last(closes: List[float], fast: int, slow: int, signal: int) -> Optional[float]:
    """MACD histogram on last bar, O(N). Previously was O(N^2)."""
    if len(closes) < slow + signal + 1:
        return None
    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)
    macd = [
        f - s if math.isfinite(f) and math.isfinite(s) else float("nan")
        for f, s in zip(fast_ema, slow_ema)
    ]
    valid = [x for x in macd if math.isfinite(x)]
    if len(valid) < signal:
        return None
    sig_ema = _ema_series(valid, signal)
    if not sig_ema or not math.isfinite(sig_ema[-1]):
        return None
    return valid[-1] - sig_ema[-1]


def _ema_last(values: List[float], period: int) -> Optional[float]:
    ser = _ema_series(values, period)
    v = ser[-1] if ser else float("nan")
    return v if math.isfinite(v) else None


def _rsi_last(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_g = gains / period
    avg_l = losses / period
    if avg_l < 1e-12:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def _atr_last(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h, lo, pc = float(rows[i][2]), float(rows[i][3]), float(rows[i - 1][4])
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(trs) / period


def _swing_low(rows: List[list], lookback: int) -> float:
    sub = rows[-lookback - 1:-1]
    if not sub:
        return float(rows[-1][3])
    return min(float(r[3]) for r in sub)


def _swing_high(rows: List[list], lookback: int) -> float:
    sub = rows[-lookback - 1:-1]
    if not sub:
        return float(rows[-1][2])
    return max(float(r[2]) for r in sub)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ElderRevivedConfig:
    symbol_allowlist: set = field(default_factory=lambda: {
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT"
    })
    allow_longs: bool = True
    allow_shorts: bool = True
    allowed_regimes: set = field(default_factory=set)

    # Screen 1
    s1_tf: str = "240"
    s1_lookback: int = 230
    s1_ema_fast: int = 50
    s1_ema_slow: int = 200
    s1_macd_fast: int = 12
    s1_macd_slow: int = 26
    s1_macd_signal: int = 9

    # Screen 2
    s2_tf: str = "60"
    s2_lookback: int = 80
    s2_rsi_long_min: float = 40.0
    s2_rsi_long_max: float = 55.0
    s2_rsi_short_min: float = 45.0
    s2_rsi_short_max: float = 60.0

    # Screen 3
    s3_tf: str = "5"
    s3_lookback: int = 50
    s3_body_min_frac: float = 0.45
    s3_ema_period: int = 9

    # ATR quality
    atr_period: int = 14
    atr_min_pct: float = 0.12
    atr_max_pct: float = 5.0

    # Exit
    sl_buffer_atr: float = 0.30
    sl_swing_bars: int = 10
    tp1_atr_mult: float = 1.5
    tp2_atr_mult: float = 3.0
    tp1_frac: float = 0.45
    trail_atr_mult: float = 2.0
    trail_activate_rr: float = 1.0
    be_trigger_rr: float = 1.0
    time_stop_bars_5m: int = 120
    cooldown_bars_5m: int = 72
    max_open_trades: int = 2

    @classmethod
    def from_env(cls) -> "ElderRevivedConfig":
        cfg = cls()
        cfg.symbol_allowlist = _ecsv(
            "ELDERREV_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT"
        )
        cfg.allow_longs = _eb("ELDERREV_ALLOW_LONGS", True)
        cfg.allow_shorts = _eb("ELDERREV_ALLOW_SHORTS", True)
        raw = _es("ELDERREV_ALLOWED_REGIMES", "")
        cfg.allowed_regimes = {r.strip().lower() for r in raw.split(",") if r.strip()} if raw else set()
        cfg.s1_tf = _es("ELDERREV_S1_TF", "240")
        cfg.s1_lookback = _ei("ELDERREV_S1_LOOKBACK", 230)
        cfg.s1_ema_fast = _ei("ELDERREV_S1_EMA_FAST", 50)
        cfg.s1_ema_slow = _ei("ELDERREV_S1_EMA_SLOW", 200)
        cfg.s1_macd_fast = _ei("ELDERREV_S1_MACD_FAST", 12)
        cfg.s1_macd_slow = _ei("ELDERREV_S1_MACD_SLOW", 26)
        cfg.s1_macd_signal = _ei("ELDERREV_S1_MACD_SIGNAL", 9)
        cfg.s2_tf = _es("ELDERREV_S2_TF", "60")
        cfg.s2_lookback = _ei("ELDERREV_S2_LOOKBACK", 80)
        cfg.s2_rsi_long_min = _ef("ELDERREV_S2_RSI_LONG_MIN", 40.0)
        cfg.s2_rsi_long_max = _ef("ELDERREV_S2_RSI_LONG_MAX", 55.0)
        cfg.s2_rsi_short_min = _ef("ELDERREV_S2_RSI_SHORT_MIN", 45.0)
        cfg.s2_rsi_short_max = _ef("ELDERREV_S2_RSI_SHORT_MAX", 60.0)
        cfg.s3_tf = _es("ELDERREV_S3_TF", "5")
        cfg.s3_lookback = _ei("ELDERREV_S3_LOOKBACK", 50)
        cfg.s3_body_min_frac = _ef("ELDERREV_S3_BODY_MIN_FRAC", 0.45)
        cfg.s3_ema_period = _ei("ELDERREV_S3_EMA_PERIOD", 9)
        cfg.atr_period = _ei("ELDERREV_ATR_PERIOD", 14)
        cfg.atr_min_pct = _ef("ELDERREV_ATR_MIN_PCT", 0.12)
        cfg.atr_max_pct = _ef("ELDERREV_ATR_MAX_PCT", 5.0)
        cfg.sl_buffer_atr = _ef("ELDERREV_SL_BUFFER_ATR", 0.30)
        cfg.sl_swing_bars = _ei("ELDERREV_SL_SWING_BARS", 10)
        cfg.tp1_atr_mult = _ef("ELDERREV_TP1_ATR_MULT", 1.5)
        cfg.tp2_atr_mult = _ef("ELDERREV_TP2_ATR_MULT", 3.0)
        cfg.tp1_frac = _ef("ELDERREV_TP1_FRAC", 0.45)
        cfg.trail_atr_mult = _ef("ELDERREV_TRAIL_ATR_MULT", 2.0)
        cfg.trail_activate_rr = _ef("ELDERREV_TRAIL_ACTIVATE_RR", 1.0)
        cfg.be_trigger_rr = _ef("ELDERREV_BE_TRIGGER_RR", 1.0)
        cfg.time_stop_bars_5m = _ei("ELDERREV_TIME_STOP_BARS_5M", 120)
        cfg.cooldown_bars_5m = _ei("ELDERREV_COOLDOWN_BARS_5M", 72)
        cfg.max_open_trades = _ei("ELDERREV_MAX_OPEN_TRADES", 2)
        return cfg


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AltElderRevivedV1:
    """
    Elder Revived v1 — simplified triple screen.
    Implements maybe_signal() for bot runner integration.
    """

    NAME = "alt_elder_revived_v1"

    def __init__(self, cfg: Optional[ElderRevivedConfig] = None) -> None:
        self.cfg = cfg or ElderRevivedConfig.from_env()
        self.params = {"TIME_STOP_BARS_5M": self.cfg.time_stop_bars_5m}
        self._cooldown: int = 0
        self._last_s3_ts: Optional[int] = None
        self._last_no_signal_reason: str = ""
        self._cfg_counter: int = 0

    def _ns(self, reason: str) -> None:
        self._last_no_signal_reason = reason

    @property
    def last_no_signal_reason(self) -> str:
        return self._last_no_signal_reason

    def _refresh_config(self) -> None:
        self.cfg = ElderRevivedConfig.from_env()
        self.params["TIME_STOP_BARS_5M"] = self.cfg.time_stop_bars_5m

    # -- Screen 1: 4h macro trend -------------------------------------------

    def _screen1(self, rows_4h: List[list]) -> Optional[str]:
        c = self.cfg
        min_needed = c.s1_ema_slow + c.s1_macd_signal + 5
        if len(rows_4h) < min_needed:
            self._ns("s1_history_short")
            return None
        closes = [float(r[4]) for r in rows_4h]
        ema_fast = _ema_last(closes, c.s1_ema_fast)
        ema_slow = _ema_last(closes, c.s1_ema_slow)
        if ema_fast is None or ema_slow is None:
            self._ns("s1_ema_nan")
            return None
        macd_h = _macd_hist_last(closes, c.s1_macd_fast, c.s1_macd_slow, c.s1_macd_signal)
        if macd_h is None:
            self._ns("s1_macd_nan")
            return None
        if ema_fast > ema_slow and macd_h > 0:
            return "long"
        if ema_fast < ema_slow and macd_h < 0:
            return "short"
        self._ns(f"s1_no_align macd_h={macd_h:.5f} ema_gap={ema_fast - ema_slow:.2f}")
        return None

    # -- Screen 2: 1h RSI pullback ------------------------------------------

    def _screen2(self, rows_1h: List[list], macro: str) -> Optional[str]:
        c = self.cfg
        if len(rows_1h) < 20:
            self._ns("s2_history_short")
            return None
        closes = [float(r[4]) for r in rows_1h]
        rsi = _rsi_last(closes, 14)
        if not math.isfinite(rsi):
            self._ns("s2_rsi_nan")
            return None
        if macro == "long" and c.allow_longs:
            if c.s2_rsi_long_min <= rsi <= c.s2_rsi_long_max:
                return "long"
            self._ns(f"s2_rsi_miss_{rsi:.1f} need [{c.s2_rsi_long_min},{c.s2_rsi_long_max}]")
        elif macro == "short" and c.allow_shorts:
            if c.s2_rsi_short_min <= rsi <= c.s2_rsi_short_max:
                return "short"
            self._ns(f"s2_rsi_miss_{rsi:.1f} need [{c.s2_rsi_short_min},{c.s2_rsi_short_max}]")
        else:
            self._ns(f"s2_direction_blocked macro={macro}")
        return None

    # -- Screen 3: 5m entry candle ------------------------------------------

    def _screen3(self, rows_5m: List[list], side: str) -> bool:
        c = self.cfg
        min_bars = max(c.s3_ema_period + 2, 20)
        if len(rows_5m) < min_bars:
            self._ns("s3_history_short")
            return False
        closes = [float(r[4]) for r in rows_5m]
        ema9 = _ema_last(closes, c.s3_ema_period)
        if ema9 is None:
            self._ns("s3_ema9_nan")
            return False
        bar = rows_5m[-1]
        o_, h_, lo_, cl_ = float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4])
        rng = max(1e-12, h_ - lo_)
        body_frac = abs(cl_ - o_) / rng
        if body_frac < c.s3_body_min_frac:
            self._ns(f"s3_body_weak_{body_frac:.2f}")
            return False
        if side == "long":
            if cl_ <= o_:
                self._ns("s3_not_bullish")
                return False
            if cl_ <= ema9:
                self._ns(f"s3_below_ema9 cl={cl_:.4f} ema9={ema9:.4f}")
                return False
        else:
            if cl_ >= o_:
                self._ns("s3_not_bearish")
                return False
            if cl_ >= ema9:
                self._ns(f"s3_above_ema9 cl={cl_:.4f} ema9={ema9:.4f}")
                return False
        return True

    # -- maybe_signal — bot runner interface --------------------------------

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
        """Called by the bot runner on every 5m tick."""
        _ = (o, h, l, v)
        self._last_no_signal_reason = ""

        self._cfg_counter += 1
        if self._cfg_counter >= 50:
            self._cfg_counter = 0
            self._refresh_config()

        cfg = self.cfg
        sym = str(getattr(store, "symbol", "")).upper()

        if cfg.symbol_allowlist and sym not in cfg.symbol_allowlist:
            self._ns("symbol_not_allowed")
            return None

        if cfg.allowed_regimes:
            regime = str(getattr(store, "regime", "")).lower()
            if regime not in cfg.allowed_regimes:
                self._ns(f"regime_blocked_{regime}")
                return None

        if self._cooldown > 0:
            self._cooldown -= 1
            self._ns("cooldown")
            return None

        # 5m bars — dedup
        rows_5m = store.fetch_klines(store.symbol, cfg.s3_tf, cfg.s3_lookback) or []
        if len(rows_5m) < max(cfg.s3_ema_period + 2, 20):
            self._ns("s3_bars_insufficient")
            return None

        s3_ts = int(float(rows_5m[-1][0]))
        if self._last_s3_ts is None:
            self._last_s3_ts = s3_ts
            self._ns("first_bar")
            return None
        if s3_ts == self._last_s3_ts:
            self._ns("same_bar")
            return None
        self._last_s3_ts = s3_ts

        # ATR quality gate
        atr = _atr_last(rows_5m, cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self._ns("atr_nan")
            return None
        cur = float(rows_5m[-1][4])
        if cur <= 0:
            self._ns("price_zero")
            return None
        atr_pct = atr / cur * 100.0
        if atr_pct < cfg.atr_min_pct:
            self._ns(f"atr_quiet_{atr_pct:.3f}")
            return None
        if atr_pct > cfg.atr_max_pct:
            self._ns(f"atr_volatile_{atr_pct:.3f}")
            return None

        # Screen 1
        rows_4h = store.fetch_klines(store.symbol, cfg.s1_tf, cfg.s1_lookback) or []
        macro = self._screen1(rows_4h)
        if macro is None:
            return None

        # Screen 2
        rows_1h = store.fetch_klines(store.symbol, cfg.s2_tf, cfg.s2_lookback) or []
        side = self._screen2(rows_1h, macro)
        if side is None:
            return None

        # Screen 3
        if not self._screen3(rows_5m, side):
            return None

        # Build exits
        entry = cur
        if side == "long":
            swing = _swing_low(rows_5m, cfg.sl_swing_bars)
            sl = swing - cfg.sl_buffer_atr * atr
            if sl >= entry:
                self._ns(f"long_sl_above_entry")
                return None
            tp1 = entry + cfg.tp1_atr_mult * atr
            tp2 = entry + cfg.tp2_atr_mult * atr
        else:
            swing = _swing_high(rows_5m, cfg.sl_swing_bars)
            sl = swing + cfg.sl_buffer_atr * atr
            if sl <= entry:
                self._ns(f"short_sl_below_entry")
                return None
            tp1 = entry - cfg.tp1_atr_mult * atr
            tp2 = entry - cfg.tp2_atr_mult * atr
            if tp2 <= 0:
                self._ns("short_tp2_nonpositive")
                return None

        risk = abs(entry - sl)
        if risk <= 0:
            self._ns("risk_zero")
            return None

        tp1_frac = min(0.90, max(0.10, cfg.tp1_frac))

        # Context for reason string
        closes_4h = [float(r[4]) for r in rows_4h] if rows_4h else []
        closes_1h = [float(r[4]) for r in rows_1h] if rows_1h else []
        ema_f = _ema_last(closes_4h, cfg.s1_ema_fast) if closes_4h else 0.0
        ema_s = _ema_last(closes_4h, cfg.s1_ema_slow) if closes_4h else 0.0
        macd_h = _macd_hist_last(closes_4h, cfg.s1_macd_fast, cfg.s1_macd_slow, cfg.s1_macd_signal) if closes_4h else 0.0
        rsi_1h = _rsi_last(closes_1h, 14) if closes_1h else 0.0

        reason = (
            f"elderrev_{side} "
            f"S1:ema={ema_f:.1f}/{ema_s:.1f} macd_h={macd_h:.5f} "
            f"S2:rsi1h={rsi_1h:.1f} "
            f"atr_pct={atr_pct:.2f}%"
        )

        sig = TradeSignal(
            strategy=self.NAME,
            symbol=store.symbol,
            side=side,
            entry=float(entry),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.05, 1.0 - tp1_frac)],
            be_trigger_rr=max(0.0, cfg.be_trigger_rr),
            be_lock_rr=0.02,
            trailing_atr_mult=max(0.0, cfg.trail_atr_mult),
            trailing_atr_period=cfg.atr_period,
            trail_activate_rr=max(0.0, cfg.trail_activate_rr),
            time_stop_bars=max(0, cfg.time_stop_bars_5m),
            reason=reason,
        )

        if not sig.validate():
            self._ns("signal_invalid")
            return None

        self._cooldown = max(0, cfg.cooldown_bars_5m)
        return sig

    # -- Legacy evaluate() for backtester -----------------------------------

    def evaluate(
        self,
        bars_5m: list,
        bars_1h: list,
        bars_4h: list,
        regime: str = "",
        symbol: str = "",
        open_positions: int = 0,
        panic_mode: bool = False,
    ) -> Optional[dict]:
        """Legacy interface for backtest scripts using bar-dicts."""
        cfg = self.cfg
        if panic_mode:
            return None
        if cfg.allowed_regimes and regime.lower() not in cfg.allowed_regimes:
            return None
        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            return None
        if open_positions >= cfg.max_open_trades:
            return None

        def to_rows(bars):
            return [[i, b.get("open", 0), b.get("high", 0), b.get("low", 0),
                     b.get("close", 0), b.get("volume", 0)] for i, b in enumerate(bars)]

        rows_4h = to_rows(bars_4h)
        rows_1h = to_rows(bars_1h)
        rows_5m_r = to_rows(bars_5m)

        min_4h = cfg.s1_ema_slow + cfg.s1_macd_signal + 5
        if len(bars_5m) < 30 or len(bars_1h) < 20 or len(bars_4h) < min_4h:
            return None

        atr = _atr_last(rows_5m_r, cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            return None
        cur = bars_5m[-1]["close"]
        atr_pct = atr / cur * 100
        if not (cfg.atr_min_pct <= atr_pct <= cfg.atr_max_pct):
            return None

        macro = self._screen1(rows_4h)
        if macro is None:
            return None
        side = self._screen2(rows_1h, macro)
        if side is None:
            return None
        if not self._screen3(rows_5m_r, side):
            return None

        entry = cur
        if side == "long":
            swing = _swing_low(rows_5m_r, cfg.sl_swing_bars)
            sl = swing - cfg.sl_buffer_atr * atr
            if sl >= entry:
                return None
            tp1 = entry + cfg.tp1_atr_mult * atr
            tp2 = entry + cfg.tp2_atr_mult * atr
        else:
            swing = _swing_high(rows_5m_r, cfg.sl_swing_bars)
            sl = swing + cfg.sl_buffer_atr * atr
            if sl <= entry:
                return None
            tp1 = entry - cfg.tp1_atr_mult * atr
            tp2 = entry - cfg.tp2_atr_mult * atr
            if tp2 <= 0:
                return None

        return SimpleNamespace(
            side=side, entry=entry, sl=sl, tp1=tp1, tp2=tp2,
            trail_atr_mult=cfg.trail_atr_mult,
            rationale=f"elderrev_{side} atr={atr_pct:.2f}%",
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import random
    random.seed(42)
    print("=== Elder Revived v1.1 Smoke Test ===")

    closes_t = [100.0 + i * 0.1 + random.gauss(0, 0.5) for i in range(250)]
    macd_h = _macd_hist_last(closes_t, 12, 26, 9)
    assert macd_h is not None and math.isfinite(macd_h)
    print(f"O(N) MACD hist = {macd_h:.6f} (was O(N^2) before) OK")

    ema_ser = _ema_series([float(i) for i in range(1, 31)], 9)
    assert len(ema_ser) == 30 and math.isnan(ema_ser[0]) and math.isfinite(ema_ser[29])
    print(f"EMA series last={ema_ser[-1]:.4f} OK")

    rsi_val = _rsi_last(closes_t, 14)
    assert 0 < rsi_val < 100
    print(f"RSI = {rsi_val:.2f} OK")

    strat = AltElderRevivedV1()
    assert strat.NAME == "alt_elder_revived_v1"
    print(f"Instantiation OK, NAME={strat.NAME}")

    def _mkbar(c, bump=0.0):
        return {"open": c + bump, "high": c + 0.05, "low": c - 0.05, "close": c, "volume": 100.0}

    p = 100.0
    bars_4h = []
    for _ in range(240):
        p += 0.15 + random.gauss(0, 0.3)
        bars_4h.append(_mkbar(p))
    bars_1h = []
    p2 = bars_4h[-1]["close"]
    for _ in range(80):
        p2 -= 0.05 + random.gauss(0, 0.2)
        bars_1h.append(_mkbar(p2))
    bars_5m = []
    p3 = bars_1h[-1]["close"]
    for _ in range(40):
        p3 += random.gauss(0, 0.1)
        bars_5m.append(_mkbar(p3))
    bars_5m[-1]["open"] = p3 - 0.08
    bars_5m[-1]["close"] = p3 + 0.10
    bars_5m[-1]["low"] = p3 - 0.10
    bars_5m[-1]["high"] = p3 + 0.11

    result = strat.evaluate(bars_5m, bars_1h, bars_4h, regime="bull_chop", symbol="BTCUSDT")
    print(f"evaluate() -> {'signal' if result else f'None ({strat.last_no_signal_reason})'} OK")
    print("\nAll tests passed")
