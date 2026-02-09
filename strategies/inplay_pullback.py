from __future__ import annotations

import os
import inspect
import math
import asyncio
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from backtest.bt_types import TradeSignal
from sr_inplay_retest import InPlayPullbackStrategy


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


@dataclass
class InPlayPullbackConfig:
    tf_break: str = "15"
    tf_entry: str = "5"
    lookback_h: int = 24

    atr_period: int = 14
    impulse_atr_mult: float = 0.70
    impulse_body_min_frac: float = 0.0
    impulse_vol_mult: float = 0.0
    impulse_vol_period: int = 20

    pullback_zone_atr: float = 0.80
    prebreak_reclaim_atr: float = 0.10
    prebreak_max_dist_atr: float = 2.50
    prebreak_sl_buffer_atr: float = 0.15
    min_rr_to_level: float = 0.3
    reclaim_body_frac: float = 0.0
    require_reclaim: bool = False

    max_wait_bars: int = 24
    range_atr_max: float = 8.0
    breakout_buffer_atr: float = 0.10

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

    allow_longs: bool = True
    allow_shorts: bool = False


class InPlayPullbackWrapper:
    def __init__(self, cfg: Optional[InPlayPullbackConfig] = None):
        if cfg is None:
            cfg = InPlayPullbackConfig()
        self.cfg = cfg

        self.cfg.tf_break = os.getenv("PULLBACK_TF_BREAK", self.cfg.tf_break)
        self.cfg.tf_entry = os.getenv("PULLBACK_TF_ENTRY", self.cfg.tf_entry)
        self.cfg.lookback_h = _env_int("PULLBACK_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.atr_period = _env_int("PULLBACK_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.impulse_atr_mult = _env_float("PULLBACK_IMPULSE_ATR_MULT", self.cfg.impulse_atr_mult)
        self.cfg.impulse_body_min_frac = _env_float("PULLBACK_IMPULSE_BODY_MIN_FRAC", self.cfg.impulse_body_min_frac)
        self.cfg.impulse_vol_mult = _env_float("PULLBACK_IMPULSE_VOL_MULT", self.cfg.impulse_vol_mult)
        self.cfg.impulse_vol_period = _env_int("PULLBACK_IMPULSE_VOL_PERIOD", self.cfg.impulse_vol_period)
        self.cfg.pullback_zone_atr = _env_float("PULLBACK_ZONE_ATR", self.cfg.pullback_zone_atr)
        self.cfg.prebreak_reclaim_atr = _env_float("PULLBACK_RECLAIM_ATR", self.cfg.prebreak_reclaim_atr)
        self.cfg.prebreak_max_dist_atr = _env_float("PULLBACK_MAX_DIST_ATR", self.cfg.prebreak_max_dist_atr)
        self.cfg.prebreak_sl_buffer_atr = _env_float("PULLBACK_SL_BUFFER_ATR", self.cfg.prebreak_sl_buffer_atr)
        self.cfg.min_rr_to_level = _env_float("PULLBACK_MIN_RR_TO_LEVEL", self.cfg.min_rr_to_level)
        self.cfg.reclaim_body_frac = _env_float("PULLBACK_RECLAIM_BODY_FRAC", self.cfg.reclaim_body_frac)
        self.cfg.require_reclaim = _env_bool("PULLBACK_REQUIRE_RECLAIM", self.cfg.require_reclaim)
        self.cfg.max_wait_bars = _env_int("PULLBACK_MAX_WAIT_BARS", self.cfg.max_wait_bars)
        self.cfg.range_atr_max = _env_float("PULLBACK_RANGE_ATR_MAX", self.cfg.range_atr_max)
        self.cfg.breakout_buffer_atr = _env_float("PULLBACK_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)

        self.cfg.regime_mode = os.getenv("PULLBACK_REGIME_MODE", self.cfg.regime_mode)
        if str(os.getenv('PULLBACK_REGIME', '')).strip().lower() in ('1','true','yes','on'):
            if str(self.cfg.regime_mode).strip().lower() in ('off','0','false','none',''):
                self.cfg.regime_mode = 'ema'
        self.cfg.regime_tf = os.getenv("PULLBACK_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("PULLBACK_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("PULLBACK_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_gap_atr = _env_float("PULLBACK_REGIME_MIN_GAP_ATR", self.cfg.regime_min_gap_atr)
        self.cfg.regime_strict = _env_bool("PULLBACK_REGIME_STRICT", self.cfg.regime_strict)
        self.cfg.regime_price_filter = _env_bool("PULLBACK_REGIME_PRICE_FILTER", self.cfg.regime_price_filter)
        self.cfg.regime_cache_sec = int(os.getenv("PULLBACK_REGIME_CACHE_SEC", str(self.cfg.regime_cache_sec)) or self.cfg.regime_cache_sec)
        self.cfg.chop_er_min = _env_float("PULLBACK_CHOP_ER_MIN", self.cfg.chop_er_min)
        self.cfg.chop_er_period = int(os.getenv("PULLBACK_CHOP_ER_PERIOD", str(self.cfg.chop_er_period)) or self.cfg.chop_er_period)
        self.cfg.chop_in_range_only = _env_bool("PULLBACK_CHOP_IN_RANGE_ONLY", self.cfg.chop_in_range_only)

        self.cfg.allow_longs = _env_bool("PULLBACK_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("PULLBACK_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._store = None
        self.impl: Optional[InPlayPullbackStrategy] = None

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

        self._store = store

        tf_break = self.cfg.tf_break
        tf_entry = self.cfg.tf_entry
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
            "tf_entry": tf_entry,
            "lookback_break_bars": int(lookback_break_bars),
            "atr_period": int(self.cfg.atr_period),
            "impulse_atr_mult": float(self.cfg.impulse_atr_mult),
            "impulse_body_min_frac": float(self.cfg.impulse_body_min_frac),
            "impulse_vol_mult": float(self.cfg.impulse_vol_mult),
            "impulse_vol_period": int(self.cfg.impulse_vol_period),
            "pullback_zone_atr": float(self.cfg.pullback_zone_atr),
            "prebreak_reclaim_atr": float(self.cfg.prebreak_reclaim_atr),
            "prebreak_max_dist_atr": float(self.cfg.prebreak_max_dist_atr),
            "prebreak_sl_buffer_atr": float(self.cfg.prebreak_sl_buffer_atr),
            "min_rr_to_level": float(self.cfg.min_rr_to_level),
            "reclaim_body_frac": float(self.cfg.reclaim_body_frac),
            "require_reclaim": bool(self.cfg.require_reclaim),
            "allow_longs": bool(self.cfg.allow_longs),
            "allow_shorts": bool(self.cfg.allow_shorts),
            "max_wait_bars": int(self.cfg.max_wait_bars),
            "range_atr_max": float(self.cfg.range_atr_max),
            "breakout_buffer_atr": float(self.cfg.breakout_buffer_atr),
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

        sig = inspect.signature(InPlayPullbackStrategy.__init__)
        accepted = set(sig.parameters.keys()) - {"self", "fetch_klines"}
        filtered = {k: v for k, v in candidate.items() if k in accepted}

        self.impl = InPlayPullbackStrategy(_fetch_klines, **filtered)

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        return _run_coro_sync(self.maybe_signal(store, ts_ms, last_price))

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        self._ensure_impl(store)
        assert self.impl is not None

        symbol = store.symbol
        sig = await self.impl.maybe_signal(symbol, price=float(last_price), ts_ms=int(ts_ms))
        if not sig:
            return None

        side = "long" if sig.side == "Buy" else "short"
        entry = float(sig.entry)
        sl = float(sig.sl)
        tp = float(sig.tp)
        level = float(sig.tp)  # for pullback, tp is the level

        min_stop_pct = _env_float('PULLBACK_MIN_STOP_PCT', 0.0)
        max_stop_pct = _env_float('PULLBACK_MAX_STOP_PCT', 0.0)
        stop_pct = abs(entry - sl) / max(1e-12, entry)
        if min_stop_pct > 0 and stop_pct < min_stop_pct:
            return None
        if max_stop_pct > 0 and stop_pct > max_stop_pct:
            return None

        base_reason = getattr(sig, "reason", "pullback")

        exit_mode = (os.getenv("PULLBACK_EXIT_MODE") or "fixed").strip().lower()
        if exit_mode in {"runner", "managed"}:
            risk = abs(entry - sl)
            if risk > 0:
                rs = _env_csv_floats("PULLBACK_PARTIAL_RS", [1.0, 2.0, 4.0])
                fracs = _env_csv_floats("PULLBACK_PARTIAL_FRACS", [0.50, 0.25, 0.15])
                if len(fracs) != len(rs):
                    fracs = [1.0 / len(rs)] * len(rs)

                if side == "long":
                    tps = [entry + (r * risk) for r in rs]
                    if level > entry:
                        tps = [level] + tps
                    tps = sorted(set(tps))
                else:
                    tps = [entry - (r * risk) for r in rs]
                    if level < entry:
                        tps = [level] + tps
                    tps = sorted(set(tps), reverse=True)

                trail_mult = _env_float("PULLBACK_TRAIL_ATR_MULT", 2.5)
                trail_period = _env_int("PULLBACK_TRAIL_ATR_PERIOD", 14)
                time_stop = _env_int("PULLBACK_TIME_STOP_BARS", 288)

                return TradeSignal(
                    strategy="inplay_pullback",
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
            strategy="inplay_pullback",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=base_reason,
        )
