"""BREAKOUT_M5_V2: свежая загрузка M5 Bybit (v5 kline, linear) для 13 монет Dev13, 2023-01-01 → последний закрытый бар.
Отдельная версия источника (не Dev13). Сырые ответы — gzip + sha256; MANIFEST.json с временем загрузки и проверкой сетки.
Возобновляемо (готовые месяцы пропускаются). Запуск в screen: .venv/bin/python research_lab/fabrika/dannye_breakout_m5_v2.py"""
import datetime as dt, gzip, hashlib, json, time, urllib.parse, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; OUT = LAB / "data" / "breakout_m5_v2"
SYMS = ["1000PEPEUSDT", "ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "ONDOUSDT", "SOLUSDT", "SUIUSDT", "TAOUSDT", "WIFUSDT", "XRPUSDT"]
M5 = 300000; START = dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc)
def utc(): return dt.datetime.now(dt.timezone.utc)
def get(**p):
    url = "https://api.bybit.com/v5/market/kline?" + urllib.parse.urlencode(p)
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                b = r.read(); j = json.loads(b)
                if j.get("retCode") == 0: time.sleep(0.1); return j["result"]["list"], b
                time.sleep(10 * (k + 1))
        except Exception: time.sleep(3 * (k + 1))
    raise RuntimeError(f"kline не ответил {p}")
def mesyacy(konec):
    m = START
    while m < konec:
        n = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1); yield m, min(n, konec); m = n
def main():
    konec = utc().replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1); man_p = OUT / "MANIFEST.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {"provider": "bybit v5 /v5/market/kline linear interval=5", "fayly": {}}
    for s in SYMS:
        for a, b in mesyacy(konec):
            f = OUT / s / f"{s}_{a:%Y-%m}.jsonl.gz"; key = str(f.relative_to(OUT))
            if key in man["fayly"] and b <= konec and man["fayly"][key].get("polnyy"): continue
            rows, syr, t = {}, [], int(b.timestamp() * 1000) - 1
            while t >= int(a.timestamp() * 1000):
                lst, raw = get(category="linear", symbol=s, interval="5", end=t, limit=1000); syr.append(raw)
                if not lst: break
                for x in lst:
                    ts = int(x[0])
                    if int(a.timestamp() * 1000) <= ts and ts + M5 <= int(b.timestamp() * 1000): rows[ts] = x
                t = min(int(x[0]) for x in lst) - 1
            ts_s = sorted(rows); ozh = (int(b.timestamp() * 1000) - int(a.timestamp() * 1000)) // M5
            dyry = sum(1 for p, q in zip(ts_s, ts_s[1:]) if q - p != M5)
            f.parent.mkdir(parents=True, exist_ok=True)
            data = "\n".join(json.dumps(rows[k]) for k in ts_s).encode()
            f.write_bytes(gzip.compress(data))
            (f.with_suffix(".raw.gz")).write_bytes(gzip.compress(b"\n".join(syr)))
            man["fayly"][key] = dict(strok=len(ts_s), ozhidalos=ozh, dyr=dyry, sha256=hashlib.sha256(data).hexdigest(),
                                     zagruzheno=utc().isoformat(timespec="seconds"), polnyy=b <= konec and len(ts_s) > 0)
            man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1))
            print(utc().isoformat(timespec="seconds"), s, f"{a:%Y-%m}", len(ts_s), "/", ozh, "дыр", dyry, flush=True)
    print("ГОТОВО", flush=True)
if __name__ == "__main__": main()
