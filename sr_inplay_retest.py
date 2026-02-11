# sr_inplay_retest.py
from dataclasses import dataclass
from typing import Optional, Callable, Any, List, Dict
import math
import time

@dataclass
class RetestSignal:
    side: str              # "Buy" / "Sell"
    entry: float
    sl: float
    tp: float
    reason: str

# Backwards-compatible alias expected by wrappers
InPlayRetestSignal = RetestSignal

# NOTE:
# The in-play strategy is used both in the live bot and in the backtest harness.
# Depending on the caller, candles can be:
#   - dicts with keys like "open/high/low/close" (strings or floats)
#   - our Candle/Kline dataclasses with fields o/h/l/c
#   - Bybit v5 kline rows: [startTime, open, high, low, close, volume, turnover]
# To avoid type issues (e.g. float(Candle) errors), we read OHLC through helpers.

_FIELD_TO_ATTR = {
    "startTime": "ts",
    "open": "o",
    "high": "h",
    "low": "l",
    "close": "c",
    "volume": "v",
}

_FIELD_TO_IDX = {
    "startTime": 0,
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


def _to_float(x: Any) -> float:
    if x is None:
        return float("nan")
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x)
        except Exception:
            return float("nan")
    try:
        return float(x)
    except Exception:
        return float("nan")


def _get_num(candle: Any, field: str, alt_field: Optional[str] = None) -> float:
    """Extract a numeric OHLC field from various candle shapes."""
    # dict-like
    if isinstance(candle, dict):
        if field in candle:
            v = candle.get(field)
            # Sometimes values might themselves be candle objects
            if hasattr(v, _FIELD_TO_ATTR.get(field, "")):
                return _to_float(getattr(v, _FIELD_TO_ATTR[field]))
            return _to_float(v)
        alt = alt_field or _FIELD_TO_ATTR.get(field)
        if alt and alt in candle:
            return _to_float(candle.get(alt))

    # list/tuple (Bybit v5 row)
    if isinstance(candle, (list, tuple)):
        idx = _FIELD_TO_IDX.get(field)
        if idx is not None and len(candle) > idx:
            return _to_float(candle[idx])

    # object with attributes
    alt = alt_field or _FIELD_TO_ATTR.get(field)
    if alt and hasattr(candle, alt):
        return _to_float(getattr(candle, alt))
    if hasattr(candle, field):
        return _to_float(getattr(candle, field))

    return float("nan")


def normalize_klines(raw: Any) -> List[Any]:
    """Normalize common kline formats to a list of candles."""
    if not raw:
        return []
    if isinstance(raw, dict):
        r = raw.get("result")
        if isinstance(r, dict) and isinstance(r.get("list"), list):
            raw = r["list"]
        elif isinstance(raw.get("list"), list):
            raw = raw["list"]
        else:
            return []
    if isinstance(raw, list):
        return raw
    try:
        return list(raw)
    except Exception:
        return []

def ema(values: List[float], period: int) -> List[float]:
    """EMA series."""
    n = int(period)
    if n <= 1 or len(values) < 2:
        return [float(values[-1])] if values else []
    k = 2.0 / (n + 1.0)
    out: List[float] = []
    ema_v = float(values[0])
    out.append(ema_v)
    for v in values[1:]:
        x = float(v)
        ema_v = ema_v + k * (x - ema_v)
        out.append(ema_v)
    return out

def atr_abs(candles: List[Any], period: int) -> float:
    """Simple ATR (absolute), last value."""
    n = int(period)
    if n <= 0:
        return 0.0
    if not candles or len(candles) < n + 1:
        return 0.0
    trs: List[float] = []
    prev_close = _get_num(candles[0], "c", "close")
    for c in candles[1:]:
        h = _get_num(c, "h", "high")
        l = _get_num(c, "l", "low")
        cl = _get_num(c, "c", "close")
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(float(tr))
        prev_close = cl
    tail = trs[-n:]
    if not tail:
        return 0.0
    return float(sum(tail) / len(tail))

def sma(values: List[float], period: int) -> float:
    n = int(period)
    if n <= 0 or len(values) < n:
        return float("nan")
    tail = values[-n:]
    if not tail:
        return float("nan")
    return float(sum(tail) / len(tail))

def efficiency_ratio(closes: List[float], period: int) -> float:
    """Kauffman Efficiency Ratio (0..1). Low values indicate chop."""
    try:
        n = int(period)
        if n <= 1 or len(closes) < n + 1:
            return 1.0
        start = float(closes[-(n + 1)])
        end = float(closes[-1])
        change = abs(end - start)
        volatility = 0.0
        for i in range(len(closes) - (n + 1), len(closes) - 1):
            volatility += abs(float(closes[i + 1]) - float(closes[i]))
        if volatility <= 0:
            return 1.0
        return float(change / volatility)
    except Exception:
        return 1.0

def _atr(candles, period: int) -> float:
    if len(candles) < period + 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = _get_num(candles[i], "high")
        l = _get_num(candles[i], "low")
        pc = _get_num(candles[i-1], "close")
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    last = trs[-period:]
    return sum(last) / max(1, len(last))

class InPlayRetestStrategy:
    """
    1) “InPlay”: волатильность/импульс (breakout candle size >= X*ATR)
    2) Breakout: пробой high/low диапазона N свечей на TF_break
    3) Retest: возврат в зону уровня и reclaim (закрытие обратно в сторону пробоя)

    Добавлены защитные фильтры, чтобы не ловить "1 тик" пробои и не висеть в armed
    состоянии слишком долго.
    """

    def __init__(
        self,
        fetch_klines: Callable[[str, str, int], Any],
        *,
        tf_break: str = "60",
        tf_entry: str = "5",
        lookback_break_bars: int = 24,     # 24h on 1h candles
        atr_period: int = 14,
        impulse_atr_mult: float = 1.0,
        impulse_body_min_frac: float = 0.0,  # min body/range on impulse candle
        impulse_vol_mult: float = 0.0,       # min vol spike vs SMA(volume)
        impulse_vol_period: int = 20,
        retest_zone_atr: float = 0.35,
        reclaim_body_frac: float = 0.25,
        rr: float = 1.6,
        # Direction toggles
        allow_longs: bool = True,
        allow_shorts: bool = False,
        # Quality filters
        max_wait_bars: int = 24,           # max bars on TF_entry to wait for retest
        range_atr_max: float = 8.0,        # skip arming if (hh-ll) > range_atr_max * ATR
        breakout_buffer_atr: float = 0.10, # require close beyond level by buffer*ATR

        # Regime filter (optional): aligns entries with a higher-timeframe trend.
        # - mode: "off" (default) or "ema"
        # - when enabled, longs are allowed only in up-trend and shorts only in down-trend
        regime_mode: str = "off",
        regime_tf: str = "240",
        regime_ema_fast: int = 20,
        regime_ema_slow: int = 50,
        regime_min_gap_atr: float = 0.0,
            regime_strict: bool = True,
        regime_price_filter: bool = False,
        regime_cache_sec: int = 180,
        chop_er_min: float = 0.0,
        chop_er_period: int = 20,
        chop_in_range_only: bool = True,
):
        self.fetch_klines = fetch_klines
        self.tf_break = tf_break
        self.tf_entry = tf_entry
        self.lookback_break_bars = int(lookback_break_bars)
        self.atr_period = int(atr_period)
        self.impulse_atr_mult = float(impulse_atr_mult)
        self.impulse_body_min_frac = float(impulse_body_min_frac)
        self.impulse_vol_mult = float(impulse_vol_mult)
        self.impulse_vol_period = int(impulse_vol_period)
        self.retest_zone_atr = float(retest_zone_atr)
        self.reclaim_body_frac = float(reclaim_body_frac)
        self.rr = float(rr)

        self.allow_longs = bool(allow_longs)
        self.allow_shorts = bool(allow_shorts)

        self.max_wait_bars = int(max_wait_bars)
        self.range_atr_max = float(range_atr_max)
        self.breakout_buffer_atr = float(breakout_buffer_atr)

        self.regime_mode = str(regime_mode or "off").strip().lower()
        self.regime_tf = str(regime_tf or "240").strip()
        self.regime_ema_fast = int(regime_ema_fast)
        self.regime_ema_slow = int(regime_ema_slow)
        self.regime_min_gap_atr = float(regime_min_gap_atr)
        self.regime_strict = bool(regime_strict)
        self.regime_price_filter = bool(regime_price_filter)
        self.regime_cache_sec = int(regime_cache_sec)

        self.chop_er_min = float(chop_er_min)
        self.chop_er_period = int(chop_er_period)
        self.chop_in_range_only = bool(chop_in_range_only)

        self._regime_cache = {}

        self._armed_side: Optional[str] = None
        self._level: float = 0.0
        self._atr: float = 0.0
        self._armed_ts_ms: int = 0

    @staticmethod
    def _tf_minutes(tf: str) -> int:
        try:
            m = int(str(tf).strip())
            return max(1, m)
        except Exception:
            return 5

    def _get_regime_state(self, symbol: str) -> Optional[Dict[str, float]]:
        """Compute & cache HTF regime state."""
        mode = (self.regime_mode or "off").strip().lower()
        if mode in ("off", "0", "false", "no", "none"):
            return None

        ttl = max(0, int(self.regime_cache_sec or 0))
        now = time.time()
        if ttl > 0:
            cached = self._regime_cache.get(symbol)
            if cached:
                ts, st = cached
                if (now - float(ts)) <= ttl:
                    return st

        raw = self.fetch_klines(symbol, self.regime_tf, limit=max(int(self.regime_ema_slow) + 60, 120))
        reg = normalize_klines(raw)
        if len(reg) < int(self.regime_ema_slow) + 5:
            return None

        closes = [float(_get_num(c, "c", "close")) for c in reg]
        ef = ema(closes, int(self.regime_ema_fast))
        es = ema(closes, int(self.regime_ema_slow))
        if not ef or not es:
            return None

        efv = float(ef[-1])
        esv = float(es[-1])
        cl = float(closes[-1])

        av = float(atr_abs(reg, int(self.atr_period)))
        gap_atr = 0.0
        bias = 1  # 0 bear, 1 range, 2 bull
        if av > 0:
            gap_atr = abs(efv - esv) / av
            min_gap = float(self.regime_min_gap_atr or 0.0)
            if (min_gap <= 0.0) or (gap_atr >= min_gap):
                bias = 2 if (efv > esv) else 0

        er = 1.0
        if float(self.chop_er_min or 0.0) > 0 and int(self.chop_er_period or 0) > 1:
            er = float(efficiency_ratio(closes, int(self.chop_er_period)))

        st = {"bias": float(bias), "er": float(er), "ef": efv, "es": esv, "cl": cl, "gap_atr": float(gap_atr)}
        if ttl > 0:
            self._regime_cache[symbol] = (now, st)
        return st


    def _regime_ok(self, symbol: str, direction: str) -> bool:
        st = self._get_regime_state(symbol)
        if not st:
            return True

        bias = int(st.get("bias", 1))  # 0 bear, 1 range, 2 bull
        er = float(st.get("er", 1.0))

        # Chop filter (blocks both directions when enabled)
        er_min = float(self.chop_er_min or 0.0)
        if er_min > 0.0:
            apply = (not bool(self.chop_in_range_only)) or (bias == 1)
            if apply and er < er_min:
                return False

        # Direction regime filter
        if not bool(self.regime_strict):
            return True

        if direction == "long":
            if bias == 0:
                return False
            if bool(self.regime_price_filter):
                return float(st.get("cl", 0.0)) >= float(st.get("ef", 0.0))
            return True

        if direction == "short":
            if bias == 2:
                return False
            if bool(self.regime_price_filter):
                return float(st.get("cl", 0.0)) <= float(st.get("ef", 0.0))
            return True

        return True


    def _maybe_timeout(self, now_ts_ms: int) -> None:
        if self._armed_side is None:
            return
        if self.max_wait_bars <= 0:
            return
        entry_min = self._tf_minutes(self.tf_entry)
        max_ms = int(self.max_wait_bars) * entry_min * 60_000
        if self._armed_ts_ms > 0 and now_ts_ms - self._armed_ts_ms > max_ms:
            # give up on this setup
            self._armed_side = None
            self._armed_ts_ms = 0

    async def maybe_signal(self, symbol: str, *, price: float, ts_ms: int) -> Optional[RetestSignal]:
        # timeout old armed setups
        self._maybe_timeout(int(ts_ms))

        # 1) read break TF
        htf = self.fetch_klines(symbol, self.tf_break, self.lookback_break_bars + 10) or []
        if len(htf) < self.lookback_break_bars + 2:
            return None

        # last closed candle (in backtests candles are already closed)
        last = htf[-1]

        atr = _atr(htf, self.atr_period)
        if atr <= 0:
            return None

        # breakout range (exclude last candle)
        window = htf[-(self.lookback_break_bars + 2):-2]
        hh = max(_get_num(x, "high") for x in window)
        ll = min(_get_num(x, "low") for x in window)

        # optional: skip if the "range" is too wide vs ATR
        if self.range_atr_max > 0:
            width = abs(hh - ll)
            if width > self.range_atr_max * atr:
                return None

        body = abs(_get_num(last, "close") - _get_num(last, "open"))
        rng = abs(_get_num(last, "high") - _get_num(last, "low"))
        impulse_size = max(body, rng)
        impulse_ok = impulse_size >= self.impulse_atr_mult * atr

        # Impulse quality filters
        if impulse_ok and self.impulse_body_min_frac > 0.0 and rng > 0:
            body_frac = body / rng
            if body_frac < self.impulse_body_min_frac:
                impulse_ok = False
        if impulse_ok and self.impulse_vol_mult > 0.0 and self.impulse_vol_period > 1:
            vols = [_get_num(x, "volume", "v") for x in htf]
            # Use prior candles for baseline (exclude last impulse candle)
            baseline = sma(vols[:-1], self.impulse_vol_period)
            last_vol = _get_num(last, "volume", "v")
            if not (baseline > 0 and last_vol >= self.impulse_vol_mult * baseline):
                impulse_ok = False

        close = _get_num(last, "close")
        buf = max(0.0, self.breakout_buffer_atr) * atr

        # Arm breakout
        if self._armed_side is None and impulse_ok:
            if self.allow_longs and close > (hh + buf) and self._regime_ok(symbol, "long"):
                self._armed_side = "Buy"
                self._level = hh
                self._atr = atr
                self._armed_ts_ms = int(ts_ms)
            elif self.allow_shorts and close < (ll - buf) and self._regime_ok(symbol, "short"):
                self._armed_side = "Sell"
                self._level = ll
                self._atr = atr
                self._armed_ts_ms = int(ts_ms)

        if self._armed_side is None:
            return None

        # 2) retest on entry TF
        ltf = self.fetch_klines(symbol, self.tf_entry, 120) or []
        if len(ltf) < 10:
            return None

        c = ltf[-1]
        o = _get_num(c, "open")
        h = _get_num(c, "high")
        l = _get_num(c, "low")
        cl = _get_num(c, "close")

        zone = self.retest_zone_atr * self._atr

        if self._armed_side == "Buy":
            touched = (l <= self._level + zone)
            # Directional body requirement: reclaim should be a meaningful bullish candle.
            reclaimed = (cl > self._level) and ((cl - o) >= self.reclaim_body_frac * self._atr)
            if touched and reclaimed:
                entry = cl
                sl = min(l, self._level - zone)
                r = entry - sl
                if r <= 0:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                tp = entry + self.rr * r
                self._armed_side = None
                self._armed_ts_ms = 0
                return RetestSignal("Buy", entry, sl, tp, "retest_long")
        else:
            touched = (h >= self._level - zone)
            # Directional body requirement: reclaim should be a meaningful bearish candle.
            reclaimed = (cl < self._level) and ((o - cl) >= self.reclaim_body_frac * self._atr)
            if touched and reclaimed:
                entry = cl
                sl = max(h, self._level + zone)
                r = sl - entry
                if r <= 0:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                tp = entry - self.rr * r
                self._armed_side = None
                self._armed_ts_ms = 0
                return RetestSignal("Sell", entry, sl, tp, "retest_short")

        return None


class InPlayPullbackStrategy(InPlayRetestStrategy):
    """
    "Pre-breakout" pullback strategy:
    - Identify a strong impulse candle on the break TF.
    - Price is still below the level (hh/ll), but close to it.
    - Enter on a pullback + reclaim on the entry TF, target the level.
    - Optionally use runner exits in the wrapper.
    """

    def __init__(
        self,
        fetch_klines: Callable[[str, str, int], Any],
        *,
        tf_break: str = "15",
        tf_entry: str = "5",
        lookback_break_bars: int = 24,
        atr_period: int = 14,
        impulse_atr_mult: float = 0.7,
        impulse_body_min_frac: float = 0.0,
        impulse_vol_mult: float = 0.0,
        impulse_vol_period: int = 20,
        pullback_zone_atr: float = 0.80,
        prebreak_reclaim_atr: float = 0.10,
        prebreak_max_dist_atr: float = 2.50,
        prebreak_sl_buffer_atr: float = 0.15,
        min_rr_to_level: float = 0.3,
        reclaim_body_frac: float = 0.0,
        require_reclaim: bool = False,
        # Direction toggles
        allow_longs: bool = True,
        allow_shorts: bool = False,
        # Quality filters
        max_wait_bars: int = 24,
        range_atr_max: float = 8.0,
        breakout_buffer_atr: float = 0.10,
        # Regime filter (same as inplay)
        regime_mode: str = "off",
        regime_tf: str = "240",
        regime_ema_fast: int = 20,
        regime_ema_slow: int = 50,
        regime_min_gap_atr: float = 0.0,
        regime_strict: bool = True,
        regime_price_filter: bool = False,
        regime_cache_sec: int = 180,
        chop_er_min: float = 0.0,
        chop_er_period: int = 20,
        chop_in_range_only: bool = True,
    ):
        super().__init__(
            fetch_klines,
            tf_break=tf_break,
            tf_entry=tf_entry,
            lookback_break_bars=lookback_break_bars,
            atr_period=atr_period,
            impulse_atr_mult=impulse_atr_mult,
            impulse_body_min_frac=impulse_body_min_frac,
            impulse_vol_mult=impulse_vol_mult,
            impulse_vol_period=impulse_vol_period,
            retest_zone_atr=pullback_zone_atr,
            reclaim_body_frac=reclaim_body_frac,
            rr=1.0,  # not used directly; target is the level
            allow_longs=allow_longs,
            allow_shorts=allow_shorts,
            max_wait_bars=max_wait_bars,
            range_atr_max=range_atr_max,
            breakout_buffer_atr=breakout_buffer_atr,
            regime_mode=regime_mode,
            regime_tf=regime_tf,
            regime_ema_fast=regime_ema_fast,
            regime_ema_slow=regime_ema_slow,
            regime_min_gap_atr=regime_min_gap_atr,
            regime_strict=regime_strict,
            regime_price_filter=regime_price_filter,
            regime_cache_sec=regime_cache_sec,
            chop_er_min=chop_er_min,
            chop_er_period=chop_er_period,
            chop_in_range_only=chop_in_range_only,
        )
        self.pullback_zone_atr = float(pullback_zone_atr)
        self.prebreak_reclaim_atr = float(prebreak_reclaim_atr)
        self.prebreak_max_dist_atr = float(prebreak_max_dist_atr)
        self.prebreak_sl_buffer_atr = float(prebreak_sl_buffer_atr)
        self.min_rr_to_level = float(min_rr_to_level)
        self.require_reclaim = bool(require_reclaim)

    async def maybe_signal(self, symbol: str, *, price: float, ts_ms: int) -> Optional[RetestSignal]:
        self._maybe_timeout(int(ts_ms))

        htf = self.fetch_klines(symbol, self.tf_break, self.lookback_break_bars + 10) or []
        if len(htf) < self.lookback_break_bars + 2:
            return None

        last = htf[-1]
        atr = _atr(htf, self.atr_period)
        if atr <= 0:
            return None

        window = htf[-(self.lookback_break_bars + 2):-2]
        hh = max(_get_num(x, "high") for x in window)
        ll = min(_get_num(x, "low") for x in window)

        if self.range_atr_max > 0:
            width = abs(hh - ll)
            if width > self.range_atr_max * atr:
                return None

        body = abs(_get_num(last, "close") - _get_num(last, "open"))
        rng = abs(_get_num(last, "high") - _get_num(last, "low"))
        impulse_size = max(body, rng)
        impulse_ok = impulse_size >= self.impulse_atr_mult * atr

        if impulse_ok and self.impulse_body_min_frac > 0.0 and rng > 0:
            body_frac = body / rng
            if body_frac < self.impulse_body_min_frac:
                impulse_ok = False
        if impulse_ok and self.impulse_vol_mult > 0.0 and self.impulse_vol_period > 1:
            vols = [_get_num(x, "volume", "v") for x in htf]
            baseline = sma(vols[:-1], self.impulse_vol_period)
            last_vol = _get_num(last, "volume", "v")
            if not (baseline > 0 and last_vol >= self.impulse_vol_mult * baseline):
                impulse_ok = False

        close = _get_num(last, "close")
        buf = max(0.0, self.breakout_buffer_atr) * atr

        if self._armed_side is None and impulse_ok:
            if self.allow_longs and close < hh and (hh - close) <= self.prebreak_max_dist_atr * atr and self._regime_ok(symbol, "long"):
                self._armed_side = "Buy"
                self._level = hh
                self._atr = atr
                self._armed_ts_ms = int(ts_ms)
            elif self.allow_shorts and close > ll and (close - ll) <= self.prebreak_max_dist_atr * atr and self._regime_ok(symbol, "short"):
                self._armed_side = "Sell"
                self._level = ll
                self._atr = atr
                self._armed_ts_ms = int(ts_ms)

        if self._armed_side is None:
            return None

        # If price already broke the level without a pullback, disarm and wait for a new setup
        if self._armed_side == "Buy" and close > (self._level + buf):
            self._armed_side = None
            self._armed_ts_ms = 0
            return None
        if self._armed_side == "Sell" and close < (self._level - buf):
            self._armed_side = None
            self._armed_ts_ms = 0
            return None

        ltf = self.fetch_klines(symbol, self.tf_entry, 120) or []
        if len(ltf) < 10:
            return None

        c = ltf[-1]
        o = _get_num(c, "open")
        h = _get_num(c, "high")
        l = _get_num(c, "low")
        cl = _get_num(c, "close")

        zone = self.pullback_zone_atr * self._atr
        reclaim = self.prebreak_reclaim_atr * self._atr

        if self._armed_side == "Buy":
            touched = (l <= self._level - zone)
            reclaimed = (cl >= (self._level - reclaim)) and ((cl - o) >= self.reclaim_body_frac * self._atr)
            if touched and (reclaimed if self.require_reclaim else (cl >= (self._level - reclaim) or cl > o)):
                entry = cl
                sl = min(l, self._level - zone - self.prebreak_sl_buffer_atr * self._atr)
                r = entry - sl
                if r <= 0:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                rr_to_level = (self._level - entry) / r
                if self.min_rr_to_level > 0 and rr_to_level < self.min_rr_to_level:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                tp = self._level
                self._armed_side = None
                self._armed_ts_ms = 0
                return RetestSignal("Buy", entry, sl, tp, "pullback_long")
        else:
            touched = (h >= self._level + zone)
            reclaimed = (cl <= (self._level + reclaim)) and ((o - cl) >= self.reclaim_body_frac * self._atr)
            if touched and (reclaimed if self.require_reclaim else (cl <= (self._level + reclaim) or cl < o)):
                entry = cl
                sl = max(h, self._level + zone + self.prebreak_sl_buffer_atr * self._atr)
                r = sl - entry
                if r <= 0:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                rr_to_level = (entry - self._level) / r
                if self.min_rr_to_level > 0 and rr_to_level < self.min_rr_to_level:
                    self._armed_side = None
                    self._armed_ts_ms = 0
                    return None
                tp = self._level
                self._armed_side = None
                self._armed_ts_ms = 0
                return RetestSignal("Sell", entry, sl, tp, "pullback_short")

        return None


class InPlayBreakoutStrategy(InPlayRetestStrategy):
    """
    Breakout (impulse) entry on break TF without retest.
    - Detect impulse candle breaking the range.
    - Enter immediately on close if conditions pass.
    - Stop placed beyond level by ATR buffer.
    - TP by RR or managed exits via wrapper.
    """

    def __init__(
        self,
        fetch_klines: Callable[[str, str, int], Any],
        *,
        tf_break: str = "15",
        tf_entry: str = "5",
        lookback_break_bars: int = 24,
        atr_period: int = 14,
        impulse_atr_mult: float = 1.0,
        impulse_body_min_frac: float = 0.4,
        impulse_vol_mult: float = 0.0,
        impulse_vol_period: int = 20,
        breakout_buffer_atr: float = 0.10,
        breakout_sl_atr: float = 0.40,
        retest_touch_atr: float = 0.35,
        reclaim_atr: float = 0.15,
        min_hold_bars: int = 0,
        max_retest_bars: int = 30,
        min_break_bars: int = 1,
        max_dist_atr: float = 1.2,
        rr: float = 1.2,
        allow_longs: bool = True,
        allow_shorts: bool = False,
        range_atr_max: float = 8.0,
        regime_mode: str = "off",
        regime_tf: str = "240",
        regime_ema_fast: int = 20,
        regime_ema_slow: int = 50,
        regime_min_gap_atr: float = 0.0,
        regime_strict: bool = True,
        regime_price_filter: bool = False,
        regime_cache_sec: int = 180,
        chop_er_min: float = 0.0,
        chop_er_period: int = 20,
        chop_in_range_only: bool = True,
    ):
        super().__init__(
            fetch_klines,
            tf_break=tf_break,
            tf_entry=tf_entry,
            lookback_break_bars=lookback_break_bars,
            atr_period=atr_period,
            impulse_atr_mult=impulse_atr_mult,
            impulse_body_min_frac=impulse_body_min_frac,
            impulse_vol_mult=impulse_vol_mult,
            impulse_vol_period=impulse_vol_period,
            retest_zone_atr=0.0,
            reclaim_body_frac=0.0,
            rr=rr,
            allow_longs=allow_longs,
            allow_shorts=allow_shorts,
            max_wait_bars=0,
            range_atr_max=range_atr_max,
            breakout_buffer_atr=breakout_buffer_atr,
            regime_mode=regime_mode,
            regime_tf=regime_tf,
            regime_ema_fast=regime_ema_fast,
            regime_ema_slow=regime_ema_slow,
            regime_min_gap_atr=regime_min_gap_atr,
            regime_strict=regime_strict,
            regime_price_filter=regime_price_filter,
            regime_cache_sec=regime_cache_sec,
            chop_er_min=chop_er_min,
            chop_er_period=chop_er_period,
            chop_in_range_only=chop_in_range_only,
        )
        self.breakout_sl_atr = float(breakout_sl_atr)
        self.retest_touch_atr = float(retest_touch_atr)
        self.reclaim_atr = float(reclaim_atr)
        self.min_hold_bars = int(min_hold_bars)
        self.max_retest_bars = int(max_retest_bars)
        self.min_break_bars = int(min_break_bars)
        self.max_dist_atr = float(max_dist_atr)

    async def maybe_signal(self, symbol: str, *, price: float, ts_ms: int) -> Optional[RetestSignal]:
        htf = self.fetch_klines(symbol, self.tf_break, self.lookback_break_bars + 10) or []
        if len(htf) < self.lookback_break_bars + 2:
            return None

        last = htf[-1]
        atr = _atr(htf, self.atr_period)
        if atr <= 0:
            return None

        window = htf[-(self.lookback_break_bars + 2):-2]
        hh = max(_get_num(x, "high") for x in window)
        ll = min(_get_num(x, "low") for x in window)

        if self.range_atr_max > 0:
            width = abs(hh - ll)
            if width > self.range_atr_max * atr:
                return None

        body = abs(_get_num(last, "close") - _get_num(last, "open"))
        rng = abs(_get_num(last, "high") - _get_num(last, "low"))
        impulse_size = max(body, rng)
        impulse_ok = impulse_size >= self.impulse_atr_mult * atr

        if impulse_ok and self.impulse_body_min_frac > 0.0 and rng > 0:
            body_frac = body / rng
            if body_frac < self.impulse_body_min_frac:
                impulse_ok = False
        if impulse_ok and self.impulse_vol_mult > 0.0 and self.impulse_vol_period > 1:
            vols = [_get_num(x, "volume", "v") for x in htf]
            baseline = sma(vols[:-1], self.impulse_vol_period)
            last_vol = _get_num(last, "volume", "v")
            if not (baseline > 0 and last_vol >= self.impulse_vol_mult * baseline):
                impulse_ok = False

        if not impulse_ok:
            return None

        close = _get_num(last, "close")
        buf = max(0.0, self.breakout_buffer_atr) * atr

        # LTF confirmation (retest + reclaim/hold)
        ltf = self.fetch_klines(symbol, self.tf_entry, max(80, self.max_retest_bars + self.min_hold_bars + 20)) or []
        if len(ltf) < max(20, self.min_hold_bars + 5):
            return None

        ltf_atr = _atr(ltf, max(5, self.atr_period))
        if ltf_atr <= 0:
            ltf_atr = atr

        touch_buf = max(0.0, self.retest_touch_atr) * ltf_atr
        reclaim_buf = max(0.0, self.reclaim_atr) * ltf_atr
        sl_buf = max(0.0, self.breakout_sl_atr) * ltf_atr
        max_dist = max(0.0, self.max_dist_atr) * ltf_atr

        # If timestamps exist, use them to filter ltf bars after breakout bar
        b_ts = _get_num(last, "startTime", "ts")
        def _after_break_idx() -> int:
            if not (isinstance(b_ts, (int, float)) and math.isfinite(b_ts) and b_ts > 0):
                return max(0, len(ltf) - self.max_retest_bars - 1)
            for i, c in enumerate(ltf):
                ts = _get_num(c, "startTime", "ts")
                if isinstance(ts, (int, float)) and math.isfinite(ts) and ts >= b_ts:
                    return max(0, i)
            return max(0, len(ltf) - self.max_retest_bars - 1)

        start_idx = _after_break_idx()
        tail = ltf[start_idx:]
        if len(tail) < 5:
            return None

        def _holds_above(level: float) -> bool:
            if self.min_hold_bars <= 0:
                return _get_num(ltf[-1], "close") >= (level + reclaim_buf)
            hold_start = max(0, len(ltf) - self.min_hold_bars)
            closes = [_get_num(c, "close") for c in ltf[hold_start:]]
            return min(closes) >= (level + reclaim_buf)

        def _holds_below(level: float) -> bool:
            if self.min_hold_bars <= 0:
                return _get_num(ltf[-1], "close") <= (level - reclaim_buf)
            hold_start = max(0, len(ltf) - self.min_hold_bars)
            closes = [_get_num(c, "close") for c in ltf[hold_start:]]
            return max(closes) <= (level - reclaim_buf)

        # Long: breakout above hh, then retest hh and reclaim
        if self.allow_longs and close > (hh + buf) and self._regime_ok(symbol, "long"):
            if abs(price - hh) <= max_dist:
                touched = any(_get_num(c, "low") <= (hh + touch_buf) for c in tail[-self.max_retest_bars:])
                if touched and _holds_above(hh):
                    entry = float(price)
                    sl = float(hh - sl_buf)
                    r = entry - sl
                    if r > 0:
                        tp = entry + self.rr * r
                        return RetestSignal("Buy", entry, sl, tp, "breakout_retest_long")

        # Short: breakout below ll, then retest ll and reclaim
        if self.allow_shorts and close < (ll - buf) and self._regime_ok(symbol, "short"):
            if abs(price - ll) <= max_dist:
                touched = any(_get_num(c, "high") >= (ll - touch_buf) for c in tail[-self.max_retest_bars:])
                if touched and _holds_below(ll):
                    entry = float(price)
                    sl = float(ll + sl_buf)
                    r = sl - entry
                    if r > 0:
                        tp = entry - self.rr * r
                        return RetestSignal("Sell", entry, sl, tp, "breakout_retest_short")

        return None
