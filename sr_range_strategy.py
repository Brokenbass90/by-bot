# # sr_range_strategy.py
# from __future__ import annotations

# import time
# import math
# from dataclasses import dataclass
# from typing import Any, Callable, Optional, Dict, Tuple, List

# from sr_range import RangeRegistry, RangeInfo, Candle, normalize_klines, maybe_await, atr


# @dataclass
# class RangeSignal:
#     side: str          # "Buy" | "Sell"
#     tp: float
#     sl: float
#     reason: str


# def _is_finite(x: float) -> bool:
#     return isinstance(x, (int, float)) and math.isfinite(x)


# class RangeStrategy:
#     """
#     Логика входа во флэт:
#       - Диапазон берём из RangeRegistry (support/resistance/mid/width).
#       - Вход только в зоне у границ (entry_zone_frac).
#       - Подтверждение по 5m свечам: touch/sweep + rejection (закрылись обратно в диапазон).
#       - TP: mid/opposite/frac
#       - SL: за границу + buffer и/или ATR
#     """

#     def __init__(
#         self,
#         fetch_klines: Callable[..., Any],
#         registry: RangeRegistry,
#         *,
#         confirm_tf: str = "5",
#         confirm_limit: int = 30,
#         entry_zone_frac: float = 0.08,
#         sweep_frac: float = 0.02,
#         tp_mode: str = "mid",     # "mid" | "opposite" | "frac"
#         tp_frac: float = 0.45,    # используется при tp_mode="frac"
#         sl_buffer_frac: float = 0.03,
#         sl_atr_mult: float = 0.8,
#         allow_long: bool = True,
#         allow_short: bool = True,
#         confirm_cache_ttl_sec: int = 8,
#     ) -> None:
#         self.fetch_klines = fetch_klines
#         self.registry = registry

#         self.confirm_tf = str(confirm_tf)
#         self.confirm_limit = int(confirm_limit)

#         self.entry_zone_frac = float(entry_zone_frac)
#         self.sweep_frac = float(sweep_frac)

#         self.tp_mode = str(tp_mode).strip().lower()
#         self.tp_frac = float(tp_frac)

#         self.sl_buffer_frac = float(sl_buffer_frac)
#         self.sl_atr_mult = float(sl_atr_mult)

#         self.allow_long = bool(allow_long)
#         self.allow_short = bool(allow_short)

#         self.confirm_cache_ttl_sec = int(confirm_cache_ttl_sec)
#         self._confirm_cache: Dict[Tuple[str, str, int], Tuple[float, List[Candle]]] = {}

#     async def _get_confirm_candles(self, symbol: str) -> List[Candle]:
#         key = (symbol, self.confirm_tf, self.confirm_limit)
#         now = time.time()
#         hit = self._confirm_cache.get(key)
#         if hit and (now - hit[0] <= self.confirm_cache_ttl_sec):
#             return hit[1]

#         raw = await maybe_await(self.fetch_klines(symbol, self.confirm_tf, self.confirm_limit))
#         candles = normalize_klines(raw)
#         self._confirm_cache[key] = (now, candles)
#         return candles

#     def _in_support_zone(self, info: RangeInfo, price: float) -> bool:
#         # зона у support: [support, support*(1+entry_zone_frac)]
#         return price <= info.support * (1.0 + self.entry_zone_frac)

#     def _in_resistance_zone(self, info: RangeInfo, price: float) -> bool:
#         # зона у resistance: [resistance*(1-entry_zone_frac), resistance]
#         return price >= info.resistance * (1.0 - self.entry_zone_frac)

#     def _confirm_long(self, info: RangeInfo, last: Candle) -> bool:
#         # touch/sweep support + close обратно выше support
#         support = info.support
#         sweep_level = support * (1.0 - self.sweep_frac)

#         touched_or_swept = (last.l <= support) or (last.l <= sweep_level)
#         closed_back_in = last.c > support

#         # rejection: нижняя тень заметная или зелёная свеча
#         rng = max(1e-12, last.h - last.l)
#         lower_wick = min(last.o, last.c) - last.l
#         lower_wick_frac = lower_wick / rng
#         green = last.c >= last.o

#         return bool(touched_or_swept and closed_back_in and (green or lower_wick_frac >= 0.35))

#     def _confirm_short(self, info: RangeInfo, last: Candle) -> bool:
#         resistance = info.resistance
#         sweep_level = resistance * (1.0 + self.sweep_frac)

#         touched_or_swept = (last.h >= resistance) or (last.h >= sweep_level)
#         closed_back_in = last.c < resistance

#         rng = max(1e-12, last.h - last.l)
#         upper_wick = last.h - max(last.o, last.c)
#         upper_wick_frac = upper_wick / rng
#         red = last.c <= last.o

#         return bool(touched_or_swept and closed_back_in and (red or upper_wick_frac >= 0.35))

#     def _calc_tp(self, info: RangeInfo, side: str) -> float:
#         m = self.tp_mode
#         if m == "mid":
#             return float(info.mid)
#         if m == "opposite":
#             return float(info.resistance if side == "Buy" else info.support)
#         if m == "frac":
#             # frac от ширины диапазона
#             if side == "Buy":
#                 return float(info.support + info.width * self.tp_frac)
#             else:
#                 return float(info.resistance - info.width * self.tp_frac)
#         # default
#         return float(info.mid)

#     def _calc_sl(self, info: RangeInfo, side: str, atr5: float) -> float:
#         if side == "Buy":
#             sl_buf = info.support * (1.0 - self.sl_buffer_frac)
#             if _is_finite(atr5) and atr5 > 0:
#                 return float(min(sl_buf, info.support - atr5 * self.sl_atr_mult))
#             return float(sl_buf)
#         else:
#             sl_buf = info.resistance * (1.0 + self.sl_buffer_frac)
#             if _is_finite(atr5) and atr5 > 0:
#                 return float(max(sl_buf, info.resistance + atr5 * self.sl_atr_mult))
#             return float(sl_buf)

#     async def maybe_signal(self, symbol: str, price: float) -> Optional[RangeSignal]:
#         info = self.registry.get(symbol)
#         if not info:
#             return None
#         if not self.registry.is_allowed(symbol):
#             return None

#         if not _is_finite(price) or price <= 0:
#             return None

#         # определяем сторону по зоне
#         want_long = self.allow_long and self._in_support_zone(info, price)
#         want_short = self.allow_short and self._in_resistance_zone(info, price)

#         if not (want_long or want_short):
#             return None

#         candles5 = await self._get_confirm_candles(symbol)
#         if len(candles5) < 3:
#             return None
#         last = candles5[-1]

#         atr5 = atr(candles5, 14)
#         if not _is_finite(atr5):
#             atr5 = 0.0

#         if want_long and self._confirm_long(info, last):
#             tp = self._calc_tp(info, "Buy")
#             sl = self._calc_sl(info, "Buy", atr5)
#             reason = f"range-long: support={info.support:.6f} mid={info.mid:.6f}"
#             return RangeSignal(side="Buy", tp=float(tp), sl=float(sl), reason=reason)

#         if want_short and self._confirm_short(info, last):
#             tp = self._calc_tp(info, "Sell")
#             sl = self._calc_sl(info, "Sell", atr5)
#             reason = f"range-short: resistance={info.resistance:.6f} mid={info.mid:.6f}"
#             return RangeSignal(side="Sell", tp=float(tp), sl=float(sl), reason=reason)

#         return None
# sr_range_strategy.py
from __future__ import annotations

import time
import math
from dataclasses import dataclass
from typing import Any, Callable, Optional, Dict, Tuple, List

from sr_range import RangeRegistry, RangeInfo, Candle, normalize_klines, maybe_await, atr


@dataclass
class RangeSignal:
    side: str          # "Buy" | "Sell"
    tp: float
    sl: float
    reason: str


def _is_finite(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


class RangeStrategy:
    """
    Range Bounce стратегия (понятная/детерминированная):

    1) Требуем, чтобы RangeRegistry дал RangeInfo(support, resistance, mid, width).
    2) Вход только в зоне у границы: от width.
    3) Подтверждение по последней закрытой 5m свече:
       - sweep/touch границы
       - reclaim (закрылись обратно в диапазон на небольшую величину)
       - rejection (wick или цвет свечи)
    4) SL: за границей на max(width*sl_width_frac, ATR5*sl_atr_mult)
    5) TP: mid или opposite
    6) Фильтр качества: RR >= min_rr
    """

    def __init__(
        self,
        fetch_klines: Callable[..., Any],
        registry: RangeRegistry,
        *,
        confirm_tf: str = "5",
        confirm_limit: int = 30,         # важно: >= atr_period+2
        atr_period: int = 14,

        entry_zone_frac: float = 0.10,   # зона входа: 10% ширины диапазона от границы
        sweep_frac: float = 0.02,        # “прокол” границы: 2% width
        reclaim_frac: float = 0.01,      # “вернулись в диапазон”: 1% width

        wick_frac_min: float = 0.35,     # минимальная доля тени для rejection
        require_prev_sweep: bool = True, # вход только после "ложного пробоя" на предыдущей свече
        impulse_body_atr_max: float = 0.9,  # запрет входа по импульсной свече (body > ATR*mult)
        adaptive_regime: bool = False,   # адаптировать пороги по волатильности
        regime_low_atr_pct: float = 0.35,
        regime_high_atr_pct: float = 0.90,
        impulse_body_atr_max_low: float = 0.60,
        impulse_body_atr_max_high: float = 1.10,
        min_rr_low: float = 2.2,
        min_rr_high: float = 1.5,
        tp_mode: str = "mid",            # "mid" | "opposite"
        min_rr: float = 1.0,             # минимум RR, иначе пропускаем

        sl_width_frac: float = 0.10,     # SL distance = max(width*10%, ATR*mult)
        sl_atr_mult: float = 1.0,
        sl_buffer_frac: float = 0.0,    # compat: optional extra buffer (unused)

        allow_long: bool = True,
        allow_short: bool = True,

        confirm_cache_ttl_sec: int = 0,  # для бэктеста держи 0
    ) -> None:
        self.fetch_klines = fetch_klines
        self.registry = registry

        self.confirm_tf = str(confirm_tf)
        self.confirm_limit = int(confirm_limit)
        self.atr_period = int(atr_period)

        self.entry_zone_frac = float(entry_zone_frac)
        self.sweep_frac = float(sweep_frac)
        self.reclaim_frac = float(reclaim_frac)

        self.wick_frac_min = float(wick_frac_min)
        self.require_prev_sweep = bool(require_prev_sweep)
        self.impulse_body_atr_max = float(impulse_body_atr_max)
        self.adaptive_regime = bool(adaptive_regime)
        self.regime_low_atr_pct = float(regime_low_atr_pct)
        self.regime_high_atr_pct = float(regime_high_atr_pct)
        self.impulse_body_atr_max_low = float(impulse_body_atr_max_low)
        self.impulse_body_atr_max_high = float(impulse_body_atr_max_high)
        self.min_rr_low = float(min_rr_low)
        self.min_rr_high = float(min_rr_high)
        self.tp_mode = str(tp_mode).strip().lower()
        self.min_rr = float(min_rr)

        self.sl_width_frac = float(sl_width_frac)
        self.sl_atr_mult = float(sl_atr_mult)
        self.sl_buffer_frac = float(sl_buffer_frac)

        self.allow_long = bool(allow_long)
        self.allow_short = bool(allow_short)

        self.confirm_cache_ttl_sec = int(confirm_cache_ttl_sec)
        self._confirm_cache: Dict[Tuple[str, str, int], Tuple[float, List[Candle]]] = {}

    async def _get_confirm_candles(self, symbol: str) -> List[Candle]:
        key = (symbol, self.confirm_tf, self.confirm_limit)
        now = time.time()

        hit = self._confirm_cache.get(key)
        if hit and self.confirm_cache_ttl_sec > 0 and (now - hit[0] <= self.confirm_cache_ttl_sec):
            return hit[1]

        raw = await maybe_await(self.fetch_klines(symbol, self.confirm_tf, self.confirm_limit))
        candles = normalize_klines(raw)
        candles.sort(key=lambda c: c.ts)

        self._confirm_cache[key] = (now, candles)
        return candles

    # ---------- geometry helpers ----------

    def _in_support_zone(self, info: RangeInfo, price: float) -> bool:
        w = max(1e-12, float(info.width))
        return price <= float(info.support) + w * self.entry_zone_frac

    def _in_resistance_zone(self, info: RangeInfo, price: float) -> bool:
        w = max(1e-12, float(info.width))
        return price >= float(info.resistance) - w * self.entry_zone_frac

    def _wick_stats(self, c: Candle) -> Tuple[float, float, float]:
        rng = max(1e-12, c.h - c.l)
        lower_wick = min(c.o, c.c) - c.l
        upper_wick = c.h - max(c.o, c.c)
        return (lower_wick / rng, upper_wick / rng, rng)

    def _impulse_body_ok(self, c: Candle, atr5: float, impulse_mult: float) -> bool:
        if not (_is_finite(atr5) and atr5 > 0 and _is_finite(impulse_mult) and impulse_mult > 0):
            return True
        body = abs(c.c - c.o)
        return body <= atr5 * impulse_mult

    def _confirm_long(self, info: RangeInfo, prev: Candle, last: Candle, atr5: float, impulse_mult: float) -> bool:
        support = float(info.support)
        w = max(1e-12, float(info.width))

        sweep_level = support - w * self.sweep_frac
        reclaim_level = support + w * self.reclaim_frac

        touched_or_swept = (last.l <= support) or (last.l <= sweep_level)
        prev_swept = (prev.l <= support) or (prev.l <= sweep_level)
        reclaimed = last.c >= reclaim_level

        lower_wick_frac, _, _ = self._wick_stats(last)
        green = last.c >= last.o
        body_ok = self._impulse_body_ok(last, atr5, impulse_mult)
        sweep_ok = prev_swept if self.require_prev_sweep else touched_or_swept

        return bool(sweep_ok and reclaimed and (green or lower_wick_frac >= self.wick_frac_min) and body_ok)

    def _confirm_short(self, info: RangeInfo, prev: Candle, last: Candle, atr5: float, impulse_mult: float) -> bool:
        resistance = float(info.resistance)
        w = max(1e-12, float(info.width))

        sweep_level = resistance + w * self.sweep_frac
        reclaim_level = resistance - w * self.reclaim_frac

        touched_or_swept = (last.h >= resistance) or (last.h >= sweep_level)
        prev_swept = (prev.h >= resistance) or (prev.h >= sweep_level)
        reclaimed = last.c <= reclaim_level

        _, upper_wick_frac, _ = self._wick_stats(last)
        red = last.c <= last.o
        body_ok = self._impulse_body_ok(last, atr5, impulse_mult)
        sweep_ok = prev_swept if self.require_prev_sweep else touched_or_swept

        return bool(sweep_ok and reclaimed and (red or upper_wick_frac >= self.wick_frac_min) and body_ok)

    def _adaptive_params(self, price: float, atr5: float) -> tuple[float, float]:
        """Return (min_rr, impulse_body_atr_mult) for current volatility regime."""
        if not self.adaptive_regime:
            return self.min_rr, self.impulse_body_atr_max
        if not (_is_finite(price) and price > 0 and _is_finite(atr5) and atr5 > 0):
            return self.min_rr, self.impulse_body_atr_max
        atr_pct = (atr5 / price) * 100.0
        if atr_pct <= self.regime_low_atr_pct:
            return self.min_rr_low, self.impulse_body_atr_max_low
        if atr_pct >= self.regime_high_atr_pct:
            return self.min_rr_high, self.impulse_body_atr_max_high
        # linear interpolation in mid regime
        t = (atr_pct - self.regime_low_atr_pct) / max(1e-9, (self.regime_high_atr_pct - self.regime_low_atr_pct))
        min_rr = self.min_rr_low + t * (self.min_rr_high - self.min_rr_low)
        imp = self.impulse_body_atr_max_low + t * (self.impulse_body_atr_max_high - self.impulse_body_atr_max_low)
        return float(min_rr), float(imp)

    def _calc_sl(self, info: RangeInfo, side: str, atr5: float) -> float:
        w = max(1e-12, float(info.width))
        dist_w = w * self.sl_width_frac
        dist_atr = (float(atr5) * self.sl_atr_mult) if _is_finite(atr5) else 0.0
        dist = max(dist_w, dist_atr, 1e-12)

        if side == "Buy":
            return float(info.support) - dist
        else:
            return float(info.resistance) + dist

    def _calc_tp(self, info: RangeInfo, side: str) -> float:
        if self.tp_mode == "opposite":
            return float(info.resistance if side == "Buy" else info.support)
        # default mid
        return float(info.mid)

    def _rr(self, entry: float, sl: float, tp: float) -> float:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk <= 0:
            return 0.0
        return reward / risk

    async def maybe_signal(self, symbol: str, price: float) -> Optional[RangeSignal]:
        info = self.registry.get(symbol)
        if not info:
            return None
        if not self.registry.is_allowed(symbol):
            return None

        if not _is_finite(price) or price <= 0:
            return None

        w = float(info.width)
        if not _is_finite(w) or w <= 0:
            return None

        want_long = self.allow_long and self._in_support_zone(info, price)
        want_short = self.allow_short and self._in_resistance_zone(info, price)
        if not (want_long or want_short):
            return None

        candles5 = await self._get_confirm_candles(symbol)
        # надо минимум atr_period+2 свечи, иначе ATR нестабилен
        if len(candles5) < max(5, self.atr_period + 2):
            return None
        prev = candles5[-2]
        last = candles5[-1]

        atr5 = atr(candles5, self.atr_period)
        if not _is_finite(atr5):
            atr5 = 0.0
        min_rr_curr, impulse_mult_curr = self._adaptive_params(price, atr5)

        # LONG
        if want_long and self._confirm_long(info, prev, last, atr5, impulse_mult_curr):
            sl = self._calc_sl(info, "Buy", atr5)
            tp = self._calc_tp(info, "Buy")
            rr = self._rr(price, sl, tp)
            if rr < min_rr_curr:
                return None
            reason = (
                f"range-long: sup={float(info.support):.6f} mid={float(info.mid):.6f} "
                f"w={float(info.width):.6f} atr5={atr5:.6f} rr={rr:.2f} min_rr={min_rr_curr:.2f}"
            )
            return RangeSignal(side="Buy", tp=float(tp), sl=float(sl), reason=reason)

        # SHORT
        if want_short and self._confirm_short(info, prev, last, atr5, impulse_mult_curr):
            sl = self._calc_sl(info, "Sell", atr5)
            tp = self._calc_tp(info, "Sell")
            rr = self._rr(price, sl, tp)
            if rr < min_rr_curr:
                return None
            reason = (
                f"range-short: res={float(info.resistance):.6f} mid={float(info.mid):.6f} "
                f"w={float(info.width):.6f} atr5={atr5:.6f} rr={rr:.2f} min_rr={min_rr_curr:.2f}"
            )
            return RangeSignal(side="Sell", tp=float(tp), sl=float(sl), reason=reason)

        return None
