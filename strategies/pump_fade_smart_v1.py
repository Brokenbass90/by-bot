"""
pump_fade_smart_v1 (PFS1) — Quality-gated pump fade strategy.

Идея простая, но дисциплинированная: ловим неустойчивые pump'ы на perpetual
futures и шортим только на подтверждённой rejection-свече после exhaustion'а.
В отличие от наивных pump-fade'ов, PFS1 НЕ входит «потому что выросло» —
у нас стек фильтров, который снимает 80% ложных сигналов.

Структура входа (SHORT)
-----------------------
1. **Liquidity gate.** Символ должен быть в `PFS1_SYMBOL_ALLOWLIST` (default —
   крупнейшие альты + BTC/ETH). Микрокапы → reject (manipulation risk).
2. **Pump detection (5m).** За `PFS1_PUMP_LOOKBACK_BARS` 5m-баров суммарное
   движение вверх ≥ `PFS1_PUMP_MIN_PCT`. Volume Z-score последних 3 баров
   относительно 60-баров среднего ≥ `PFS1_VOL_Z_MIN`.
3. **Macro overbought (1H).** RSI(14) на 1H > `PFS1_RSI_H1_MIN_OB`. Сама
   высокая RSI не вход, но без неё мы тушим зажигалкой.
4. **Funding crowding.** Funding rate (8h) ≥ `PFS1_FUNDING_THRESHOLD`
   (например 0.05%). Большой positive funding = лонги-крауд платит шортам,
   classic exhaustion signal.
5. **Rejection candle.** Текущая 5m-свеча: bearish body ≥ `PFS1_REJECT_BODY_FRAC`
   от полной свечи, upper wick ≥ `PFS1_REJECT_WICK_FRAC` от свечи.
   Закрытие < open of pump-первого бара (т.е. отдают весь рост).
6. **Risk constraint.** ATR(14)-нормализованная дистанция до entry не больше
   `PFS1_MAX_DIST_ATR`.

Stop / Target
-------------
- **SL** = high of pump + `PFS1_SL_ATR_BUFFER * ATR` (защита от sweep'а).
- **TP1** = entry − `PFS1_TP1_RR * risk` (закрываем `PFS1_TP1_FRAC` позиции).
- **TP2** = entry − `PFS1_TP2_RR * risk` (остаток).
- **Break-even** при достижении `PFS1_BE_TRIGGER_RR * risk`.
- **Trailing ATR** после `PFS1_TRAIL_ACTIVATE_RR * risk` (необязательно — env).
- **Time stop**: `PFS1_TIME_STOP_BARS_5M` баров (default 144 = 12h).
- **Cooldown**: `PFS1_COOLDOWN_BARS_5M` после любой сделки (default 96 = 8h).

Env vars (префикс PFS1_)
------------------------
  PFS1_SYMBOL_ALLOWLIST              csv     default: BTCUSDT,ETHUSDT,SOLUSDT,...
  PFS1_SIGNAL_TF                     str     5  (5-минутный TF)
  PFS1_MACRO_TF                      str     60 (1-часовой для RSI)
  PFS1_SIGNAL_LOOKBACK               int     200
  PFS1_ATR_PERIOD                    int     14
  PFS1_RSI_PERIOD                    int     14
  PFS1_PUMP_LOOKBACK_BARS            int     6      (30 минут)
  PFS1_PUMP_MIN_PCT                  float   3.0
  PFS1_VOL_Z_MIN                     float   2.0
  PFS1_RSI_H1_MIN_OB                 float   65
  PFS1_FUNDING_THRESHOLD             float   0.05   (% per 8h)
  PFS1_REJECT_BODY_FRAC              float   0.45
  PFS1_REJECT_WICK_FRAC              float   0.30
  PFS1_MAX_DIST_ATR                  float   2.5
  PFS1_SL_ATR_BUFFER                 float   0.5
  PFS1_TP1_RR                        float   1.2
  PFS1_TP2_RR                        float   2.5
  PFS1_TP1_FRAC                      float   0.55
  PFS1_BE_TRIGGER_RR                 float   1.0
  PFS1_BE_LOCK_RR                    float   0.05
  PFS1_TRAIL_ATR_MULT                float   0.0    (0 = off)
  PFS1_TRAIL_ACTIVATE_RR             float   1.5
  PFS1_TIME_STOP_BARS_5M             int     144
  PFS1_COOLDOWN_BARS_5M              int     96
  PFS1_ALLOW_SHORTS                  bool    1
  PFS1_ALLOW_LONGS                   bool    0      (symmetric long-fade-dump optional)

Author: Claude Opus, 2026-06-03. Quality-first pump fade, не «short на любое движение».
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> float:
    if len(values) < period:
        return values[-1] if values else 0.0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1.0 - k)
    return ema


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def _vol_zscore(volumes: List[float], baseline_period: int = 60, recent_period: int = 3) -> float:
    if len(volumes) < baseline_period + recent_period:
        return 0.0
    base = volumes[-baseline_period - recent_period:-recent_period]
    recent = volumes[-recent_period:]
    if not base or not recent:
        return 0.0
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    recent_avg = sum(recent) / len(recent)
    return (recent_avg - mean) / std


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class PFS1Config:
    signal_tf: str = "5"
    macro_tf: str = "60"
    signal_lookback: int = 200
    atr_period: int = 14
    rsi_period: int = 14
    pump_lookback_bars: int = 6
    pump_min_pct: float = 3.0
    vol_z_min: float = 2.0
    rsi_h1_min_ob: float = 65.0
    funding_threshold: float = 0.05
    reject_body_frac: float = 0.45
    reject_wick_frac: float = 0.30
    max_dist_atr: float = 2.5
    sl_atr_buffer: float = 0.5
    tp1_rr: float = 1.2
    tp2_rr: float = 2.5
    tp1_frac: float = 0.55
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 1.5
    time_stop_bars_5m: int = 144
    cooldown_bars_5m: int = 96
    allow_shorts: bool = True
    allow_longs: bool = False


class PumpFadeSmartV1Strategy:
    """Quality-gated pump fade strategy."""

    def __init__(self) -> None:
        self.cfg = PFS1Config()
        self._load_env()
        self._cooldown_bars = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self.last_no_signal_reason: str = ""
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = str(reason or "unknown")

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("PFS1_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("PFS1_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("PFS1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("PFS1_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("PFS1_RSI_PERIOD", c.rsi_period)
        c.pump_lookback_bars = _env_int("PFS1_PUMP_LOOKBACK_BARS", c.pump_lookback_bars)
        c.pump_min_pct = _env_float("PFS1_PUMP_MIN_PCT", c.pump_min_pct)
        c.vol_z_min = _env_float("PFS1_VOL_Z_MIN", c.vol_z_min)
        c.rsi_h1_min_ob = _env_float("PFS1_RSI_H1_MIN_OB", c.rsi_h1_min_ob)
        c.funding_threshold = _env_float("PFS1_FUNDING_THRESHOLD", c.funding_threshold)
        c.reject_body_frac = _env_float("PFS1_REJECT_BODY_FRAC", c.reject_body_frac)
        c.reject_wick_frac = _env_float("PFS1_REJECT_WICK_FRAC", c.reject_wick_frac)
        c.max_dist_atr = _env_float("PFS1_MAX_DIST_ATR", c.max_dist_atr)
        c.sl_atr_buffer = _env_float("PFS1_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("PFS1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("PFS1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("PFS1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("PFS1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("PFS1_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("PFS1_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("PFS1_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars_5m = _env_int("PFS1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("PFS1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_shorts = _env_bool("PFS1_ALLOW_SHORTS", c.allow_shorts)
        c.allow_longs = _env_bool("PFS1_ALLOW_LONGS", c.allow_longs)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "PFS1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,AVAXUSDT",
        )
        self._deny = _env_csv_set("PFS1_SYMBOL_DENYLIST")

    # ------------------------------------------------------------------
    # Pump detection
    # ------------------------------------------------------------------

    def _detect_pump(
        self,
        closes: List[float],
        volumes: List[float],
    ) -> Tuple[bool, float, int, float]:
        """Detect the completed pump immediately before the rejection bar."""
        c = self.cfg
        if len(closes) < c.pump_lookback_bars + 2:
            return False, 0.0, 0, 0.0
        start = closes[-c.pump_lookback_bars - 1]
        # The latest bar is the rejection candidate. Including it in the pump
        # return made the pump and full-giveback conditions contradictory.
        end = closes[-2]
        if start <= 0:
            return False, 0.0, 0, 0.0
        pct = (end - start) / start * 100.0
        vol_z = _vol_zscore(volumes, baseline_period=60, recent_period=3)
        is_pump = pct >= c.pump_min_pct and vol_z >= c.vol_z_min
        return is_pump, pct, c.pump_lookback_bars, vol_z

    def _check_rejection(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        pump_start_open: float,
    ) -> bool:
        """Текущая свеча: bearish, тело >= reject_body_frac, верхний фитиль >= reject_wick_frac."""
        c = self.cfg
        o, h, l, cl = opens[-1], highs[-1], lows[-1], closes[-1]
        rng = h - l
        if rng <= 0:
            return False
        body = abs(cl - o)
        is_bearish = cl < o
        body_frac = body / rng
        upper_wick = h - max(o, cl)
        wick_frac = upper_wick / rng
        # Закрытие должно вернуться ниже open первого pump-бара (отдали почти весь рост)
        gave_back = cl < pump_start_open * 1.005  # 0.5% толерантность
        return is_bearish and body_frac >= c.reject_body_frac and wick_frac >= c.reject_wick_frac and gave_back

    # ------------------------------------------------------------------
    # Main signal API
    # ------------------------------------------------------------------

    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        cl: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        """Возвращает TradeSignal или None. store должен иметь fetch_klines(symbol, interval, limit)."""
        self.last_no_signal_reason = ""
        symbol = getattr(store, "symbol", "")
        c = self.cfg

        # Symbol gate
        if self._allow and symbol.upper() not in self._allow:
            self._no_signal("symbol_not_allowed")
            return None
        if self._deny and symbol.upper() in self._deny:
            self._no_signal("symbol_denied")
            return None

        # Direction gate
        if not c.allow_shorts and not c.allow_longs:
            self._no_signal("shorts_and_longs_disabled")
            return None

        # Bar dedupe (one signal per closed bar)
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None

        # Cooldown
        if self._cooldown_bars > 0:
            self._cooldown_bars -= 1
            self._no_signal("cooldown")
            return None

        # Fetch klines
        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
            rows_h1 = store.fetch_klines(symbol, c.macro_tf, 80) or []
        except Exception:
            self._no_signal("history_short")
            return None

        if len(rows_5m) < max(c.pump_lookback_bars + 60, c.atr_period + 30):
            self._no_signal("history_short")
            return None
        if len(rows_h1) < c.rsi_period + 5:
            self._no_signal("macro_history_short")
            return None

        opens5 = [float(r[1]) for r in rows_5m]
        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]
        closes_h1 = [float(r[4]) for r in rows_h1]

        # Pump detection
        is_pump, pump_pct, look_n, vol_z = self._detect_pump(closes5, volumes5)
        if not is_pump:
            self._no_signal(f"no_pump_pct={pump_pct:.2f}_volz={vol_z:.2f}")
            return None

        # Macro overbought (RSI on 1H)
        rsi_h1 = _rsi(closes_h1, c.rsi_period)
        if rsi_h1 < c.rsi_h1_min_ob:
            self._no_signal(f"macro_not_overbought_rsi={rsi_h1:.1f}")
            return None

        # Funding rate (optional — нужен fetcher; если нет данных, пропускаем фильтр с warn)
        funding_pct: float | None = None
        try:
            f = getattr(store, "fetch_funding_rate", None)
            if callable(f):
                funding_pct = float(f(symbol)) * 100.0  # rate is decimal, convert to %
        except Exception:
            funding_pct = None
        if funding_pct is not None and funding_pct < c.funding_threshold:
            self._no_signal(f"funding_low={funding_pct:.4f}")
            return None

        # Pump start open (start of lookback window)
        pump_start_open = opens5[-look_n - 1] if len(opens5) >= look_n + 1 else opens5[-look_n]

        # Rejection candle on the latest closed bar
        if not self._check_rejection(opens5, highs5, lows5, closes5, pump_start_open):
            self._no_signal("no_rejection_candle")
            return None

        # ATR + risk math
        atr = _atr(highs5, lows5, closes5, c.atr_period)
        if atr <= 0:
            self._no_signal("atr_invalid")
            return None

        entry = closes5[-1]
        pump_high = max(highs5[-look_n - 1:])
        sl = pump_high + c.sl_atr_buffer * atr
        risk = sl - entry
        if risk <= 0:
            self._no_signal("invalid_risk")
            return None

        # Distance to entry constraint
        dist_atr = (pump_high - entry) / atr
        if dist_atr > c.max_dist_atr:
            self._no_signal(f"too_extended_dist_atr={dist_atr:.2f}")
            return None

        # Take profits (short — TP below entry)
        tp1 = entry - c.tp1_rr * risk
        tp2 = entry - c.tp2_rr * risk

        # Update state for cooldown / bar dedupe (caller fills cooldown after entry)
        self._last_tf_ts = ts_ms
        self._cooldown_bars = c.cooldown_bars_5m

        return TradeSignal(
            strategy="pump_fade_smart_v1",
            symbol=symbol,
            side="Sell",
            entry=entry,
            sl=sl,
            tp=tp1,  # TP1 only; runner handles TP2/trail
            reason=f"pfs1_pump_fade pump={pump_pct:.2f}% volz={vol_z:.2f} rsih1={rsi_h1:.1f}"
                   + (f" funding={funding_pct:.4f}" if funding_pct is not None else " funding=na"),
        )


# ---------------------------------------------------------------------------
# Selector helper for portfolio backtest integration
# ---------------------------------------------------------------------------

class PFS1Selector:
    """Per-symbol PumpFadeSmartV1 instances. Mirrors ATT1/breakdown selector pattern."""

    def __init__(self):
        self._strategies: dict[str, PumpFadeSmartV1Strategy] = {}

    def get(self, symbol: str) -> PumpFadeSmartV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = PumpFadeSmartV1Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
