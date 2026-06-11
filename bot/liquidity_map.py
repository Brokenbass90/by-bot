"""Liquidity map + sweep-reversal — охотник за ликвидностью без стакана (Claude 2026-06-11).

Идея: стопы толпы скапливаются за «равными» экстремумами (equal highs/lows)
и свинг-точками. Эти кластеры = пулы ликвидности. Крупный игрок «снимает» пул
(прокол фитилём) и разворачивает цену. Мы НЕ предсказываем — входим ПОСЛЕ
снятия, когда возврат подтверждён закрытием.

Всё из OHLC: пулы из пивотов, снятие из фитилей. L2/ликвидационный фид позже
усилят (фильтр «снятие совпало с каскадом ликвидаций»), но базовая геометрия
работает на свечах.

API:
    pools = LiquidityMap(cfg).build(highs, lows)          # карта пулов
    sig   = LiquiditySweepReversalV1().signal(h, l, c)    # сигнал для харнесса
Сигнал совместим с scripts/backtest_candidates.py (как RMR1/TPB1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class LiqMapConfig:
    pivot_left: int = 3
    pivot_right: int = 3
    cluster_tol_pct: float = 0.25   # пивоты в пределах этого % = один пул
    min_touches: int = 2            # пул = минимум 2 касания (equal highs/lows)
    max_age_bars: int = 400         # пул протухает, если касаний давно не было
    atr_period: int = 14


@dataclass
class Pool:
    side: str                # "above" (buy-side liq, стопы шортов) | "below"
    price: float             # уровень пула (среднее касаний)
    touches: int
    last_touch_i: int
    strength: float          # touches с поправкой на свежесть

    def contains(self, px: float, tol: float) -> bool:
        return abs(px - self.price) <= tol


@dataclass
class SweepEvent:
    pool: Pool
    bar_i: int
    extreme: float           # экстремум фитиля, снявшего пул
    side: str                # "long" (снят нижний пул) | "short" (снят верхний)


def _ema_last(vals: Sequence[float], n: int) -> float:
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    for x in vals[n:]:
        e = x * k + e * (1 - k)
    return e


def _atr(h: Sequence[float], l: Sequence[float], c: Sequence[float], p: int) -> float:
    n = len(c)
    if n < p + 1:
        return float("nan")
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
           for i in range(n - p, n)]
    return sum(trs) / len(trs)


def find_pivots(highs: Sequence[float], lows: Sequence[float],
                left: int, right: int):
    """Фрактальные свинг-точки: бар выше/ниже left соседей слева и right справа."""
    ph: List[tuple] = []
    pl: List[tuple] = []
    n = len(highs)
    for i in range(left, n - right):
        win_h = highs[i - left:i + right + 1]
        win_l = lows[i - left:i + right + 1]
        if highs[i] == max(win_h) and list(win_h).count(highs[i]) == 1:
            ph.append((i, highs[i]))
        if lows[i] == min(win_l) and list(win_l).count(lows[i]) == 1:
            pl.append((i, lows[i]))
    return ph, pl


def _cluster(pivots: List[tuple], tol_pct: float, min_touches: int,
             max_age_bars: int, now_i: int, side: str) -> List[Pool]:
    pools: List[Pool] = []
    used = [False] * len(pivots)
    for i, (bi, price) in enumerate(pivots):
        if used[i]:
            continue
        members = [(bi, price)]
        used[i] = True
        tol = price * tol_pct / 100.0
        for j in range(i + 1, len(pivots)):
            if used[j]:
                continue
            bj, pj = pivots[j]
            if abs(pj - price) <= tol:
                members.append((bj, pj))
                used[j] = True
        last_i = max(m[0] for m in members)
        if len(members) < min_touches:
            continue
        if now_i - last_i > max_age_bars:
            continue
        avg = sum(m[1] for m in members) / len(members)
        recency = max(0.25, 1.0 - (now_i - last_i) / max_age_bars)
        pools.append(Pool(side=side, price=avg, touches=len(members),
                          last_touch_i=last_i,
                          strength=round(len(members) * recency, 3)))
    pools.sort(key=lambda p: -p.strength)
    return pools


class LiquidityMap:
    def __init__(self, cfg: Optional[LiqMapConfig] = None):
        self.cfg = cfg or LiqMapConfig()

    def build(self, highs: Sequence[float], lows: Sequence[float]) -> Dict[str, List[Pool]]:
        c = self.cfg
        now_i = len(highs) - 1
        ph, pl = find_pivots(highs, lows, c.pivot_left, c.pivot_right)
        return {
            "above": _cluster(ph, c.cluster_tol_pct, c.min_touches, c.max_age_bars, now_i, "above"),
            "below": _cluster(pl, c.cluster_tol_pct, c.min_touches, c.max_age_bars, now_i, "below"),
        }


@dataclass
class LSRConfig:
    map: LiqMapConfig = field(default_factory=LiqMapConfig)
    atr_period: int = 14
    max_overshoot_atr: float = 1.5   # фитиль за пул не дальше этого (иначе это пробой, не снятие)
    sl_atr_mult: float = 1.0         # стоп за экстремум фитиля
    overshoot_min_atr: float = 0.2   # фитиль должен реально проколоть пул (не шум)
    min_pool_touches: int = 3        # только сильные пулы (толстая ликвидность)
    tp_rr: float = 2.0
    min_rr: float = 1.5
    max_pool_dist_atr: float = 3.0   # пул не дальше этого от цены (иначе не наш сетап)
    htf_factor: int = 4              # пулы строим на старшем ТФ (4×базовый, напр. 1h→4h).
                                     # 1 = пулы на базовом ТФ (шумно; PF~0.9 в матрице).
                                     # 4 = НАСТОЯЩИЕ кластеры стопов: 3/4 монет в плюсе.
    # Тренд-фильтр (данные 2026-06-11, разрез по тегам): контр-трендовые снятия
    # PF 1.60 (+34%), флэт PF 0.80, по-тренду PF 0.57. Терминальный вынос против
    # затяжного движения — вот где разворот. По умолчанию торгуем ТОЛЬКО их.
    trend_filter: str = "counter_only"  # "counter_only" | "off"
    trend_ema: int = 200             # EMA на базовом ТФ (1h EMA200 ≈ 4h EMA50)
    trend_slope_bars: int = 12       # наклон EMA за столько баров
    trend_slope_min: float = 0.001   # |наклон|/цена ниже порога = флэт (не торгуем)


class LiquiditySweepReversalV1:
    """Sweep-reversal: бар проколол пул фитилём и ЗАКРЫЛСЯ обратно — входим в реверс.

    long: лоу бара < нижний пул, close > пул (снятие sell-side ликвидности);
    short: хай бара > верхний пул, close < пул. SL за экстремум фитиля.
    """
    NAME = "liquidity_sweep_map_v1"

    def __init__(self, cfg: Optional[LSRConfig] = None):
        self.cfg = cfg or LSRConfig()
        self.lmap = LiquidityMap(self.cfg.map)
        self.last_reason = ""

    def signal(self, highs: Sequence[float], lows: Sequence[float],
               closes: Sequence[float]) -> Optional[Dict]:
        cfg = self.cfg
        need = cfg.map.pivot_left + cfg.map.pivot_right + cfg.atr_period + 20
        if len(closes) < need:
            self.last_reason = "history_short"
            return None
        atr = _atr(highs, lows, closes, cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_reason = "atr_nan"
            return None
        price = closes[-1]
        bar_h, bar_l = highs[-1], lows[-1]
        # пулы строим БЕЗ текущего бара (он — кандидат на снятие, не на касание).
        # htf_factor>1: агрегируем в старший ТФ — пулы из закрытых HTF-баров.
        f = max(1, int(cfg.htf_factor))
        if f > 1:
            n = len(highs)
            m = (n - 1) // f * f
            hh = [max(highs[i:i + f]) for i in range(0, m, f)]
            ll = [min(lows[i:i + f]) for i in range(0, m, f)]
            pools = self.lmap.build(hh, ll)
        else:
            pools = self.lmap.build(highs[:-1], lows[:-1])

        # long: снят ближайший нижний пул
        for p in pools["below"]:
            if p.touches < cfg.min_pool_touches:
                continue
            if p.price - price > 0:            # пул выше цены — не наш
                continue
            if price - p.price > cfg.max_pool_dist_atr * atr:
                continue
            swept = bar_l < p.price and price > p.price
            if not swept:
                continue
            overshoot = p.price - bar_l
            if overshoot > cfg.max_overshoot_atr * atr:
                self.last_reason = "overshoot_too_deep"   # это пробой, не снятие
                continue
            if overshoot < cfg.overshoot_min_atr * atr:
                self.last_reason = "overshoot_too_shallow"  # чирк, не снятие
                continue
            sl = bar_l - cfg.sl_atr_mult * atr
            risk = price - sl
            tp = price + cfg.tp_rr * risk
            rr = (tp - price) / risk if risk > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            if not self._trend_ok("long", closes):
                self.last_reason = "trend_filter_long"
                continue
            self.last_reason = f"long_sweep_pool@{p.price:.4g}_t{p.touches}"
            return {"side": "long", "entry": price, "sl": sl, "tp": tp,
                    "rr": round(rr, 2), "reason": self.last_reason}

        # short: снят ближайший верхний пул
        for p in pools["above"]:
            if p.touches < cfg.min_pool_touches:
                continue
            if price - p.price > 0:
                continue
            if p.price - price > cfg.max_pool_dist_atr * atr:
                continue
            swept = bar_h > p.price and price < p.price
            if not swept:
                continue
            overshoot = bar_h - p.price
            if overshoot > cfg.max_overshoot_atr * atr:
                self.last_reason = "overshoot_too_deep"
                continue
            if overshoot < cfg.overshoot_min_atr * atr:
                self.last_reason = "overshoot_too_shallow"
                continue
            sl = bar_h + cfg.sl_atr_mult * atr
            risk = sl - price
            tp = price - cfg.tp_rr * risk
            rr = (price - tp) / risk if risk > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            if not self._trend_ok("short", closes):
                self.last_reason = "trend_filter_short"
                continue
            self.last_reason = f"short_sweep_pool@{p.price:.4g}_t{p.touches}"
            return {"side": "short", "entry": price, "sl": sl, "tp": tp,
                    "rr": round(rr, 2), "reason": self.last_reason}

        self.last_reason = "no_sweep"
        return None

    def _trend_ok(self, side: str, closes: Sequence[float]) -> bool:
        """counter_only: лонг только против даунтренда, шорт — против аптренда.
        Недостаточно истории для EMA → пропускаем без фильтра (не наказываем)."""
        cfg = self.cfg
        if cfg.trend_filter != "counter_only":
            return True
        need = cfg.trend_ema + cfg.trend_slope_bars
        if len(closes) < need:
            return True
        e_now = _ema_last(list(closes), cfg.trend_ema)
        e_prev = _ema_last(list(closes[:-cfg.trend_slope_bars]), cfg.trend_ema)
        slope = (e_now - e_prev) / closes[-1]
        if side == "long":
            return slope < -cfg.trend_slope_min
        return slope > cfg.trend_slope_min
