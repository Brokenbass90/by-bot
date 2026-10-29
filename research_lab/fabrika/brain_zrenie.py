#!/usr/bin/env python3
"""brain_zrenie.py — рыночное зрение Brain v1 (27.10.2026, Claude; путь развития интеллекта, ступень 3). Хук сторожа.
Шире режима BTC: по топ-100 ликвидным перпам Binance на закрытии каждого дня (известно до сигналов следующего дня):
  shirota_rosta — доля монет с ростом за день; alt_minus_btc_7d — средняя 7-дн доходность альтов минус BTC;
  sinhron_tejker — среднее по монетам отклонения доли тейкера-покупателя от её 28-дн нормы (общая агрессия покупателей);
  shirota_obema — доля монет с объёмом > 1.5 × 28-дн нормы; disp_ret — разброс дневных доходностей (синхронность: мало = все вместе).
Каждой записи журнала ног ставится зрение последнего ЗАКРЫТОГО дня до сигнала. Сводка: исход ноги в верхней и нижней трети признака
(описательно; правило из этого — только prereg и проверка вперёд). Только с 2026-09-01 (вне запечатанного окна). Ордеров нет.
Выход: data/brain_shadow_v1/zrenie_dni.json, zrenie_svodka.json."""
import json, math, statistics as st, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data" / "brain_shadow_v1"
sys.path.insert(0, str(LAB / "fabrika")); import fabrika_vpered as FV
DEN = FV.DEN; OT = 1788220800000                                           # 2026-09-01 UTC
PRIZNAKI = ["shirota_rosta", "alt_minus_btc_7d", "sinhron_tejker", "shirota_obema", "disp_ret"]

def dni():
    dan = FV.zagruzka(); posl = max(max(r["klines"]) for r in dan.values()); out = {}
    t = OT
    while t <= posl:
        A = {s: FV.atomy_dnya(r, t) for s, r in dan.items()}; A = {s: v for s, v in A.items() if v}
        liq = sorted(A, key=lambda s: -A[s]["_oborot28"])[:FV.TOP]
        if len(liq) < 50: t += DEN; continue
        r1 = [A[s]["mom1"] for s in liq if A[s].get("mom1") is not None]
        btc7 = (A.get("BTCUSDT") or {}).get("mom7")
        m7 = [A[s]["mom7"] for s in liq if s != "BTCUSDT" and A[s].get("mom7") is not None]
        vs = [A[s]["m3_vsplesk"] for s in liq if A[s].get("m3_vsplesk") is not None]
        ob = [A[s]["obem_vsplesk"] for s in liq if A[s].get("obem_vsplesk") is not None]
        out[str(t)] = dict(shirota_rosta=round(sum(x > 0 for x in r1) / len(r1), 3) if r1 else None,
                           alt_minus_btc_7d=round(st.mean(m7) - btc7, 4) if m7 and btc7 is not None else None,
                           sinhron_tejker=round(st.mean(vs), 4) if vs else None,
                           shirota_obema=round(sum(x > 0.5 for x in ob) / len(ob), 3) if ob else None,
                           disp_ret=round(st.pstdev(r1), 4) if len(r1) > 2 else None)
        t += DEN
    return out

def prohod():
    Z = dni(); (D / "zrenie_dni.json").write_text(json.dumps(Z, ensure_ascii=False))
    zap = [json.loads(l) for l in (D / "zhurnal_nog.jsonl").open()] if (D / "zhurnal_nog.jsonl").exists() else []
    ks = sorted(int(k) for k in Z)
    def zr(ts):
        d = ts // DEN * DEN - DEN                                           # последний закрытый день
        return Z.get(str(d))
    sv = {}
    for noga in sorted({z["noga"] for z in zap}):
        g = [(z["ishod"], zr(z["t_signala"])) for z in zap if z["noga"] == noga and z.get("ishod") is not None and z["t_signala"] >= OT]
        g = [(x, v) for x, v in g if v]
        sv[noga] = dict(n=len(g))
        if len(g) < 15: continue
        for p in PRIZNAKI:
            h = sorted([(v[p], x) for x, v in g if v.get(p) is not None])
            if len(h) < 15: continue
            k = len(h) // 3; niz, verh = [x for _, x in h[:k]], [x for _, x in h[-k:]]
            def m(a): return dict(n=len(a), sred=round(st.mean(a), 4), se=round(st.stdev(a) / math.sqrt(len(a)), 4) if len(a) > 2 else None)
            sv[noga][p] = dict(nizhnyaya_tret=m(niz), verhnyaya_tret=m(verh), granicy=[h[k - 1][0], h[-k][0]],
                               raznica=round(st.mean(verh) - st.mean(niz), 4))
    # детектор новизны (PM/DeepSeek 29.10): признаки последнего дня против 60 предыдущих; |z| ≥ 3 хоть по одному → режим НОВЫЙ, Brain «не знает»
    ks_ = sorted(Z, key=int); nov = {}
    if len(ks_) > 20:
        posl = Z[ks_[-1]]; ist = [Z[k] for k in ks_[-61:-1]]
        for p_ in PRIZNAKI:
            h = [v[p_] for v in ist if v.get(p_) is not None]
            if len(h) > 10 and posl.get(p_) is not None and st.pstdev(h) > 0: nov[p_] = round((posl[p_] - st.mean(h)) / st.pstdev(h), 2)
    neopr = dict(den=time.strftime("%Y-%m-%d", time.gmtime(int(ks_[-1]) / 1000)) if ks_ else None, z=nov,
                 status=("NOVYY_REZHIM_NE_ZNAYU" if any(abs(v) >= 3 for v in nov.values()) else ("POGRANICHNYY" if any(abs(v) >= 2 for v in nov.values()) else "IZVESTNYY")),
                 pravilo="|z| ≥ 3 хоть по одному признаку → Brain не даёт советов по режиму (только наблюдение); 2–3 → пограничный")
    (D / "zrenie_svodka.json").write_text(json.dumps(dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), dney=len(Z), nogi=sv, neopredelennost_rezhima=neopr,
        primechanie="описательно; |разница| > 2×√(se²+se²) — кандидат в prereg, проверка только вперёд"), ensure_ascii=False, indent=1))
    return dict(dney=len(Z), nogi={k: v["n"] for k, v in sv.items()}, rezhim=neopr["status"], trevogi=["Brain: новый режим рынка — советы по режиму отключены"] if neopr["status"] == "NOVYY_REZHIM_NE_ZNAYU" else [])

if __name__ == "__main__":
    print(prohod()); s = json.loads((D / "zrenie_svodka.json").read_text())
    for n, v in s["nogi"].items():
        for p, w in v.items():
            if p == "n": continue
            se = math.hypot(w["nizhnyaya_tret"]["se"] or 0, w["verhnyaya_tret"]["se"] or 0)
            print(n, p, "низ", w["nizhnyaya_tret"]["sred"], "верх", w["verhnyaya_tret"]["sred"], "разн", w["raznica"], "2se", round(2 * se, 3), "<<" if abs(w["raznica"]) > 2 * se else "")
