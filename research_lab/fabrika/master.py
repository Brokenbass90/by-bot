"""master.py — STRATEGY_MASTER.md как ВИД на канонический реестр (data/reestr.json).
Руками файл не правится: всё, что в нём есть, берётся из реестра и журнала фабрики.
    python3 master.py
"""
from __future__ import annotations
import datetime as dt, json
from collections import Counter, defaultdict
from pathlib import Path
from reestr_sink import BAZA, SOSTOYANIYA, atomarno

LAB = Path(__file__).resolve().parents[1]
MASTER = LAB / "STRATEGY_MASTER.md"
VERDIKTY = Path(__file__).resolve().parent / "verdikty.jsonl"
SLOTY = [("akcii", "Акции"), ("padenie", "Крипта: падение / флет вниз"), ("neytral", "Крипта: нейтральный / боковик"),
         ("rost", "Крипта: рост"), ("fon", "Фоновые эксперименты"), (None, "Без слота")]


def k(s, n=90):
    s = "" if s is None else str(s).replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def glavnoe(x):
    f = x.get("fabrika") or {}
    return f.get("pochemu") or x.get("edzh") or ""


def postroit():
    z = json.loads(BAZA.read_text(encoding="utf-8"))
    rang = {s: i for i, s in enumerate(SOSTOYANIYA)}
    z.sort(key=lambda x: (-rang.get(x["sostoyanie"], 0), x["id"]))
    t = ["# STRATEGY_MASTER — вид на реестр", "",
         f"Сгенерировано {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC} из `research_lab/data/reestr.json` "
         "(единственная машинная база) и `research_lab/fabrika/verdikty.jsonl` (журнал доказательств).",
         "Руками не править: `python3 research_lab/fabrika/master.py`. Приоритеты — в `ROADMAP.md`.", "",
         "## Слоты портфеля", "",
         "Слот — это место в портфеле, а не обещанный победитель. Умерла нога — слот ищет другую.", ""]
    po_slotu = defaultdict(list)
    for x in z:
        if x["sostoyanie"] != "NEGATIVE":
            po_slotu[x.get("slot")].append(x)
    for slot, imya in SLOTY:
        xs = [x for x in po_slotu.get(slot, []) if slot is not None or x["sostoyanie"] not in ("HYPOTHESIS",)]
        if not xs:
            continue
        t += [f"**{imya}**", "", "| id | состояние | главное | следующий шаг | владелец |", "|---|---|---|---|---|"]
        for x in xs:
            t.append(f"| {x['id']} | {x['sostoyanie']} | {k(glavnoe(x))} | {k(x.get('sleduyushchiy_test'), 70)} | {x.get('vladelec', '')} |")
        t.append("")
    hyp = [x for x in z if x["sostoyanie"] == "HYPOTHESIS" and x.get("slot") is None]
    if hyp:
        t += ["## Гипотезы без слота (ждут данных/переходника или «плюс без уверенности»)", ""]
        t += [f"- `{x['id']}` — {k(glavnoe(x), 110)}" for x in hyp] + [""]
    t += ["## Доказательства по живым строкам", ""]
    for x in z:
        if x["sostoyanie"] not in ("NEGATIVE", "HYPOTHESIS"):
            t.append(f"- `{x['id']}`: {k(x.get('svidetelstvo'), 160)}")
    t.append("")
    vv = [json.loads(s) for s in VERDIKTY.read_text().splitlines() if s.strip()] if VERDIKTY.exists() else []
    c = Counter(v["verdikt"] for v in vv if v["verdikt"] not in ("FAILED_TECHNICAL",))
    t += ["## Фабрика", "", "Вердиктов всего: " + ", ".join(f"{a} {b}" for a, b in c.most_common()), ""]
    neg = defaultdict(list)
    for x in z:
        if x["sostoyanie"] == "NEGATIVE":
            neg[x.get("semya") or "прочее"].append(x["id"])
    t += [f"## Архив (NEGATIVE, {sum(len(v) for v in neg.values())})", "",
          "Решений не принимает. Хранится, чтобы не убивать второй раз.", ""]
    t += [f"- {s}: {', '.join(ids)}" for s, ids in sorted(neg.items())] + [""]
    atomarno(MASTER, "\n".join(t))
    return MASTER


if __name__ == "__main__":
    print(postroit())
