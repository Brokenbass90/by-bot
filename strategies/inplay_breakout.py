from __future__ import annotations

import os
import inspect
import math
import asyncio
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from backtest.bt_types import TradeSignal
from sr_inplay_retest import InPlayBreakoutStrategy


def _run_coro_sync(obj: Any) -> Any:
    if asyncio.iscoroutine(obj):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(obj)
                finally:
                    new_loop.close()
            return loop.run_until_complete(obj)
        except RuntimeError:
            return asyncio.run(obj)
    return obj


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return float(v.strip())
    except Exception:
        return default


def _env_csv_floats(name: str, default: List[float]) -> List[float]:
    v = os.getenv(name)
    if v is None or not v.strip():
        return list(default)
    parts = [p.strip() for p in v.replace(';', ',').split(',')]
    out: List[float] = []
    for p in parts:
        if not p:
            continue
        try:
            out.append(float(p))
        except Exception:
            pass
    return out if out else list(default)


def _env_csv_set(name: str) -> set[str]:
    raw = os.getenv(name, "") or ""
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


@dataclass
class InPlayBreakoutConfig:
    tf_break: str = "240"
    tf_entry: str = "5"
    lookback_h: int = 24
    atr_period: int = 14
    impulse_atr_mult: float = 1.0
    impulse_body_min_frac: float = 0.4
    impulse_vol_mult: float = 0.0
    impulse_vol_period: int = 20
    breakout_buffer_atr: float = 0.10
    breakout_sl_atr: float = 0.40
    retest_touch_atr: float = 0.35
    reclaim_atr: float = 0.15
    min_hold_bars: int = 0
    max_retest_bars: int = 30
    min_break_bars: int = 1
    max_dist_atr: float = 1.2
    rr: float = 1.2

    range_atr_max: float = 8.0
    allow_longs: bool = True
    allow_shorts: bool = False

    regime_mode: str = "off"
    regime_tf: str = "240"
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_min_gap_atr: float = 0.0
    regime_strict: bool = True
    regime_price_filter: bool = False
    regime_cache_sec: int = 180
    chop_er_min: float = 0.0
    chop_er_period: int = 20
    chop_in_range_only: bool = True


class InPlayBreakoutWrapper:
    def __init__(self, cfg: Optional[InPlayBreakoutConfig] = None):
        self.cfg = cfg or InPlayBreakoutConfig()
        self._allow = _env_csv_set("BREAKOUT_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKOUT_SYMBOL_DENYLIST")

        self.cfg.tf_break = os.getenv("BREAKOUT_TF_BREAK", self.cfg.tf_break)
        self.cfg.tf_entry = os.getenv("BREAKOUT_TF_ENTRY", self.cfg.tf_entry)
        self.cfg.lookback_h = _env_int("BREAKOUT_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.atr_period = _env_int("BREAKOUT_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.impulse_atr_mult = _env_float("BREAKOUT_IMPULSE_ATR_MULT", self.cfg.impulse_atr_mult)
        self.cfg.impulse_body_min_frac = _env_float("BREAKOUT_IMPULSE_BODY_MIN_FRAC", self.cfg.impulse_body_min_frac)
        self.cfg.impulse_vol_mult = _env_float("BREAKOUT_IMPULSE_VOL_MULT", self.cfg.impulse_vol_mult)
        self.cfg.impulse_vol_period = _env_int("BREAKOUT_IMPULSE_VOL_PERIOD", self.cfg.impulse_vol_period)
        self.cfg.breakout_buffer_atr = _env_float("BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.breakout_sl_atr = _env_float("BREAKOUT_SL_ATR", self.cfg.breakout_sl_atr)
        self.cfg.retest_touch_atr = _env_float("BREAKOUT_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_atr = _env_float("BREAKOUT_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.min_hold_bars = _env_int("BREAKOUT_MIN_HOLD_BARS", self.cfg.min_hold_bars)
        self.cfg.max_retest_bars = _env_int("BREAKOUT_MAX_RETEST_BARS", self.cfg.max_retest_bars)
        self.cfg.min_break_bars = _env_int("BREAKOUT_MIN_BREAK_BARS", self.cfg.min_break_bars)
        self.cfg.max_dist_atr = _env_float("BREAKOUT_MAX_DIST_ATR", self.cfg.max_dist_atr)
        self.cfg.rr = _env_float("BREAKOUT_RR", self.cfg.rr)
        self.cfg.range_atr_max = _env_float("BREAKOUT_RANGE_ATR_MAX", self.cfg.range_atr_max)

        self.cfg.allow_longs = _env_bool("BREAKOUT_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BREAKOUT_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.regime_mode = os.getenv("BREAKOUT_REGIME_MODE", self.cfg.regime_mode)
        if str(os.getenv('BREAKOUT_REGIME', '')).strip().lower() in ('1','true','yes','on'):
            if str(self.cfg.regime_mode).strip().lower() in ('off','0','false','none',''):
                self.cfg.regime_mode = 'ema'
        self.cfg.regime_tf = os.getenv("BREAKOUT_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("BREAKOUT_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BREAKOUT_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_gap_atr = _env_float("BREAKOUT_REGIME_MIN_GAP_ATR", self.cfg.regime_min_gap_atr)
        self.cfg.regime_strict = _env_bool("BREAKOUT_REGIME_STRICT", self.cfg.regime_strict)
        self.cfg.regime_price_filter = _env_bool("BREAKOUT_REGIME_PRICE_FILTER", self.cfg.regime_price_filter)
        self.cfg.regime_cache_sec = int(os.getenv("BREAKOUT_REGIME_CACHE_SEC", str(self.cfg.regime_cache_sec)) or self.cfg.regime_cache_sec)
        self.cfg.chop_er_min = _env_float("BREAKOUT_CHOP_ER_MIN", self.cfg.chop_er_min)
        self.cfg.chop_er_period = int(os.getenv("BREAKOUT_CHOP_ER_PERIOD", str(self.cfg.chop_er_period)) or self.cfg.chop_er_period)
        self.cfg.chop_in_range_only = _env_bool("BREAKOUT_CHOP_IN_RANGE_ONLY", self.cfg.chop_in_range_only)

        self.impl: Optional[InPlayBreakoutStrategy] = None

    @staticmethod
    def _bar_value(bar: Any, key: str) -> Optional[float]:
        if isinstance(bar, dict):
            v = bar.get(key)
            if v is None and key in {"h", "l", "c"}:
                alt = {"h": "high", "l": "low", "c": "close"}[key]
                v = bar.get(alt)
            try:
                return float(v) if v is not None else None
            except Exception:
                return None
        try:
            return float(getattr(bar, key))
        except Exception:
            return None

    def _passes_entry_timing_guards(self, store: Any, side: str, entry: float) -> bool:
        max_late_pct = _env_float("BREAKOUT_MAX_LATE_VS_REF_PCT", 0.0)
        min_pullback_pct = _env_float("BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT", 0.0)
        if max_late_pct <= 0 and min_pullback_pct <= 0:
            return True

        bars = getattr(store, "c5", None)
        i = getattr(store, "i5", None)
        if bars is None or i is None:
            return True
        i = int(i)
        if i <= 2:
            return True

        lookback = max(5, _env_int("BREAKOUT_REF_LOOKBACK_BARS", 20))
        lo = max(0, i - lookback)
        seg = list(bars[lo:i])
        if len(seg) < 3:
            return True

        highs = [self._bar_value(b, "h") for b in seg]
        lows = [self._bar_value(b, "l") for b in seg]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        if not highs or not lows:
            return True

        if side == "long":
            brk_ref = max(highs)
            if max_late_pct > 0 and brk_ref > 0:
                late_pct = ((entry / brk_ref) - 1.0) * 100.0
                if late_pct > max_late_pct:
                    return False
            if min_pullback_pct > 0 and brk_ref > 0:
                pb_pct = ((brk_ref - entry) / brk_ref) * 100.0
                if pb_pct < min_pullback_pct:
                    return False
            return True

        brk_ref = min(lows)
        if max_late_pct > 0 and brk_ref > 0:
            late_pct = ((brk_ref / entry) - 1.0) * 100.0
            if late_pct > max_late_pct:
                return False
        if min_pullback_pct > 0 and brk_ref > 0:
            bounce_pct = ((entry - brk_ref) / brk_ref) * 100.0
            if bounce_pct < min_pullback_pct:
                return False
        return True

    @staticmethod
    def _hours_to_break_bars(lookback_h: int, tf_break: str) -> int:
        try:
            minutes = int(tf_break)
            if minutes <= 0:
                raise ValueError
        except Exception:
            minutes = 60
        bars = int(math.ceil((lookback_h * 60) / minutes))
        return max(10, bars)

    def _ensure_impl(self, store) -> None:
        if self.impl is not None:
            return

        tf_break = self.cfg.tf_break
        lookback_break_bars = self._hours_to_break_bars(self.cfg.lookback_h, tf_break)

        def _fetch_klines(symbol: str, interval: str, limit: int):
            raw = store.fetch_klines(symbol, interval, int(limit))
            out: List[Dict[str, Any]] = []
            for r in (raw or []):
                if isinstance(r, dict):
                    o = r.get("open", r.get("o"))
                    h = r.get("high", r.get("h"))
                    l = r.get("low", r.get("l"))
                    c = r.get("close", r.get("c"))
                    ts = r.get("startTime", r.get("ts", r.get("t")))
                    v = r.get("volume", r.get("v", 0.0))
                    out.append({
                        "startTime": ts,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v) if v is not None else 0.0,
                    })
                    continue

                if hasattr(r, "o") and hasattr(r, "h") and hasattr(r, "l") and hasattr(r, "c"):
                    ts = getattr(r, "ts", getattr(r, "t", None))
                    v = getattr(r, "v", 0.0)
                    out.append({
                        "startTime": ts,
                        "open": float(getattr(r, "o")),
                        "high": float(getattr(r, "h")),
                        "low": float(getattr(r, "l")),
                        "close": float(getattr(r, "c")),
                        "volume": float(v) if v is not None else 0.0,
                    })
                    continue

                if isinstance(r, (list, tuple)) and len(r) >= 5:
                    ts, o, h, l, c = r[0], r[1], r[2], r[3], r[4]
                    v = r[5] if len(r) > 5 else 0.0
                    out.append({
                        "startTime": ts,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v) if v is not None else 0.0,
                    })
                    continue
            return out

        candidate: Dict[str, Any] = {
            "tf_break": tf_break,
            "lookback_break_bars": int(lookback_break_bars),
            "atr_period": int(self.cfg.atr_period),
            "impulse_atr_mult": float(self.cfg.impulse_atr_mult),
            "impulse_body_min_frac": float(self.cfg.impulse_body_min_frac),
            "impulse_vol_mult": float(self.cfg.impulse_vol_mult),
            "impulse_vol_period": int(self.cfg.impulse_vol_period),
            "breakout_buffer_atr": float(self.cfg.breakout_buffer_atr),
            "breakout_sl_atr": float(self.cfg.breakout_sl_atr),
            "tf_entry": str(self.cfg.tf_entry),
            "retest_touch_atr": float(self.cfg.retest_touch_atr),
            "reclaim_atr": float(self.cfg.reclaim_atr),
            "min_hold_bars": int(self.cfg.min_hold_bars),
            "max_retest_bars": int(self.cfg.max_retest_bars),
            "min_break_bars": int(self.cfg.min_break_bars),
            "max_dist_atr": float(self.cfg.max_dist_atr),
            "rr": float(self.cfg.rr),
            "range_atr_max": float(self.cfg.range_atr_max),
            "allow_longs": bool(self.cfg.allow_longs),
            "allow_shorts": bool(self.cfg.allow_shorts),
            "regime_mode": str(self.cfg.regime_mode),
            "regime_tf": str(self.cfg.regime_tf),
            "regime_ema_fast": int(self.cfg.regime_ema_fast),
            "regime_ema_slow": int(self.cfg.regime_ema_slow),
            "regime_min_gap_atr": float(self.cfg.regime_min_gap_atr),
            "regime_strict": bool(self.cfg.regime_strict),
            "regime_price_filter": bool(self.cfg.regime_price_filter),
            "regime_cache_sec": int(self.cfg.regime_cache_sec),
            "chop_er_min": float(self.cfg.chop_er_min),
            "chop_er_period": int(self.cfg.chop_er_period),
            "chop_in_range_only": bool(self.cfg.chop_in_range_only),
        }

        sig = inspect.signature(InPlayBreakoutStrategy.__init__)
        accepted = set(sig.parameters.keys()) - {"self", "fetch_klines"}
        filtered = {k: v for k, v in candidate.items() if k in accepted}

        self.impl = InPlayBreakoutStrategy(_fetch_klines, **filtered)

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        return _run_coro_sync(self.maybe_signal(store, ts_ms, last_price))

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        self._ensure_impl(store)
        assert self.impl is not None

        symbol = store.symbol
        sym_u = str(symbol or "").upper()
        if self._allow and sym_u not in self._allow:
            return None
        if sym_u in self._deny:
            return None
        sig = await self.impl.maybe_signal(symbol, price=float(last_price), ts_ms=int(ts_ms))
        if not sig:
            return None

        side = "long" if sig.side == "Buy" else "short"
        entry = float(sig.entry)
        sl = float(sig.sl)
        tp = float(sig.tp)

        if not self._passes_entry_timing_guards(store, side, entry):
            return None

        min_stop_pct = _env_float('BREAKOUT_MIN_STOP_PCT', 0.0)
        max_stop_pct = _env_float('BREAKOUT_MAX_STOP_PCT', 0.0)
        stop_pct = abs(entry - sl) / max(1e-12, entry)
        if min_stop_pct > 0 and stop_pct < min_stop_pct:
            return None
        if max_stop_pct > 0 and stop_pct > max_stop_pct:
            return None

        base_reason = getattr(sig, "reason", "breakout")

        exit_mode = (os.getenv("BREAKOUT_EXIT_MODE") or "fixed").strip().lower()
        if exit_mode in {"runner", "managed"}:
            risk = abs(entry - sl)
            if risk > 0:
                rs = _env_csv_floats("BREAKOUT_PARTIAL_RS", [1.0, 2.0, 3.5])
                fracs = _env_csv_floats("BREAKOUT_PARTIAL_FRACS", [0.50, 0.25, 0.15])
                if len(fracs) != len(rs):
                    fracs = [1.0 / len(rs)] * len(rs)

                if side == "long":
                    tps = [entry + (r * risk) for r in rs]
                else:
                    tps = [entry - (r * risk) for r in rs]

                trail_mult = _env_float("BREAKOUT_TRAIL_ATR_MULT", 2.2)
                trail_period = _env_int("BREAKOUT_TRAIL_ATR_PERIOD", 14)
                time_stop = _env_int("BREAKOUT_TIME_STOP_BARS", 288)

                return TradeSignal(
                    strategy="inplay_breakout",
                    symbol=symbol,
                    side=side,
                    entry=entry,
                    sl=sl,
                    tp=float(tps[-1]),
                    tps=tps,
                    tp_fracs=fracs,
                    trailing_atr_mult=trail_mult,
                    trailing_atr_period=trail_period,
                    time_stop_bars=time_stop,
                    reason=(base_reason + ";runner"),
                )

        return TradeSignal(
            strategy="inplay_breakout",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=base_reason,
        )
