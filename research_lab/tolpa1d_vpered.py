#!/usr/bin/env python3
"""tolpa1d_vpered.py — судья TOLPA_1D вперёд (правила discovery_paket8 один в один). Заморожено 2026-10-01
до первых будущих данных. Поиск: +16 bps/день, t 2.14, половины 1.5/31 — подтверждения нет, только вперёд.
Одна семья с TOLPA_XS (недельной): доказательства не складываются; PASS любой из двух не делает семью вдвое сильнее.

Каждый день с входом закрытием 2026-10-02 и позже: PIT топ-50 по OI в $, доля лонг-аккаунтов Bybit в 22:00 UTC,
шорт верхнего дециля, лонг нижнего, 1 день, discovery_paket1.sdelka (фандинг, 12 bps на круг).
Два заранее объявленных взгляда на фиксированных префиксах: 180 и 365 дневных наблюдений;
на каждом PASS, если среднее > 0, обе половины > 0, t Ньюи–Уэста (лаг 1) ≥ 2.2. На 365 — PASS или FAIL.
Мощность (сказано заранее): при эффекте поиска +16 bps и разбросе ~270 bps/день t 2.2 недостижим даже за год;
PASS реален, только если вперёд держится уровень второй половины поиска (~+30 bps/день).

Обновление данных (раз в 1–4 недели, с Mac):
  dannye_pit_kripto.py --vse --obnovit ; dannye_pit_kripto.py --poz-chas --bez-oi --dopolnit ;
  dannye_pit_kripto.py --lsr --obnovit ; vselennaya_usd.py
    python3 research_lab/tolpa1d_vpered.py
"""
import datetime as dt, json
import numpy as np
import discovery_paket1 as P

OT = "2026-10-02"; CHAS = 22; POROG = 2.2; VZGLYADY = (180, 365)


def main():
    sostav = {d: set(v) for d, v in json.load(open(P.D / "basis/vselennaya_pit_usd50.json"))["sostav"].items()}
    M = P.zagruzit_kripto()
    for s, x in M.items():
        f = P.D / "poz_chas" / f"{s}.json"
        m = {int(t): v for t, v in json.load(open(f))["lsr"]} if f.exists() else {}
        x["lsr"] = np.array([m.get(int(t) + CHAS * 3_600_000, np.nan) for t in x["ts"]])
    den = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date().isoformat()
    ts_all = sorted({int(t) for x in M.values() for t in x["ts"]})
    v, net_vselennoy = [], 0
    for t in ts_all:
        if den(t) < OT:
            continue
        if den(t) not in sostav:
            net_vselennoy += 1; continue
        rows = []
        for s, x in M.items():
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60 or s not in sostav[den(t)]:
                continue
            if np.isfinite(x["lsr"][i]):
                rows.append((x["lsr"][i], s, i))
        if len(rows) < 30:
            continue
        rows.sort(); k = len(rows) // 10
        leg = [P.sdelka(M[s], i, 1, +1) for _, s, i in rows[:k]] + [P.sdelka(M[s], i, 1, -1) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        if len(leg) == 2 * k:
            v.append(float(np.mean(leg)))
    def vz(a):
        a = np.array(a); h = len(a) // 2; t_ = P.t_nw(a, 1)
        return (a.mean() > 0 and a[:h].mean() > 0 and a[h:].mean() > 0 and t_ >= POROG,
                dict(srednee_bps=round(a.mean() * 1e4, 1), t=round(t_, 2),
                     polovinki_bps=(round(a[:h].mean() * 1e4, 1), round(a[h:].mean() * 1e4, 1))))
    rez = {"dney": len(v), "dney_bez_vselennoy": net_vselennoy}
    if len(v) >= VZGLYADY[1]:
        ok1, _ = vz(v[:VZGLYADY[0]]); ok2, r = vz(v[:VZGLYADY[1]]); rez.update(r); rez["verdikt"] = "PASS" if ok1 or ok2 else "FAIL"
    elif len(v) >= VZGLYADY[0]:
        ok1, r = vz(v[:VZGLYADY[0]]); rez.update(r); rez["verdikt"] = "PASS" if ok1 else "ЖДЁМ_ДО_365"
    else:
        if len(v) >= 3:
            rez.update(vz(v)[1]); rez["primechanie"] = "справка, не взгляд"
        rez["verdikt"] = "ЖДЁМ"
    if net_vselennoy:
        rez["nado"] = "обновить данные и запустить vselennaya_usd.py"
    print("TOLPA_1D вперёд:", json.dumps(rez, ensure_ascii=False))


if __name__ == "__main__":
    main()
