#!/usr/bin/env python3
"""discovery_paket5.py — пачка 5: акции США на вселенной без смещения выживших (второе семейство, 01.10).

Данные: data/akcii_grouped/<дата>.json — все бумаги, торговавшиеся в этот день (Massive grouped daily),
справочник обычных акций (активные + снятые). Правила заморожены 2026-10-01 ДО загрузки дневок.

Вселенная на дату t (только прошлое): тип CS по справочнику; цена закрытия ≥ $5; медианный оборот
за 20 дней ≥ $2 млн. Издержки 10 bps на круг. Бумага исчезла во время удержания (делистинг) →
лонг закрывается по последнему закрытию −30%, шорт по последнему закрытию (консервативно для обеих сторон).
Доходность сравнивается с равновзвешенной вселенной того же дня (рыночно нейтрально).
Окна: поиск — до 2026-04-01; 2026-04-01 и позже — НЕТРОНУТО, только для подтверждения выживших.
Правило экрана — discovery_paket1.itog. Кластер — дата входа.

  A1 WEEKLY_REVERSAL   пт: лонг худшего дециля 5-дн доходности, шорт лучшего, 5 дней
  A2 OVERNIGHT         ежедневно: равновзвешенно купить на закрытии, продать на открытии (минус издержки)
  A3 NEAR_52W_HIGH     раз в 20 дней: лонг бумаг в пределах 2% от 250-дн максимума против вселенной, 20 дней
  A4 GAP_VOLUME_DRIFT  гэп ≥ 5% и объём ≥ 3 медиан 20 дн → в сторону гэпа с закрытия дня события, 10 дней, против вселенной
  A5 LOTTERY_MAX       раз в 10 дней: шорт верхнего дециля макс. дневной доходности за 20 дн, лонг нижнего, 10 дней
                       (A3 с годовым прогревом на 2 годах данных даст ~6 периодов — ожидаемо мало, это известно заранее)
  A6 TURN_OF_MONTH     равновзвешенная вселенная с закрытия предпоследнего дня месяца по 3-й день следующего, против прочих дней

    python3 research_lab/discovery_paket5.py
"""
import glob, json, math, sys
from collections import defaultdict
import numpy as np
import discovery_paket1 as P

D = P.D / "akcii_grouped"; DEN = P.DEN
GRAN_PODTV = "2026-04-01"
KOM = 10e-4; DELIST = 0.30; MIN_CENA = 5.0; MIN_OBOROT = 2e6


def zagruzit():
    cs = set()
    for f in ("spravochnik_active.json", "spravochnik_inactive.json"):
        p = D / f
        if p.exists():
            cs |= {x.get("ticker") for x in json.load(open(p))}
    dni = sorted(f for f in glob.glob(str(D / "20*.json")))
    dates, px = [], {}
    for k, f in enumerate(dni):
        d = json.load(open(f)); rows = [r for r in d["rows"] if r[0] in cs and r[4]]
        if len(rows) < 1000:            # праздник / пустой день
            continue
        dates.append(d["date"])
        for T, o, h, l, c, v, vw, n in rows:
            px.setdefault(T, {})[len(dates) - 1] = (o, c, (v or 0) * (vw or c))
    return dates, px, cs


def matricy(dates, px):
    tick = sorted(px); n, m = len(dates), len(tick)
    O = np.full((n, m), np.nan); C = np.full((n, m), np.nan); U = np.full((n, m), np.nan)
    for j, t in enumerate(tick):
        for i, (o, c, usd) in px[t].items():
            O[i, j], C[i, j], U[i, j] = o, c, usd
    return tick, O, C, U


def vselennaya(C, U, i):
    if i < 20:
        return np.zeros(C.shape[1], bool)
    obor = np.nanmedian(U[i - 19:i + 1], axis=0)
    return (C[i] >= MIN_CENA) & (obor >= MIN_OBOROT) & np.isfinite(C[i])


def vyhod(C, j, i0, hold, side):
    """доход позиции с закрытия i0 на hold дней, с правилом делистинга"""
    i1 = i0 + hold
    if i1 >= C.shape[0]:
        return None
    if np.isfinite(C[i1, j]):
        return side * (C[i1, j] / C[i0, j] - 1)
    zhiv = np.flatnonzero(np.isfinite(C[i0:i1 + 1, j]))
    last = C[i0 + zhiv[-1], j]
    if i0 + zhiv[-1] >= C.shape[0] - 3:     # просто конец данных, не делистинг
        return None
    return side * (last * (1 - DELIST if side > 0 else 1) / C[i0, j] - 1)


def rynok(C, univ, i0, hold):
    js = np.flatnonzero(univ)
    r = [vyhod(C, j, i0, hold, 1) for j in js]
    r = [x for x in r if x is not None]
    return float(np.mean(r)) if r else None


def v_okne(dates, i):
    return dates[i] < GRAN_PODTV


def xs(dates, C, U, score, hold, shag, tolko_long=False):
    sob = []
    for i0 in range(260 if score.__name__ == "s52" else 25, len(dates) - hold, shag):
        if not v_okne(dates, i0 + hold):
            break
        un = vselennaya(C, U, i0); js = np.flatnonzero(un)
        sc = np.array([score(C, i0, j) for j in js])
        ok = np.isfinite(sc); js, sc = js[ok], sc[ok]
        if len(js) < 200:
            continue
        o = np.argsort(sc); k = len(js) // 10
        lng = [vyhod(C, j, i0, hold, 1) for j in js[o[:k]]]; sht = [vyhod(C, j, i0, hold, -1) for j in js[o[-k:]]]
        lng = [x for x in lng if x is not None]; sht = [x for x in sht if x is not None]
        if lng and sht:
            sob.append((i0 * DEN, (np.mean(lng) + np.mean(sht)) / 2 - KOM, None))
    return P.itog(sob, s_kontrolem=False)


def A1(dates, C, U):
    def s(C, i, j):
        return C[i, j] / C[i - 5, j] - 1
    return xs(dates, C, U, s, 5, 5)


def A2(dates, O, C, U):
    sob = []
    for i in range(25, len(dates) - 1):
        if not v_okne(dates, i + 1):
            break
        un = vselennaya(C, U, i); js = np.flatnonzero(un & np.isfinite(O[i + 1]))
        if len(js) > 200:
            sob.append((i * DEN, float(np.mean(O[i + 1, js] / C[i, js] - 1)) - KOM, None))
    return P.itog(sob, s_kontrolem=False)


def A3(dates, C, U):
    sob = []
    for i0 in range(260, len(dates) - 20, 20):
        if not v_okne(dates, i0 + 20):
            break
        un = vselennaya(C, U, i0); js = np.flatnonzero(un)
        mx = np.nanmax(C[i0 - 249:i0 + 1, js], axis=0)
        sel = js[C[i0, js] >= 0.98 * mx]
        r = [vyhod(C, j, i0, 20, 1) for j in sel]; r = [x for x in r if x is not None]
        m = rynok(C, un, i0, 20)
        if len(r) >= 10 and m is not None:
            sob.append((i0 * DEN, float(np.mean(r)) - m - KOM, None))
    return P.itog(sob, s_kontrolem=False)


def A4(dates, O, C, U):
    sob = []
    for i0 in range(25, len(dates) - 10):
        if not v_okne(dates, i0 + 10):
            break
        un = vselennaya(C, U, i0 - 1)
        gap = O[i0] / C[i0 - 1] - 1
        med = np.nanmedian(U[i0 - 20:i0], axis=0)
        sel = np.flatnonzero(un & np.isfinite(gap) & (np.abs(gap) >= 0.05) & (U[i0] >= 3 * med))
        if not len(sel):
            continue
        m = rynok(C, un, i0, 10)
        r = [vyhod(C, j, i0, 10, 1 if gap[j] > 0 else -1) for j in sel]
        r = [x - (m if gap[j] > 0 else -m) for x, j in zip(r, sel) if x is not None and m is not None]
        if r:
            sob.append((i0 * DEN, float(np.mean(r)) - KOM, None))
    return P.itog(sob, s_kontrolem=False)


def A5(dates, C, U):
    def s(C, i, j):
        r = C[i - 19:i + 1, j] / C[i - 20:i, j] - 1
        return float(np.nanmax(r)) if np.isfinite(r).sum() >= 15 else np.nan    # нижний дециль — лонг, верхний — шорт
    return xs(dates, C, U, s, 10, 10)


def A6(dates, C, U):
    sob = []
    mes = [d[:7] for d in dates]
    for i in range(25, len(dates) - 1):
        if not v_okne(dates, i + 1):
            break
        konec = i + 2 < len(dates) and mes[i + 2] != mes[i]          # предпоследний день месяца
        if not konec:
            continue
        k = i + 1
        while k < len(dates) and mes[k] == mes[i]:
            k += 1
        k += 3                                                        # по 3-й торговый день нового месяца
        if k >= len(dates):
            break
        un = vselennaya(C, U, i)
        m = rynok(C, un, i, k - i)
        if m is not None:
            # против средней доходности вселенной за такое же число дней в середине месяца
            i_mid = max(25, i - 12); mm = rynok(C, vselennaya(C, U, i_mid), i_mid, k - i)
            if mm is not None:
                sob.append((i * DEN, m - mm - KOM, None))
    return P.itog(sob, s_kontrolem=False)


if __name__ == "__main__":
    dates, px, cs = zagruzit()
    if len(dates) < 300:
        print(f"мало дней ({len(dates)}) — выгрузка не закончена; правила заморожены, ждём"); sys.exit(0)
    tick, O, C, U = matricy(dates, px)
    print(f"дней {len(dates)} ({dates[0]}…{dates[-1]}), бумаг {len(tick)}, в справочнике CS {len(cs)}")
    rez = {"A1": A1(dates, C, U), "A2": A2(dates, O, C, U), "A3": A3(dates, C, U),
           "A4": A4(dates, O, C, U), "A5": A5(dates, C, U), "A6": A6(dates, C, U)}
    for k, v in rez.items():
        print(k, v)
    json.dump(rez, open(P.D / "discovery_paket5.json", "w"), ensure_ascii=False, indent=1)
