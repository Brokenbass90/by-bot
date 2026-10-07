"""Проба источника потока тейкеров Bybit: публичный архив сделок public.bybit.com/trading/<SYM>/<SYM><дата>.csv.gz
(каждая сделка со стороной агрессора). Читает потоком, НЕ сохраняет сырые файлы — только агрегат дня.
Цель: понять вес и скорость, чтобы решить, можно ли историческую репликацию KITY M3 на Bybit (топ-50, день d−1 по четвергам).
Запуск: python3 research_lab/fabrika/bybit_arhiv_proba.py [дата YYYY-MM-DD] [SYM ...]"""
import csv, gzip, io, sys, time, urllib.request
URL = "https://public.bybit.com/trading/{s}/{s}{d}.csv.gz"

def den(sym, d):
    t0 = time.time(); req = urllib.request.Request(URL.format(s=sym, d=d), headers={"User-Agent": "research-paper"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    t1 = time.time(); buy = sell = 0.0; n = 0
    rd = csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding="utf-8"))
    for row in rd:
        v = float(row.get("foreignNotional") or 0) or float(row["size"]) * float(row["price"])
        if row["side"] == "Buy": buy += v
        else: sell += v
        n += 1
    return dict(sym=sym, den=d, mb=round(len(raw) / 1e6, 2), sdelok=n, dolya_pokupok=round(buy / (buy + sell), 4) if buy + sell else None,
                oborot_musd=round((buy + sell) / 1e6, 1), sek_zagruzki=round(t1 - t0, 1), sek_razbora=round(time.time() - t1, 1),
                kolonki=rd.fieldnames)

if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "2026-10-05"
    syms = sys.argv[2:] or ["BTCUSDT", "SOLUSDT", "ADAUSDT", "WLDUSDT"]
    for s in syms:
        try: print(den(s, d), flush=True)
        except Exception as e: print(s, "ОШИБКА", type(e).__name__, str(e)[:200], flush=True)
