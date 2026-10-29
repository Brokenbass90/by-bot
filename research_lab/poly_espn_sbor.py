#!/usr/bin/env python3
"""poly_espn_sbor.py — поток фактов для Polymarket: счёт и статус матчей ESPN раз в минуту (29.10.2026, Claude). Только чтение, без ключей.
Источник — неофициальный публичный JSON ESPN (site.api.espn.com/.../scoreboard; не официальный API, может измениться — пишем ошибки, не падаем).
Зачем: проверить «факт быстрее цены» — момент, когда матч стал FINAL (или счёт решающий), против момента, когда цена Polymarket дошла до 0.95 (монитор).
Пишется только изменение состояния матча. Выход data/poly_espn/matchi.jsonl. Запуск вручную рядом с монитором:
    screen -S espn .venv/bin/python3 research_lab/poly_espn_sbor.py"""
import json, time, urllib.request
from pathlib import Path
OUT = Path(__file__).resolve().parent / "data" / "poly_espn"; OUT.mkdir(parents=True, exist_ok=True); ZH = OUT / "matchi.jsonl"
LIGI = ["basketball/nba", "hockey/nhl", "football/nfl", "baseball/mlb", "football/college-football", "basketball/mens-college-basketball",
        "soccer/eng.1", "soccer/esp.1", "soccer/ita.1", "soccer/ger.1", "soccer/fra.1", "soccer/uefa.champions", "soccer/usa.1"]

def main():
    prosh = {}
    while True:
        t0 = time.time()
        for lg in LIGI:
            try:
                with urllib.request.urlopen(urllib.request.Request(f"https://site.api.espn.com/apis/site/v2/sports/{lg}/scoreboard", headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
                    d = json.loads(r.read())
            except Exception as e:
                with ZH.open("a") as f: f.write(json.dumps(dict(t=int(t0), liga=lg, oshibka=str(e)[:80])) + "\n")
                continue
            for ev in d.get("events") or []:
                try:
                    c = ev["competitions"][0]; stt = c["status"]["type"]
                    kom = [(x["team"].get("displayName"), x.get("score"), x.get("homeAway"), x.get("winner")) for x in c["competitors"]]
                    sost = (stt.get("state"), stt.get("completed"), tuple(k[1] for k in kom), c["status"].get("period"))
                    if prosh.get(ev["id"]) == sost: continue
                    prosh[ev["id"]] = sost
                    with ZH.open("a") as f:
                        f.write(json.dumps(dict(t=int(time.time()), liga=lg, id=ev["id"], nazvanie=ev.get("name"), start=ev.get("date"), state=stt.get("state"),
                                                completed=stt.get("completed"), detal=stt.get("shortDetail"), period=c["status"].get("period"),
                                                clock=c["status"].get("displayClock"), komandy=kom), ensure_ascii=False) + "\n")
                except Exception: continue
            time.sleep(0.5)
        time.sleep(max(5, 60 - (time.time() - t0)))

if __name__ == "__main__":
    main()
