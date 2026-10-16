#!/usr/bin/env python3
"""dannye_obem_ploshchadok.py — дневной ОБЪЁМ (в базовой монете) на Coinbase USD и Upbit KRW для монет Binance-перпов
(PREREG_DOLYA_OBEMA_PLOSHCHADOK_2026_10_16). Только загрузка: измерения без доходностей и тест конвейер Фабрики делает сам.
    .venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py obem -- .venv/bin/python research_lab/fabrika/dannye_obem_ploshchadok.py
Пишет data/obem_coinbase_d1/, data/obem_upbit_d1/ (<SYMBOL>.json = {"YYYY-MM-DD": объём}) и MANIFEST.json (gotovo=true после загрузки).
"""
import datetime as dt, hashlib, json, sys, time, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]
OT, DO = dt.date(2022, 11, 1), dt.date(2026, 9, 30)


def get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "trading-os-research/1.0", "Accept": "application/json"}), timeout=30) as f:
                return json.loads(f.read().decode())
        except Exception:
            if k == 4: raise
            time.sleep(2 + 3 * k)


def simvoly():
    return sorted(p.stem for p in (LAB / "data" / "binance_kity" / "klines").glob("*USDT.json") if not p.stem.startswith("1000"))


def coinbase(out):
    prod = {p["base_currency"]: p["id"] for p in get("https://api.exchange.coinbase.com/products") if p.get("quote_currency") == "USD"}
    for s in simvoly():
        pid = prod.get(s[:-4]); fp = out / f"{s}.json"
        if not pid or fp.exists(): continue
        r, a = {}, OT
        while a <= DO:
            b = min(DO, a + dt.timedelta(days=290))
            for c in get(f"https://api.exchange.coinbase.com/products/{pid}/candles?granularity=86400&start={a}T00:00:00Z&end={b}T23:59:59Z") or []:
                d = dt.datetime.fromtimestamp(int(c[0]), dt.timezone.utc).date()
                if OT <= d <= DO: r[d.isoformat()] = float(c[5])
            a = b + dt.timedelta(days=1); time.sleep(0.25)
        fp.write_text(json.dumps(dict(sorted(r.items())))); print("coinbase", s, len(r), flush=True)


def upbit(out):
    rynki = {m["market"].split("-", 1)[1]: m["market"] for m in get("https://api.upbit.com/v1/market/all") if m["market"].startswith("KRW-")}
    for s in simvoly():
        mk = rynki.get(s[:-4]); fp = out / f"{s}.json"
        if not mk or fp.exists(): continue
        r, do = {}, DO + dt.timedelta(days=1)
        while do > OT:
            lst = get(f"https://api.upbit.com/v1/candles/days?market={mk}&count=200&to={do}T00:00:00Z") or []
            if not lst: break
            for c in lst:
                d = dt.date.fromisoformat(c["candle_date_time_utc"][:10])
                if OT <= d <= DO: r[d.isoformat()] = float(c["candle_acc_trade_volume"])
            novoe = min(dt.date.fromisoformat(c["candle_date_time_utc"][:10]) for c in lst)
            if novoe >= do: break
            do = novoe; time.sleep(0.15)
        fp.write_text(json.dumps(dict(sorted(r.items())))); print("upbit", s, len(r), flush=True)


if __name__ == "__main__":
    for imya, fn in (("coinbase", coinbase), ("upbit", upbit)):
        out = LAB / "data" / f"obem_{imya}_d1"; out.mkdir(parents=True, exist_ok=True); fn(out)
        h = hashlib.sha256()
        for fp in sorted(out.glob("*USDT.json")): h.update(fp.name.encode()); h.update(fp.read_bytes())
        (out / "MANIFEST.json").write_text(json.dumps(dict(dataset=f"obem_{imya}_d1", monet=len(list(out.glob("*USDT.json"))), sha256=h.hexdigest(),
                                                           sobrano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), gotovo=True), ensure_ascii=False))
        print(imya, "MANIFEST gotovo", flush=True)
