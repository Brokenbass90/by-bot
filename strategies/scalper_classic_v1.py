"""
scalper_classic_v1 (SC1) — Classic scalper-mode strategy.

Реализует три классических скальперских setup'а через единый интерфейс,
переключаемых через `SC1_MODE`:

  • `bounce` — wick-bounce от свежего pivot support/resistance
  • `sweep`  — liquidity sweep + reverse (stop-hunt fade)
  • `breakout` — range breakout с volume spike confirmation

Базируется на 5-минутном TF с macro-cross-check на 15m/1H. Жёсткие SL,
быстрые TP, time-stop по умолчанию 30 баров (2.5h).

Структура входа (SHORT example для sweep mode)
----------------------------------------------
1. **Symbol gate** — `SC1_SYMBOL_ALLOWLIST` (BTC/ETH/major alts)
2. **Mode-specific detection** (см. ниже)
3. **Volume confirmation** — current bar volume z-score ≥ `SC1_VOL_Z_MIN`
4. **Cross-TF non-conflict** — 15m EMA21 не сильно против direction
   (за `SC1_MACRO_SLOPE_BARS` baрous: |slope| < `SC1_MAX_CONFLICT_SLOPE_PCT`)
5. **ATR sanity** — ATR_PCT в рамках `SC1_MIN_ATR_PCT..SC1_MAX_ATR_PCT`
6. **Cooldown** — `SC1_COOLDOWN_BARS_5M` (default 12 = 1h)

Mode: bounce
  - Найти recent swing low/high за `SC1_PIVOT_LOOKBACK` баров
  - Текущая свеча: wick to pivot + reject candle (body opposite, ≥
    `SC1_REJECT_BODY_FRAC`)
  - Entry: close of reject candle; SL: pivot ± `SC1_SL_ATR_BUFFER * ATR`
  - TP1: entry ± `SC1_TP1_RR * risk`; TP2: `SC1_TP2_RR * risk`

Mode: sweep
  - Detect liquidity sweep: high/low за `SC1_SWEEP_LOOKBACK` баров пробит +
    закрытие обратно за уровень в той же или следующей свече
  - Entry: close of reverse candle
  - SL: extreme of sweep ± `SC1_SL_ATR_BUFFER * ATR`
  - TP1/TP2 как bounce

Mode: breakout
  - Detect tight range за `SC1_RANGE_LOOKBACK` баров (high-low < `SC1_RANGE_MAX_ATR`)
  - Break out of range + volume spike ≥ `SC1_BREAKOUT_VOL_Z_MIN`
  - Entry: close after break confirmation bar
  - SL: opposite range edge ± buffer
  - TP1/TP2 как bounce

Env vars (префикс SC1_)
-----------------------
  SC1_SYMBOL_ALLOWLIST           csv     BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT
  SC1_SIGNAL_TF                  str     5
  SC1_MACRO_TF                   str     15
  SC1_SIGNAL_LOOKBACK            int     180
  SC1_ATR_PERIOD                 int     14
  SC1_MODE                       str     bounce   {bounce, sweep, breakout}
  SC1_PIVOT_LOOKBACK             int     20
  SC1_SWEEP_LOOKBACK             int     30
  SC1_RANGE_LOOKBACK             int     20
  SC1_RANGE_MAX_ATR              float   2.5
  SC1_REJECT_BODY_FRAC           float   0.45
  SC1_REJECT_WICK_FRAC           float   0.30
  SC1_BREAKOUT_VOL_Z_MIN         float   2.0
  SC1_VOL_Z_MIN                  float   1.0
  SC1_MIN_ATR_PCT                float   0.20
  SC1_MAX_ATR_PCT                float   3.50
  SC1_MAX_CONFLICT_SLOPE_PCT     float   0.40
  SC1_MACRO_SLOPE_BARS           int     6
  SC1_SL_ATR_BUFFER              float   0.30
  SC1_TP1_RR                     float   0.80
  SC1_TP2_RR                     float   1.50
  SC1_TP1_FRAC                   float   0.55
  SC1_BE_TRIGGER_RR              float   0.50
  SC1_TIME_STOP_BARS_5M          int     30
  SC1_COOLDOWN_BARS_5M           int     12
  SC1_ALLOW_LONGS                bool    1
  SC1_ALLOW_SHORTS               bool    1

Author: Claude Opus, 2026-06-03. Скальперская классика (bounce/sweep/breakout).
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


def _vol_zscore(volumes: List[float], baseline_period: int = 30, recent_n: int = 1) -> float:
    if len(volumes) < baseline_period + recent_n:
        return 0.0
    base = volumes[-baseline_period - recent_n:-recent_n]
    recent = volumes[-recent_n:]
    mean = sum(base) / len(base) if base else 0.0
    if not base:
        return 0.0
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    return ((sum(recent) / len(recent)) - mean) / std


def _slope_pct_per_bar(values: List[float], lookback: int, price_ref: float) -> float:
    if lookback <= 0 or len(values) < lookback + 1 or price_ref <= 0:
        return 0.0
    return ((values[-1] - values[-lookback - 1]) / price_ref) * 100.0 / lookback


def _find_swing_lows(lows: List[float], left: int = 2, right: int = 2) -> List[Tuple[int, float]]:
    out = []
    for i in range(left, len(lows) - right):
        win = lows[i - left:i + right + 1]
        if lows[i] == min(win):
            out.append((i, lows[i]))
    return out


def _find_swing_highs(highs: List[float], left: int = 2, right: int = 2) -> List[Tuple[int, float]]:
    out = []
    for i in range(left, len(highs) - right):
        win = highs[i - left:i + right + 1]
        if highs[i] == max(win):
            out.append((i, highs[i]))
    return out


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class SC1Config:
    signal_tf: str = "5"
    macro_tf: str = "15"
    signal_lookback: int = 180
    atr_period: int = 14
    mode: str = "bounce"
    pivot_lookback: int = 20
    sweep_lookback: int = 30
    range_lookback: int = 20
    range_max_atr: float = 2.5
    reject_body_frac: float = 0.45
    reject_wick_frac: float = 0.30
    breakout_vol_z_min: float = 2.0
    vol_z_min: float = 1.0
    min_atr_pct: float = 0.20
    max_atr_pct: float = 3.50
    max_conflict_slope_pct: float = 0.40
    macro_slope_bars: int = 6
    sl_atr_buffer: float = 0.30
    tp1_rr: float = 0.80
    tp2_rr: float = 1.50
    tp1_frac: float = 0.55
    be_trigger_rr: float = 0.50
    time_stop_bars_5m: int = 30
    cooldown_bars_5m: int = 12
    allow_longs: bool = True
    allow_shorts: bool = True


class ScalperClassicV1Strategy:
    """3-mode scalper: bounce / sweep / breakout."""

    def __init__(self) -> None:
        self.cfg = SC1Config()
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
        c.signal_tf = os.getenv("SC1_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("SC1_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("SC1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("SC1_ATR_PERIOD", c.atr_period)
        c.mode = os.getenv("SC1_MODE", c.mode).strip().lower()
        c.pivot_lookback = _env_int("SC1_PIVOT_LOOKBACK", c.pivot_lookback)
        c.sweep_lookback = _env_int("SC1_SWEEP_LOOKBACK", c.sweep_lookback)
        c.range_lookback = _env_int("SC1_RANGE_LOOKBACK", c.range_lookback)
        c.range_max_atr = _env_float("SC1_RANGE_MAX_ATR", c.range_max_atr)
        c.reject_body_frac = _env_float("SC1_REJECT_BODY_FRAC", c.reject_body_frac)
        c.reject_wick_frac = _env_float("SC1_REJECT_WICK_FRAC", c.reject_wick_frac)
        c.breakout_vol_z_min = _env_float("SC1_BREAKOUT_VOL_Z_MIN", c.breakout_vol_z_min)
        c.vol_z_min = _env_float("SC1_VOL_Z_MIN", c.vol_z_min)
        c.min_atr_pct = _env_float("SC1_MIN_ATR_PCT", c.min_atr_pct)
        c.max_atr_pct = _env_float("SC1_MAX_ATR_PCT", c.max_atr_pct)
        c.max_conflict_slope_pct = _env_float("SC1_MAX_CONFLICT_SLOPE_PCT", c.max_conflict_slope_pct)
        c.macro_slope_bars = _env_int("SC1_MACRO_SLOPE_BARS", c.macro_slope_bars)
        c.sl_atr_buffer = _env_float("SC1_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("SC1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("SC1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("SC1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("SC1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.time_stop_bars_5m = _env_int("SC1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("SC1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("SC1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("SC1_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "SC1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT",
        )
        self._deny = _env_csv_set("SC1_SYMBOL_DENYLIST")

    # ------------------------------------------------------------------
    # Common pre-checks
    # ------------------------------------------------------------------

    def _passes_common_gates(self, symbol: str, ts_ms: int) -> Optional[str]:
        if self._allow and symbol.upper() not in self._allow:
            return "symbol_not_allowed"
        if self._deny and symbol.upper() in self._deny:
            return "symbol_denied"
        if not self.cfg.allow_shorts and not self.cfg.allow_longs:
            return "both_sides_disabled"
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            return "same_signal_bar"
        if self._cooldown > 0:
            self._cooldown -= 1
            return "cooldown"
        return None

    # ------------------------------------------------------------------
    # Mode: BOUNCE
    # ------------------------------------------------------------------

    def _detect_bounce(self, opens: List[float], highs: List[float], lows: List[float],
                       closes: List[float], atr: float) -> Optional[dict]:
        """Wick-bounce off recent pivot. Returns dict with side/entry/sl OR None."""
        c = self.cfg
        n = len(closes)
        if n < c.pivot_lookback + 5:
            return None

        # Last bar = our candidate
        o, h, l, cl = opens[-1], highs[-1], lows[-1], closes[-1]
        rng = h - l
        if rng <= 0:
            return None
        body = abs(cl - o)
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - l

        # Long bounce: lower wick touches recent swing low, bullish reject body
        recent_lows = _find_swing_lows(lows[-c.pivot_lookback - 5:], left=2, right=2)
        recent_highs = _find_swing_highs(highs[-c.pivot_lookback - 5:], left=2, right=2)

        if c.allow_longs and recent_lows:
            pivot = max(recent_lows, key=lambda x: x[0])[1]  # most recent low
            touched = l <= pivot + 0.20 * atr
            is_bullish_reject = cl > o and (body / rng) >= c.reject_body_frac and (lower_wick / rng) >= c.reject_wick_frac
            if touched and is_bullish_reject:
                sl = pivot - c.sl_atr_buffer * atr
                return {"side": "Buy", "entry": cl, "sl": sl, "ref": pivot, "mode": "bounce_long"}

        if c.allow_shorts and recent_highs:
            pivot = max(recent_highs, key=lambda x: x[0])[1]
            touched = h >= pivot - 0.20 * atr
            is_bearish_reject = cl < o and (body / rng) >= c.reject_body_frac and (upper_wick / rng) >= c.reject_wick_frac
            if touched and is_bearish_reject:
                sl = pivot + c.sl_atr_buffer * atr
                return {"side": "Sell", "entry": cl, "sl": sl, "ref": pivot, "mode": "bounce_short"}

        return None

    # ------------------------------------------------------------------
    # Mode: SWEEP (liquidity sweep + reverse)
    # ------------------------------------------------------------------

    def _detect_sweep(self, opens: List[float], highs: List[float], lows: List[float],
                      closes: List[float], atr: float) -> Optional[dict]:
        c = self.cfg
        n = len(closes)
        if n < c.sweep_lookback + 5:
            return None
        o, h, l, cl = opens[-1], highs[-1], lows[-1], closes[-1]

        # Lookback range (excl. current bar)
        prior_highs = highs[-c.sweep_lookback - 1:-1]
        prior_lows = lows[-c.sweep_lookback - 1:-1]
        prior_max_high = max(prior_highs) if prior_highs else 0
        prior_min_low = min(prior_lows) if prior_lows else 0

        # Short sweep: high spiked above prior_max_high but close back below
        if c.allow_shorts and h > prior_max_high and cl < prior_max_high:
            sl = h + c.sl_atr_buffer * atr
            return {"side": "Sell", "entry": cl, "sl": sl, "ref": prior_max_high, "mode": "sweep_short"}

        # Long sweep: low spiked below prior_min_low but close back above
        if c.allow_longs and l < prior_min_low and cl > prior_min_low:
            sl = l - c.sl_atr_buffer * atr
            return {"side": "Buy", "entry": cl, "sl": sl, "ref": prior_min_low, "mode": "sweep_long"}

        return None

    # ------------------------------------------------------------------
    # Mode: BREAKOUT (tight range break with volume)
    # ------------------------------------------------------------------

    def _detect_breakout(self, opens: List[float], highs: List[float], lows: List[float],
                         closes: List[float], volumes: List[float], atr: float) -> Optional[dict]:
        c = self.cfg
        n = len(closes)
        if n < c.range_lookback + 5:
            return None
        o, h, l, cl = opens[-1], highs[-1], lows[-1], closes[-1]

        # Prior range
        prior_highs = highs[-c.range_lookback - 1:-1]
        prior_lows = lows[-c.range_lookback - 1:-1]
        if not prior_highs or not prior_lows:
            return None
        range_top = max(prior_highs)
        range_bot = min(prior_lows)
        rng = range_top - range_bot
        if rng <= 0 or atr <= 0:
            return None

        # Tight range filter
        if rng > c.range_max_atr * atr:
            return None

        # Volume spike on current bar
        vol_z = _vol_zscore(volumes, baseline_period=30, recent_n=1)
        if vol_z < c.breakout_vol_z_min:
            return None

        # Long break: close > range_top
        if c.allow_longs and cl > range_top:
            sl = range_bot - c.sl_atr_buffer * atr
            return {"side": "Buy", "entry": cl, "sl": sl, "ref": range_top, "mode": "breakout_long"}

        # Short break: close < range_bot
        if c.allow_shorts and cl < range_bot:
            sl = range_top + c.sl_atr_buffer * atr
            return {"side": "Sell", "entry": cl, "sl": sl, "ref": range_bot, "mode": "breakout_short"}

        return None

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

        gate = self._passes_common_gates(symbol, ts_ms)
        if gate is not None:
            self._no_signal(gate)
            return None

        # Fetch klines
        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
            rows_macro = store.fetch_klines(symbol, c.macro_tf, 80) or []
        except Exception:
            self._no_signal("history_short")
            return None

        if len(rows_5m) < max(c.pivot_lookback, c.sweep_lookback, c.range_lookback) + 10:
            self._no_signal("history_short")
            return None
        if len(rows_macro) < c.macro_slope_bars + 25:
            self._no_signal("macro_history_short")
            return None

        opens5 = [float(r[1]) for r in rows_5m]
        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]
        closes_macro = [float(r[4]) for r in rows_macro]

        # ATR + ATR_PCT sanity
        atr = _atr(highs5, lows5, closes5, c.atr_period)
        price = closes5[-1]
        if atr <= 0 or price <= 0:
            self._no_signal("atr_or_price_invalid")
            return None
        atr_pct = (atr / price) * 100.0
        if atr_pct < c.min_atr_pct:
            self._no_signal(f"atr_too_low={atr_pct:.3f}")
            return None
        if atr_pct > c.max_atr_pct:
            self._no_signal(f"atr_too_high={atr_pct:.3f}")
            return None

        # Mode dispatch
        if c.mode == "bounce":
            setup = self._detect_bounce(opens5, highs5, lows5, closes5, atr)
        elif c.mode == "sweep":
            setup = self._detect_sweep(opens5, highs5, lows5, closes5, atr)
        elif c.mode == "breakout":
            setup = self._detect_breakout(opens5, highs5, lows5, closes5, volumes5, atr)
        else:
            self._no_signal(f"unknown_mode={c.mode}")
            return None

        if setup is None:
            self._no_signal(f"no_setup_{c.mode}")
            return None

        # Volume confirmation (common, separate from breakout's stricter check)
        vol_z = _vol_zscore(volumes5, baseline_period=30, recent_n=1)
        if vol_z < c.vol_z_min and c.mode != "breakout":  # breakout already checks
            self._no_signal(f"vol_low_z={vol_z:.2f}")
            return None

        # Cross-TF non-conflict
        macro_ema = _ema_series(closes_macro, 21)
        if macro_ema:
            macro_slope_pct = _slope_pct_per_bar(macro_ema, c.macro_slope_bars, price)
            side = setup["side"]
            if side == "Buy" and macro_slope_pct < -c.max_conflict_slope_pct:
                self._no_signal(f"macro_against_long={macro_slope_pct:.3f}")
                return None
            if side == "Sell" and macro_slope_pct > c.max_conflict_slope_pct:
                self._no_signal(f"macro_against_short={macro_slope_pct:.3f}")
                return None

        # Risk math
        entry = float(setup["entry"])
        sl = float(setup["sl"])
        risk = abs(entry - sl)
        if risk <= 0:
            self._no_signal("invalid_risk")
            return None

        side = setup["side"]
        if side == "Buy":
            tp1 = entry + c.tp1_rr * risk
            tp2 = entry + c.tp2_rr * risk
        else:
            tp1 = entry - c.tp1_rr * risk
            tp2 = entry - c.tp2_rr * risk

        # State update
        self._last_tf_ts = ts_ms
        self._cooldown = c.cooldown_bars_5m

        return TradeSignal(
            strategy="scalper_classic_v1",
            symbol=symbol,
            side="long" if side == "Buy" else "short",
            entry=entry,
            sl=sl,
            tp=tp1,
            tps=[tp1, tp2],
            tp_fracs=[c.tp1_frac, max(0.0, 1.0 - c.tp1_frac)],
            be_trigger_rr=c.be_trigger_rr,
            time_stop_bars=c.time_stop_bars_5m,
            reason=f"sc1_{setup['mode']} vol_z={vol_z:.2f} atr_pct={atr_pct:.2f}",
        )


# ---------------------------------------------------------------------------
# Selector helper
# ---------------------------------------------------------------------------

class SC1Selector:
    def __init__(self):
        self._strategies: dict[str, ScalperClassicV1Strategy] = {}

    def get(self, symbol: str) -> ScalperClassicV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ScalperClassicV1Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
