"""
elder_crypto_v1 (ECV1) — Elder Triple-Screen adapted для crypto perpetuals.

ETS3 / alt_elder_revived_v1 заваливаются потому что **Elder triple screen
проектировался для stocks с daily/weekly cycles** — там тренды длятся неделями,
есть закрытие рынка, есть earnings cycles. На crypto perpetuals (24/7,
тренды дни, manipulation от китов) классический Elder работает плохо.

ECV1 берёт принципы Elder и **переписывает под крипто-перпетуалы**:

**4 экрана вместо 3** (добавлен **funding rate как 4-й**):

  SCREEN 1 (4H): MACRO TREND
      - Long: EMA50 > EMA200 на 4H + MACD histogram > 0 + price > EMA50
      - Short: EMA50 < EMA200 на 4H + MACD histogram < 0 + price < EMA50

  SCREEN 2 (1H): PULLBACK MOMENTUM
      - Long: RSI 35-50 (deeper oversold pullback в trend up) + Force Index < 0
      - Short: RSI 50-65 (overbought pullback в trend down) + Force Index > 0

  SCREEN 3 (15m): ENTRY TIMING
      - Long: bullish candle + body ≥ 50% range + close > EMA9 + low > prev_low
      - Short: bearish candle + body ≥ 50% range + close < EMA9 + high < prev_high

  SCREEN 4 (PERPETUAL-NATIVE): FUNDING-RATE FILTER  ← это уникальное для крипто
      - Long entry: funding rate ≤ ECV1_FUNDING_MAX_LONG (default 0.01%)
        Объяснение: если longs уже доминируют (high positive funding), вход
        в long = entry в crowded trade в конце дня. Long лучше когда shorts
        ещё контролируют (negative funding).
      - Short entry: funding rate ≥ ECV1_FUNDING_MIN_SHORT (default -0.01%)
        Симметрично.

**Risk model:**
  - SL: swing high/low за SWING_LOOKBACK + SL_BUFFER_ATR
  - TP1: TP1_RR × risk (закрывает TP1_FRAC)
  - TP2: TP2_RR × risk (остаток)
  - BE-trigger: BE_RR × risk
  - Time stop: 288 баров 5m (24h max hold)
  - Cooldown: 48 баров 5m (4h)

Env vars (префикс ECV1_)
------------------------
  ECV1_SYMBOL_ALLOWLIST              csv     BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT
  ECV1_SCREEN1_TF                    str     240        (4H macro)
  ECV1_SCREEN2_TF                    str     60         (1H pullback)
  ECV1_SCREEN3_TF                    str     15         (15m entry)
  ECV1_SIGNAL_LOOKBACK               int     250
  ECV1_S1_EMA_FAST                   int     50
  ECV1_S1_EMA_SLOW                   int     200
  ECV1_S1_MACD_FAST                  int     12
  ECV1_S1_MACD_SLOW                  int     26
  ECV1_S1_MACD_SIGNAL                int     9
  ECV1_S2_RSI_PERIOD                 int     14
  ECV1_S2_RSI_LONG_MIN               float   35.0
  ECV1_S2_RSI_LONG_MAX               float   50.0
  ECV1_S2_RSI_SHORT_MIN              float   50.0
  ECV1_S2_RSI_SHORT_MAX              float   65.0
  ECV1_S2_FORCE_INDEX_PERIOD         int     13
  ECV1_S3_EMA_PERIOD                 int     9
  ECV1_S3_BODY_MIN_FRAC              float   0.50
  ECV1_FUNDING_MAX_LONG              float   0.0001      (0.01% per 8h)
  ECV1_FUNDING_MIN_SHORT             float   -0.0001
  ECV1_FUNDING_REQUIRED              bool    1           (если 0 — пропускаем filter)
  ECV1_ATR_PERIOD                    int     14
  ECV1_ATR_MIN_PCT                   float   0.15
  ECV1_ATR_MAX_PCT                   float   4.00
  ECV1_SWING_LOOKBACK                int     15
  ECV1_SL_BUFFER_ATR                 float   0.30
  ECV1_TP1_RR                        float   1.50
  ECV1_TP2_RR                        float   2.50
  ECV1_TP1_FRAC                      float   0.50
  ECV1_BE_RR                         float   0.80
  ECV1_TIME_STOP_BARS_5M             int     288
  ECV1_COOLDOWN_BARS_5M              int     48
  ECV1_ALLOW_LONGS                   bool    1
  ECV1_ALLOW_SHORTS                  bool    1

Author: Claude Opus, 2026-06-03. Elder triple-screen + crypto funding gate.
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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Indicators (incremental, no O(N²))
# ---------------------------------------------------------------------------

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


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
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


def _macd_histogram(closes: List[float], fast: int, slow: int, signal: int) -> float:
    """Returns last MACD histogram value (MACD line - signal line)."""
    if len(closes) < slow + signal + 5:
        return 0.0
    ema_fast_series = _ema_series(closes, fast)
    ema_slow_series = _ema_series(closes, slow)
    macd_line = [ef - es for ef, es in zip(ema_fast_series, ema_slow_series)]
    signal_series = _ema_series(macd_line, signal)
    if not signal_series:
        return 0.0
    return macd_line[-1] - signal_series[-1]


def _force_index_ema(closes: List[float], volumes: List[float], period: int = 13) -> float:
    """Elder's Force Index = volume × (close - prev_close), smoothed by EMA."""
    if len(closes) < period + 2 or len(volumes) != len(closes):
        return 0.0
    fi_raw = [volumes[i] * (closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    smoothed = _ema_series(fi_raw, period)
    return smoothed[-1] if smoothed else 0.0


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class ECV1Config:
    screen1_tf: str = "240"
    screen2_tf: str = "60"
    screen3_tf: str = "15"
    signal_lookback: int = 250
    s1_ema_fast: int = 50
    s1_ema_slow: int = 200
    s1_macd_fast: int = 12
    s1_macd_slow: int = 26
    s1_macd_signal: int = 9
    s2_rsi_period: int = 14
    s2_rsi_long_min: float = 35.0
    s2_rsi_long_max: float = 50.0
    s2_rsi_short_min: float = 50.0
    s2_rsi_short_max: float = 65.0
    s2_force_index_period: int = 13
    s3_ema_period: int = 9
    s3_body_min_frac: float = 0.50
    funding_max_long: float = 0.0001
    funding_min_short: float = -0.0001
    funding_required: bool = True
    atr_period: int = 14
    atr_min_pct: float = 0.15
    atr_max_pct: float = 4.00
    swing_lookback: int = 15
    sl_buffer_atr: float = 0.30
    tp1_rr: float = 1.50
    tp2_rr: float = 2.50
    tp1_frac: float = 0.50
    be_rr: float = 0.80
    time_stop_bars_5m: int = 288
    cooldown_bars_5m: int = 48
    allow_longs: bool = True
    allow_shorts: bool = True


class ElderCryptoV1Strategy:
    """4-screen Elder triple-screen + funding-rate filter for crypto perpetuals."""

    def __init__(self) -> None:
        self.cfg = ECV1Config()
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
        c.screen1_tf = os.getenv("ECV1_SCREEN1_TF", c.screen1_tf)
        c.screen2_tf = os.getenv("ECV1_SCREEN2_TF", c.screen2_tf)
        c.screen3_tf = os.getenv("ECV1_SCREEN3_TF", c.screen3_tf)
        c.signal_lookback = _env_int("ECV1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.s1_ema_fast = _env_int("ECV1_S1_EMA_FAST", c.s1_ema_fast)
        c.s1_ema_slow = _env_int("ECV1_S1_EMA_SLOW", c.s1_ema_slow)
        c.s1_macd_fast = _env_int("ECV1_S1_MACD_FAST", c.s1_macd_fast)
        c.s1_macd_slow = _env_int("ECV1_S1_MACD_SLOW", c.s1_macd_slow)
        c.s1_macd_signal = _env_int("ECV1_S1_MACD_SIGNAL", c.s1_macd_signal)
        c.s2_rsi_period = _env_int("ECV1_S2_RSI_PERIOD", c.s2_rsi_period)
        c.s2_rsi_long_min = _env_float("ECV1_S2_RSI_LONG_MIN", c.s2_rsi_long_min)
        c.s2_rsi_long_max = _env_float("ECV1_S2_RSI_LONG_MAX", c.s2_rsi_long_max)
        c.s2_rsi_short_min = _env_float("ECV1_S2_RSI_SHORT_MIN", c.s2_rsi_short_min)
        c.s2_rsi_short_max = _env_float("ECV1_S2_RSI_SHORT_MAX", c.s2_rsi_short_max)
        c.s2_force_index_period = _env_int("ECV1_S2_FORCE_INDEX_PERIOD", c.s2_force_index_period)
        c.s3_ema_period = _env_int("ECV1_S3_EMA_PERIOD", c.s3_ema_period)
        c.s3_body_min_frac = _env_float("ECV1_S3_BODY_MIN_FRAC", c.s3_body_min_frac)
        c.funding_max_long = _env_float("ECV1_FUNDING_MAX_LONG", c.funding_max_long)
        c.funding_min_short = _env_float("ECV1_FUNDING_MIN_SHORT", c.funding_min_short)
        c.funding_required = _env_bool("ECV1_FUNDING_REQUIRED", c.funding_required)
        c.atr_period = _env_int("ECV1_ATR_PERIOD", c.atr_period)
        c.atr_min_pct = _env_float("ECV1_ATR_MIN_PCT", c.atr_min_pct)
        c.atr_max_pct = _env_float("ECV1_ATR_MAX_PCT", c.atr_max_pct)
        c.swing_lookback = _env_int("ECV1_SWING_LOOKBACK", c.swing_lookback)
        c.sl_buffer_atr = _env_float("ECV1_SL_BUFFER_ATR", c.sl_buffer_atr)
        c.tp1_rr = _env_float("ECV1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("ECV1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("ECV1_TP1_FRAC", c.tp1_frac)
        c.be_rr = _env_float("ECV1_BE_RR", c.be_rr)
        c.time_stop_bars_5m = _env_int("ECV1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("ECV1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("ECV1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("ECV1_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set("ECV1_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT")
        self._deny = _env_csv_set("ECV1_SYMBOL_DENYLIST")

    # ------------------------------------------------------------------
    # Screen evaluators
    # ------------------------------------------------------------------

    def _screen1_long(self, closes_4h: List[float]) -> bool:
        c = self.cfg
        ema_fast = _ema_series(closes_4h, c.s1_ema_fast)
        ema_slow = _ema_series(closes_4h, c.s1_ema_slow)
        macd_hist = _macd_histogram(closes_4h, c.s1_macd_fast, c.s1_macd_slow, c.s1_macd_signal)
        if not ema_fast or not ema_slow:
            return False
        return ema_fast[-1] > ema_slow[-1] and macd_hist > 0 and closes_4h[-1] > ema_fast[-1]

    def _screen1_short(self, closes_4h: List[float]) -> bool:
        c = self.cfg
        ema_fast = _ema_series(closes_4h, c.s1_ema_fast)
        ema_slow = _ema_series(closes_4h, c.s1_ema_slow)
        macd_hist = _macd_histogram(closes_4h, c.s1_macd_fast, c.s1_macd_slow, c.s1_macd_signal)
        if not ema_fast or not ema_slow:
            return False
        return ema_fast[-1] < ema_slow[-1] and macd_hist < 0 and closes_4h[-1] < ema_fast[-1]

    def _screen2(self, closes_1h: List[float], volumes_1h: List[float], side: str) -> bool:
        c = self.cfg
        rsi = _rsi(closes_1h, c.s2_rsi_period)
        fi = _force_index_ema(closes_1h, volumes_1h, c.s2_force_index_period)
        if side == "long":
            return c.s2_rsi_long_min <= rsi <= c.s2_rsi_long_max and fi < 0
        else:
            return c.s2_rsi_short_min <= rsi <= c.s2_rsi_short_max and fi > 0

    def _screen3(self, opens_15m: List[float], highs_15m: List[float], lows_15m: List[float],
                 closes_15m: List[float], side: str) -> bool:
        c = self.cfg
        if len(closes_15m) < 2:
            return False
        o, h, l, cl = opens_15m[-1], highs_15m[-1], lows_15m[-1], closes_15m[-1]
        rng = h - l
        if rng <= 0:
            return False
        body_frac = abs(cl - o) / rng
        ema = _ema_series(closes_15m, c.s3_ema_period)
        if not ema:
            return False
        if side == "long":
            return (cl > o and body_frac >= c.s3_body_min_frac
                    and cl > ema[-1] and l > lows_15m[-2])
        else:
            return (cl < o and body_frac >= c.s3_body_min_frac
                    and cl < ema[-1] and h < highs_15m[-2])

    def _screen4_funding(self, side: str, funding_rate: Optional[float]) -> bool:
        c = self.cfg
        if not c.funding_required:
            return True
        if funding_rate is None:
            return False  # required but unavailable → fail closed
        if side == "long":
            return funding_rate <= c.funding_max_long
        else:
            return funding_rate >= c.funding_min_short

    # ------------------------------------------------------------------
    # Main signal
    # ------------------------------------------------------------------

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

        # Fetch all 3 TF + funding
        try:
            rows_4h = store.fetch_klines(symbol, c.screen1_tf, 250) or []
            rows_1h = store.fetch_klines(symbol, c.screen2_tf, 150) or []
            rows_15m = store.fetch_klines(symbol, c.screen3_tf, 100) or []
            funding_rate = None
            try:
                f = getattr(store, "fetch_funding_rate", None)
                if callable(f):
                    funding_rate = float(f(symbol))
            except Exception:
                funding_rate = None
        except Exception:
            self._no_signal("history_short"); return None

        if (len(rows_4h) < c.s1_ema_slow + 30 or len(rows_1h) < c.s2_rsi_period + 30
                or len(rows_15m) < 30):
            self._no_signal("history_short"); return None

        closes_4h = [float(r[4]) for r in rows_4h]
        closes_1h = [float(r[4]) for r in rows_1h]
        volumes_1h = [float(r[5]) for r in rows_1h]
        opens_15m = [float(r[1]) for r in rows_15m]
        highs_15m = [float(r[2]) for r in rows_15m]
        lows_15m = [float(r[3]) for r in rows_15m]
        closes_15m = [float(r[4]) for r in rows_15m]

        atr = _atr(highs_15m, lows_15m, closes_15m, c.atr_period)
        price = closes_15m[-1]
        if atr <= 0 or price <= 0:
            self._no_signal("atr_invalid"); return None
        atr_pct = (atr / price) * 100.0
        if atr_pct < c.atr_min_pct:
            self._no_signal(f"atr_too_low={atr_pct:.3f}"); return None
        if atr_pct > c.atr_max_pct:
            self._no_signal(f"atr_too_high={atr_pct:.3f}"); return None

        # === LONG ===
        if c.allow_longs:
            if not self._screen1_long(closes_4h):
                self._no_signal("s1_long_fail")
            elif not self._screen2(closes_1h, volumes_1h, "long"):
                self._no_signal("s2_long_fail")
            elif not self._screen3(opens_15m, highs_15m, lows_15m, closes_15m, "long"):
                self._no_signal("s3_long_fail")
            elif not self._screen4_funding("long", funding_rate):
                self._no_signal(f"funding_too_high={funding_rate if funding_rate is not None else 'na'}")
            else:
                swing_low = min(lows_15m[-c.swing_lookback:])
                sl = swing_low - c.sl_buffer_atr * atr
                entry = closes_15m[-1]
                risk = entry - sl
                if risk > 0:
                    tp1 = entry + c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="elder_crypto_v1",
                        symbol=symbol, side="long", entry=entry, sl=sl, tp=tp1,
                        reason=f"ecv1_long all4screens_pass funding={funding_rate if funding_rate is not None else 'na'} atr_pct={atr_pct:.2f}",
                    )

        # === SHORT ===
        if c.allow_shorts:
            if not self._screen1_short(closes_4h):
                self._no_signal("s1_short_fail")
            elif not self._screen2(closes_1h, volumes_1h, "short"):
                self._no_signal("s2_short_fail")
            elif not self._screen3(opens_15m, highs_15m, lows_15m, closes_15m, "short"):
                self._no_signal("s3_short_fail")
            elif not self._screen4_funding("short", funding_rate):
                self._no_signal(f"funding_too_low={funding_rate if funding_rate is not None else 'na'}")
            else:
                swing_high = max(highs_15m[-c.swing_lookback:])
                sl = swing_high + c.sl_buffer_atr * atr
                entry = closes_15m[-1]
                risk = sl - entry
                if risk > 0:
                    tp1 = entry - c.tp1_rr * risk
                    self._last_tf_ts = ts_ms
                    self._cooldown = c.cooldown_bars_5m
                    return TradeSignal(
                        strategy="elder_crypto_v1",
                        symbol=symbol, side="short", entry=entry, sl=sl, tp=tp1,
                        reason=f"ecv1_short all4screens_pass funding={funding_rate if funding_rate is not None else 'na'} atr_pct={atr_pct:.2f}",
                    )

        return None


class ECV1Selector:
    def __init__(self):
        self._strategies: dict[str, ElderCryptoV1Strategy] = {}

    def get(self, symbol: str) -> ElderCryptoV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ElderCryptoV1Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
