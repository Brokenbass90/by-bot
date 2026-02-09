# sr_range.py
from __future__ import annotations

import time
import math
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


# =========================
# Models
# =========================

@dataclass
class Candle:
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


@dataclass
class RangeInfo:
    symbol: str
    support: float
    resistance: float
    mid: float
    width: float
    range_pct: float
    touches_support: int
    touches_resistance: int
    ema_spread_pct: float
    atr_1h: float
    score: float
    detected_at: float
    expires_at: float
    cooldown_until: float = 0.0
    is_active: bool = True


# =========================
# Utils
# =========================

def _to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def _is_finite_pos(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0


async def maybe_await(x: Any) -> Any:
    if inspect.isawaitable(x):
        return await x
    return x


# =========================
# Kline normalization
# =========================

def normalize_klines(raw: Any) -> List[Candle]:
    """
    Поддерживает распространённые форматы:
    - Bybit v5 kline: [[startTime, open, high, low, close, volume, turnover], ...] (строки)
    - dict-формат: [{"startTime":..., "open":..., ...}, ...] или с ключами o/h/l/c
    """
    if not raw:
        return []

    out: List[Candle] = []

    # Иногда raw приходит как dict с ключом "list"/"result"/"data"
    if isinstance(raw, dict):
        for k in ("list", "result", "data"):
            if k in raw and isinstance(raw[k], list):
                raw = raw[k]
                break

    # list-of-lists
    if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)):
        for row in raw:
            if len(row) < 5:
                continue

            ts = int(row[0])
            if ts > 10_000_000_000:  # ms -> sec
                ts //= 1000

            o = _to_float(row[1])
            h = _to_float(row[2])
            l = _to_float(row[3])
            c = _to_float(row[4])
            v = _to_float(row[5]) if len(row) > 5 else 0.0

            out.append(Candle(ts=ts, o=o, h=h, l=l, c=c, v=v))

    # list-of-dicts
    elif isinstance(raw, list) and raw and isinstance(raw[0], dict):
        for row in raw:
            ts = int(row.get("startTime") or row.get("ts") or row.get("t") or 0)
            if ts > 10_000_000_000:  # ms -> sec
                ts //= 1000

            o = _to_float(row.get("open") or row.get("o"))
            h = _to_float(row.get("high") or row.get("h"))
            l = _to_float(row.get("low") or row.get("l"))
            c = _to_float(row.get("close") or row.get("c"))
            v = _to_float(row.get("volume") or row.get("v") or 0.0)

            out.append(Candle(ts=ts, o=o, h=h, l=l, c=c, v=v))

    out.sort(key=lambda x: x.ts)
    return out


# =========================
# Indicators
# =========================

def ema(values: List[float], period: int) -> float:
    """
    EMA по всему ряду (без numpy), возвращает nan если данных мало.
    """
    if not values or period <= 1 or len(values) < period:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = sum(values[:period]) / period
    for x in values[period:]:
        e = x * k + e * (1.0 - k)
    return float(e)


def atr(candles: List[Candle], period: int = 14) -> float:
    """
    ATR в абсолютных единицах (не %).
    """
    if len(candles) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(candles)):
        cur = candles[i]
        prev = candles[i - 1]
        tr = max(cur.h - cur.l, abs(cur.h - prev.c), abs(cur.l - prev.c))
        trs.append(float(tr))
    if len(trs) < period:
        return float("nan")
    return float(sum(trs[-period:]) / period)


def count_touches(
    candles: List[Candle],
    level: float,
    side: str,
    tolerance_pct: float = 0.003,
) -> int:
    """
    touches = сколько свечей касались уровня с допуском tolerance_pct (доля, не %).
    side: "support" -> смотрим low; "resistance" -> смотрим high
    """
    if not candles or not math.isfinite(level) or level <= 0:
        return 0

    tol = level * float(tolerance_pct)
    n = 0

    if side == "support":
        for c in candles:
            if math.isfinite(c.l) and abs(c.l - level) <= tol:
                n += 1
    else:
        for c in candles:
            if math.isfinite(c.h) and abs(c.h - level) <= tol:
                n += 1

    return int(n)


# =========================
# Registry
# =========================

class RangeRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, RangeInfo] = {}

    def set(self, info: RangeInfo, *args) -> None:
        """Store a RangeInfo.

        Backward-compat: some callers used set(symbol, info).
        We accept both (info) and (symbol, info) forms.
        """
        if args:
            # called as set(symbol, info)
            info = args[-1]
        self._items[info.symbol] = info

    def get(self, symbol: str) -> Optional[RangeInfo]:
        info = self._items.get(symbol)
        if not info:
            return None
        now = time.time()
        if now >= info.expires_at:
            self._items.pop(symbol, None)
            return None
        return info

    def deactivate(self, symbol: str, cooldown_sec: int) -> None:
        info = self._items.get(symbol)
        if not info:
            return
        now = time.time()
        info.is_active = False
        info.cooldown_until = now + int(cooldown_sec)
        info.expires_at = max(info.expires_at, info.cooldown_until)

    def is_allowed(self, symbol: str) -> bool:
        info = self.get(symbol)
        if not info:
            return False
        now = time.time()
        if (not info.is_active) and now < info.cooldown_until:
            return False
        return True


# =========================
# Scanner
# =========================

class RangeScanner:
    """
    Детект “флэта” на 1h:
      - вычисляем support/resistance по хвостам low/high (10% хвост, минимум 5 точек)
      - фильтр по ширине диапазона (min/max range_pct)
      - фильтр “плоскости” по EMA-spread (fast/slow)
      - фильтр по касаниям границ
      - фильтр по спайкам за последние 24 свечи (по range%)
    """

    def __init__(
        self,
        fetch_klines: Callable[..., Any],
        registry: RangeRegistry,
        *,
        interval_1h: str = "60",
        lookback_h: int = 72,
        rescan_ttl_sec: int = 14400,
        min_range_pct: float = 3.0,
        max_range_pct: float = 8.0,
        min_touches: int = 3,
        ema_fast: int = 20,
        ema_slow: int = 50,
        max_ema_spread_pct: float = 0.6,
        touch_tolerance_pct: float = 0.003,
        spike_mult: float = 2.5,
        tail_frac: float = 0.10,  # доля хвоста для расчёта границ
        tail_min_k: int = 5,
    ) -> None:
        self.fetch_klines = fetch_klines
        self.registry = registry

        self.interval_1h = str(interval_1h)
        self.lookback_h = int(lookback_h)
        self.rescan_ttl_sec = int(rescan_ttl_sec)

        self.min_range_pct = float(min_range_pct)
        self.max_range_pct = float(max_range_pct)
        self.min_touches = int(min_touches)

        self.ema_fast = int(ema_fast)
        self.ema_slow = int(ema_slow)
        self.max_ema_spread_pct = float(max_ema_spread_pct)

        self.touch_tolerance_pct = float(touch_tolerance_pct)
        self.spike_mult = float(spike_mult)

        self.tail_frac = float(tail_frac)
        self.tail_min_k = int(tail_min_k)

    async def detect(self, symbol: str) -> Optional[RangeInfo]:
        raw = await maybe_await(self.fetch_klines(symbol, self.interval_1h, self.lookback_h))
        candles = normalize_klines(raw)

        if len(candles) < max(self.ema_slow + 5, 30):
            return None

        lows = [c.l for c in candles if _is_finite_pos(c.l)]
        highs = [c.h for c in candles if _is_finite_pos(c.h)]
        closes = [c.c for c in candles if _is_finite_pos(c.c)]

        if len(lows) < 10 or len(highs) < 10 or len(closes) < (self.ema_slow + 2):
            return None

        # EMA spread filter (флэт должен быть “плоским”)
        ema_fast_v = ema(closes, self.ema_fast)
        ema_slow_v = ema(closes, self.ema_slow)
        if not (math.isfinite(ema_fast_v) and math.isfinite(ema_slow_v) and ema_slow_v > 0):
            return None

        ema_spread_pct = abs(ema_fast_v - ema_slow_v) / ema_slow_v * 100.0
        if ema_spread_pct > self.max_ema_spread_pct:
            return None

        # Границы диапазона через хвосты low/high
        sorted_lows = sorted(lows)
        sorted_highs = sorted(highs)

        n = min(len(sorted_lows), len(sorted_highs))
        if n < 10:
            return None

        k = max(self.tail_min_k, int(n * self.tail_frac))
        k = min(k, n)

        support = sum(sorted_lows[:k]) / float(k)
        resistance = sum(sorted_highs[-k:]) / float(k)

        if not (math.isfinite(support) and math.isfinite(resistance)):
            return None
        if support <= 0 or resistance <= support:
            return None

        width = resistance - support
        mid = (support + resistance) / 2.0
        range_pct = width / support * 100.0

        if range_pct < self.min_range_pct or range_pct > self.max_range_pct:
            return None

        # Спайк-фильтр по диапазону свечей за последние 24h
        last_n = candles[-24:] if len(candles) >= 24 else candles
        ranges_pct: List[float] = []
        for c in last_n:
            if not (_is_finite_pos(c.h) and _is_finite_pos(c.l) and _is_finite_pos(c.c)):
                continue
            ranges_pct.append(((c.h - c.l) / max(c.c, 1e-12)) * 100.0)

        if len(ranges_pct) >= 5:
            avg_r = sum(ranges_pct) / len(ranges_pct)
            max_r = max(ranges_pct)
            if avg_r > 0 and max_r > avg_r * self.spike_mult:
                return None

        # Касания границ
        t_sup = count_touches(candles, support, "support", self.touch_tolerance_pct)
        t_res = count_touches(candles, resistance, "resistance", self.touch_tolerance_pct)
        if t_sup < self.min_touches or t_res < self.min_touches:
            return None

        a1h = atr(candles, 14)
        if not math.isfinite(a1h):
            a1h = 0.0

        # Score: чем уже диапазон и чем меньше ema_spread, тем выше; плюс касания
        score = 0.0
        score += max(0.0, (self.max_range_pct - range_pct))  # предпочтение более узким
        score += max(0.0, (self.max_ema_spread_pct - ema_spread_pct)) * 2.0
        score += (t_sup + t_res) * 0.5

        now = time.time()
        return RangeInfo(
            symbol=str(symbol),
            support=float(support),
            resistance=float(resistance),
            mid=float(mid),
            width=float(width),
            range_pct=float(range_pct),
            touches_support=int(t_sup),
            touches_resistance=int(t_res),
            ema_spread_pct=float(ema_spread_pct),
            atr_1h=float(a1h),
            score=float(score),
            detected_at=float(now),
            expires_at=float(now + self.rescan_ttl_sec),
        )

    async def rescan(self, symbols: List[str], top_n: int = 50) -> List[RangeInfo]:
        found: List[RangeInfo] = []

        for sym in symbols:
            try:
                info = await self.detect(sym)
                if info:
                    found.append(info)
            except Exception:
                # намеренно глушим, чтобы один символ не валил весь рескан
                continue

        found.sort(key=lambda x: x.score, reverse=True)
        picked = found[: max(1, int(top_n))]

        for info in picked:
            self.registry.set(info)

        return picked
