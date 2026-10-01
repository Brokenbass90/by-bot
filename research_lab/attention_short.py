#!/usr/bin/env python3
"""attention_short.py — судья PREREG_ATTENTION_SHORT_2026_10_01.md (заморожено в 073affb). Один прогон
на нетронутом окне 2026-04-01+. Правила взяты дословно из предрегистрации; вселенная и выход — из
discovery_paket5 (те же функции), чтобы не было расхождения с поиском."""
import math, json
import numpy as np
import discovery_paket5 as A

ZAEM = 0.03 * 10 / 252          # заём 3% годовых за 10 торговых дней
OKNO_OT = "2026-04-01"


def main():
    A.DELIST = 0.0                      # prereg: делистинг — по последнему закрытию
    dates, px, cs = A.zagruzit(); tick, O, C, U = A.matricy(dates, px)
    po_dnyam, storony = {}, {1: [], -1: []}
    for i0 in range(25, len(dates) - 10):
        if dates[i0] < OKNO_OT:
            continue
        un = A.vselennaya(C, U, i0 - 1); gap = O[i0] / C[i0 - 1] - 1
        med = np.nanmedian(U[i0 - 20:i0], axis=0)
        sel = np.flatnonzero(un & np.isfinite(gap) & (np.abs(gap) >= 0.05) & (U[i0] >= 3 * med))
        m = A.rynok(C, un, i0, 10)
        if not len(sel) or m is None:
            continue
        r = []
        for j in sel:
            x = A.vyhod(C, j, i0, 10, -1)                     # шорт
            if x is None:
                continue
            v = x + m - A.KOM - ZAEM                          # шорт бумаги + лонг вселенной
            r.append(v); storony[1 if gap[j] > 0 else -1].append(v)
        if r:
            po_dnyam[dates[i0]] = float(np.mean(r))
    v = np.array(list(po_dnyam.values())); vse = np.array(storony[1] + storony[-1])
    t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    up, dn = np.mean(storony[1]), np.mean(storony[-1])
    ok = v.mean() > 0 and np.median(vse) > 0 and t >= 2.0 and up > 0 and dn > 0
    rez = {"verdikt": "PASS" if ok else "FAIL", "okno": f"{min(po_dnyam)}…{max(po_dnyam)}", "dat": len(v),
           "sobytiy": len(vse), "srednee_bps": round(v.mean() * 1e4, 1), "mediana_bps": round(float(np.median(vse)) * 1e4, 1),
           "t_po_datam": round(float(t), 2), "gep_vverh_bps": round(up * 1e4, 1), "n_vverh": len(storony[1]),
           "gep_vniz_bps": round(dn * 1e4, 1), "n_vniz": len(storony[-1])}
    print(json.dumps(rez, ensure_ascii=False))
    json.dump(rez, open(A.P.D / "attention_short_verdikt.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
