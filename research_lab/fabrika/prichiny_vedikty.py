#!/usr/bin/env python3
"""prichiny_vedikty.py — почему умерла каждая идея Фабрики (27.10.2026, Claude). Только чтение `fabrika/verdikty.jsonl`.
Класс причины по окнам O1..O3 (среднее R после издержек, контроль случайным входом той же монеты/стороны, edge = R − контроль, z):
  MALO_DANNYH        — сделок во всех окнах < 60
  NET_INFORMACII     — во всех окнах |z| < 1.5: сигнал неотличим от случайного входа
  PROTIV_SLUCHAYA    — edge < 0 во всех окнах и хотя бы где-то z ≤ −1.5: сигнал ХУЖЕ случайного (зеркальная идея?)
  NESTABILNO         — знак edge меняется между окнами при |z| ≥ 1.5 хотя бы в одном: работает в одной эпохе, ломается в другой (режим)
  INFO_EST_DENEG_NET — edge > 0 во всех окнах, но средний R ≤ 0: в сигнале есть информация, её съедает рынок/издержки → форма с хеджем/мейкером
  SLABYY_PLYUS       — edge > 0 и R > 0 во всех окнах, но значимости не хватило → нужна мощность (данные), не новая идея
Выход: data/factory_v3/PRICHINY_VERDIKTOV.json + .md (таблица по шаблонам механизмов)."""
import collections, json, re
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; F = LAB / "fabrika" / "verdikty.jsonl"; OUT = LAB / "data" / "factory_v3" / "PRICHINY_VERDIKTOV"

def klass(ok):
    w = [v for v in ok.values() if isinstance(v, dict) and v.get("n")]
    if not w: return "NET_OKON"
    if all(v["n"] < 60 for v in w): return "MALO_DANNYH"
    w = [v for v in w if v["n"] >= 30 and v.get("edge") is not None]
    if not w: return "MALO_DANNYH"
    z = [v.get("z") or 0 for v in w]; e = [v["edge"] for v in w]; m = [v.get("mean", 0) for v in w]
    if all(abs(x) < 1.5 for x in z): return "NET_INFORMACII"
    if all(x < 0 for x in e): return "PROTIV_SLUCHAYA"
    if any(x > 0 for x in e) and any(x < 0 for x in e): return "NESTABILNO"
    if all(x > 0 for x in e) and all(x <= 0 for x in m): return "INFO_EST_DENEG_NET"
    if all(x > 0 for x in e): return "SLABYY_PLYUS" if not all(x > 0 for x in m) or True else "SLABYY_PLYUS"
    return "PROCHEE"

SLED = {"NET_INFORMACII": "не спасать этот сигнал; механизм искать в других данных (поток, позиционирование, события)",
        "PROTIV_SLUCHAYA": "проверить зеркальную сторону как ОТДЕЛЬНУЮ гипотезу (prereg), если есть причина",
        "NESTABILNO": "найти, в каком режиме работает: заранее заданная карта режимов → проверка вперёд",
        "INFO_EST_DENEG_NET": "сменить форму: хедж бетой/корзиной, мейкер-вход, длиннее удержание — информация уже есть",
        "SLABYY_PLYUS": "добрать данные (глубже история / вперёд), не менять правило",
        "MALO_DANNYH": "источник данных глубже", "NET_OKON": "—", "PROCHEE": "разбор вручную"}

def shablon(i):
    return re.split(r"__", i)[0]

def main():
    L = [json.loads(s) for s in F.open(encoding="utf-8") if s.strip()]
    rows = []
    for v in L:
        ok = v.get("okna") or {}
        k = klass(ok)
        rows.append(dict(id=v.get("id"), verdikt=v.get("verdikt"), klass=k, sled=SLED[k],
                         okna={n: dict(n=w.get("n"), R=round(w.get("mean", 0), 4), edge=round(w.get("edge", 0), 4), z=round(w.get("z", 0) or 0, 2))
                               for n, w in ok.items() if isinstance(w, dict) and w.get("n")}))
    c = collections.Counter(r["klass"] for r in rows)
    po_shabl = collections.defaultdict(collections.Counter)
    for r in rows: po_shabl[shablon(r["id"])][r["klass"]] += 1
    OUT.with_suffix(".json").write_text(json.dumps(dict(vsego=len(rows), klassy=c, po_shablonam=po_shabl, verdikty=rows), ensure_ascii=False, indent=1))
    md = ["# Почему умерли идеи Фабрики — автоматический разбор вердиктов (`fabrika/prichiny_vedikty.py`)", "",
          f"Вердиктов: {len(rows)}. Классы: " + ", ".join(f"{k} {n}" for k, n in c.most_common()), "",
          "| класс | что значит | следующий ход |", "|---|---|---|"]
    for k, n in c.most_common(): md.append(f"| {k} ({n}) | см. код | {SLED[k]} |")
    md += ["", "## Кандидаты на доработку (информация есть / плюс без силы / работает в одной эпохе)", "", "| id | класс | окна (n, R, edge, z) |", "|---|---|---|"]
    for r in rows:
        if r["klass"] in ("INFO_EST_DENEG_NET", "SLABYY_PLYUS", "NESTABILNO", "PROTIV_SLUCHAYA"):
            md.append(f"| {r['id']} | {r['klass']} | " + "; ".join(f"{n}: {w['n']}, {w['R']:+}, {w['edge']:+}, z {w['z']}" for n, w in r["okna"].items()) + " |")
    OUT.with_suffix(".md").write_text("\n".join(md)); print("\n".join(md[:8])); print("кандидатов:", sum(1 for r in rows if r["klass"] in ("INFO_EST_DENEG_NET", "SLABYY_PLYUS", "NESTABILNO", "PROTIV_SLUCHAYA")))

if __name__ == "__main__": main()
