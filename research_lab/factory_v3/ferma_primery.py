"""ferma_primery.py — эксперименты-образцы для фермы (только синтетика/шум, для тестов и как шаблон)."""
import math, statistics


def moment_na_shume(parametry, dostup):
    """Шаблон: 'моментум' на синтетическом шуме. Ожидаемый эффект = 0 → любая PASS здесь — ложная находка."""
    rows = dostup.ryad("sintetika", parametry["sym"]); L = parametry.get("lookback", 20); H = parametry.get("hold", 5)
    c = [r[4] for r in rows]; x = []
    for i in range(L, len(c) - H, H):
        znak = 1 if c[i] > c[i - L] else -1
        x.append(znak * (c[i + H] / c[i] - 1))
    if len(x) < 3: return dict(t=0.0, n=len(x))
    sd = statistics.pstdev(x)
    return dict(t=statistics.fmean(x) / (sd / math.sqrt(len(x))) if sd else 0.0, n=len(x))


def podglyadyvaet(parametry, dostup):
    """Пытается взять данные — забор обязан отдать только окно попытки."""
    rows = dostup.ryad("sintetika", "X")
    return dict(t=0.0, n=len(rows), metrika=dict(t_min=rows[0][0], t_max=rows[-1][0]))
