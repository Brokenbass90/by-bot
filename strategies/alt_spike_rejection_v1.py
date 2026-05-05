"""alt_spike_rejection_v1 — volume spike rejection at strong level + auto-flip to breakout.

ПОЛЬЗОВАТЕЛЬСКАЯ ИДЕЯ (2026-05-XX):
  «Есть сильный уровень сопротивления. Резко пошли объёмы одной свечой.
   Если отбивает (длинный wick + reclaim) — fade.
   Если давление продолжается — пробой.»

Логика двух фаз:

Phase 1 (REJECT — fade entry):
  • На свече i: high достигает strong_resistance ± touch_tol
  • Volume на этой свече > VOL_SPIKE_MULT × avg_vol(20)
  • Свеча закрывается обратно с длинным upper wick (wick_pct ≥ 0.55)
  • close < strong_resistance - reclaim_atr*ATR
  → SHORT вход с SL = high + sl_pad*ATR

  Симметрично для LONG на support.

Phase 2 (BREAKOUT FOLLOW — flip):
  Если после Phase-1 entry в течение N баров (default 8) свеча close > strong_resistance + break_atr*ATR
  И volume снова > VOL_SPIKE_MULT × avg_vol
  → закрываем reject-позицию, открываем breakout в обратную сторону.

Strong level detection:
  • Rolling pivot (lookback default 48 bars 5m = 4 hours)
  • Уровень считается «strong» если коснулись ≥ MIN_TOUCHES (default 3) в lookback window

Env vars (all prefixed SPR1_):
  SPR1_LOOKBACK_BARS         (48)   — окно для поиска strong level
  SPR1_MIN_TOUCHES           (3)    — минимум touches для strong level
  SPR1_TOUCH_TOL_ATR         (0.20) — точность touch
  SPR1_VOL_SPIKE_MULT        (2.5)  — объём спайка vs avg(20)
  SPR1_VOL_AVG_BARS          (20)
  SPR1_MIN_WICK_PCT          (0.55) — wick / range >= 0.55 для reject
  SPR1_RECLAIM_ATR           (0.10) — close должен вернуться внутрь на N×ATR
  SPR1_BREAK_ATR             (0.20) — для Phase 2: пробой ≥ N×ATR
  SPR1_FLIP_WINDOW_BARS      (8)    — окно для Phase 2 flip
  SPR1_SL_PAD_ATR            (0.15)
  SPR1_RR                    (1.8)
  SPR1_TP1_RR                (0.7)
  SPR1_TP1_FRAC              (0.50)
  SPR1_TIME_STOP_BARS        (96)   — 8h на 5m
  SPR1_COOLDOWN_BARS_5M      (24)   — per-symbol
  SPR1_ATR_PERIOD            (14)
  SPR1_REGIME_MODE           (all)  — all|chop|trending
  SPR1_SYMBOL_ALLOWLIST      ()
  SPR1_ALLOW_LONGS           (1)
  SPR1_ALLOW_SHORTS          (1)
  SPR1_ENABLE_FLIP           (1)    — 0 = только Phase 1 без auto-flip
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
    if raw is None or not str(raw).strip():
        return default
    try: return float(str(raw).strip())
    except: return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try: return int(float(str(raw).strip()))
    except: return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None: return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _atr(candles: list, period: int) -> float:
    if len(candles) < period + 1:
        return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h)
        l = float(candles[i].l)
        pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / float(len(recent)) if recent else float("nan")


@dataclass
class SPR1Config:
    lookback_bars: int = field(default_factory=lambda: _env_int("SPR1_LOOKBACK_BARS", 48))
    min_touches: int = field(default_factory=lambda: _env_int("SPR1_MIN_TOUCHES", 3))
    touch_tol_atr: float = field(default_factory=lambda: _env_float("SPR1_TOUCH_TOL_ATR", 0.20))
    vol_spike_mult: float = field(default_factory=lambda: _env_float("SPR1_VOL_SPIKE_MULT", 2.5))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("SPR1_VOL_AVG_BARS", 20))
    min_wick_pct: float = field(default_factory=lambda: _env_float("SPR1_MIN_WICK_PCT", 0.55))
    reclaim_atr: float = field(default_factory=lambda: _env_float("SPR1_RECLAIM_ATR", 0.10))
    break_atr: float = field(default_factory=lambda: _env_float("SPR1_BREAK_ATR", 0.20))
    flip_window_bars: int = field(default_factory=lambda: _env_int("SPR1_FLIP_WINDOW_BARS", 8))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("SPR1_SL_PAD_ATR", 0.15))
    rr: float = field(default_factory=lambda: _env_float("SPR1_RR", 1.8))
    tp1_rr: float = field(default_factory=lambda: _env_float("SPR1_TP1_RR", 0.7))
    tp1_frac: float = field(default_factory=lambda: _env_float("SPR1_TP1_FRAC", 0.50))
    time_stop_bars: int = field(default_factory=lambda: _env_int("SPR1_TIME_STOP_BARS", 96))
    cooldown_bars: int = field(default_factory=lambda: _env_int("SPR1_COOLDOWN_BARS_5M", 24))
    atr_period: int = field(default_factory=lambda: _env_int("SPR1_ATR_PERIOD", 14))
    regime_mode: str = field(default_factory=lambda: os.getenv("SPR1_REGIME_MODE", "all").strip().lower())
    symbol_allowlist: set[str] = field(default_factory=lambda: _env_csv_set("SPR1_SYMBOL_ALLOWLIST"))
    allow_longs: bool = field(default_factory=lambda: _env_bool("SPR1_ALLOW_LONGS", True))
    allow_shorts: bool = field(default_factory=lambda: _env_bool("SPR1_ALLOW_SHORTS", True))
    enable_flip: bool = field(default_factory=lambda: _env_bool("SPR1_ENABLE_FLIP", True))

    def regime_ok(self, regime: Optional[str]) -> bool:
        if not regime: return True
        r = regime.upper()
        if self.regime_mode == "all": return True
        if self.regime_mode == "chop": return r in {"BEAR_CHOP", "BULL_CHOP"}
        if self.regime_mode == "trending": return r in {"BEAR_TREND", "BULL_TREND"}
        return True


def _detect_strong_levels(candles: list, lookback: int, min_touches: int, touch_tol_atr: float, atr: float) -> tuple[Optional[float], Optional[float]]:
    """Find strong resistance (max touched) and strong support (min touched) in lookback window.
    Returns (resistance, support) — None if no strong level."""
    if len(candles) < lookback or atr <= 0:
        return None, None
    pool = candles[-lookback:]
    pool_high = max(float(x.h) for x in pool)
    pool_low = min(float(x.l) for x in pool)

    high_touches = sum(1 for x in pool if abs(float(x.h) - pool_high) <= touch_tol_atr * atr)
    low_touches = sum(1 for x in pool if abs(float(x.l) - pool_low) <= touch_tol_atr * atr)

    resistance = pool_high if high_touches >= min_touches else None
    support = pool_low if low_touches >= min_touches else None
    return resistance, support


class AltSpikeRejectionV1Strategy:
    NAME = "alt_spike_rejection_v1"

    def __init__(self):
        self.cfg = SPR1Config()
        self._last_signal_i: dict[str, int] = {}
        # Per-symbol Phase-1 state for potential Phase-2 flip
        self._phase1_state: dict[str, dict] = {}
        self.last_no_signal_reason = ""

    def signal(self, store, symbol: str, i: int, regime: Optional[str] = None) -> Optional[TradeSignal]:
        cfg = self.cfg
        candles = store.candles(symbol) if hasattr(store, "candles") else getattr(store, "rows", [])
        need = max(cfg.lookback_bars + 3, cfg.atr_period + 2, cfg.vol_avg_bars + 2)
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        if not cfg.regime_ok(regime):
            self.last_no_signal_reason = f"regime_blocked:{regime}"
            return None

        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            self.last_no_signal_reason = "symbol_blocked"
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

        # Volume context
        avg_vol = sum(float(candles[j].v) * float(candles[j].c) for j in range(i - cfg.vol_avg_bars, i)) / float(cfg.vol_avg_bars)

        cur = candles[i]
        o, h, l, c, v = float(cur.o), float(cur.h), float(cur.l), float(cur.c), float(cur.v)
        cur_vol = v * c

        # ── PHASE 2 — check existing Phase-1 state for flip opportunity ──────
        ph1 = self._phase1_state.get(symbol)
        if cfg.enable_flip and ph1 and i - ph1["entry_i"] <= cfg.flip_window_bars:
            level = ph1["level"]
            side_p1 = ph1["side"]
            # If Phase-1 was SHORT (rejected at resistance) and now bar BREAKS resistance
            if side_p1 == "short" and c > level + cfg.break_atr * atr and cur_vol >= cfg.vol_spike_mult * avg_vol:
                # Flip to LONG breakout
                if cfg.allow_longs:
                    sl = level - cfg.sl_pad_atr * atr
                    risk = c - sl
                    if risk > 0:
                        self._last_signal_i[symbol] = i
                        self._phase1_state.pop(symbol, None)
                        sig = self._make_signal(symbol, "long", c, sl, c + cfg.rr * risk,
                                                f"SPR1_FLIP_LONG level={level:.6g} from_short_phase1")
                        return sig
            elif side_p1 == "long" and c < level - cfg.break_atr * atr and cur_vol >= cfg.vol_spike_mult * avg_vol:
                if cfg.allow_shorts:
                    sl = level + cfg.sl_pad_atr * atr
                    risk = sl - c
                    if risk > 0:
                        self._last_signal_i[symbol] = i
                        self._phase1_state.pop(symbol, None)
                        sig = self._make_signal(symbol, "short", c, sl, c - cfg.rr * risk,
                                                f"SPR1_FLIP_SHORT level={level:.6g} from_long_phase1")
                        return sig

        # Cleanup expired phase1 state
        if ph1 and i - ph1["entry_i"] > cfg.flip_window_bars:
            self._phase1_state.pop(symbol, None)

        # ── PHASE 1 — detect rejection ───────────────────────────────────────
        # Need volume spike
        if cur_vol < cfg.vol_spike_mult * avg_vol:
            self.last_no_signal_reason = "no_volume_spike"
            return None

        resistance, support = _detect_strong_levels(
            candles[: i], cfg.lookback_bars, cfg.min_touches, cfg.touch_tol_atr, atr,
        )

        bar_range = max(h - l, 1e-9)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        upper_wick_pct = upper_wick / bar_range
        lower_wick_pct = lower_wick / bar_range

        # SHORT — rejected at resistance
        if cfg.allow_shorts and resistance is not None:
            if (h >= resistance - cfg.touch_tol_atr * atr   # touched/exceeded resistance
                and c < resistance - cfg.reclaim_atr * atr   # closed back inside
                and upper_wick_pct >= cfg.min_wick_pct       # long upper wick
            ):
                sl = h + cfg.sl_pad_atr * atr
                risk = sl - c
                if risk > 0:
                    self._last_signal_i[symbol] = i
                    # Save phase-1 state for potential flip
                    self._phase1_state[symbol] = {
                        "entry_i": i, "level": resistance, "side": "short",
                    }
                    sig = self._make_signal(symbol, "short", c, sl, c - cfg.rr * risk,
                                            f"SPR1_REJECT_SHORT level={resistance:.6g} vol={cur_vol/avg_vol:.2f}x wick={upper_wick_pct:.2f}")
                    return sig

        # LONG — rejected at support
        if cfg.allow_longs and support is not None:
            if (l <= support + cfg.touch_tol_atr * atr
                and c > support + cfg.reclaim_atr * atr
                and lower_wick_pct >= cfg.min_wick_pct
            ):
                sl = l - cfg.sl_pad_atr * atr
                risk = c - sl
                if risk > 0:
                    self._last_signal_i[symbol] = i
                    self._phase1_state[symbol] = {
                        "entry_i": i, "level": support, "side": "long",
                    }
                    sig = self._make_signal(symbol, "long", c, sl, c + cfg.rr * risk,
                                            f"SPR1_REJECT_LONG level={support:.6g} vol={cur_vol/avg_vol:.2f}x wick={lower_wick_pct:.2f}")
                    return sig

        self.last_no_signal_reason = "no_reject_at_level"
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
        # Optional partial TP1 / trailing
        risk = abs(entry - sl)
        if risk > 0 and cfg.tp1_frac > 0 and hasattr(sig, "tps"):
            tp1 = entry + cfg.tp1_rr * risk if side == "long" else entry - cfg.tp1_rr * risk
            sig.tps = [float(tp1), float(tp)]
            sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
        return sig
