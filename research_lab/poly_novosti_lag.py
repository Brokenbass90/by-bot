#!/usr/bin/env python3
"""poly_novosti_lag.py — опережает ли новость цену на Polymarket (29.10.2026, Claude; поправка PM: время, когда новость УВИДЕЛИ МЫ, а не pubDate).
По рынкам монитора с исходом: T95 — первая минута, когда середина победившей стороны ≥ 0.95 (при наблюдении ≥ 5 мин до этого).
Для каждого рынка: заголовки, которые мы увидели (uvideli) за 6 ч до T95, и их pubDate. Окно = T95 − uvideli (сколько минут у нас была новость до того,
как цена стала «решённой»), и ask победившей стороны в момент, когда мы увидели новость. Описательно; ИИ не используется. python3 research_lab/poly_novosti_lag.py"""
import collections, datetime as dt, json, statistics as st
from pathlib import Path
M = Path(__file__).resolve().parent / "data" / "poly_monitor"
def ts(s): return dt.datetime.fromisoformat(s).timestamp()
kn = collections.defaultdict(list)
for l in (M / "knigi.jsonl").open(): z = json.loads(l); kn[z["id"]].append(z)
nov = collections.defaultdict(list)
for l in (M / "novosti.jsonl").open(): z = json.loads(l); nov[z["id"]].append(z)
ish = {}
for l in (M / "rynki.jsonl").open():
    z = json.loads(l)
    if z["sob"] == "vybyl" and z.get("closed"):
        try: pr = json.loads(z["outcomePrices"]) if isinstance(z["outcomePrices"], str) else z["outcomePrices"]; ish[z["id"]] = 1 if str(pr[0]) == "1" else 0
        except Exception: pass
rez = []
for i, y in ish.items():
    r = sorted(kn.get(i, []), key=lambda z: z["t"])
    if not r: continue
    def side(z):
        if z["bid"] is None or z["ask"] is None: return None, None
        m = (z["bid"] + z["ask"]) / 2
        return (m, z["ask"]) if y == 1 else (1 - m, 1 - z["bid"])
    t95 = next((z["t"] for z in r if (side(z)[0] or 0) >= 0.95), None)
    if t95 is None or t95 - r[0]["t"] < 300: continue
    n6 = [n for n in nov.get(i, []) if t95 - 6 * 3600 <= ts(n["uvideli"]) <= t95]
    if not n6: rez.append(dict(id=i, novost=False)); continue
    perv = min(n6, key=lambda n: ts(n["uvideli"])); tu = ts(perv["uvideli"])
    snap = [z for z in r if z["t"] <= tu]; ask_u = side(snap[-1])[1] if snap else None
    rez.append(dict(id=i, novost=True, okno_min=round((t95 - tu) / 60, 1), pub_do_uvideli_min=round((tu - ts(perv["pub"])) / 60, 1) if perv.get("pub") else None,
                    ask_kogda_uvideli=ask_u, zagolovok=perv["zagolovok"][:80]))
s = [x for x in rez if x["novost"]]
print("рынков с исходом и переходом к 0.95:", len(rez), "| с новостью за 6 ч до T95:", len(s))
if s:
    print("окно (мин от «увидели» до 0.95): медиана", st.median(x["okno_min"] for x in s), "| ask победителя в момент «увидели»: медиана",
          st.median(x["ask_kogda_uvideli"] for x in s if x["ask_kogda_uvideli"] is not None) if any(x["ask_kogda_uvideli"] for x in s) else None,
          "| задержка нашего RSS после pubDate, мин: медиана", st.median(x["pub_do_uvideli_min"] for x in s if x["pub_do_uvideli_min"] is not None))
    for x in sorted(s, key=lambda x: -x["okno_min"])[:10]: print(" ", x)
