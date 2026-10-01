#!/usr/bin/env python3
"""attention_etb_sudya.py — судья PREREG_ATTENTION_SHORT_ETB_2026_10_01.md. Написан 2026-10-01, ДО будущих данных.

Только чтение data/akcii_grouped и data/etb_snimki. Правила — из предрегистрации, ничего не подбирается:
- события с 2026-10-02: |гэп| ≥ 5%, оборот ≥ 3× медианы 20 дн, вселенная как в ATTENTION_SHORT;
- бумага ETB (shortable и easy_to_borrow) в последнем снимке data/etb_snimki с датой ≤ даты события;
  нет такого снимка — снимок Alpaca 2026-08-12 (счётчик «старый_снимок» показывает, сколько таких);
- SSR: гэп ≤ −10% или день ≤ −10% → вход по закрытию через 2 торговых дня; иначе по закрытию дня события;
- выход: закрытие на 10-й день, либо раньше — первое закрытие ≥ +25% к цене входа (защита от сквиза);
- издержки по обороту (30/15/5 bps на сторону), заём 3% годовых за 10 дней, против рынка за тот же срок;
- событие учитывается только когда его 10-дневное окно целиком в данных (без отбора по исходу);
- PASS: ≥ 300 событий, среднее > 0, медиана > 0, t по датам Ньюи–Уэст лаг 10 ≥ 2.0. FAIL: ≥ 600 и не PASS.

    python3 research_lab/attention_etb_sudya.py
"""
import json, sys
import numpy as np
import discovery_paket5 as A
from discovery_paket1 import t_nw

OT = "2026-10-02"; ZAEM = 0.03 * 10 / 252; HOLD = 10; SKVIZ = 1.25; LAG = 10


def snimki():
    d = A.P.D / "etb_snimki"
    out = []
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        z = json.load(open(p)); out.append((p.stem, {s for s, v in z.items() if v[0] and v[1]}))
    star = json.load(open(A.P.D / "alpaca_pit_daily_v1/alpaca_active_assets.json"))["records"]
    return out, {x["symbol"] for x in star if x.get("shortable") and x.get("easy_to_borrow")}


def main():
    A.DELIST = 0.0
    sn, star = snimki()
    dates, px, cs = A.zagruzit(); tick, O, C, U = A.matricy(dates, px)
    po, vse, ozhid, staryh = {}, [], 0, 0
    for i0 in range(25, len(dates)):
        if dates[i0] < OT:
            continue
        un = A.vselennaya(C, U, i0 - 1); gap = O[i0] / C[i0 - 1] - 1
        med = np.nanmedian(U[i0 - 20:i0], axis=0)
        sel = np.flatnonzero(un & np.isfinite(gap) & (np.abs(gap) >= 0.05) & (U[i0] >= 3 * med))
        prig = [m for d, m in sn if d <= dates[i0]]
        etb = prig[-1] if prig else star
        r = []
        for j in sel:
            if tick[j] not in etb:
                continue
            staryh += not prig
            den = C[i0, j] / C[i0 - 1, j] - 1
            iv = i0 + 2 if (gap[j] <= -0.10 or den <= -0.10) else i0
            if iv + HOLD >= len(dates) or not np.isfinite(C[iv, j]):
                ozhid += iv + HOLD >= len(dates); continue
            h = HOLD
            for k in range(1, HOLD + 1):
                if np.isfinite(C[iv + k, j]) and C[iv + k, j] / C[iv, j] >= SKVIZ:
                    h = k; break
            x = A.vyhod(C, j, iv, h, -1); m = A.rynok(C, A.vselennaya(C, U, iv - 1), iv, h)
            if x is None or m is None:
                continue
            ob = med[j]; kk = 0.0030 if ob < 1e7 else (0.0015 if ob < 5e7 else 0.0005)
            v = x + m - 2 * kk - ZAEM
            r.append(v); vse.append(v)
        if r:
            po[dates[i0]] = float(np.mean(r))
    n = len(vse)
    rez = {"sobytiy": n, "ozhidayut_okna": ozhid, "staryy_snimok": int(staryh), "dat": len(po)}
    if n:
        v = np.array([po[d] for d in sorted(po)])
        rez.update(srednee_bps=round(float(np.mean(vse)) * 1e4, 1), mediana_bps=round(float(np.median(vse)) * 1e4, 1),
                   t_nw=round(t_nw(v, LAG), 2))
    if n < 300:
        rez["verdikt"] = "ЖДЁМ"
    else:
        ok = np.mean(vse) > 0 and np.median(vse) > 0 and rez["t_nw"] >= 2.0
        rez["verdikt"] = "PASS" if ok else ("FAIL" if n >= 600 else "ЖДЁМ_ДО_600")
    print("ATTENTION_SHORT_ETB:", json.dumps(rez, ensure_ascii=False))


if __name__ == "__main__":
    main()
