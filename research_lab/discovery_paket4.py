#!/usr/bin/env python3
"""discovery_paket4.py — пачка 4, семейство TRADFI_CLOSED_MARKET (DISCOVERY_PAKET4_2026_09_30.md).

Перпы Bybit на золото, нефть, индексы и акции торгуются 24/7, базовый рынок — нет. Пока базовый закрыт,
цена складывается без арбитражёров; к открытию базового рынка перп обязан к нему сойтись.
Гипотеза одна на всё семейство: крупное движение перпа за время закрытия ПЕРЕРЕАГИРУЕТ — ставка против него
от момента «за час до открытия» до «через два часа после открытия».

Правила заморожены 2026-09-30 ДО получения данных (`dannye_pit_kripto.py --chasy` ещё не выгружался):
  W1 золото (PAXG, XAUT) и W4 нефть (CL, BZ): закрытие пт 17:00 ET, открытие вс 18:00 ET;
     движение = от закрытия до «открытие − 1 ч»; вход там же, выход «открытие + 2 ч»; порог |движение| ≥ 0.5%.
  W2 акции/индексы, выходные: закрытие пт 16:00 ET, открытие пн 09:30 ET → вход пн 08:30 ET, выход 11:30 ET; порог 1%.
  W3 акции/индексы, будничная ночь: закрытие 16:00 ET, открытие следующего дня 09:30 ET; вход 08:30, выход 11:30; порог 1%.
Время: ET с переходом США на летнее (2-е вс марта — 1-е вс ноября). Издержки 12 bps на круг + фандинг.
Правило экрана — discovery_paket1.itog (без изменений). Кластер — дата входа.
    python3 research_lab/discovery_paket4.py
"""
import calendar, datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

D = P.D; CH = 3600000
ZOLOTO_NEFT = {"W1": ["PAXGUSDT", "XAUTUSDT"], "W4": ["CLUSDT", "BZUSDT"]}
AKCII = ["AAPLUSDT", "NVDAUSDT", "TSLAUSDT", "MSTRUSDT", "COINUSDT", "HOODUSDT", "INTCUSDT", "CRCLUSDT", "BMNRUSDT",
         "SPXUSDT", "SPYUSDT", "QQQUSDT", "EWYUSDT"]


def et_smeshenie(d):
    """часов между ET и UTC на дату d (4 летом, 5 зимой)"""
    y = d.year
    mar = [w[6] for w in calendar.monthcalendar(y, 3) if w[6]][1]
    nov = [w[6] for w in calendar.monthcalendar(y, 11) if w[6]][0]
    return 4 if dt.date(y, 3, mar) <= d < dt.date(y, 11, nov) else 5


def et(d, chas, minuta=0):
    """момент d chas:minuta по Нью-Йорку в мс UTC"""
    return int(dt.datetime(d.year, d.month, d.day, chas, minuta, tzinfo=dt.timezone.utc).timestamp() * 1000) \
        + et_smeshenie(d) * CH


def zagruzit(s):
    p = D / "tradfi_h1" / f"{s}.json"
    if not p.exists():
        return None
    a = np.array(json.load(open(p))["h1"], float)
    return dict(ts=a[:, 0].astype(np.int64), o=a[:, 1])


def cena(x, t):
    """цена открытия часового бара, начинающегося не раньше t (в пределах 30 мин)"""
    i = int(np.searchsorted(x["ts"], t))
    if i < len(x["ts"]) and x["ts"][i] - t <= 30 * 60000:
        return x["o"][i]
    return None


def sdelka(x, t_zakr, t_vhod, t_vyhod, porog, fx=None):
    p0, p1, p2 = cena(x, t_zakr), cena(x, t_vhod), cena(x, t_vyhod)
    if not (p0 and p1 and p2):
        return None
    dvizh = p1 / p0 - 1
    if abs(dvizh) < porog:
        return None
    side = -1 if dvizh > 0 else 1
    f = P.fand(fx, t_vhod, t_vyhod) if fx else 0.0
    return side * (p2 / p1 - 1) - side * f - P.KOM_KRIPTO


def W_vyhodnye_zoloto(kod):
    M = P.zagruzit_kripto(); sob = []; est = 0
    for s in ZOLOTO_NEFT[kod]:
        x = zagruzit(s)
        if x is None:
            continue
        est += 1
        d0 = dt.datetime.utcfromtimestamp(x["ts"][0] / 1000).date()
        d1 = dt.datetime.utcfromtimestamp(x["ts"][-1] / 1000).date()
        d = d0
        while d <= d1:
            if d.weekday() == 4:                                   # пятница
                vs = d + dt.timedelta(days=2)
                r = sdelka(x, et(d, 17), et(vs, 17), et(vs, 20), 0.005, M.get(s))
                if r is not None:
                    sob.append((et(vs, 17), r, None))
            d += dt.timedelta(days=1)
    return P.itog(sob, s_kontrolem=False) if est else {"verdikt": "BLOCKED_DATA", "prichina": "нет tradfi_h1 (--chasy)"}


def W_akcii(vyhodnye):
    M = P.zagruzit_kripto(); sob = []; est = 0
    for s in AKCII:
        x = zagruzit(s)
        if x is None:
            continue
        est += 1
        d0 = dt.datetime.utcfromtimestamp(x["ts"][0] / 1000).date()
        d1 = dt.datetime.utcfromtimestamp(x["ts"][-1] / 1000).date()
        d = d0
        while d <= d1:
            wd = d.weekday()
            if (vyhodnye and wd == 4) or (not vyhodnye and wd in (0, 1, 2, 3)):
                sled = d + dt.timedelta(days=3 if vyhodnye else 1)
                r = sdelka(x, et(d, 16), et(sled, 8, 30), et(sled, 11, 30), 0.01, M.get(s))
                if r is not None:
                    sob.append((et(sled, 8, 30), r, None))
            d += dt.timedelta(days=1)
    return P.itog(sob, s_kontrolem=False) if est else {"verdikt": "BLOCKED_DATA", "prichina": "нет tradfi_h1 (--chasy)"}


if __name__ == "__main__":
    rez = {"W1": W_vyhodnye_zoloto("W1"), "W4": W_vyhodnye_zoloto("W4"), "W2": W_akcii(True), "W3": W_akcii(False)}
    for k, v in rez.items():
        print(k, v)
    json.dump(rez, open(D / "discovery_paket4.json", "w"), ensure_ascii=False, indent=1)
