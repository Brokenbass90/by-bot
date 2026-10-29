#!/usr/bin/env python3
"""alpaca_sobytiya_audit.py — ограниченный аудит событийных данных для Alpaca (29.10.2026, Claude; задание PM: проверить источник, без нового сборщика).
Источник: SEC EDGAR (бесплатно, официально, с точным временем подачи): company_tickers.json → CIK; submissions/CIK*.json → формы 8-K с пунктом 2.02
(«Results of Operations» = публикация квартальной отчётности) и время acceptanceDateTime (до/после торгов). Только чтение, ~1 мин.
Пишет data/alpaca_sobytiya/otchetnosti.json и печатает покрытие по бумагам. Индексные изменения: бесплатной истории с точным временем объявления
для бумаг ВНЕ индекса у нас нет (наши 58 бумаг почти все уже в S&P 500) — это блокер, не собираем.
    .venv/bin/python3 research_lab/alpaca_sobytiya_audit.py ~/Documents/Work/bot-new/alpaca-wt-20260907/data_cache/equities_daily_10y"""
import json, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; OUT = HERE / "data" / "alpaca_sobytiya"; OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "TradingResearch research@example.com"}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r: return json.loads(r.read())
def main():
    tick = sorted(p.stem.replace("_M5", "") for p in Path(sys.argv[1]).glob("*_M5.csv") if p.stem not in ("SPY_M5", "QQQ_M5"))
    mp = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
    out = {}
    for t in tick:
        c = mp.get(t if t != "XYZ" else "XYZ")
        if not c: print(t, "нет CIK"); continue
        try: d = get(f"https://data.sec.gov/submissions/CIK{c}.json")
        except Exception as e: print(t, "ошибка", str(e)[:60]); continue
        sob = []
        def berem(r):
            for f, it, acc, fd in zip(r["form"], r.get("items", [""] * len(r["form"])), r["acceptanceDateTime"], r["filingDate"]):
                if f == "8-K" and "2.02" in (it or ""): sob.append(dict(data=fd, prinyato=acc))
        berem(d["filings"]["recent"])
        for fl in d["filings"].get("files", []):
            try: berem(get("https://data.sec.gov/submissions/" + fl["name"])); time.sleep(0.15)
            except Exception: pass
        sob = sorted({s["prinyato"]: s for s in sob}.values(), key=lambda s: s["prinyato"])
        out[t] = sob
        s15 = [s for s in sob if s["data"] >= "2015-01-01"]
        print(f"{t:6s} отчётностей с 2015: {len(s15):3d}  первая {s15[0]['data'] if s15 else '-'}  последняя {s15[-1]['data'] if s15 else '-'}")
        time.sleep(0.15)
    (OUT / "otchetnosti.json").write_text(json.dumps(out, ensure_ascii=False))
    n = [len([s for s in v if s["data"] >= "2015-01-01"]) for v in out.values()]
    print("ИТОГ: бумаг", len(out), "из", len(tick), "| событий с 2015:", sum(n), "| медиана на бумагу", sorted(n)[len(n) // 2] if n else 0)
if __name__ == "__main__":
    main()
