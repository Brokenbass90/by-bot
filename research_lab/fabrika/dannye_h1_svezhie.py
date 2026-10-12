#!/usr/bin/env python3
"""Свежие H1 Bybit linear для варианта «ложный пробой | NEUTRAL» (POSTMORTEM_LOZHNYY_PROBOY_I_VARIANT_2026_10_12).
Символы = файлы data/h1 кроме Dev13, плюс BTCUSDT (для REZHIM_V1). Период 2026-04-15 … 2026-10-03 (прогрев REZHIM ≥ 200 4h-баров,
окно события 51 бар, удержание 48 ч). Только закрытые бары. Пишет data/h1_svezhie/<SYM>.npz (ts, ohlcv) + MANIFEST.json.
    .venv/bin/python research_lab/fabrika/dannye_h1_svezhie.py
"""
import datetime as dt, glob, hashlib, json, time, urllib.parse, urllib.request
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; OUT = LAB / "data/h1_svezhie"; H = 3_600_000
DEV13 = {"1000PEPEUSDT", "ADAUSDT", "AVAXUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT", "ONDOUSDT", "SOLUSDT", "SUIUSDT",
         "TAOUSDT", "WIFUSDT", "XRPUSDT"}                       # BTCUSDT нужен для режима
S0 = int(dt.datetime(2026, 4, 15, tzinfo=dt.timezone.utc).timestamp() * 1000)
S1 = int(dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc).timestamp() * 1000)


def get(**p):
    url = "https://api.bybit.com/v5/market/kline?" + urllib.parse.urlencode(p)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                j = json.loads(r.read()); time.sleep(0.1)
                if j.get("retCode") == 0: return j["result"]["list"]
        except Exception: pass
        time.sleep(3 * (k + 1))
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sim = sorted({Path(f).stem for f in glob.glob(str(LAB / "data/h1/*.npz"))} - DEV13)
    man = {}
    for s in sim:
        rows, nach = {}, S0
        while nach < S1:
            lst = get(category="linear", symbol=s, interval="60", start=nach, end=min(S1, nach + 1000 * H) - 1, limit=1000)
            if lst is None: break
            for x in lst:
                t = int(x[0])
                if S0 <= t and t + H <= min(S1, int(time.time() * 1000)): rows[t] = [float(x[i]) for i in (1, 2, 3, 4, 5)]
            nach += 1000 * H
        if not rows: man[s] = "net_dannyh"; continue
        ts = np.array(sorted(rows), dtype=np.int64); o = np.array([rows[t] for t in ts])
        np.savez(OUT / f"{s}.npz", ts=ts, ohlcv=o)
        man[s] = dict(barov=len(ts), dyr=int((np.diff(ts) != H).sum()), sha256=hashlib.sha256((OUT / f"{s}.npz").read_bytes()).hexdigest())
        print(s, man[s] if isinstance(man[s], str) else (man[s]["barov"], man[s]["dyr"]), flush=True)
    (OUT / "MANIFEST.json").write_text(json.dumps(dict(zagruzheno=dt.datetime.now(dt.timezone.utc).isoformat(), S0=S0, S1=S1, simvoly=man), indent=1))
    print("ГОТОВО", len(man))


if __name__ == "__main__":
    main()
