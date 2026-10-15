#!/usr/bin/env python3
"""dannye_upbit.py — дневные свечи Upbit (KRW) для монет Binance-перпов + измерения БЕЗ доходностей для
PREREG_UPBIT_PREMIYA_XS_2026_10_15.md. Публичный API без ключей; запуск на Маке в screen:
    .venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py upbit -- .venv/bin/python research_lab/fabrika/dannye_upbit.py
Дневная свеча Upbit начинается 00:00 UTC (09:00 KST) — совпадает с днём Binance. Пишет data/upbit_d1/<SYMBOL>.json и MANIFEST.json;
gotovo=true только если прошли ЧЕТЫРЕ замороженных измерения — тогда конвейер Фабрики запускает тест сам.
"""
import datetime as dt, hashlib, json, statistics, sys, time, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; OUT = LAB / "data" / "upbit_d1"
API = "https://api.upbit.com/v1"
OT, DO = dt.date(2022, 11, 1), dt.date(2026, 9, 30)
POROG = dict(mediana_pokrytiya=20, nedel_s_pokrytiem=104, korr_s_m3_max=0.5, mediana_modulya_bps=12.0)   # заморожено в prereg


def get(put):
    for popytka in range(5):
        try:
            r = urllib.request.Request(API + put, headers={"User-Agent": "trading-os-research/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(r, timeout=30) as f: return json.loads(f.read().decode())
        except Exception:
            if popytka == 4: raise
            time.sleep(2 + 3 * popytka)


def skachat():
    sys.path.insert(0, str(LAB / "factory_v3")); import ferma_shablony as F
    M = F._dannye()["M"]
    rynki = {m["market"].split("-", 1)[1]: m["market"] for m in get("/market/all") if m["market"].startswith("KRW-")}
    OUT.mkdir(parents=True, exist_ok=True); est = {}
    for s in sorted(M):
        if not s.endswith("USDT") or s.startswith("1000"): continue
        mk = rynki.get(s[:-4])
        if not mk: continue
        fp = OUT / f"{s}.json"
        if fp.exists(): est[s] = mk; continue
        r, do = {}, DO + dt.timedelta(days=1)
        while do > OT:
            lst = get(f"/candles/days?market={mk}&count=200&to={do.isoformat()}T00:00:00Z") or []
            if not lst: break
            for c in lst:
                d = dt.date.fromisoformat(c["candle_date_time_utc"][:10])
                if OT <= d <= DO and float(c["trade_price"]) > 0: r[d.isoformat()] = float(c["trade_price"])
            novoe = min(dt.date.fromisoformat(c["candle_date_time_utc"][:10]) for c in lst)
            if novoe >= do: break
            do = novoe; time.sleep(0.15)
        fp.write_text(json.dumps(dict(sorted(r.items())))); est[s] = mk
        print(s, mk, len(r), flush=True)
    return est


def izmereniya():
    sys.path.insert(0, str(LAB / "factory_v3")); sys.path.insert(0, str(LAB)); import ferma_shablony as F, kity_sudya as K
    import numpy as np
    D = F._dannye(); M = D["M"]; up = F._priznak("up_premiya", D); m3 = F._priznak("m3_perp", D)
    pokr, korr, modul = [], [], []
    for d in K.SETKA:
        if not dt.date(2023, 1, 1) <= d <= dt.date(2026, 9, 23): continue
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        pary = [(up(s, vch), m3(s, vch)) for _, s in oi]; pary = [(a, b) for a, b in pary if a is not None]
        pokr.append(len(pary)); modul += [abs(a) for a, _ in pary]
        bb = [(a, b) for a, b in pary if b is not None]
        if len(bb) >= 20: korr.append(float(np.corrcoef([a for a, _ in bb], [b for _, b in bb])[0, 1]))
    rez = dict(nedel=len(pokr), mediana_pokrytiya=statistics.median(pokr) if pokr else 0, nedel_s_pokrytiem=sum(p >= 20 for p in pokr),
               korr_s_m3_mediana=round(statistics.median(korr), 3) if korr else None,
               mediana_modulya_bps=round(statistics.median(modul) * 1e4, 2) if modul else 0.0)
    rez["uslovia"] = {"pokrytie": rez["mediana_pokrytiya"] >= POROG["mediana_pokrytiya"],
                      "nedeli": rez["nedel_s_pokrytiem"] >= POROG["nedel_s_pokrytiem"],
                      "nezavisimost_ot_kity": rez["korr_s_m3_mediana"] is not None and abs(rez["korr_s_m3_mediana"]) < POROG["korr_s_m3_max"],
                      "velichina_vyshe_izderzhek": rez["mediana_modulya_bps"] >= POROG["mediana_modulya_bps"]}
    return rez


if __name__ == "__main__":
    est = skachat(); iz = izmereniya()
    h = hashlib.sha256()
    for fp in sorted(OUT.glob("*USDT.json")): h.update(fp.name.encode()); h.update(fp.read_bytes())
    man = dict(dataset="upbit_d1", istochnik=API + "/candles/days", period=[OT.isoformat(), DO.isoformat()], monet=len(est),
               sha256=h.hexdigest(), sobrano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), izmereniya=iz, porogi=POROG,
               gotovo=all(iz["uslovia"].values()), status="DATA_READY" if all(iz["uslovia"].values()) else "BLOCKED_BY_MEASUREMENT")
    (OUT / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1)); print(json.dumps(man, ensure_ascii=False, indent=1))
