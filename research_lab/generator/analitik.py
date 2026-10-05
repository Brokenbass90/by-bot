#!/usr/bin/env python3
"""analitik.py — AUTONOMOUS_SHADOW_RESEARCH_V1, срез 3: автоматический аналитик (Ollama qwen3:8b, think=false).

Права: ЧИТАЕТ data/digest/digest_latest.json, generator/kladbische.json, fabrika/katalog_dannyh.json;
ПИШЕТ только черновики data/fabrika_xs/drafty/DRAFT_<UTC>.json (статус DRAFT). Ничего не запускает: нет shell, правки кода,
порогов, брокера, денег. Промоушен DRAFT → prereg делает только Claude после проверки семьи/причинности.

    python3 research_lab/generator/analitik.py [--fokus LONG]      (на Mac: Ollama на 127.0.0.1:11434)
    python3 research_lab/generator/analitik.py --mock файл.json   (тест без модели)
"""
from __future__ import annotations
import datetime as dt, json, re, sys, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
MODEL = "qwen3:8b"
ZAPRET_MODELI = ("llava", "vl")          # визуальные модели для анализа запрещены
STORONY = {"LONG", "LONG_SHORT", "SHORT"}
MAX_K = 3
SHEMA = {"type": "object", "properties": {"kandidaty": {"type": "array", "maxItems": MAX_K, "items": {"type": "object",
         "properties": {"imya": {"type": "string"}, "semya": {"type": "string"}, "mehanizm": {"type": "string"},
                        "kto_ostavlyaet_dengi": {"type": "string"}, "storona": {"type": "string", "enum": sorted(STORONY)},
                        "izmereniya": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
                        "dannye": {"type": "string"}, "pochemu_ne_dubl": {"type": "string"}, "deshevyy_test": {"type": "string"}},
         "required": ["imya", "semya", "mehanizm", "kto_ostavlyaet_dengi", "storona", "izmereniya", "dannye", "pochemu_ne_dubl", "deshevyy_test"]}}},
         "required": ["kandidaty"]}


def norm(s: str) -> str: return re.sub(r"[^A-Z0-9]", "", s.upper())


def kontekst():
    dg = json.loads((LAB / "data" / "digest" / "digest_latest.json").read_text())
    kl = json.loads((LAB / "generator" / "kladbische.json").read_text())
    kat = json.loads((LAB / "fabrika" / "katalog_dannyh.json").read_text())
    kratko = dict(trevogi=dg["trevogi"], slot=dg["slot"], prereg={k: v["status"] for k, v in dg["prereg"].items() if v["status"]},
                  nabory={k: {p: x["poslednyaya"] for p, x in v["podpapki"].items()} for k, v in dg["nabory"].items()})
    return kratko, kl, kat


KLASSY = ("вынужденные потоки (ребалансировки, экспирации, разлоки, делистинги)", "события листинга и включения в индексы/корзины",
          "межрыночные смещения (крипта ↔ традиционные часы торговли, выходные)", "структура издержек/доступности (кто не может торговать и когда)",
          "поведение после экстремальных, но не ценовых событий (OI, фандинг-сбросы) — если не на кладбище")


def prompt(fokus, kratko, kl, kat, otkazy=()):
    dop = ""
    if otkazy:
        dop = ("\nПРОШЛАЯ ПОПЫТКА ОТКЛОНЕНА: " + "; ".join(otkazy) +
               ". Не повторяй эти названия и идеи. Придумай НОВОЕ название семьи, которого нет в кладбище.")
    return ("Ты — аналитик исследовательской фабрики крипто-стратегий. Предложи НЕ БОЛЕЕ 3 новых проверяемых механизмов"
            f" с фокусом {fokus}. Каждый — экономическая причина (кто и почему оставляет деньги), 2–3 способа измерения,"
            " данные ТОЛЬКО из каталога, дешёвый тест фальсификации. Запрещено: семьи из кладбища и их переименования,"
            " индикаторные перестановки (RSI/EMA/пробои), перебор порогов, механизмы, зависящие от позиций толпы/топ-трейдеров"
            " или потока тейкеров (они заняты). Поле semya — НОВОЕ имя, которого НЕТ в списке УЖЕ УБИТО."
            f" Ищи в классах: {'; '.join(KLASSY)}. Ответ — строго JSON по схеме.\n\n"
            f"СОСТОЯНИЕ: {json.dumps(kratko, ensure_ascii=False)}\nУЖЕ УБИТО (НЕ ПРЕДЛАГАТЬ): {json.dumps([x['semya'] for x in kl], ensure_ascii=False)}\n"
            f"КАТАЛОГ ДАННЫХ: {json.dumps(kat, ensure_ascii=False)}{dop}")


def ollama(tekst):
    if any(z in MODEL for z in ZAPRET_MODELI):
        raise SystemExit("визуальная модель запрещена")
    body = json.dumps(dict(model=MODEL, prompt=tekst, stream=False, think=False, format=SHEMA,
                           options=dict(temperature=0.3, seed=7))).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate", body,
                                          {"Content-Type": "application/json"}), timeout=900).read())
    return json.loads(r["response"])


def proverit(otvet, kl):
    mertvye = {norm(x["semya"]) for x in kl}
    zanyato = {norm(x) for x in ("TOLPA", "KITY", "TAKER", "TEYKER", "CARRY")}
    prinyato, otkaz = [], []
    for k in (otvet.get("kandidaty") or [])[:MAX_K]:
        prich = None
        if not all(k.get(p) for p in SHEMA["properties"]["kandidaty"]["items"]["required"]):
            prich = "не по схеме"
        elif k["storona"] not in STORONY or not (2 <= len(k["izmereniya"]) <= 3):
            prich = "сторона/измерения вне схемы"
        elif norm(k["semya"]) in mertvye or any(z in norm(k["semya"]) + norm(k["imya"]) for z in zanyato):
            prich = "семья на кладбище или занята"
        (otkaz if prich else prinyato).append(dict(k, prichina_otkaza=prich) if prich else dict(k, status="DRAFT"))
    return prinyato, otkaz


def main():
    fokus = sys.argv[sys.argv.index("--fokus") + 1] if "--fokus" in sys.argv else "LONG"
    kratko, kl, kat = kontekst()
    prin, otk = [], []
    if "--mock" in sys.argv:
        prin, otk = proverit(json.loads(Path(sys.argv[sys.argv.index("--mock") + 1]).read_text()), kl)
    else:
        for popytka in range(3):                      # ≤ 3 раунда с обратной связью; принятые копятся, дубли по семье отсекаются
            p, o = proverit(ollama(prompt(fokus, kratko, kl, kat, [f"{x.get('semya')} ({x['prichina_otkaza']})" for x in otk])), kl)
            uzhe = {norm(x["semya"]) for x in prin}
            prin += [x for x in p if norm(x["semya"]) not in uzhe]; otk += o
            print(f"раунд {popytka + 1}: принято {len(p)}, отказано {len(o)}", flush=True)
            if len(prin) >= MAX_K:
                break
        prin = prin[:MAX_K]
    out = LAB / "data" / "fabrika_xs" / "drafty"; out.mkdir(parents=True, exist_ok=True)
    kogda = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    f = out / f"DRAFT_{kogda}.json"
    f.write_text(json.dumps(dict(kogda=kogda, model=MODEL, fokus=fokus, drafty=prin, otkazano=otk), ensure_ascii=False, indent=1))
    print(f"черновиков {len(prin)}, отказано {len(otk)} → {f}")
    for k in prin:
        print(f"  DRAFT {k['imya']} [{k['storona']}] {k['mehanizm'][:140]}")
    for k in otk:
        print(f"  ОТКАЗ {k.get('imya')}: {k['prichina_otkaza']}")


if __name__ == "__main__":
    main()
