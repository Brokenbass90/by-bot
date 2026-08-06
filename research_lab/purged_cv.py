"""PURGED / EMBARGOED КРОСС-ВАЛИДАЦИЯ ДЛЯ ВРЕМЕННЫХ РЯДОВ.

ЗАЧЕМ ЭТО НУЖНО ИМЕННО НАМ.

Обычная кросс-валидация предполагает, что наблюдения независимы. В трейдинге
это неверно дважды:

  1. Сделка ЗАНИМАЕТ ИНТЕРВАЛ. Открылась в понедельник, закрылась в четверг.
     Если тестовый фолд начинается во вторник, то обучающая сделка
     понедельника уже «видела» вторник. Утечка.

  2. Соседние наблюдения коррелированы. Даже без пересечения интервалов
     сделка, закрытая за минуту до начала теста, несёт почти ту же
     информацию, что первая сделка теста.

Лечится двумя приёмами (Lopez de Prado, "Advances in Financial ML", гл. 7):

  * PURGE   — выбросить из обучения все наблюдения, чей интервал пересекается
              с интервалом тестового фолда;
  * EMBARGO — дополнительно выбросить обучающие наблюдения, начинающиеся
              вскоре ПОСЛЕ теста (доля от общей длины выборки).

ПОЧЕМУ ЭТО ПЕРВООЧЕРЕДНОЕ. В `backtest_runs/` лежит 53 467 прогонов.
Кандидаты стабильно рассыпаются на OOS. Утечка через перекрытие сделок —
одна из двух наиболее вероятных причин (вторая — отбор из большого
пространства, её закрывает `significance.py`).

ЕДИНИЦЫ. Времена — в любых сравнимых числах (unix ms, unix s, индексы баров),
лишь бы `t_start <= t_end` и всё в одной шкале.

ИСПОЛЬЗОВАНИЕ.

    from research_lab.purged_cv import PurgedKFold, leakage_report

    cv = PurgedKFold(n_splits=5, embargo_frac=0.01)
    for train_idx, test_idx in cv.split(starts, ends):
        ...

    print(leakage_report(starts, ends, n_splits=5))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence


@dataclass
class PurgedKFold:
    """K-fold по времени с очисткой пересечений и эмбарго.

    n_splits      — число фолдов;
    embargo_frac  — доля ОБЩЕГО числа наблюдений, вычёркиваемая сразу после
                    тестового фолда. 0.01 = 1%. Ноль отключает эмбарго.
    """

    n_splits: int = 5
    embargo_frac: float = 0.01

    def split(
        self,
        starts: Sequence[float],
        ends: Sequence[float],
    ) -> Iterator[tuple[list[int], list[int]]]:
        n = len(starts)
        if n != len(ends):
            raise ValueError("starts и ends разной длины")
        if self.n_splits < 2:
            raise ValueError("n_splits должно быть >= 2")
        if n < self.n_splits:
            raise ValueError(f"наблюдений {n} меньше числа фолдов {self.n_splits}")
        for i, (a, b) in enumerate(zip(starts, ends)):
            if b < a:
                raise ValueError(f"наблюдение {i}: end < start")

        # фолды нарезаются по ПОРЯДКУ ВРЕМЕНИ начала, а не по позиции в массиве
        order = sorted(range(n), key=lambda k: (starts[k], ends[k]))
        embargo = int(round(n * max(0.0, self.embargo_frac)))

        bounds = [round(n * k / self.n_splits) for k in range(self.n_splits + 1)]
        for k in range(self.n_splits):
            lo, hi = bounds[k], bounds[k + 1]
            if hi <= lo:
                continue
            test_pos = order[lo:hi]
            t0 = min(starts[i] for i in test_pos)
            t1 = max(ends[i] for i in test_pos)

            # эмбарго: наблюдения сразу после теста по порядку времени
            embargoed = set(order[hi:hi + embargo]) if embargo > 0 else set()

            train_pos = []
            for pos_idx, i in enumerate(order):
                if lo <= pos_idx < hi:
                    continue                      # сам тест
                if i in embargoed:
                    continue                      # эмбарго
                # PURGE: любое пересечение интервалов [start,end]
                if starts[i] <= t1 and ends[i] >= t0:
                    continue
                train_pos.append(i)
            yield train_pos, test_pos


def leakage_report(
    starts: Sequence[float],
    ends: Sequence[float],
    *,
    n_splits: int = 5,
    embargo_frac: float = 0.01,
) -> str:
    """Сколько наблюдений обычная CV отдала бы в обучение с утечкой.

    Это ответ на вопрос «а насколько вообще велика проблема на НАШИХ данных».
    Если утечка около нуля — можно не усложнять. Если десятки процентов —
    все прошлые OOS-выводы под вопросом.
    """
    n = len(starts)
    cv = PurgedKFold(n_splits=n_splits, embargo_frac=embargo_frac)
    naive_total = 0
    purged_total = 0
    for train_idx, test_idx in cv.split(starts, ends):
        purged_total += len(train_idx)
        naive_total += n - len(test_idx)
    dropped = naive_total - purged_total
    pct = (dropped / naive_total * 100) if naive_total else 0.0
    dur = [e - s for s, e in zip(starts, ends)]
    span = (max(ends) - min(starts)) if n else 0.0
    mean_dur = (sum(dur) / n) if n else 0.0
    return (
        f"наблюдений: {n}, фолдов: {n_splits}, эмбарго: {embargo_frac*100:.1f}%\n"
        f"средняя длительность наблюдения: {mean_dur:.1f} "
        f"({mean_dur/span*100:.2f}% от всей истории)\n"
        f"обучающих наблюдений без очистки: {naive_total}\n"
        f"обучающих наблюдений после очистки: {purged_total}\n"
        f"ВЫБРОШЕНО ИЗ-ЗА УТЕЧКИ: {dropped} ({pct:.1f}%)"
    )


# ───────────────────────────── самопроверка ─────────────────────────────

def _self_test() -> None:
    # 1. непересекающиеся мгновенные наблюдения -> очищать почти нечего
    starts = list(range(100))
    ends = list(range(100))
    cv = PurgedKFold(n_splits=5, embargo_frac=0.0)
    for tr, te in cv.split(starts, ends):
        assert not (set(tr) & set(te)), "train и test пересеклись"
        assert len(tr) + len(te) == 100, "потеряны наблюдения без причины"

    # 2. длинные пересекающиеся наблюдения -> очистка обязана срабатывать
    starts2 = list(range(100))
    ends2 = [s + 30 for s in starts2]          # каждое живёт 30 единиц
    cv2 = PurgedKFold(n_splits=5, embargo_frac=0.0)
    for tr, te in cv2.split(starts2, ends2):
        t0 = min(starts2[i] for i in te)
        t1 = max(ends2[i] for i in te)
        for i in tr:
            assert not (starts2[i] <= t1 and ends2[i] >= t0), \
                f"наблюдение {i} пересекается с тестом — очистка не сработала"
        assert len(tr) < 100 - len(te), "ничего не выброшено, хотя должно"

    # 3. эмбарго действительно убирает наблюдения ПОСЛЕ теста
    cv3 = PurgedKFold(n_splits=5, embargo_frac=0.10)
    tr3, te3 = next(iter(cv3.split(starts, ends)))
    cv4 = PurgedKFold(n_splits=5, embargo_frac=0.0)
    tr4, _ = next(iter(cv4.split(starts, ends)))
    assert len(tr3) < len(tr4), "эмбарго не уменьшило обучающую выборку"

    # 4. защита от кривого входа
    for bad in (
        lambda: list(PurgedKFold(1).split([1, 2], [1, 2])),
        lambda: list(PurgedKFold(2).split([1, 2], [1])),
        lambda: list(PurgedKFold(2).split([5, 1], [1, 2])),   # end < start
    ):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("кривой вход не отвергнут")

    print("самопроверка purged_cv: ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    print()
    print("Пример на реалистичных данных (сделки живут ~30 из 130 единиц):")
    print(leakage_report(starts2, ends2, n_splits=5, embargo_frac=0.01))


if __name__ == "__main__":
    _self_test()
