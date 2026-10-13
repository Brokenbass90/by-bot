#!/usr/bin/env python3
"""sudya_most_v1.py — мост «замороженные судьи → реестр» (Factory V3). 13.10.2026.
Реестр — единственная правда о том, что проверялось, на каких окнах и с каким итогом (заменяет ворота G4/G5 Фабрики V2:
журнал потраченных окон = попытки реестра; самопроверка судьи = sha спецификации + один результат на попытку).

sudit(...)      — новый прогон судьи: регистрация попытки ДО вызова, вызов, запись результата. Судья — любая функция,
                  возвращающая dict(t, n, metrika). Упал → попытка остаётся без результата (бюджет потрачен), исключение наружу.
verdikt(...)    — проспективный вердикт тени (KEEP/CONTINUE/DEPRIORITIZE/KILL) с документом-основанием.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reestr_v1 import Reestr


def sudit(reestr, popytka, gipoteza, okno, stadiya, spec, kriterii, sudya, *args, **kw):
    reestr.zaregistrirovat_popytku(popytka, gipoteza, okno, stadiya, spec, kriterii)
    r = sudya(*args, **kw)
    return reestr.zapisat_rezultat(popytka, spec, t=float(r["t"]), n=int(r["n"]), metrika=r.get("metrika"))


def verdikt(reestr, gipoteza, znachenie, dokument, detali=None):
    return reestr.verdikt_teni(gipoteza, znachenie, dokument, detali)


def zapisat_vechernie_12_10(reestr=None):
    """Вердикты, вынесенные 12.10 по живым линиям (тени не меняются)."""
    r = reestr or Reestr(); g = r.sostoyanie()["gipotezy"]
    if not any(v["znachenie"] == "DEPRIORITIZE" for v in g.get("BREAKOUT_TOP50", {}).get("verdikty", [])):
        verdikt(r, "BREAKOUT_TOP50", "DEPRIORITIZE", "data/breakout_dev_early/ITOG.json @ 23f0ff9",
                dict(okno="2023-01..2024-06", n=31, sred_R=-0.174, pf=0.586, primechanie="DEV-сигнал; тень работает дальше"))
    return r.sostoyanie()["gipotezy"]["BREAKOUT_TOP50"]


if __name__ == "__main__":
    print(zapisat_vechernie_12_10()["verdikty"])
