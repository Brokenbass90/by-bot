"""alt_whale_print_follow_v1 — следование за крупным игроком (whale print).

ИДЕЯ:
  Когда крупный игрок (whale) делает большой market order, появляется свеча с:
    • аномальным объёмом (>= 3x от 20-bar average)
    • широким диапазоном (>= 1.5x от ATR)
    • закрытием у дальнего конца диапазона (close в верхней/нижней 25% свечи)
    • body >= 50% диапазона (доминирует одна сторона)
  → Следуем в направлении движения на 60-90 баров (5-7.5h на 5m).

  Это особенно полезно в МЁРТВОМ рынке, когда trend-стратегии не работают,
  но киты иногда делают prints — это часто единственное реальное движение.

ВАЖНО: это PROXY для whale tracking через bar-level OHLCV. Полноценный
whale-tracker требовал бы Bybit WS publicTrade channel с event-buffer.
v2 может это добавить позже.

Entry (LONG):
  • Bar i имеет volume >= VOL_SPIKE_MULT × avg_vol
  • Range >= MIN_RANGE_ATR × ATR
  • Close в верхней 25% свечи (close_pos >= 0.75)
  • Body >= MIN_BODY_FRAC × range
  • Текущий bar — bullish (close > open)
  • Опциональный фильтр: цена не в overbought RSI (< 75)
  → SHORT entry зеркально: close в нижней 25%, bearish.

Exit:
  • SL = low of whale bar - sl_pad × ATR (для long)
  • TP = entry + RR × risk
  • Time stop = WHALE_TIME_STOP_BARS_5M (default 90 = 7.5h)
  • Partial TP1 на 0.6R, breakeven после TP1

Env vars (WHALE_):
  WHALE_VOL_SPIKE_MULT       (3.0)
  WHALE_VOL_AVG_BARS         (20)
  WHALE_MIN_RANGE_ATR        (1.5)
  WHALE_MIN_BODY_FRAC        (0.50)
  WHALE_CLOSE_POS_THRESHOLD  (0.75)
  WHALE_MAX_RSI_LONG         (75)
  WHALE_MIN_RSI_SHORT        (25)
  WHALE_RSI_PERIOD           (14)
  WHALE_SL_PAD_ATR           (0.20)
  WHALE_RR                   (1.5)
  WHALE_TP1_RR               (0.6)
  WHALE_TP1_FRAC             (0.50)
  WHALE_TIME_STOP_BARS_5M    (90)
  WHALE_COOLDOWN_BARS_5M     (24)
  WHALE_ATR_PERIOD           (14)
  WHALE_REGIME_MODE          (all)  — all|chop|trending
  WHALE_SYMBOL_ALLOWLIST     ()
  WHALE_ALLOW_LONGS          (1)
  WHALE_ALLOW_SHORTS         (1)
  WHALE_REQUIRE_DOMINANT_VOL (1)    — bar volume должен быть max в lookback 10
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None: return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
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


_REGIME_MODE_PRESETS = {
    "all": {"BEAR_CHOP", "BULL_CHOP", "BEAR_TREND", "BULL_TREND"},
    "chop": {"BEAR_CHOP", "BULL_CHOP"},
    "trending": {"BEAR_TREND", "BULL_TREND"},
}


@dataclass
class WhaleConfig:
    vol_spike_mult: float = field(default_factory=lambda: _env_float("WHALE_VOL_SPIKE_MULT", 3.0))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("WHALE_VOL_AVG_BARS", 20))
    min_range_atr: float = field(default_factory=lambda: _env_float("WHALE_MIN_RANGE_ATR", 1.5))
    min_body_frac: float = field(default_factory=lambda: _env_float("WHALE_MIN_BODY_FRAC", 0.50))
    close_pos_threshold: float = field(default_factory=lambda: _env_float("WHALE_CLOSE_POS_THRESHOLD", 0.75))
    max_rsi_long: float = field(default_factory=lambda: _env_float("WHALE_MAX_RSI_LONG", 75))
    min_rsi_short: float = field(default_factory=lambda: _env_float("WHALE_MIN_RSI_SHORT", 25))
    rsi_period: int = field(default_factory=lambda: _env_int("WHALE_RSI_PERIOD", 14))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("WHALE_SL_PAD_ATR", 0.20))
    rr: float = field(default_factory=lambda: _env_float("WHALE_RR", 1.5))
    tp1_rr: float = field(default_factory=lambda: _env_float("WHALE_TP1_RR", 0.6))
    tp1_frac: float = field(default_factory=lambda: _env_float("WHALE_TP1_FRAC", 0.50))
    time_stop_bars: int = field(default_factory=lambda: _env_int("WHALE_TIME_STOP_BARS_5M", 90))
    cooldown_bars: int = field(default_factory=lambda: _env_int("WHALE_COOLDOWN_BARS_5M", 24))
    atr_period: int = field(default_factory=lambda: _env_int("WHALE_ATR_PERIOD", 14))
    regime_mode: str = field(default_factory=lambda: os.getenv("WHALE_REGIME_MODE", "all").strip().lower())
    symbol_allowlist: set[str] = field(default_factory=lambda: _env_csv_set("WHALE_SYMBOL_ALLOWLIST"))
    allow_longs: bool = field(default_factory=lambda: _env_bool("WHALE_ALLOW_LONGS", True))
    allow_shorts: bool = field(default_factory=lambda: _env_bool("WHALE_ALLOW_SHORTS", True))
    require_dominant_vol: bool = field(default_factory=lambda: _env_bool("WHALE_REQUIRE_DOMINANT_VOL", True))

    def regime_ok(self, regime: Optional[str]) -> bool:
        if not regime: return True
        allowed = _REGIME_MODE_PRESETS.get(self.regime_mode, _REGIME_MODE_PRESETS["all"])
        return regime.upper() in allowed


class AltWhalePrintFollowV1Strategy:
    NAME = "alt_whale_print_follow_v1"

    def __init__(self):
        self.cfg = WhaleConfig()
        self._last_signal_i: dict[str, int] = {}
        self.last_no_signal_reason = ""

    def signal(self, store, symbol: str, i: int, regime: Optional[str] = None) -> Optional[TradeSignal]:
        cfg = self.cfg
        candles = _candles_5m(store, symbol)
        need = max(cfg.atr_period + 5, cfg.vol_avg_bars + 12, cfg.rsi_period + 5)
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        if not cfg.regime_ok(regime):
            self.last_no_signal_reason = f"regime_blocked:{regime}"
            return None

        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            self.last_no_signal_reason = "symbol_blocked"
            return None

        last_i = self._last_signal_i.get(symbol, -10**9)
        if i - last_i < cfg.cooldown_bars:
            self.last_no_signal_reason = f"cooldown:{symbol}"
            return None

        atr = _atr(candles[max(0, i - cfg.atr_period - 2): i + 1], cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "bad_atr"
            return None

        cur = candles[i]
        o, h, l, c, v = float(cur.o), float(cur.h), float(cur.l), float(cur.c), float(cur.v)
        bar_range = max(h - l, 1e-9)
        body = abs(c - o)
        body_frac = body / bar_range
        cur_vol = v * c

        # ── Volume spike check ──────────────────────────────────────────────
        vol_window = candles[i - cfg.vol_avg_bars: i]
        avg_vol = sum(float(x.v) * float(x.c) for x in vol_window) / float(cfg.vol_avg_bars)
        if avg_vol <= 0 or cur_vol < cfg.vol_spike_mult * avg_vol:
            self.last_no_signal_reason = "no_volume_spike"
            return None

        # Optional: must be max volume in last 10 bars (real whale dominance)
        if cfg.require_dominant_vol:
            recent10 = candles[i - 10: i + 1]
            max_vol_in_10 = max(float(x.v) * float(x.c) for x in recent10)
            if cur_vol < max_vol_in_10 * 0.99:
                self.last_no_signal_reason = "not_dominant_vol"
                return None

        # ── Range check ─────────────────────────────────────────────────────
        if bar_range < cfg.min_range_atr * atr:
            self.last_no_signal_reason = "range_too_small"
            return None

        # ── Body dominance ──────────────────────────────────────────────────
        if body_frac < cfg.min_body_frac:
            self.last_no_signal_reason = "body_too_small"
            return None

        # ── Close position (where in the range?) ────────────────────────────
        close_pos = (c - l) / bar_range  # 0 = at low, 1 = at high

        # ── RSI sanity ──────────────────────────────────────────────────────
        rsi_closes = [float(x.c) for x in candles[max(0, i - cfg.rsi_period - 2): i + 1]]
        rsi = _rsi(rsi_closes, cfg.rsi_period)

        # ── LONG: bullish whale bar ─────────────────────────────────────────
        if cfg.allow_longs and c > o and close_pos >= cfg.close_pos_threshold:
            if math.isfinite(rsi) and rsi > cfg.max_rsi_long:
                self.last_no_signal_reason = f"rsi_too_high:{rsi:.1f}"
                return None
            sl = l - cfg.sl_pad_atr * atr
            risk = c - sl
            if risk <= 0:
                self.last_no_signal_reason = "bad_risk_long"
                return None
            tp = c + cfg.rr * risk
            self._last_signal_i[symbol] = i
            return self._make_signal(symbol, "long", c, sl, tp,
                                     f"WHALE_LONG vol={cur_vol/avg_vol:.1f}x range={bar_range/atr:.1f}atr body={body_frac:.2f} close_pos={close_pos:.2f} rsi={rsi:.0f}")

        # ── SHORT: bearish whale bar ────────────────────────────────────────
        if cfg.allow_shorts and c < o and close_pos <= (1.0 - cfg.close_pos_threshold):
            if math.isfinite(rsi) and rsi < cfg.min_rsi_short:
                self.last_no_signal_reason = f"rsi_too_low:{rsi:.1f}"
                return None
            sl = h + cfg.sl_pad_atr * atr
            risk = sl - c
            if risk <= 0:
                self.last_no_signal_reason = "bad_risk_short"
                return None
            tp = c - cfg.rr * risk
            self._last_signal_i[symbol] = i
            return self._make_signal(symbol, "short", c, sl, tp,
                                     f"WHALE_SHORT vol={cur_vol/avg_vol:.1f}x range={bar_range/atr:.1f}atr body={body_frac:.2f} close_pos={close_pos:.2f} rsi={rsi:.0f}")

        self.last_no_signal_reason = "no_whale_pattern"
        return None

    def _make_signal(self, symbol: str, side: str, entry: float, sl: float, tp: float, reason: str) -> TradeSignal:
        cfg = self.cfg
        sig = TradeSignal(
            strategy=self.NAME,
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            time_stop_bars=cfg.time_stop_bars,
            reason=reason,
        )
        risk = abs(entry - sl)
        if risk > 0 and cfg.tp1_frac > 0 and hasattr(sig, "tps"):
            tp1 = entry + cfg.tp1_rr * risk if side == "long" else entry - cfg.tp1_rr * risk
            sig.tps = [float(tp1), float(tp)]
            sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
        return sig
