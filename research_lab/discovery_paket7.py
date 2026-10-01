#!/usr/bin/env python3
"""discovery_paket7.py — пачка 7: позиционирование толпы Bybit (доля лонг-аккаунтов, account-ratio), класс №2.
Правила заморожены 2026-10-01 ДО первого прогона (коммит до запуска).

Данные: data/lsr_sutochnyy (buyRatio по дням, метка дня = начало суток UTC; используем значение за
ПРЕДЫДУЩИЙ день относительно бара входа — чтобы не заглядывать внутрь бара), pit_daily (цены, фандинг).
Вселенная на дату: PIT топ-50 по OI в $ (basis/vselennaya_pit_usd50.json, только прошлое).
Сделка: discovery_paket1.sdelka (закрытие → закрытие, фандинг, 12 bps на круг). Перекрёстные — раз в 7 дней.
Окна: поиск — вход до 2026-04-01. 2026-04-01…2026-09-30 — подтверждение ОДИН раз для выживших
(для цен крипты это окно не девственно — его видели другие механизмы; данные толпы — впервые; сказано заранее).
Порог: itog с t Ньюи–Уэста (перекрёстные — лаг 1, события — лаг 7) и поправка на 3 проверки: t ≥ 2.39.
Ограничение данных: биржа отдаёт историю только по живым контрактам — делистинговые монеты без данных толпы.

  L1 TOLPA_XS          шорт верхнего дециля доли лонг-аккаунтов, лонг нижнего, 7 дней (толпа ошибается на краях)
  L2 SDVIG_TOLPY_XS    шорт верхнего дециля прироста доли лонгов за 7 дней, лонг нижнего, 7 дней (свежая толпа — топливо разворота)
  L3 TOLPA_PROTIV_ROSTA цена +20% за 7 дней, а доля лонгов за те же 7 дней упала ≥ 3 п.п. → лонг 7 дней
                       (толпа шортит рост → выносы шортов продолжают движение)

    python3 research_lab/discovery_paket7.py           поиск
    python3 research_lab/discovery_paket7.py --podtv   подтверждение выживших (один раз)
"""
import datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

OKNO = "2026-04-01"; KONEC = "2026-09-30"; POROG = 2.39; HOLD = 7


def main():
    podtv = "--podtv" in sys.argv
    M = P.zagruzit_kripto()
    sostav = {d: set(v) for d, v in json.load(open(P.D / "basis/vselennaya_pit_usd50.json"))["sostav"].items()}
    for s, x in M.items():
        f = P.D / "lsr_sutochnyy" / f"{s}.json"
        lsr = np.full(len(x["ts"]), np.nan)
        if f.exists():
            m = {int(t): v for t, v in json.load(open(f))["lsr"]}
            lsr = np.array([m.get(int(t) - P.DEN, np.nan) for t in x["ts"]])   # значение предыдущих суток
        x["lsr"] = lsr
    def den(t):
        return dt.datetime.utcfromtimestamp(t / 1000).date().isoformat()
    def v_okne(t):
        d = den(t); return (OKNO <= d <= KONEC) if podtv else d < OKNO
    def v_univ(s, t):
        return s in sostav.get(den(t), ())

    def xs(score):
        ts_all = sorted({int(t) for x in M.values() for t in x["ts"]})
        sob = []
        for t in ts_all[60::7]:
            if not v_okne(t):
                continue
            rows = []
            for s, x in M.items():
                i = int(np.searchsorted(x["ts"], t))
                if i >= len(x["ts"]) or x["ts"][i] != t or i < 60 or not v_univ(s, t):
                    continue
                v = score(x, i)
                if v is not None and np.isfinite(v):
                    rows.append((v, s, i))
            if len(rows) < 30:
                continue
            rows.sort(); k = len(rows) // 10
            leg = [P.sdelka(M[s], i, HOLD, +1) for _, s, i in rows[:k]] + [P.sdelka(M[s], i, HOLD, -1) for _, s, i in rows[-k:]]
            leg = [r for r in leg if r is not None]
            if leg:
                sob.append((t, float(np.mean(leg)), None))
        return P.itog(sob, s_kontrolem=False, lag=1)

    rez = {}
    rez["L1"] = xs(lambda x, i: x["lsr"][i])
    rez["L2"] = xs(lambda x, i: x["lsr"][i] - x["lsr"][i - 7])
    sob = []
    for s, x in M.items():
        blok = -1
        for i in range(60, len(x["ts"]) - HOLD):
            if i <= blok or not v_okne(x["ts"][i]) or not v_univ(s, x["ts"][i]):
                continue
            if x["c"][i] / x["c"][i - 7] - 1 >= 0.20 and x["lsr"][i] - x["lsr"][i - 7] <= -0.03:
                r = P.sdelka(x, i, HOLD, +1)
                if r is not None:
                    sob.append((int(x["ts"][i]), r, None)); blok = i + HOLD
    rez["L3"] = P.itog(sob, s_kontrolem=False, lag=HOLD)
    for k, it in rez.items():
        if it["verdikt"] == "SURVIVED" and it["t"] < POROG:
            it["verdikt"] = "KILLED"; it["prichina"] = f"t {it['t']} < {POROG} (поправка на 3 проверки)"
        print(f"{k} {'ПОДТВ' if podtv else 'ПОИСК'} {it}")
    json.dump(rez, open(P.D / f"discovery_paket7{'_podtv' if podtv else ''}.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
