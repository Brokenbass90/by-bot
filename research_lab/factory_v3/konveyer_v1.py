#!/usr/bin/env python3
"""konveyer_v1.py — закрывает разрыв «модули Фабрики есть» ↔ «Фабрика сама исследует» (15.10.2026).

Очередь data/factory_v3/ochered.jsonl (append-only): {"tip":"zayavka", "spec":{id, gipoteza, okno, eksperiment, parametry, kriterii},
"karta":{...}}. Сторож раз в час вызывает prohod(): каждая НОВАЯ заявка с полной картой кандидата и разрешённым шаблоном
исполняется фермой ОДИН раз (ferma_v1.zapustit → реестр: попытка до прогона, результат после), итог дописывается в очередь
как {"tip":"itog", ...}. Повтора нет: заявка с итогом не исполняется второй раз.

Карта кандидата обязательна ДО прогона (без неё — отказ, не прогон):
  data_ready (bool), istochniki (список), hist_dev ("ferma"|"skript:<путь>"), sobytiy_v_nedelyu (число),
  ozhidanie_vpered_dney (число), ispolnimost ("ponyatna"|"neyasna"), put_k_micro_live (строка), mehanizm (строка)
Правило: если data_ready=False — отказ BLOCKED_DATA; если ispolnimost="neyasna" — прогон разрешён, но к тени не допускается.
Шаблоны — только из RAZRESHENO. Окна HOLDOUT ферма сама запрещает.
"""
import json, time, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
OCHERED = HERE.parent / "data" / "factory_v3" / "ochered.jsonl"
RAZRESHENO = {"ferma_shablony:xs_nedelya_binance", "ferma_primery:moment_na_shume"}
KARTA = {"data_ready": bool, "istochniki": list, "hist_dev": str, "sobytiy_v_nedelyu": (int, float), "ozhidanie_vpered_dney": (int, float),
         "ispolnimost": str, "put_k_micro_live": str, "mehanizm": str}


def chitat(put=OCHERED):
    put = Path(put)
    return [json.loads(l) for l in open(put, encoding="utf-8") if l.strip()] if put.exists() else []


def dopisat(zap, put=OCHERED):
    put = Path(put); put.parent.mkdir(parents=True, exist_ok=True)
    with open(put, "a", encoding="utf-8") as f: f.write(json.dumps(zap, ensure_ascii=False) + "\n")


def podat(spec, karta, put=OCHERED):
    """Подать заявку (Claude / ИИ-раунд). Проверка карты — сразу, чтобы мусор не попадал в очередь."""
    plohie = [k for k, t in KARTA.items() if not isinstance(karta.get(k), t) or isinstance(karta.get(k), bool) != (t is bool)]
    if plohie: raise ValueError(f"карта кандидата неполна: {plohie}")
    if spec.get("eksperiment") not in RAZRESHENO: raise ValueError(f"шаблон не разрешён: {spec.get('eksperiment')}")
    if karta["ispolnimost"] not in ("ponyatna", "neyasna"): raise ValueError("ispolnimost ∈ {ponyatna, neyasna}")
    dopisat(dict(tip="zayavka", kogda=int(time.time() * 1000), spec=spec, karta=karta), put)


def prohod(put=OCHERED, reestr=None, processov=2):
    zap = chitat(put); sdelano = {z["id"] for z in zap if z["tip"] == "itog"}
    novye = [z for z in zap if z["tip"] == "zayavka" and z["spec"]["id"] not in sdelano]
    itogi = []
    blok = [z for z in novye if not z["karta"]["data_ready"]]
    for z in blok:
        itogi.append(dict(tip="itog", id=z["spec"]["id"], status="BLOCKED_DATA", kogda=int(time.time() * 1000)))
    gotovye = [z for z in novye if z["karta"]["data_ready"]]
    if gotovye:
        import ferma_v1
        for x in ferma_v1.zapustit([z["spec"] for z in gotovye], reestr=reestr, processov=processov):
            k = next(z["karta"] for z in gotovye if z["spec"]["id"] == x["id"])
            x.update(tip="itog", kogda=int(time.time() * 1000),
                     k_teni=bool(x.get("status") == "PASS" and k["ispolnimost"] == "ponyatna"))
            itogi.append(x)
    for x in itogi: dopisat(x, put)
    return itogi
