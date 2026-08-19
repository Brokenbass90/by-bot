"""КАЛИБРОВКА СТОРОЖЕЙ — прогнать заведомо здоровую ногу и посмотреть,
как часто защита её убивает.

ЗАЧЕМ. За час этим методом найдены три ошибки калибровки подряд:

  edge_monitor      глушит прибыльную ногу в 98% случаев при n=200
                    (порог просадки — константа, а просадка растёт как sqrt(n))
  oos_selector      отклоняет 50% хороших кандидатов при 6 фолдах по 10 сделок
                    (требование «75% плюсовых фолдов» не зависит от их числа)
  strategy_breaker  пороги в долларах, не в R — сломается при смене сайзинга

Природа у всех одна: **порог задан константой там, где величина зависит
от числа сделок или от размера позиции.** Поэтому проверять надо не каждый
сторож руками, а любой — этим харнессом.

ГЛАВНАЯ МЫСЛЬ. Сторож, который душит здоровых, опаснее отсутствия сторожа:
он выглядит как забота и не вызывает подозрений. Единственный способ его
поймать — подать ему заведомо здоровый вход.

ИСПОЛЬЗОВАНИЕ.

    from research_lab.guard_calibration import calibrate, healthy_leg

    def guard(rs):                      # вернуть True, если «убил»
        return assess_sleeve(rs, baseline_expectancy_R=0.35).status == "halt"

    print(calibrate(guard, label="edge_monitor halt"))
"""
from __future__ import annotations

import random
import statistics
from typing import Callable, Sequence

DEFAULT_SIZES = (20, 30, 50, 100, 200, 500)


def healthy_leg(n: int, *, win_rate: float = 0.45, win_r: float = 2.0,
                loss_r: float = 1.0, rnd: random.Random | None = None) -> list[float]:
    """Заведомо ПРИБЫЛЬНАЯ последовательность R-мультипликаторов.

    По умолчанию: винрейт 45%, тейк +2R, стоп −1R -> ожидание +0.35R.
    Такая нога — успех, а не пограничный случай. Если сторож убивает её,
    он неверен.
    """
    r = rnd or random
    return [win_r if r.random() < win_rate else -loss_r for _ in range(n)]


def true_expectancy(win_rate: float = 0.45, win_r: float = 2.0,
                    loss_r: float = 1.0) -> float:
    return win_rate * win_r - (1.0 - win_rate) * loss_r


def calibrate(
    guard: Callable[[Sequence[float]], bool],
    *,
    label: str = "guard",
    sizes: Sequence[int] = DEFAULT_SIZES,
    runs: int = 1000,
    seed: int = 7,
    win_rate: float = 0.45,
    tolerable: float = 0.05,
) -> str:
    """Доля ложных срабатываний сторожа на здоровой ноге, по длинам выборки.

    `tolerable` — какую долю ложных убийств считаем приемлемой. 5% —
    та же логика, что у уровня значимости: убивать здоровое чаще, чем
    в одном случае из двадцати, нельзя.
    """
    rnd = random.Random(seed)
    exp = true_expectancy(win_rate)
    lines = [
        f"КАЛИБРОВКА: {label}",
        f"вход: заведомо прибыльная нога, истинное ожидание {exp:+.2f}R, "
        f"винрейт {win_rate*100:.0f}%",
        f"{runs} симуляций на длину; приемлемо не более {tolerable*100:.0f}% ложных",
        "",
        f"{'сделок':>8}{'ложных убийств':>18}{'вердикт':>12}",
    ]
    worst = 0.0
    for n in sizes:
        killed = sum(1 for _ in range(runs) if guard(healthy_leg(n, win_rate=win_rate, rnd=rnd)))
        frac = killed / runs
        worst = max(worst, frac)
        mark = "ok" if frac <= tolerable else ("плохо" if frac <= 0.25 else "СЛОМАН")
        lines.append(f"{n:>8}{frac*100:>17.1f}%{mark:>12}")
    lines.append("")
    if worst <= tolerable:
        lines.append("ВЫВОД: калибровка приемлема.")
    elif worst <= 0.25:
        lines.append(f"ВЫВОД: пороги завышены — до {worst*100:.0f}% здоровых ног "
                     "убиваются. Требуется пересчёт.")
    else:
        lines.append(f"ВЫВОД: СТОРОЖ НЕПРИГОДЕН как есть — {worst*100:.0f}% "
                     "здоровых ног убиваются. Подключать нельзя.")
    if len(sizes) > 1:
        first = sum(1 for _ in range(runs) if guard(healthy_leg(sizes[0], win_rate=win_rate, rnd=rnd))) / runs
        last = sum(1 for _ in range(runs) if guard(healthy_leg(sizes[-1], win_rate=win_rate, rnd=rnd))) / runs
        if last > first + 0.10:
            lines.append("ПРИЗНАК: доля растёт с длиной выборки — почти наверняка "
                         "порог задан константой для величины, которая копится "
                         "со временем (просадка, серия, суммарный убыток).")
    return "\n".join(lines)


def expected_drawdown_table(win_rate: float = 0.45, runs: int = 2000,
                            sizes: Sequence[int] = DEFAULT_SIZES,
                            seed: int = 11) -> str:
    """Какая просадка НОРМАЛЬНА для прибыльной ноги — для замены констант."""
    rnd = random.Random(seed)

    def dd(rs):
        peak = cum = worst = 0.0
        for r in rs:
            cum += r
            peak = max(peak, cum)
            worst = max(worst, peak - cum)
        return worst

    lines = ["НОРМАЛЬНАЯ просадка прибыльной ноги (для калибровки порогов)",
             f"{'сделок':>8}{'медиана':>10}{'90-й':>8}{'99-й':>8}"]
    for n in sizes:
        d = sorted(dd(healthy_leg(n, win_rate=win_rate, rnd=rnd)) for _ in range(runs))
        lines.append(f"{n:>8}{statistics.median(d):>9.1f}R"
                     f"{d[int(0.90*len(d))]:>7.1f}R{d[int(0.99*len(d))]:>7.1f}R")
    lines.append("Порог halt разумно ставить не ниже 99-го перцентиля ДЛЯ ЭТОГО n.")
    return "\n".join(lines)


def _self_test() -> None:
    # сторож, который не трогает никого -> 0% ложных
    assert "калибровка приемлема" in calibrate(lambda rs: False, runs=200, label="никого")
    # сторож, который убивает всех -> непригоден
    assert "НЕПРИГОДЕН" in calibrate(lambda rs: True, runs=200, label="всех")
    # сторож с константным порогом на копящуюся величину -> должен ловиться признак
    def bad(rs):
        peak = cum = worst = 0.0
        for r in rs:
            cum += r
            peak = max(peak, cum)
            worst = max(worst, peak - cum)
        return worst >= 6.0
    out = calibrate(bad, runs=400, label="константный порог просадки")
    assert "ПРИЗНАК" in out, "не распознан рост доли с длиной выборки"
    assert true_expectancy() > 0, "тестовая нога обязана быть прибыльной"
    print("самопроверка guard_calibration: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    _self_test()
    print()
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from bot.edge_monitor import assess_sleeve
        print(calibrate(
            lambda rs: assess_sleeve(rs, baseline_expectancy_R=0.35).status == "halt",
            label="bot/edge_monitor.py -> halt"))
        print()
        print(expected_drawdown_table())
    except Exception as e:
        print(f"edge_monitor недоступен: {e}")
