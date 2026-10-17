#!/usr/bin/env python3
"""wfo_v1 — общий скользящий подбор настроек (PREREG_WFO_ASM1_2026_10_17). Любая стратегия, отдающая таблицу сделок
по клеткам: (монета, t_vhod, t_vyhod, storona, kletka..., R). Подбор: 6 мес обучения (только закрытые сделки) → 1 мес вперёд."""
import datetime as dt, json, math
import numpy as np

UTC = dt.timezone.utc


def mesyacy(s, e):
    out, d = [], dt.datetime(s.year, s.month, 1, tzinfo=UTC)
    while d < e:
        n = dt.datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=UTC); out.append((d, n)); d = n
    return out


def ms(d): return int(d.timestamp() * 1000)


def bez_perekrytiy(tr):
    """tr — список (sym, tv, ty, R) одной клетки; одна позиция на монету."""
    out, konec = [], {}
    for sym, tv, ty, R in sorted(tr, key=lambda x: (x[1], x[0])):
        if tv < konec.get(sym, -1): continue
        konec[sym] = ty; out.append((sym, tv, ty, R))
    return out


def t_po_dnyam(z):
    """z — список (t_vhod_ms, R) → t по кластерам «сутки входа»."""
    d = {}
    for t, R in z: d.setdefault(t // 86_400_000, []).append(R)
    x = np.array([np.mean(v) for v in d.values()])
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0


def progon(kletki, pervyy, posledniy, obuch_mes=6, min_n=30, t_porog=2.5, min_n_vsego=200):
    """kletki: {imya: [(sym, tv, ty, R)]} (уже без перекрытий). → результат и вердикт по prereg."""
    vybory, nevid, sred_vseh = [], [], []
    for a, b in mesyacy(pervyy, posledniy):
        ob_s = a.replace(year=a.year - (1 if a.month <= obuch_mes else 0), month=(a.month - obuch_mes - 1) % 12 + 1)
        luchshe, lr = None, -1e9
        for imya, tr in kletki.items():
            R = [x[3] for x in tr if ms(ob_s) <= x[1] and x[2] <= ms(a)]
            if len(R) >= min_n and np.mean(R) > lr: luchshe, lr = imya, float(np.mean(R))
        vse_mes = [x[3] for tr in kletki.values() for x in tr if ms(a) <= x[1] < ms(b)]
        if luchshe is None: vybory.append((a.strftime("%Y-%m"), None, None, 0)); continue
        z = [(x[1], x[3]) for x in kletki[luchshe] if ms(a) <= x[1] < ms(b)]
        nevid += [(t, R, a.strftime("%Y-%m")) for t, R in z]
        sred_vseh += vse_mes
        vybory.append((a.strftime("%Y-%m"), luchshe, round(lr, 3), len(z)))
    R = np.array([x[1] for x in nevid]); n = len(R)
    if n == 0: return dict(n=0, verdikt="FAIL", vybory=vybory)
    t = t_po_dnyam([(x[0], x[1]) for x in nevid])
    srt = sorted(nevid); pol = n // 2
    p1, p2 = float(np.mean([x[1] for x in srt[:pol]])), float(np.mean([x[1] for x in srt[pol:]]))
    po_mes = {}
    for _, r, m in nevid: po_mes[m] = po_mes.get(m, 0.0) + r
    top3 = set(sorted(po_mes, key=po_mes.get, reverse=True)[:3])
    bez = [x[1] for x in nevid if x[2] not in top3]
    usl = dict(n=n >= min_n_vsego, sredniy_i_t=bool(R.mean() > 0 and t >= t_porog),
               luchshe_srednego=bool(R.mean() > np.mean(sred_vseh)), polovinki=p1 > 0 and p2 > 0,
               bez_top3=bool(len(bez) and np.mean(bez) > 0))
    return dict(n=n, sredniy_R=round(float(R.mean()), 4), t=round(t, 2), summa_R=round(float(R.sum()), 1),
                sredniy_vseh_kletok=round(float(np.mean(sred_vseh)), 4), polovinki=[round(p1, 4), round(p2, 4)],
                bez_top3=round(float(np.mean(bez)), 4) if bez else None, dolya_plyus=round(float((R > 0).mean()), 3),
                usloviya=usl, verdikt="PASS" if all(usl.values()) else "FAIL", vybory=vybory)
