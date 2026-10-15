#!/usr/bin/env python3
"""dannye_coinbase.py — дневные свечи Coinbase Exchange (USD) для монет Binance-перпов + измерения БЕЗ доходностей
для PREREG_COINBASE_PREMIYA_XS_2026_10_15.md. Только публичный API, без ключей. Запуск на Маке (нужна сеть), в screen:
    .venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py coinbase -- .venv/bin/python research_lab/fabrika/dannye_coinbase.py
Пишет data/coinbase_d1/<SYMBOL>.json = {"YYYY-MM-DD": close} и MANIFEST.json. Конвейер Фабрики запускает тест САМ,
когда в MANIFEST gotovo=true, а gotovo ставится только если прошли все три замороженных измерения (prereg).
"""
import datetime as dt, hashlib, json, statistics, sys, time, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; OUT = LAB / "data" / "coinbase_d1"
API = "https://api.exchange.coinbase.com"
OT, DO = dt.date(2022, 11, 1), dt.date(2026, 9, 30)
POROG = dict(mediana_pokrytiya=20, nedel_s_pokrytiem=104, korr_s_m3_max=0.5)          # заморожено в prereg


def get(put):
    for popytka in range(5):
        try:
            r = urllib.request.Request(API + put, headers={"User-Agent": "trading-os-research/1.0"})
            with urllib.request.urlopen(r, timeout=30) as f: return json.loads(f.read().decode())
        except Exception as e:
            if popytka == 4: raise
            time.sleep(2 + 3 * popytka)


def skachat():
    sys.path.insert(0, str(LAB / "factory_v3")); import ferma_shablony as F
    M = F._dannye()["M"]
    prod = {p["base_currency"]: p["id"] for p in get("/products") if p.get("quote_currency") == "USD"}
    OUT.mkdir(parents=True, exist_ok=True); est = {}
    for s in sorted(M):
        if not s.endswith("USDT") or s.startswith("1000"): continue
        pid = prod.get(s[:-4])
        if not pid: continue
        fp = OUT / f"{s}.json"
        if fp.exists(): est[s] = pid; continue
        r, a = {}, OT
        while a <= DO:
            b = min(DO, a + dt.timedelta(days=290))
            for c in get(f"/products/{pid}/candles?granularity=86400&start={a.isoformat()}T00:00:00Z&end={b.isoformat()}T23:59:59Z") or []:
                d = dt.datetime.fromtimestamp(int(c[0]), dt.timezone.utc).date()
                if OT <= d <= DO and float(c[4]) > 0: r[d.isoformat()] = float(c[4])
            a = b + dt.timedelta(days=1); time.sleep(0.25)
        fp.write_text(json.dumps(dict(sorted(r.items())))); est[s] = pid
        print(s, pid, len(r), flush=True)
    return est


def izmereniya():
    """Без доходностей: покрытие топ-50 по неделям, разброс признака, связь с KITY m3_perp."""
    sys.path.insert(0, str(LAB / "factory_v3")); sys.path.insert(0, str(LAB)); import ferma_shablony as F, kity_sudya as K
    import numpy as np
    D = F._dannye(); M = D["M"]; cb = F._priznak("cb_premiya", D); m3 = F._priznak("m3_perp", D)
    pokr, korr, razbros = [], [], []
    for d in K.SETKA:
        if not dt.date(2023, 1, 1) <= d <= dt.date(2026, 9, 23): continue
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        pary = [(cb(s, vch), m3(s, vch)) for _, s in oi]; pary = [(a, b) for a, b in pary if a is not None]
        pokr.append(len(pary))
        if len(pary) >= 20:
            razbros.append(float(np.std([a for a, _ in pary])))
            bb = [(a, b) for a, b in pary if b is not None]
            if len(bb) >= 20: korr.append(float(np.corrcoef([a for a, _ in bb], [b for _, b in bb])[0, 1]))
    rez = dict(nedel=len(pokr), mediana_pokrytiya=statistics.median(pokr) if pokr else 0, nedel_s_pokrytiem=sum(p >= 20 for p in pokr),
               razbros_premii_mediana_bps=round(statistics.median(razbros) * 1e4, 2) if razbros else None,
               korr_s_m3_mediana=round(statistics.median(korr), 3) if korr else None)
    rez["uslovia"] = {"pokrytie": rez["mediana_pokrytiya"] >= POROG["mediana_pokrytiya"],
                      "nedeli": rez["nedel_s_pokrytiem"] >= POROG["nedel_s_pokrytiem"],
                      "nezavisimost_ot_kity": rez["korr_s_m3_mediana"] is not None and abs(rez["korr_s_m3_mediana"]) < POROG["korr_s_m3_max"]}
    return rez


if __name__ == "__main__":
    est = skachat(); iz = izmereniya()
    h = hashlib.sha256()
    for fp in sorted(OUT.glob("*USDT.json")): h.update(fp.name.encode()); h.update(fp.read_bytes())
    man = dict(dataset="coinbase_d1", istochnik=API + "/products/{id}/candles granularity=86400", period=[OT.isoformat(), DO.isoformat()],
               monet=len(est), sha256=h.hexdigest(), sobrano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               izmereniya=iz, porogi=POROG, gotovo=all(iz["uslovia"].values()),
               status="DATA_READY" if all(iz["uslovia"].values()) else "BLOCKED_BY_MEASUREMENT")
    (OUT / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1)); print(json.dumps(man, ensure_ascii=False, indent=1))
