#!/usr/bin/env python3
"""glubina_izmereniya.py — измерения M1–M3 по PREREG_GLUBINA_PEREKOS_2026_10_14 (БЕЗ будущих доходностей) и правило заморозки.
M1 покрытие; M2 недельная ранговая автокорреляция перекоса по полосам ±1/2/5%; M3 ранговая корреляция с KITY m3 и с доходностью
того же дня d−1. Выбор полосы: max M2; |корр. с m3| > 0.5 → снять как дубликат KITY. Пишет data/binance_glubina/IZMERENIYA.json.
"""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "factory_v3")); sys.path.insert(0, str(LAB))
import ferma_shablony as F       # noqa: E402

OUT = LAB / "data" / "binance_glubina" / "IZMERENIYA.json"
POLOSY = ("imb1", "imb2", "imb5")


def rk(a): return np.argsort(np.argsort(np.asarray(a, float)))


def main():
    D = F._dannye(); K, M = D["K"], D["M"]
    f_m3 = F._priznak("m3_perp", D); f_d = F._priznak("pogloshchenie", D)          # (доход d−1, поток d−1)
    f_g = {p: F._priznak(f"glubina_{p}", D) for p in POLOSY}
    nedeli, pokr, pred = [], [], {p: None for p in POLOSY}
    avto = {p: [] for p in POLOSY}; c_m3 = {p: [] for p in POLOSY}; c_ret = {p: [] for p in POLOSY}
    for d in K.SETKA:
        if not (dt.date(2023, 1, 2) <= d <= dt.date(2026, 9, 30)): continue
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        nedeli.append(vch)
        g = {p: {s: f_g[p](s, vch) for _, s in oi} for p in POLOSY}
        ok = [s for _, s in oi if g["imb1"][s] is not None]; pokr.append(len(ok))
        for p in POLOSY:
            cur = {s: v for s, v in g[p].items() if v is not None}
            if pred[p]:
                obsh = [s for s in cur if s in pred[p]]
                if len(obsh) >= 30: avto[p].append(np.corrcoef(rk([cur[s] for s in obsh]), rk([pred[p][s] for s in obsh]))[0, 1])
            pred[p] = cur
            rows = [(cur[s], f_m3(s, vch), f_d(s, vch)) for s in cur]
            rows = [r for r in rows if r[1] is not None and r[2] is not None]
            if len(rows) >= 30:
                c_m3[p].append(np.corrcoef(rk([r[0] for r in rows]), rk([r[1] for r in rows]))[0, 1])
                c_ret[p].append(np.corrcoef(rk([r[0] for r in rows]), rk([r[2][0] for r in rows]))[0, 1])
    m = lambda x: round(float(np.mean(x)), 3) if x else None
    rez = dict(M1=dict(nedel=len(nedeli), nedel_ge30=int(sum(c >= 30 for c in pokr)), mediana_monet=int(np.median(pokr)) if pokr else 0),
               M2_avtokorrelyaciya={p: m(avto[p]) for p in POLOSY},
               M3_korr_s_kity_m3={p: m(c_m3[p]) for p in POLOSY}, M3_korr_s_dohodom_d1={p: m(c_ret[p]) for p in POLOSY})
    vybor = max(POLOSY, key=lambda p: rez["M2_avtokorrelyaciya"][p] if rez["M2_avtokorrelyaciya"][p] is not None else -9)
    dubl = abs(rez["M3_korr_s_kity_m3"][vybor] or 0) > 0.5
    rez.update(vybrana_polosa=vybor, priznak=f"glubina_{vybor}", dublikat_kity=dubl,
               reshenie="СНЯТЬ как дубликат KITY" if dubl else "ЗАМОРОЖЕНО к одному PnL-тесту")
    OUT.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
