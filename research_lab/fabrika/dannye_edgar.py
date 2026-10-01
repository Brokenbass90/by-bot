#!/usr/bin/env python3
"""dannye_edgar.py — даты и точное время отчётностей компаний США из SEC EDGAR (новый класс данных №1, 01.10).

Что берём: для каждой компании из справочника акций (активные + снятые с торгов после 2024-08, т.е. та же
вселенная без смещения выживших, что и дневки) — список подач из data.sec.gov/submissions:
8-K с пунктом 2.02 («результаты деятельности» = пресс-релиз отчётности) и 10-Q/10-K, с acceptanceDateTime
(точное время приёма SEC: до открытия / после закрытия рынка). Только публичные данные, без ключей.
Правила SEC: ≤ 10 запросов/с и User-Agent с контактом — здесь пауза 0.15 с.
Можно прерывать: обработанные CIK пропускаются.

    python3 dannye_edgar.py          ≈ 7 000 компаний ≈ 20–30 минут
Кладёт research_lab/data/edgar/otchety.jsonl: {"cik","tickers","sobytiya":[[acceptanceDateTime, form, items], ...]}
"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
SPR = LAB / "data/akcii_grouped"; OUT = LAB / "data/edgar"; OUT.mkdir(parents=True, exist_ok=True)
FAYL = OUT / "otchety.jsonl"
UA = {"User-Agent": "bybit-bot-research research-lab@users.noreply.github.com", "Accept-Encoding": "identity"}
PAUZA = 0.15; OT = "2024-08-01"
FORMY = {"8-K", "8-K/A", "10-Q", "10-K", "10-Q/A", "10-K/A"}


def kompanii():
    k = {}
    for f, aktiv in (("spravochnik_active.json", True), ("spravochnik_inactive.json", False)):
        for r in json.load(open(SPR / f)):
            if not r.get("cik") or (not aktiv and (r.get("delisted_utc") or "") < OT):
                continue
            k.setdefault(r["cik"].zfill(10), set()).add(r["ticker"])
    return k


def zapros(url):
    for popytka in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429):
                print(f"SEC ответил {e.code} — пауза 60 с", flush=True); time.sleep(60)
            else:
                time.sleep(5)
        except Exception:
            time.sleep(5)
    return None


def main():
    gotovo = {json.loads(l)["cik"] for l in FAYL.open() if l.strip()} if FAYL.exists() else set()
    K = kompanii(); ost = [c for c in sorted(K) if c not in gotovo]
    print(f"компаний {len(K)}, уже есть {len(gotovo)}, качаем {len(ost)}", flush=True)
    with FAYL.open("a") as f:
        for n, cik in enumerate(ost, 1):
            d = zapros(f"https://data.sec.gov/submissions/CIK{cik}.json")
            sob = []
            if d:
                r = d.get("filings", {}).get("recent", {})
                for fm, acc, it, fd in zip(r.get("form", []), r.get("acceptanceDateTime", []),
                                           r.get("items", []), r.get("filingDate", [])):
                    if fm in FORMY and fd >= OT and (not fm.startswith("8-K") or "2.02" in (it or "")):
                        sob.append([acc, fm, it])
            f.write(json.dumps({"cik": cik, "tickers": sorted(K[cik]), "ok": d is not None, "sobytiya": sob}) + "\n")
            if n % 250 == 0:
                f.flush(); print(f"{n}/{len(ost)}", flush=True)
            time.sleep(PAUZA)
    print("готово")


if __name__ == "__main__":
    main()
