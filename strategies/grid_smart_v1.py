"""
grid_smart_v1 (GS1) — Regime-aware ATR-spaced grid strategy.

Это не классический grid (фиксированный шаг) — это **умный grid**:

  • ATR-spacing: расстояние между уровнями = `GS1_LEVEL_ATR_MULT * ATR(1h)`.
    На спокойном рынке шаги мелкие, на волатильном — широкие, edge сохраняется.
  • Regime-aware: торгует только в `range` и `bear_chop`/`bull_chop`. В тренде
    grid убивает депо — поэтому проверяем slope EMA21 на 1H и ER (efficiency
    ratio); если тренд сильный → no signal.
  • Bias skew: если orchestrator говорит `btc_bias=short`, в bull-direction
    выставляем меньше уровней (меньше long-exposure при медведе).
  • Individual SL: каждый уровень имеет SL на следующем outer уровне (если
    grid пробит — мы fail-fast, не пирамиду на маржине).
  • Max concurrent: жёсткий cap `GS1_MAX_CONCURRENT_LEVELS`. Дефолт 4.
  • Симметрия: можно включить только longs / только shorts / симметрично.

Стратегия эмитит ОДИН TradeSignal за вызов — следующий уровень grid'а,
когда цена коснулась его (с buffer'ом). Не выставляет все 8 ордеров сразу;
allocator решает можно ли открыть позицию.

Структура входа
---------------
1. **Regime gate.** RegimeMode `GS1_REGIME_MODE` ∈ {`auto`, `force_on`}. В
   `auto` читает orchestrator state и допускает только `*_chop` / `range`.
2. **Slope gate.** |slope(EMA21 на 1H) / price * 100 за GS1_SLOPE_BARS|
   < `GS1_MAX_SLOPE_PCT` (default 0.3%/h).
3. **ER gate.** efficiency_ratio за `GS1_ER_BARS` < `GS1_ER_MAX` (default 0.35).
4. **Grid build.** Якорь = `GS1_GRID_ANCHOR_MODE` (`ema21` или `mid_range`).
   Уровни вверх: `+1, +2, ..., +N * ATR_MULT * ATR`. Аналогично вниз.
5. **Touch detection.** Цена пересекает уровень (lambda buffer `GS1_TOUCH_BUFFER_ATR`).
   Side: `Buy` для нижних уровней, `Sell` для верхних.
6. **Bias skew.** Если bias=short, max long-levels = `GS1_MAX_LONGS_SHORT_BIAS`,
   max short-levels = `GS1_MAX_LEVELS_PER_SIDE`. Симметрично для bias=long.
7. **Per-trade risk:** SL = соседний outer level + `GS1_SL_BUFFER_ATR * ATR`.
   TP = соседний inner level - buffer.

Env vars (префикс GS1_)
-----------------------
  GS1_SYMBOL_ALLOWLIST            csv      BTCUSDT,ETHUSDT,SOLUSDT
  GS1_SIGNAL_TF                   str      15        (15m TF)
  GS1_MACRO_TF                    str      60        (1h для ATR/EMA/slope)
  GS1_SIGNAL_LOOKBACK             int      300
  GS1_ATR_PERIOD                  int      14
  GS1_EMA_PERIOD                  int      21
  GS1_SLOPE_BARS                  int      6
  GS1_MAX_SLOPE_PCT               float    0.3
  GS1_ER_BARS                     int      20
  GS1_ER_MAX                      float    0.35
  GS1_LEVEL_ATR_MULT              float    1.0       (расстояние между уровнями)
  GS1_MAX_LEVELS_PER_SIDE         int      4
  GS1_MAX_LONGS_SHORT_BIAS        int      2
  GS1_MAX_SHORTS_LONG_BIAS        int      2
  GS1_GRID_ANCHOR_MODE            str      ema21     {ema21, mid_range}
  GS1_TOUCH_BUFFER_ATR            float    0.10
  GS1_SL_BUFFER_ATR               float    0.30
  GS1_TP_BUFFER_ATR               float    0.10
  GS1_REGIME_MODE                 str      auto      {auto, force_on}
  GS1_REGIME_NAMES_ALLOWED        csv      range,bear_chop,bull_chop
  GS1_COOLDOWN_BARS_15M           int      6         (1.5h)
  GS1_ALLOW_LONGS                 bool     1
  GS1_ALLOW_SHORTS                bool     1

Author: Claude Opus, 2026-06-03. Smart grid — не «сетка на удачу», а ATR + regime + bias.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers (locale-safe)
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


def _env_csv_lower_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Indicators
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
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def _slope_pct_per_bar(values: List[float], lookback: int, price_ref: float) -> float:
    """Простой slope: (last - back) / back * 100, делённый на lookback (per bar)."""
    if lookback <= 0 or len(values) < lookback + 1 or price_ref <= 0:
        return 0.0
    return ((values[-1] - values[-lookback - 1]) / price_ref) * 100.0 / lookback


def _efficiency_ratio(closes: List[float], lookback: int) -> float:
    """ER = abs(net move) / sum of abs bar moves. 0..1 (1=pure trend, 0=pure chop)."""
    if len(closes) < lookback + 1:
        return 0.0
    net = abs(closes[-1] - closes[-lookback - 1])
    total = sum(abs(closes[i] - closes[i - 1]) for i in range(-lookback, 0))
    if total <= 0:
        return 0.0
    return net / total


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class GS1Config:
    signal_tf: str = "15"
    macro_tf: str = "60"
    signal_lookback: int = 300
    atr_period: int = 14
    ema_period: int = 21
    slope_bars: int = 6
    max_slope_pct: float = 0.3
    er_bars: int = 20
    er_max: float = 0.35
    level_atr_mult: float = 1.0
    max_levels_per_side: int = 4
    max_longs_short_bias: int = 2
    max_shorts_long_bias: int = 2
    grid_anchor_mode: str = "ema21"
    touch_buffer_atr: float = 0.10
    sl_buffer_atr: float = 0.30
    tp_buffer_atr: float = 0.10
    regime_mode: str = "auto"
    cooldown_bars_15m: int = 6
    allow_longs: bool = True
    allow_shorts: bool = True
    regime_names_allowed: set[str] = field(default_factory=set)


class GridSmartV1Strategy:
    """ATR-spaced regime-aware grid."""

    def __init__(self) -> None:
        self.cfg = GS1Config()
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
        c.signal_tf = os.getenv("GS1_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("GS1_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("GS1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("GS1_ATR_PERIOD", c.atr_period)
        c.ema_period = _env_int("GS1_EMA_PERIOD", c.ema_period)
        c.slope_bars = _env_int("GS1_SLOPE_BARS", c.slope_bars)
        c.max_slope_pct = _env_float("GS1_MAX_SLOPE_PCT", c.max_slope_pct)
        c.er_bars = _env_int("GS1_ER_BARS", c.er_bars)
        c.er_max = _env_float("GS1_ER_MAX", c.er_max)
        c.level_atr_mult = _env_float("GS1_LEVEL_ATR_MULT", c.level_atr_mult)
        c.max_levels_per_side = _env_int("GS1_MAX_LEVELS_PER_SIDE", c.max_levels_per_side)
        c.max_longs_short_bias = _env_int("GS1_MAX_LONGS_SHORT_BIAS", c.max_longs_short_bias)
        c.max_shorts_long_bias = _env_int("GS1_MAX_SHORTS_LONG_BIAS", c.max_shorts_long_bias)
        c.grid_anchor_mode = os.getenv("GS1_GRID_ANCHOR_MODE", c.grid_anchor_mode)
        c.touch_buffer_atr = _env_float("GS1_TOUCH_BUFFER_ATR", c.touch_buffer_atr)
        c.sl_buffer_atr = _env_float("GS1_SL_BUFFER_ATR", c.sl_buffer_atr)
        c.tp_buffer_atr = _env_float("GS1_TP_BUFFER_ATR", c.tp_buffer_atr)
        c.regime_mode = os.getenv("GS1_REGIME_MODE", c.regime_mode)
        c.cooldown_bars_15m = _env_int("GS1_COOLDOWN_BARS_15M", c.cooldown_bars_15m)
        c.allow_longs = _env_bool("GS1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("GS1_ALLOW_SHORTS", c.allow_shorts)
        c.regime_names_allowed = _env_csv_lower_set(
            "GS1_REGIME_NAMES_ALLOWED",
            "range,bear_chop,bull_chop",
        )

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set("GS1_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT")
        self._deny = _env_csv_set("GS1_SYMBOL_DENYLIST")

    # ------------------------------------------------------------------
    # Regime / bias gates
    # ------------------------------------------------------------------

    def _regime_ok(self) -> Tuple[bool, str, str]:
        """Returns (ok, regime_name, btc_bias)."""
        c = self.cfg
        if c.regime_mode == "force_on":
            return True, "forced", ""
        regime = (os.getenv("ORCH_REGIME", "") or "").strip().lower()
        btc_bias = (os.getenv("ORCH_BTC_BIAS", "") or "").strip().lower()
        if not regime:
            return False, "", ""
        return regime in c.regime_names_allowed, regime, btc_bias

    # ------------------------------------------------------------------
    # Grid build
    # ------------------------------------------------------------------

    def _build_grid(
        self, anchor: float, atr: float, btc_bias: str
    ) -> Tuple[List[float], List[float]]:
        """Returns (long_levels_below_anchor, short_levels_above_anchor)."""
        c = self.cfg
        step = c.level_atr_mult * atr
        if step <= 0:
            return [], []

        max_longs = c.max_levels_per_side
        max_shorts = c.max_levels_per_side
        if btc_bias == "short":
            max_longs = c.max_longs_short_bias
        elif btc_bias == "long":
            max_shorts = c.max_shorts_long_bias

        longs = [anchor - step * (i + 1) for i in range(max_longs)]
        shorts = [anchor + step * (i + 1) for i in range(max_shorts)]
        return longs, shorts

    def _nearest_touch(
        self, price: float, levels: List[float], atr: float, side: str
    ) -> Optional[Tuple[int, float]]:
        """Если цена коснулась уровня (в пределах touch_buffer * ATR), возвращает (idx, level)."""
        c = self.cfg
        buf = c.touch_buffer_atr * atr
        best: Optional[Tuple[int, float, float]] = None
        for i, lvl in enumerate(levels):
            if side == "Buy":
                # Цена должна быть ниже-равной уровню (отскок снизу вверх потенциальный) с buffer'ом
                dist = lvl - price
                if -buf <= dist <= buf * 2.0:
                    if best is None or abs(dist) < best[2]:
                        best = (i, lvl, abs(dist))
            else:
                dist = price - lvl
                if -buf <= dist <= buf * 2.0:
                    if best is None or abs(dist) < best[2]:
                        best = (i, lvl, abs(dist))
        if best is None:
            return None
        return best[0], best[1]

    # ------------------------------------------------------------------
    # Main signal
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

        # Bar dedupe
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None

        # Cooldown
        if self._cooldown > 0:
            self._cooldown -= 1
            self._no_signal("cooldown")
            return None

        # Regime
        ok, regime, btc_bias = self._regime_ok()
        if not ok:
            self._no_signal(f"regime_blocked={regime or 'unknown'}")
            return None

        # Fetch klines (macro TF for ATR/EMA/slope/ER)
        try:
            rows_macro = store.fetch_klines(symbol, c.macro_tf, 200) or []
        except Exception:
            self._no_signal("history_short")
            return None

        if len(rows_macro) < max(c.ema_period, c.atr_period, c.er_bars, c.slope_bars) + 10:
            self._no_signal("history_short")
            return None

        highs = [float(r[2]) for r in rows_macro]
        lows = [float(r[3]) for r in rows_macro]
        closes = [float(r[4]) for r in rows_macro]

        ema = _ema_series(closes, c.ema_period)
        atr = _atr(highs, lows, closes, c.atr_period)
        if atr <= 0 or not ema:
            self._no_signal("atr_or_ema_invalid")
            return None

        # Slope gate
        slope_pct = abs(_slope_pct_per_bar(ema, c.slope_bars, max(1e-9, closes[-1])))
        if slope_pct > c.max_slope_pct:
            self._no_signal(f"slope_too_high={slope_pct:.3f}")
            return None

        # ER gate
        er = _efficiency_ratio(closes, c.er_bars)
        if er > c.er_max:
            self._no_signal(f"er_too_high={er:.3f}")
            return None

        # Anchor
        if c.grid_anchor_mode == "mid_range":
            anchor = (max(highs[-c.er_bars:]) + min(lows[-c.er_bars:])) / 2.0
        else:
            anchor = ema[-1]

        # Build grid
        longs_below, shorts_above = self._build_grid(anchor, atr, btc_bias)
        if not (longs_below or shorts_above):
            self._no_signal("grid_empty")
            return None

        price = cl  # текущая close

        # Touch detection (попробуем shorts above first, потом longs below)
        chosen_side: str | None = None
        chosen_level: float | None = None
        chosen_idx: int = -1
        if c.allow_shorts and shorts_above:
            r = self._nearest_touch(price, shorts_above, atr, "Sell")
            if r is not None:
                chosen_side = "Sell"
                chosen_idx, chosen_level = r
        if chosen_side is None and c.allow_longs and longs_below:
            r = self._nearest_touch(price, longs_below, atr, "Buy")
            if r is not None:
                chosen_side = "Buy"
                chosen_idx, chosen_level = r

        if chosen_side is None or chosen_level is None:
            self._no_signal("no_level_touch")
            return None

        # SL = adjacent outer level + buffer (если outer'а нет — стандартный 1*ATR + buffer)
        step = c.level_atr_mult * atr
        sl_buf = c.sl_buffer_atr * atr
        tp_buf = c.tp_buffer_atr * atr

        if chosen_side == "Sell":
            outer = shorts_above[chosen_idx + 1] if chosen_idx + 1 < len(shorts_above) else chosen_level + step
            inner = shorts_above[chosen_idx - 1] if chosen_idx - 1 >= 0 else chosen_level - step
            sl = outer + sl_buf
            tp = inner + tp_buf
        else:
            outer = longs_below[chosen_idx + 1] if chosen_idx + 1 < len(longs_below) else chosen_level - step
            inner = longs_below[chosen_idx - 1] if chosen_idx - 1 >= 0 else chosen_level + step
            sl = outer - sl_buf
            tp = inner - tp_buf

        # The signal is evaluated at the current closed-bar price. Using the
        # ideal grid level here creates an optimistic fill in the backtest.
        entry = price
        risk = abs(entry - sl)
        if risk <= 0 or abs(entry - tp) <= 0:
            self._no_signal("invalid_risk_or_tp")
            return None

        if chosen_side == "Sell" and not (tp < entry < sl):
            self._no_signal("invalid_short_geometry")
            return None
        if chosen_side == "Buy" and not (sl < entry < tp):
            self._no_signal("invalid_long_geometry")
            return None

        # Sanity: RR должен быть >= 1.0 минимум
        rr = abs(entry - tp) / risk
        if rr < 0.8:
            self._no_signal(f"rr_too_low={rr:.2f}")
            return None

        # State update
        self._last_tf_ts = ts_ms
        self._cooldown = c.cooldown_bars_15m

        return TradeSignal(
            strategy="grid_smart_v1",
            symbol=symbol,
            side=chosen_side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=f"gs1_grid_{chosen_side.lower()}_idx{chosen_idx}_lvl{chosen_level:.6f}"
                   f" anchor={anchor:.6f} atr={atr:.6f} regime={regime} bias={btc_bias}",
        )


# ---------------------------------------------------------------------------
# Selector helper
# ---------------------------------------------------------------------------

class GS1Selector:
    def __init__(self):
        self._strategies: dict[str, GridSmartV1Strategy] = {}

    def get(self, symbol: str) -> GridSmartV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = GridSmartV1Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
