"""ЭТАЛОННАЯ РЕАЛИЗАЦИЯ XSEC V3 — переносить В ПРОД ИМЕННО ЭТО.

    ВНИМАНИЕ ИНТЕГРАТОРУ
    V2 (только моментум) УСТАРЕЛА. Актуальная версия - V3 с фактором волатильности.
    Отличие ровно одно: score = ранг_моментума + ранг_волатильности, а не только ранг моментума.
    V2: Sharpe 1.59, слабая фаза 7.2%
    V3: Sharpe 2.19, слабых фаз нет (40.5/31.3/35.7)
    Не портируй xsec_v2_run.py. Портируй ЭТОТ файл.

Пре-регистрации: prereg/XSEC_MATURE_V2_STAGGERED_2026_07_22.json + prereg/XSEC_VOLFACTOR_2026_07_22.json
Валидатор: 9 PASS / 2 WARN / 0 FAIL.

Модуль чистый: без сети, без брокера, без глобального состояния. Только математика решения.
Интегратор подаёт цены, получает целевые позиции.
"""
from __future__ import annotations
import math
from typing import Dict, List, Sequence

LOOKBACKS: List[int] = [7, 14, 21, 30, 45]
REBALANCE_DAYS: int = 3
K: int = 5
PHASES: int = 3                 # = REBALANCE_DAYS, иного значения быть не может
TARGET_ANNUAL_VOL: float = 0.15
LEVERAGE_CAP: float = 1.0
VOL_WINDOW_REBALANCES: int = 20
MIN_UNIVERSE: int = 2 * K + 4   # = 14, иначе ребаланс ПРОПУСКАЕТСЯ
MATURITY_DAYS: int = 390        # считать по launchTime БИРЖИ, не по длине локальной истории


def _stdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2: return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def daily_volatility(closes: Sequence[float]) -> float | None:
    """Волатильность дневных доходностей. closes - завершённые дневные закрытия, старые -> новые."""
    if len(closes) < 5: return None
    rets = [closes[i] / closes[i-1] - 1.0 for i in range(1, len(closes)) if closes[i-1] > 0]
    if len(rets) < 4: return None
    sd = _stdev(rets)
    return sd if sd > 0 else None


def target_weights(history: Dict[str, List[float]]) -> Dict[str, float]:
    """ГЛАВНАЯ ФУНКЦИЯ. Целевые веса для ОДНОГО подпортфеля на ОДИН ребаланс.

    history: {symbol: [дневные закрытия, старые -> новые]}. Нужно >= max(LOOKBACKS)+1 значений.
             Подавать ТОЛЬКО завершённые дневные свечи UTC (иначе заглядывание вперёд).
             Символы должны быть предварительно отфильтрованы по зрелости (launchTime).

    Возврат: {symbol: вес}. Пустой словарь = ребаланс ПРОПУСКАЕТСЯ.

    !!! ЛОВУШКА ДЛЯ ИНТЕГРАТОРА - ПРОЧТИ ДО ТОГО, КАК "ЧИНИТЬ" !!!
    Сумма длинных весов будет МЕНЬШЕ +1.0 по модулю (в замере: +0.92 / -0.92).
    Это НЕ ошибка. Монета может попасть в лонг по одному lookback и в шорт по другому -
    позиции взаимозачитываются, и валовая экспозиция честно уменьшается.
    Бэктест, давший Sharpe 2.19, считался ИМЕННО ТАК.
    НЕ нормируй веса обратно к +-1.0: это увеличит экспозицию и сломает совпадение
    с бэктестом. Подавай веса как есть, умножая только на leverage().
    """
    need = max(LOOKBACKS) + 1
    usable = {s: c for s, c in history.items() if len(c) >= need and c[-1] > 0}
    if len(usable) < MIN_UNIVERSE:
        return {}

    acc: Dict[str, float] = {s: 0.0 for s in usable}
    used = 0
    for L in LOOKBACKS:
        cand = []
        for s, c in usable.items():
            if c[-1-L] <= 0: continue
            mom = c[-1] / c[-1-L] - 1.0
            vol = daily_volatility(c[-1-L:])       # окно волатильности = окну моментума
            if vol is None: continue
            cand.append((s, mom, vol))
        if len(cand) < MIN_UNIVERSE:
            continue
        # ранги: 0 = минимум. Высокий моментум и ВЫСОКАЯ волатильность = высокий ранг.
        by_mom = sorted(range(len(cand)), key=lambda i: cand[i][1])
        by_vol = sorted(range(len(cand)), key=lambda i: cand[i][2])
        rank: Dict[str, int] = {}
        for r, i in enumerate(by_mom): rank[cand[i][0]] = r
        for r, i in enumerate(by_vol): rank[cand[i][0]] += r
        order = sorted(rank.items(), key=lambda kv: kv[1], reverse=True)
        for s, _ in order[:K]:  acc[s] += 1.0 / K
        for s, _ in order[-K:]: acc[s] -= 1.0 / K
        used += 1
    if used == 0:
        return {}
    return {s: w / used for s, w in acc.items() if abs(w) > 1e-12}


def leverage(past_rebalance_returns: Sequence[float]) -> float:
    """Таргетирование волатильности. Подаётся история доходностей ЭТОГО подпортфеля."""
    hist = list(past_rebalance_returns)[-VOL_WINDOW_REBALANCES:]
    if len(hist) < 8:
        return 0.5                                   # прогрев
    sd = _stdev(hist)
    if sd <= 0:
        return LEVERAGE_CAP
    annual = sd * math.sqrt(365.0 / REBALANCE_DAYS)
    return min(LEVERAGE_CAP, TARGET_ANNUAL_VOL / annual)


def phase_of(day_index: int) -> int:
    """Какой подпортфель ребалансится сегодня. day_index - номер дня от старта shadow."""
    return day_index % PHASES


# --- Ожидания и границы, зафиксированные исследованием -------------------------
EXPECTED = {
    "total_pct_13_months": 37.0, "max_drawdown_pct": 9.2, "sharpe": 2.19,
    "halves_pct": [13.0, 21.2], "phases_pct": [40.5, 31.3, 35.7],
    "symbol_holdout_pct": [31.0, 30.6], "positive_months": "8 of 12",
    "backtest_costs_bps": {"entry": 2.0, "exit": 5.5},
}
LIMITS = {
    "capacity_usd": "1000-2000; медианный оборот универсума ~$410k/день",
    "slippage_NOT_modelled": "бэктест содержит комиссию, но НЕ проскальзывание — это главный риск",
    "stop_rule": "медианное проскальзывание > 10 bps => экономика неверна, вернуть на пересчёт",
    "survivorship": "универсум без делистингов; доходность — верхняя оценка",
}


# =============================================================================
# V4 — ДВА СОБЫТИЙНЫХ ФИЛЬТРА поверх V3.  Pre-reg: prereg/XSEC_EVENTFILTER_2026_07_22.json
# V4: Sharpe 2.73, DD 6.8%, итог 49.1%.  Валидатор 9 PASS / 2 WARN / 0 FAIL.
# Оба фильтра ОБЯЗАТЕЛЬНЫ — они улучшают результат и по отдельности, и вместе.
# =============================================================================

POST_EVENT_SIGMA: float = 3.0        # F1: порог «шума после события»
STRESS_PERCENTILE: float = 0.90      # F2: порог рыночного стресса
STRESS_LOOKBACK_DAYS: int = 60


def is_post_event_noise(closes: Sequence[float], lookback: int) -> bool:
    """F1: движение за ПОСЛЕДНИЙ день больше 3 сигм собственной волатильности.
    Такую монету исключаем из ранжирования — её ранг ненадёжен."""
    if len(closes) < lookback + 2: return False
    v = daily_volatility(closes[-lookback:])
    if v is None or v <= 0: return False
    if closes[-2] <= 0: return False
    return abs(closes[-1] / closes[-2] - 1.0) > POST_EVENT_SIGMA * v


def is_market_stress(universe_daily_abs_returns_history: Sequence[float],
                     today_median_abs_return: float) -> bool:
    """F2: медиана |дневной доходности| по универсуму выше своего 90-го процентиля за 60 дней.
    В такие дни ребаланс ПРОПУСКАЕТСЯ ЦЕЛИКОМ (позиции держатся, новых сделок нет)."""
    h = sorted(universe_daily_abs_returns_history[-STRESS_LOOKBACK_DAYS:])
    if len(h) < 30: return False
    return today_median_abs_return > h[int(len(h) * STRESS_PERCENTILE)]


EXPECTED_V4 = {
    "total_pct_13_months": 49.1, "max_drawdown_pct": 6.8, "sharpe": 2.73,
    "halves_pct": [19.7, 24.5], "phases_pct": [58.3, 40.0, 45.8],
    "symbol_holdout_pct": [31.5, 39.0], "loso_pct": 28.4,
    "without_best_month_pct": 32.1, "positive_months": "8 of 12",
}
