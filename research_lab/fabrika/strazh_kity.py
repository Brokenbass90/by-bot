#!/usr/bin/env python3
"""strazh_kity.py — страж деградации KITY M3. СОВЕТНИК, только чтение (см. CEL_SISTEMY.md).
Статистические сигналы (R1–R4) → только РЕКОМЕНДАЦИЯ владельцу: KEEP / WATCH / REDUCE 0.5x / PAUSE, с причиной.
Размер в LIVE по статистике сам не меняется — решает владелец (GO).
Операционный отказ (R5) → AVARIYA: относится к заранее одобренным жёстким предохранителям (стоп новых входов
исполняет прод Codex автоматически). Поднять риск страж не может в принципе — у него нет такого выхода.

--zamorozit : один раз считает пороги из ИСТОРИИ (окно PRIMARY, та же сделка, что kity_m3_risk.py) и пишет
              data/kity_m3_ten/STRAZH_POROGI.json с sha256. Повторно не перезаписывает.
(без флага) : читает недельные квитанции тени (KVITANCIYA_NEDELI.json) и печатает статус по замороженным порогам.

Правила (записаны до первой недели вперёд, 06.10.2026):
 R1 просадка вперёд от пика   ≤ 1.0× исторической макс. → REDUCE_HALF; ≤ 1.5× → PAUSE
 R2 одна неделя               ≤ 1.5× худшей исторической недели → REDUCE_HALF
 R3 дрейф edge (CUSUM, сдвиг среднего к нулю; k = μ/2, порог h из бутстрепа истории
    с вычтенным средним так, что при нулевом edge сигнал в среднем через ≈ ARL0 недель — печатается) → PAUSE
 R4 одна нога                 ≤ −50% → WATCH (в истории 10 таких из 1588 ног)
 R5 две подряд PAPER_WEEK_OPERATIONAL_FAIL → PAUSE
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
TEN = LAB / "data" / "kity_m3_ten"
POR = TEN / "STRAZH_POROGI.json"
STATUSY = ["OK", "WATCH", "REDUCE_HALF", "PAUSE"]
REKOM = {"OK": "KEEP", "WATCH": "KEEP (наблюдать)", "REDUCE_HALF": "рекомендую REDUCE 0.5x — нужен GO владельца", "PAUSE": "рекомендую PAUSE — нужен GO владельца"}

def istoriya():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sudya_xs as X
    M = X.zagruzit(LAB / "data" / "binance_kity"); ned = []
    d = dt.date(2023, 1, 5)
    while d <= dt.date(2026, 9, 23):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], X.ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != X.ms(d) or i < 60: continue
            z = x["taker"].get(vch)
            if z is not None and np.isfinite(z): rows.append((z, s, i))
        if len(rows) >= 30:
            rows.sort(); k = len(rows) // 10; legs = []
            for side, part in ((-1, rows[:k]), (+1, rows[-k:])):
                for _, s, i in part:
                    r = X.sdelka(M[s], i, 7, side, 0.0012, dt.date(2026, 9, 30))
                    if r is not None: legs.append(r)
            if legs: ned.append(float(np.mean(legs)))
        d += dt.timedelta(days=7)
    return np.array(ned)

def cusum(r, mu, sd):
    s, mx = 0.0, 0.0; tr = []
    for x in r:
        s = max(0.0, s + (mu / 2 - x) / sd); tr.append(s); mx = max(mx, s)
    return np.array(tr), mx

def arl(r0, mu, sd, h, rng, n=4000, dlina=520):
    t = []
    for _ in range(n):
        s = 0.0
        for j, x in enumerate(rng.choice(r0, dlina)):
            s = max(0.0, s + (mu / 2 - x) / sd)
            if s >= h: t.append(j + 1); break
        else: t.append(dlina)
    return float(np.median(t))

def zamorozit():
    if POR.exists(): sys.exit("пороги уже заморожены: " + str(POR))
    r = istoriya(); mu, sd = float(r.mean()), float(r.std(ddof=1))
    eq = np.cumprod(1 + r); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    _, mx_ist = cusum(r, mu, sd)
    rng = np.random.default_rng(20261006); r0 = r - mu
    h = 4.0
    while arl(r - 0, mu, sd, h, rng, n=1500) < 104 and h < 20: h += 0.5   # при ИСТИННОМ edge ложная тревога реже, чем раз в 2 года
    p = dict(sozdano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), nedel=len(r),
             mu=mu, sd=sd, maks_prosadka=dd, hudshaya_nedelya=float(r.min()),
             R1_reduce=dd, R1_pause=1.5 * dd, R2_reduce=1.5 * float(r.min()), R3_h=h, R3_cusum_maks_v_istorii=mx_ist,
             R3_ARL_pri_nulevom_edge_nedel=arl(r0, mu, sd, h, rng), R3_ARL_pri_istinnom_edge_nedel=arl(r, mu, sd, h, rng),
             R4_noga=-0.50, R5_operac_fail_podryad=2)
    b = json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True).encode()
    TEN.mkdir(parents=True, exist_ok=True); POR.write_bytes(b)
    print(b.decode()); print("sha256", hashlib.sha256(b).hexdigest())

def status():
    p = json.loads(POR.read_text())
    kv = sorted(TEN.glob("*/KVITANCIYA_NEDELI.json"))
    nedeli = [json.loads(f.read_text()) for f in kv]
    r = [w["nedelya_bps_spravochno"] / 1e4 for w in nedeli if w.get("nedelya_bps_spravochno") is not None]
    flagi = []
    if r:
        eq = np.cumprod(1 + np.array(r)); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        if dd <= p["R1_pause"]: flagi.append(("PAUSE", f"R1 просадка {dd:.1%}"))
        elif dd <= p["R1_reduce"]: flagi.append(("REDUCE_HALF", f"R1 просадка {dd:.1%}"))
        if min(r) <= p["R2_reduce"]: flagi.append(("REDUCE_HALF", f"R2 неделя {min(r):.1%}"))
        tr, _ = cusum(r, p["mu"], p["sd"])
        if tr[-1] >= p["R3_h"]: flagi.append(("PAUSE", f"R3 CUSUM {tr[-1]:.2f} ≥ {p['R3_h']}"))
    for f in sorted(TEN.glob("*/vyhod.json")):
        for n in json.loads(f.read_text()).get("nogi", []):
            if n.get("dohod") is not None and n["dohod"] <= p["R4_noga"]:
                flagi.append(("WATCH", f"R4 нога {n.get('s') or n.get('sym')} {n['dohod']:.0%} ({f.parent.name})"))
    st = [w["status"] for w in nedeli]
    if len(st) >= 2 and all(s == "PAPER_WEEK_OPERATIONAL_FAIL" for s in st[-2:]): flagi.append(("PAUSE", "R5 две операционные FAIL подряд"))
    avariya = [f for f in flagi if f[1].startswith("R5")]
    stat = [f for f in flagi if not f[1].startswith("R5")]
    itog = max([f[0] for f in stat], key=STATUSY.index, default="OK")
    print(json.dumps(dict(status=itog, rekomendaciya=REKOM[itog], avtomatom_v_live="ничего (статистика — только совет)",
                          avariya_stop_novyh_vhodov=bool(avariya), avariya_prichiny=[a[1] for a in avariya],
                          nedel_vpered=len(r), flagi=stat,
                          porogi_sha256=hashlib.sha256(POR.read_bytes()).hexdigest()), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    zamorozit() if "--zamorozit" in sys.argv else status()
