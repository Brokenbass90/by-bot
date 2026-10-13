#!/usr/bin/env python3
"""ferma_v1.py — Backtest Farm V1 (Factory V3, слой 3). 13.10.2026.

Ферма УБИВАЕТ идеи дёшево, а не ищет красивые кривые. Поэтому:
  1. Каждый эксперимент регистрируется в реестре ДО запуска (стадия SCREEN, только DEV-окна; HOLDOUT/CONFIRM — отказ реестра).
     Критерии (min_n, znak) входят в спецификацию → sha → поменять после результата нельзя.
  2. Код эксперимента не видит путей: только объект Dostup, который отдаёт данные строго внутри окна попытки
     и отказывает при пересечении с любым HOLDOUT-окном реестра.
  3. Порог t растёт с числом попыток на окне (реестр). Неудачный/упавший эксперимент тоже тратит бюджет окна.
  4. Параллельно считает пул процессов; результаты пишет только главный процесс (один писатель реестра).
Ферма не меняет статусы гипотез и не запускает точную проверку — это делают судьи и человек.

Эксперимент — функция f(parametry: dict, dostup: Dostup) -> dict(t=float, n=int, metrika=dict|None),
указывается в спецификации как "modul:funkciya" (модуль ищется в research_lab/factory_v3 и research_lab).
"""
import datetime as dt, gzip, importlib, json, sys, traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent; LAB = HERE.parent
for p in (str(HERE), str(LAB)):
    if p not in sys.path: sys.path.insert(0, p)
from reestr_v1 import Reestr, OshibkaReestra


def ms(d): return int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


class ZaborNarushen(Exception):
    pass


# ---------- загрузчики (единственное место, где ферма знает пути) ----------
def _pit_daily(sym):
    x = json.loads((LAB / "data" / "pit_daily" / f"{sym}.json").read_text())
    return [list(r) for r in x["daily"]]                       # [ts, o, h, l, c, v]


def _breakout_m5(sym):
    rows = []
    for f in sorted((LAB / "data" / "breakout_m5_v2" / sym).glob(f"{sym}_*.jsonl.gz")):
        if f.name.endswith(".raw.gz"): continue
        rows += [[float(v) if i else int(v) for i, v in enumerate(json.loads(l))] for l in gzip.open(f, "rt") if l.strip()]
    return rows


def _sintetika(sym):
    """Детерминированный шум для тестов фермы: дневные бары 2021–2027, семя от символа."""
    import random
    rnd = random.Random(sym); t0 = ms("2021-01-01"); c = 100.0; out = []
    for i in range(365 * 7):
        o = c; c = max(1.0, c * (1 + rnd.gauss(0, 0.03))); out.append([t0 + i * 86_400_000, o, max(o, c), min(o, c), c, 1.0])
    return out


ZAGRUZCHIKI = {"pit_daily": _pit_daily, "breakout_m5": _breakout_m5, "sintetika": _sintetika}


class Dostup:
    """Забор данных: только [nachalo, konec] окна попытки; любое пересечение с HOLDOUT — исключение."""
    def __init__(self, okno, holdout):
        self.t0, self.t1 = ms(okno["nachalo"]), ms(okno["konec"]) + 86_400_000 - 1
        for h in holdout:
            if not (ms(h["konec"]) + 86_400_000 - 1 < self.t0 or ms(h["nachalo"]) > self.t1):
                raise ZaborNarushen(f"окно {okno['id']} пересекается с HOLDOUT {h['id']}")
        self.okno_id = okno["id"]

    def ryad(self, nabor, sym):
        if nabor not in ZAGRUZCHIKI: raise ZaborNarushen(f"неизвестный набор {nabor}")
        return [r for r in ZAGRUZCHIKI[nabor](sym) if self.t0 <= r[0] <= self.t1]


def _vypolnit(zadanie):
    spec, okno, holdout = zadanie
    try:
        mod, fn = spec["eksperiment"].split(":")
        f = getattr(importlib.import_module(mod), fn)
        r = f(spec.get("parametry", {}), Dostup(okno, holdout))
        return dict(ok=True, t=float(r["t"]), n=int(r["n"]), metrika=r.get("metrika"))
    except Exception as e:
        return dict(ok=False, oshibka=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-600:])


def zapustit(specs, reestr=None, processov=4):
    """specs: [{id, gipoteza, okno, eksperiment, parametry, kriterii}]. Возвращает список итогов по каждой спецификации."""
    r = reestr or Reestr(); S = r.sostoyanie()
    holdout = [o for o in S["okna"].values() if o["rol"] == "HOLDOUT"]
    gotovye, itogi = [], []
    for s in specs:
        try:
            r.zaregistrirovat_popytku(s["id"], s["gipoteza"], s["okno"], "SCREEN", s, s["kriterii"])
            gotovye.append(s)
        except OshibkaReestra as e:
            itogi.append(dict(id=s["id"], status="OTKAZ_REESTRA", prichina=str(e)))
    S = r.sostoyanie()
    zadaniya = [(s, S["okna"][s["okno"]], holdout) for s in gotovye]
    with ProcessPoolExecutor(max_workers=max(1, processov)) as ex:
        rez = list(ex.map(_vypolnit, zadaniya))
    for s, x in zip(gotovye, rez):
        if not x["ok"]:
            itogi.append(dict(id=s["id"], status="OSHIBKA_EKSPERIMENTA", prichina=x["oshibka"]))   # бюджет окна потрачен
            continue
        z = r.zapisat_rezultat(s["id"], s, t=x["t"], n=x["n"], metrika=x["metrika"])
        itogi.append(dict(id=s["id"], status=z["verdikt"], t=x["t"], n=x["n"], trebuemyy_t=z["trebuemyy_t"]))
    return itogi
