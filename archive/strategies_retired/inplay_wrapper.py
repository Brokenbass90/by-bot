from __future__ import annotations

import os
import inspect
import math
import asyncio
from dataclasses import dataclass
from typing import Optional, Any, Dict, List

from backtest.bt_types import TradeSignal
from sr_inplay_retest import InPlayRetestStrategy


def _run_coro_sync(obj: Any) -> Any:
    """If `obj` is a coroutine, execute it and return the result.

    The backtest loop is synchronous. We keep strategy logic async-friendly
    (it may call async scanners in the future), but provide a synchronous
    adapter for backtesting.
    """
    if asyncio.iscoroutine(obj):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Should not happen in our CLI/backtest usage, but stay safe.
                new_loop = asyncio.new_event_loop()
                try:
                    return new_loop.run_until_complete(obj)
                finally:
                    new_loop.close()
            return loop.run_until_complete(obj)
        except RuntimeError:
            # No event loop in this thread.
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
class InPlayWrapperConfig:
    """Configuration for the in-play strategy wrapper.

    The backtest engine provides a `KlineStore` with candles in an internal
    `Candle` dataclass format. `sr_inplay_retest.InPlayRetestStrategy` expects a
    `fetch_klines()` function that returns raw klines in a Bybit-like format
    (list-of-lists / list-of-dicts), because it reuses `normalize_klines()`.

    This wrapper bridges those two worlds and also protects against init
    signature drift by only passing kwargs that the current
    `InPlayRetestStrategy.__init__` actually accepts.
    """

    # Breakout detection timeframe (minutes as string, e.g. "60" for 1h)
    tf_break: str = "15"
    # Entry/retest confirmation timeframe (minutes as string, e.g. "5")
    tf_entry: str = "5"

    # Lookback window expressed in HOURS; will be converted to bars of `tf_break`.
    # Default reduced to make the strategy actually trade in typical 30d backtests.
    lookback_h: int = 24

    # Core parameters (match names used in sr_inplay_retest)
    atr_period: int = 14
    # Make the detector less strict by default (backtests were producing 0 trades).
    impulse_atr_mult: float = 0.95
    impulse_body_min_frac: float = 0.0
    impulse_vol_mult: float = 0.0
    impulse_vol_period: int = 20
    retest_zone_atr: float = 0.50
    reclaim_body_frac: float = 0.20
    rr: float = 1.4

    # New quality filters (optional)
    max_wait_bars: int = 24
    range_atr_max: float = 8.0
    breakout_buffer_atr: float = 0.10

    # Regime filter (optional)
    regime_mode: str = "off"      # off|ema
    regime_tf: str = "240"       # minutes
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_min_gap_atr: float = 0.0

    regime_strict: bool = True
    regime_price_filter: bool = False
    regime_cache_sec: int = 180
    chop_er_min: float = 0.0
    chop_er_period: int = 20
    chop_in_range_only: bool = True


    # Direction toggles (useful when you want to focus on long pumps first).
    allow_longs: bool = True
    allow_shorts: bool = False

    # Optional: allow older configs to override using previous field names
    # (kept for backward compatibility; not used directly).
    interval_1h: Optional[str] = None
    interval_5m: Optional[str] = None


class InPlayWrapper:
    """Adapter that exposes a `maybe_signal(store, ts_ms, last_price)` API."""

    def __init__(self, cfg: Optional[InPlayWrapperConfig] = None):
        if cfg is None:
            cfg = InPlayWrapperConfig()
        self.cfg = cfg

        # Optional env overrides (for quick parameter sweeps without editing code)
        self.cfg.tf_break = os.getenv("INPLAY_TF_BREAK", self.cfg.tf_break)
        self.cfg.tf_entry = os.getenv("INPLAY_TF_ENTRY", self.cfg.tf_entry)
        self.cfg.lookback_h = _env_int("INPLAY_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.impulse_atr_mult = _env_float("INPLAY_IMPULSE_ATR_MULT", self.cfg.impulse_atr_mult)
        self.cfg.impulse_body_min_frac = _env_float("INPLAY_IMPULSE_BODY_MIN_FRAC", self.cfg.impulse_body_min_frac)
        self.cfg.impulse_vol_mult = _env_float("INPLAY_IMPULSE_VOL_MULT", self.cfg.impulse_vol_mult)
        self.cfg.impulse_vol_period = _env_int("INPLAY_IMPULSE_VOL_PERIOD", self.cfg.impulse_vol_period)
        self.cfg.retest_zone_atr = _env_float("INPLAY_RETEST_ZONE_ATR", self.cfg.retest_zone_atr)
        self.cfg.reclaim_body_frac = _env_float("INPLAY_RECLAIM_BODY_FRAC", self.cfg.reclaim_body_frac)
        self.cfg.rr = _env_float("INPLAY_RR", self.cfg.rr)
        self.cfg.atr_period = _env_int("INPLAY_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.allow_longs = _env_bool("INPLAY_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("INPLAY_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.max_wait_bars = _env_int("INPLAY_MAX_WAIT_BARS", self.cfg.max_wait_bars)
        self.cfg.range_atr_max = _env_float("INPLAY_RANGE_ATR_MAX", self.cfg.range_atr_max)
        self.cfg.breakout_buffer_atr = _env_float("INPLAY_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)

        # Regime filter (optional)
        self.cfg.regime_mode = os.getenv("INPLAY_REGIME_MODE", self.cfg.regime_mode)
        # Backward-compatible alias: INPLAY_REGIME=1 enables the EMA-based regime filter.
        if str(os.getenv('INPLAY_REGIME', '')).strip().lower() in ('1','true','yes','on'):
            if str(self.cfg.regime_mode).strip().lower() in ('off','0','false','none',''):
                self.cfg.regime_mode = 'ema'
        self.cfg.regime_tf = os.getenv("INPLAY_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("INPLAY_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("INPLAY_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_gap_atr = _env_float("INPLAY_REGIME_MIN_GAP_ATR", self.cfg.regime_min_gap_atr)
        # extra regime/chop filters
        self.cfg.regime_strict = _env_bool("INPLAY_REGIME_STRICT", self.cfg.regime_strict)
        self.cfg.regime_price_filter = _env_bool("INPLAY_REGIME_PRICE_FILTER", self.cfg.regime_price_filter)
        self.cfg.regime_cache_sec = int(os.getenv("INPLAY_REGIME_CACHE_SEC", str(self.cfg.regime_cache_sec)) or self.cfg.regime_cache_sec)
        self.cfg.chop_er_min = _env_float("INPLAY_CHOP_ER_MIN", self.cfg.chop_er_min)
        self.cfg.chop_er_period = int(os.getenv("INPLAY_CHOP_ER_PERIOD", str(self.cfg.chop_er_period)) or self.cfg.chop_er_period)
        self.cfg.chop_in_range_only = _env_bool("INPLAY_CHOP_IN_RANGE_ONLY", self.cfg.chop_in_range_only)
        self._store = None
        self.impl: Optional[InPlayRetestStrategy] = None
        self.soft_impl: Optional[InPlayRetestStrategy] = None
        self.soft_enabled: bool = _env_bool("INPLAY_SOFT_ENABLE", False)

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

    @staticmethod
    def _candles_to_raw_klines(candles: List[Any]) -> List[List[Any]]:
        """Convert engine Candle objects to a normalize_klines()-friendly format."""
        out: List[List[Any]] = []
        for c in candles:
            # Engine Candle fields: ts (ms), o, h, l, c, v
            out.append([int(getattr(c, "ts")), float(getattr(c, "o")), float(getattr(c, "h")),
                        float(getattr(c, "l")), float(getattr(c, "c")), float(getattr(c, "v", 0.0)), 0.0])
        return out

    def _ensure_impl(self, store) -> None:
        if self.impl is not None:
            return

        self._store = store

        # Choose tf values (support older config aliases if someone set them)
        tf_break = self.cfg.interval_1h or self.cfg.tf_break
        tf_entry = self.cfg.interval_5m or self.cfg.tf_entry
        lookback_break_bars = self._hours_to_break_bars(self.cfg.lookback_h, tf_break)

        def _fetch_klines(symbol: str, interval: str, limit: int):
            """Return klines in the format expected by sr_inplay_retest.

            The in-play retest implementation expects a list of dicts with keys
            open/high/low/close (and optionally startTime/volume). The backtest
            engine may provide:
              - raw Bybit-like rows: [ts, o, h, l, c, v, turnover]
              - sr_range.Candle objects
              - already-dict rows

            This adapter makes the wrapper resilient to any of the above.
            """

            raw = store.fetch_klines(symbol, interval, int(limit))
            out: List[Dict[str, Any]] = []
            for r in (raw or []):
                # 1) Already a mapping
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

                # 2) sr_range.Candle-style object
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

                # 3) Raw list/tuple rows
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

                # Unknown row shape: ignore it
                # (better to skip than to crash the entire backtest run)

            return out

        # Build a superset of kwargs, then filter by the impl's init signature.
        candidate: Dict[str, Any] = {
            "tf_break": tf_break,
            "tf_entry": tf_entry,
            "lookback_break_bars": int(lookback_break_bars),
            "atr_period": int(self.cfg.atr_period),
            "impulse_atr_mult": float(self.cfg.impulse_atr_mult),
            "impulse_body_min_frac": float(self.cfg.impulse_body_min_frac),
            "impulse_vol_mult": float(self.cfg.impulse_vol_mult),
            "impulse_vol_period": int(self.cfg.impulse_vol_period),
            "retest_zone_atr": float(self.cfg.retest_zone_atr),
            "reclaim_body_frac": float(self.cfg.reclaim_body_frac),
            "rr": float(self.cfg.rr),

            # Direction toggles
            "allow_longs": bool(self.cfg.allow_longs),
            "allow_shorts": bool(self.cfg.allow_shorts),

            # Quality filters
            "max_wait_bars": int(self.cfg.max_wait_bars),
            "range_atr_max": float(self.cfg.range_atr_max),
            "breakout_buffer_atr": float(self.cfg.breakout_buffer_atr),

            # Regime filter
            "regime_mode": str(self.cfg.regime_mode),
            "regime_tf": str(self.cfg.regime_tf),
            "regime_ema_fast": int(self.cfg.regime_ema_fast),
            "regime_ema_slow": int(self.cfg.regime_ema_slow),
            "regime_min_gap_atr": float(self.cfg.regime_min_gap_atr),

            # Older/alternate names (harmless if filtered out)
            "interval_1h": tf_break,
            "interval_5m": tf_entry,
            "lookback_h": int(self.cfg.lookback_h),
        }

        sig = inspect.signature(InPlayRetestStrategy.__init__)
        accepted = set(sig.parameters.keys()) - {"self", "fetch_klines"}
        filtered = {k: v for k, v in candidate.items() if k in accepted}

        self.impl = InPlayRetestStrategy(_fetch_klines, **filtered)

        # Optional "soft" fallback profile (looser filters).
        if self.soft_enabled:
            soft = dict(filtered)
            soft["impulse_atr_mult"] = float(os.getenv("INPLAY_SOFT_IMPULSE_ATR_MULT", "0.75"))
            soft["retest_zone_atr"] = float(os.getenv("INPLAY_SOFT_RETEST_ZONE_ATR", "0.70"))
            soft["reclaim_body_frac"] = float(os.getenv("INPLAY_SOFT_RECLAIM_BODY_FRAC", "0.10"))
            soft["breakout_buffer_atr"] = float(os.getenv("INPLAY_SOFT_BREAKOUT_BUFFER_ATR", "0.05"))
            soft["regime_min_gap_atr"] = float(os.getenv("INPLAY_SOFT_REGIME_MIN_GAP_ATR", "0.0"))
            self.soft_impl = InPlayRetestStrategy(_fetch_klines, **soft)

    @staticmethod
    def _coerce_price(x: Any) -> float:
        """Best-effort conversion of various price/candle representations into float price."""
        if x is None:
            return float("nan")
        # Our Candle dataclass (backtest/normalize)
        if hasattr(x, "c"):
            try:
                return float(getattr(x, "c"))
            except Exception:
                pass
        # dict-like
        if isinstance(x, dict):
            for k in ("c", "close", "last", "price"):
                if k in x:
                    try:
                        return float(x[k])
                    except Exception:
                        pass
        # list/tuple: [ts, o, h, l, c, ...]
        if isinstance(x, (list, tuple)) and len(x) >= 5:
            try:
                return float(x[4])
            except Exception:
                pass
        # scalar
        return float(x)

    @staticmethod
    def _coerce_ts(x: Any) -> int:
        """Best-effort conversion of various timestamp representations into int milliseconds."""
        if x is None:
            return 0
        if hasattr(x, "ts"):
            try:
                return int(getattr(x, "ts"))
            except Exception:
                pass
        if isinstance(x, dict):
            for k in ("ts", "t", "startTime", "timestamp", "time"):
                if k in x:
                    try:
                        return int(float(x[k]))
                    except Exception:
                        pass
        if isinstance(x, (list, tuple)) and len(x) >= 1:
            try:
                return int(float(x[0]))
            except Exception:
                pass
        try:
            return int(float(x))
        except Exception:
            return 0

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        """Sync adapter for backtest runner.

        The backtest engine calls strategies in a synchronous loop.
        Our implementation is async because it may call async fetchers.
        """
        return _run_coro_sync(self.maybe_signal(store, ts_ms, last_price))

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        self._ensure_impl(store)
        assert self.impl is not None

        symbol = store.symbol
        before_armed = getattr(self.impl, '_armed_side', None)
        sig = await self.impl.maybe_signal(symbol, price=self._coerce_price(last_price), ts_ms=int(self._coerce_ts(ts_ms)))
        after_armed = getattr(self.impl, '_armed_side', None)
        if os.getenv('INPLAY_DEBUG') == '1' and before_armed is None and after_armed is not None:
            try:
                lvl = getattr(self.impl, '_armed_level', None)
                print(f'[inplay] ARMED {symbol} side={after_armed} level={lvl} ts={int(ts_ms)} price={last_price}')
            except Exception:
                pass

        if not sig and self.soft_impl is not None:
            sig = await self.soft_impl.maybe_signal(symbol, price=self._coerce_price(last_price), ts_ms=int(self._coerce_ts(ts_ms)))
            if not sig:
                return None
        elif not sig:
            return None

        # Apply wrapper-level direction filter (we keep this here because
        # sr_inplay_retest currently only has an `allow_shorts` toggle).
        if sig.side == "Buy" and not self.cfg.allow_longs:
            return None
        if sig.side == "Sell" and not self.cfg.allow_shorts:
            return None

        # Backtest engine expects side in {"long", "short"}.
        # InPlayRetestStrategy emits {"Buy", "Sell"}.
        side = "long" if sig.side == "Buy" else "short"

        entry = float(sig.entry)
        sl = float(sig.sl)
        tp = float(sig.tp)

        # Optional filter: skip signals with too-tight or too-wide stops.
        min_stop_pct = _env_float('INPLAY_MIN_STOP_PCT', 0.0)
        max_stop_pct = _env_float('INPLAY_MAX_STOP_PCT', 0.0)
        stop_pct = abs(entry - sl) / max(1e-12, entry)
        if min_stop_pct > 0 and stop_pct < min_stop_pct:
            return None
        if max_stop_pct > 0 and stop_pct > max_stop_pct:
            return None

        base_reason = getattr(sig, "reason", "inplay")

        # Optional: runner-style exit management (partial TPs + ATR trailing + time stop).
        exit_mode = (os.getenv("INPLAY_EXIT_MODE") or "fixed").strip().lower()
        if exit_mode in {"runner", "long_runner", "run", "managed"}:
            risk = abs(entry - sl)
            if risk > 0:
                rs = _env_csv_floats("INPLAY_PARTIAL_RS", [1.0, 2.0, 4.0])
                fracs = _env_csv_floats("INPLAY_PARTIAL_FRACS", [0.50, 0.25, 0.15])
                # Leave remainder for trailing/time (do not force sum(fracs)=1.0).
                if len(fracs) != len(rs):
                    fracs = [1.0 / len(rs)] * len(rs)

                if side == "long":
                    tps = [entry + (r * risk) for r in rs]
                    # Optional "nearest resistance" as the last tp.
                    if _env_bool("INPLAY_USE_LEVEL_TP", True):
                        lookback_h = _env_int("INPLAY_LEVEL_LOOKBACK_1H", 72)
                        margin = _env_float("INPLAY_LEVEL_MARGIN_PCT", 0.003)
                        try:
                            c1h = getattr(store, "_slice", None)
                            highs = []
                            if callable(c1h):
                                for c in c1h("60", lookback_h):
                                    highs.append(float(getattr(c, "h", 0.0)))
                            if highs:
                                above = sorted([h for h in highs if h > entry * (1 + margin)])
                                if above:
                                    lvl_tp = above[0]
                                    if lvl_tp > tps[-1] * 0.98:
                                        tps[-1] = lvl_tp
                        except Exception:
                            pass
                else:
                    tps = [entry - (r * risk) for r in rs]
                    if _env_bool("INPLAY_USE_LEVEL_TP", True):
                        lookback_h = _env_int("INPLAY_LEVEL_LOOKBACK_1H", 72)
                        margin = _env_float("INPLAY_LEVEL_MARGIN_PCT", 0.003)
                        try:
                            c1h = getattr(store, "_slice", None)
                            lows = []
                            if callable(c1h):
                                for c in c1h("60", lookback_h):
                                    lows.append(float(getattr(c, "l", 0.0)))
                            if lows:
                                below = sorted([l for l in lows if l < entry * (1 - margin)], reverse=True)
                                if below:
                                    lvl_tp = below[0]
                                    if lvl_tp < tps[-1] * 1.02:
                                        tps[-1] = lvl_tp
                        except Exception:
                            pass

                trail_mult = _env_float("INPLAY_TRAIL_ATR_MULT", 2.5)
                trail_period = _env_int("INPLAY_TRAIL_ATR_PERIOD", 14)
                time_stop = _env_int("INPLAY_TIME_STOP_BARS", 288)  # ~24h on 5m

                # TradeSignal requires strategy + symbol for downstream logging/aggregation.
                return TradeSignal(
                    strategy="inplay",
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

        # Default: fixed TP exit.
        return TradeSignal(
            strategy="inplay",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            reason=base_reason,
        )
