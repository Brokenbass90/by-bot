"""Загрузка потока тейкеров Bybit для PREREG_KITY_BYBIT_ARHIV: для каждого четверга d — день d−1 по монетам sostav[d].
Архив сделок читается потоком в памяти, на диск пишется ТОЛЬКО агрегат дня (buy/sell notional, число сделок, sha256 файла).
Возобновляемо: готовые пропускаются. 4 потока. Нет файла (404) → записывается net=1 (честная дыра).
Запуск в screen:  python3 research_lab/fabrika/dannye_bybit_potok.py   (лог: data/bybit_potok.log)"""
import concurrent.futures as cf, csv, datetime as dt, gzip, hashlib, io, json, sys, time, urllib.error, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "data" / "bybit_potok"
URL = "https://public.bybit.com/trading/{s}/{s}{d}.csv.gz"

def agregat(sym, den):
    f = OUT / den / f"{sym}.json"
    if f.exists(): return "uzhe"
    for k in range(4):
        try:
            req = urllib.request.Request(URL.format(s=sym, d=den), headers={"User-Agent": "research-paper"})
            with urllib.request.urlopen(req, timeout=180) as r: raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps({"net": 1})); return "404"
            time.sleep(5 * (k + 1))
        except Exception:
            time.sleep(5 * (k + 1))
    else:
        return "oshibka"
    buy = sell = 0.0; n = 0
    for row in csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding="utf-8")):
        try: v = float(row.get("foreignNotional") or 0) or float(row["size"]) * float(row["price"])
        except (TypeError, ValueError): continue
        if row["side"] == "Buy": buy += v
        else: sell += v
        n += 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"buy": buy, "sell": sell, "n": n, "sha256": hashlib.sha256(raw).hexdigest(), "mb": round(len(raw) / 1e6, 2)}))
    return "ok"

def main():
    sostav = json.loads((LAB / "data/basis/vselennaya_pit_usd50.json").read_text())["sostav"]
    zadachi = []; d = dt.date(2023, 1, 5)
    while d <= dt.date(2026, 9, 24):
        for s in sostav.get(d.isoformat(), []):
            zadachi.append((s, (d - dt.timedelta(days=1)).isoformat()))
        d += dt.timedelta(days=7)
    print(f"{dt.datetime.utcnow():%Y-%m-%dT%H:%M} задач {len(zadachi)}", flush=True)
    st = {}; t0 = time.time()
    with cf.ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(lambda z: agregat(*z), zadachi), 1):
            st[r] = st.get(r, 0) + 1
            if i % 100 == 0:
                print(f"{dt.datetime.utcnow():%Y-%m-%dT%H:%M} {i}/{len(zadachi)} {st} {round((time.time()-t0)/60)} мин", flush=True)
    print("ГОТОВО", st, flush=True)

if __name__ == "__main__":
    main()
