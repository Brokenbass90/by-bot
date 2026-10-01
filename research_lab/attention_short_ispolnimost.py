#!/usr/bin/env python3
"""attention_short_ispolnimost.py — ворота исполнимости ATTENTION_SHORT. ЗАМОРОЖЕНО 2026-10-01 до прогона.
Сигнал (PREREG_ATTENTION_SHORT) не меняется; меняются только условия исполнения, объявленные здесь:

1. Шорт возможен только по бумагам, которые в снимке активов Alpaca (data/alpaca_pit_daily_v1/
   alpaca_active_assets.json, 2026-08-12) shortable=True и easy_to_borrow=True. Остальные события выбрасываются.
2. Правило SSR: если гэп ≤ −10% или закрытие дня ≤ −10% к вчерашнему — вход не в день события,
   а по закрытию через 2 торговых дня (SSR действует в день срабатывания и на следующий); удержание 10 дней от входа.
3. Издержки на сторону по обороту бумаги (медиана 20 дн): < $10 млн — 30 bps; $10–50 млн — 15 bps; > $50 млн — 5 bps.
   Плюс заём 3% годовых (ETB). Против рынка — как в предрегистрации.
4. EXECUTABLE: событий ≥ 300, среднее > 0, медиана > 0, t по датам ≥ 2.0 на окне 2026-04-01+.
   Иначе NOT_EXECUTABLE. Ёмкость: медианный оборот событий и 1% от него.
"""
import json, math
import numpy as np
import discovery_paket5 as A

ZAEM = 0.03 * 10 / 252; OKNO_OT = "2026-04-01"


def main():
    A.DELIST = 0.0
    sn = json.load(open(A.P.D / "alpaca_pit_daily_v1/alpaca_active_assets.json"))["records"]
    etb = {x["symbol"] for x in sn if x.get("shortable") and x.get("easy_to_borrow")}
    dates, px, cs = A.zagruzit(); tick, O, C, U = A.matricy(dates, px)
    po_dnyam, vse, adv, vybr, ssr = {}, [], [], 0, 0
    for i0 in range(25, len(dates) - 12):
        if dates[i0] < OKNO_OT:
            continue
        un = A.vselennaya(C, U, i0 - 1); gap = O[i0] / C[i0 - 1] - 1
        med = np.nanmedian(U[i0 - 20:i0], axis=0)
        sel = np.flatnonzero(un & np.isfinite(gap) & (np.abs(gap) >= 0.05) & (U[i0] >= 3 * med))
        r = []
        for j in sel:
            if tick[j] not in etb:
                vybr += 1; continue
            den = C[i0, j] / C[i0 - 1, j] - 1
            iv = i0 + 2 if (gap[j] <= -0.10 or den <= -0.10) else i0
            ssr += iv != i0
            if iv + 10 >= len(dates):
                continue
            m = A.rynok(C, A.vselennaya(C, U, iv - 1), iv, 10)
            x = A.vyhod(C, j, iv, 10, -1)
            if x is None or m is None:
                continue
            ob = med[j]; k = 0.0030 if ob < 1e7 else (0.0015 if ob < 5e7 else 0.0005)
            v = x + m - 2 * k - ZAEM
            r.append(v); vse.append(v); adv.append(ob)
        if r:
            po_dnyam[dates[i0]] = float(np.mean(r))
    v = np.array(list(po_dnyam.values())); t = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    ok = len(vse) >= 300 and v.mean() > 0 and np.median(vse) > 0 and t >= 2.0
    rez = {"verdikt": "EXECUTABLE" if ok else "NOT_EXECUTABLE", "sobytiy": len(vse), "vybrosheno_ne_ETB": vybr,
           "ssr_sdvig": int(ssr), "dat": len(v), "srednee_bps": round(v.mean() * 1e4, 1),
           "mediana_bps": round(float(np.median(vse)) * 1e4, 1), "t_po_datam": round(float(t), 2),
           "mediannyy_oborot_mln": round(float(np.median(adv)) / 1e6, 1),
           "pozitsiya_1pct_oborota_tys": round(float(np.median(adv)) * 0.01 / 1e3, 0)}
    print(json.dumps(rez, ensure_ascii=False))
    json.dump(rez, open(A.P.D / "attention_short_ispolnimost.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
