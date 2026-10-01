#!/usr/bin/env python3
"""discovery_paket6.py — пачка 6: отчётности компаний США (SEC EDGAR), новый класс данных №1.
Правила заморожены 2026-10-01 ДО первого прогона на ценах (коммит до запуска).

Данные: data/edgar/otchety.jsonl (8-K пункт 2.02 с точным временем приёма SEC, UTC) + дневки akcii_grouped.
Вселенная, издержки (10 bps на круг), делистинг, рыночная нейтральность — как в пачке 5 (discovery_paket5).
День реакции: время приёма → Нью-Йорк; до 09:30 → этот торговый день; после 16:00 → следующий; между → этот.
Тикер компании: из её тикеров тот, у кого больше оборот в день реакции.
Окна: поиск — вход до 2026-04-01. 2026-04-01…2026-09-30 — подтверждение ОДИН раз и только для выживших
(для этих механизмов окно не тронуто; ранее его использовал другой механизм — ATTENTION_SHORT; сказано заранее).
Порог выживания: itog (t ≥ 2, обе половины > 0, сырой > 0) с t Ньюи–Уэста (лаг = удержание)
и поправкой на 3 проверки: t ≥ 2.39.

  E1 PREMIA_PERED_OTCHETOM  через 84 календарных дня после отчёта (если нового отчёта ещё не было) — лонг на
                            5 торговых дней против вселенной: внимание и спрос розницы перед ожидаемым отчётом.
  E2 DREYF_POSLE_OTCHETA    реакция дня отчёта против вселенной ≥ +5% → лонг, ≤ −5% → шорт, с закрытия дня
                            реакции на 20 дней: рынок недореагирует на новую информацию (в отличие от гэпов без новостей).
  E3 OPOZDAVSHIY            через 105 календарных дней после отчёта нового отчёта нет, бумага торгуется → шорт на
                            20 дней против вселенной: задержка отчёта — сигнал плохих новостей.

    python3 research_lab/discovery_paket6.py            поиск
    python3 research_lab/discovery_paket6.py --podtv    подтверждение выживших (один раз, после записи итогов поиска)
"""
import datetime as dt, json, sys
from collections import defaultdict
from zoneinfo import ZoneInfo
import numpy as np
import discovery_paket1 as P
import discovery_paket5 as A

NY = ZoneInfo("America/New_York"); OKNO = "2026-04-01"; KONEC = "2026-09-30"
POROG = 2.39


def otchety():
    out = defaultdict(list)            # cik -> [(datetime NY, tickers)]
    for l in open(P.D / "edgar/otchety.jsonl"):
        z = json.loads(l)
        for acc, fm, it in z["sobytiya"]:
            if fm == "8-K" and "2.02" in (it or ""):
                t = dt.datetime.fromisoformat(acc.replace("Z", "+00:00")).astimezone(NY)
                out[z["cik"]].append((t, z["tickers"]))
    for c in out:
        out[c].sort()
        # несколько 8-K 2.02 за 3 дня (поправки, дубликаты) — одно событие, первое
        u = []
        for t, tk in out[c]:
            if not u or (t - u[-1][0]).days > 3:
                u.append((t, tk))
        out[c] = u
    return out


def main():
    podtv = "--podtv" in sys.argv
    A.DELIST = 0.30
    dates, px, cs = A.zagruzit(); tick, O, C, U = A.matricy(dates, px)
    kol = {t: j for j, t in enumerate(tick)}
    idx_po_date = {d: i for i, d in enumerate(dates)}
    def den_reakcii(t):
        d = t.date().isoformat()
        posle = t.time() >= dt.time(16, 0)
        for k in range(0, 8):
            dd = (t.date() + dt.timedelta(days=k)).isoformat()
            if dd in idx_po_date and (k > 0 or not posle):
                return idx_po_date[dd]
        return None
    def pervyy_torg(d0):
        for k in range(0, 8):
            dd = (d0 + dt.timedelta(days=k)).isoformat()
            if dd in idx_po_date:
                return idx_po_date[dd]
        return None
    def v_okne(i):
        return (OKNO <= dates[i] <= KONEC) if podtv else dates[i] < OKNO

    sob = {"E1": defaultdict(list), "E2": defaultdict(list), "E3": defaultdict(list)}
    rynok_cache = {}
    def rynok(i, h):
        if (i, h) not in rynok_cache:
            rynok_cache[(i, h)] = A.rynok(C, A.vselennaya(C, U, i - 1), i, h)
        return rynok_cache[(i, h)]
    def zapis(kod, i, j, h, side):
        if i is None or i < 25 or i + h >= len(dates) or not v_okne(i):
            return
        if not A.vselennaya(C, U, i - 1)[j]:
            return
        x = A.vyhod(C, j, i, h, side); m = rynok(i, h)
        if x is None or m is None:
            return
        sob[kod][dates[i]].append(x - side * m - A.KOM)

    for cik, ev in otchety().items():
        for n, (t, tk) in enumerate(ev):
            r = den_reakcii(t)
            if r is None or r < 1:
                continue
            js = [kol[s] for s in tk if s in kol and np.isfinite(C[r, kol[s]])]
            if not js:
                continue
            j = max(js, key=lambda q: U[r, q] if np.isfinite(U[r, q]) else -1)
            sled = ev[n + 1][0] if n + 1 < len(ev) else None
            # E1: вход через 84 дня, если нового отчёта ещё не было к закрытию дня входа
            e = pervyy_torg(t.date() + dt.timedelta(days=84))
            if e is not None and (sled is None or den_reakcii(sled) is None or den_reakcii(sled) > e):
                zapis("E1", e, j, 5, +1)
            # E2: реакция дня отчёта против рынка
            if np.isfinite(C[r - 1, j]):
                m1 = rynok(r - 1, 1)
                if m1 is not None:
                    re = C[r, j] / C[r - 1, j] - 1 - m1
                    if abs(re) >= 0.05:
                        zapis("E2", r, j, 20, 1 if re > 0 else -1)
            # E3: через 105 дней нового отчёта нет
            e3 = pervyy_torg(t.date() + dt.timedelta(days=105))
            if e3 is not None and (sled is None or den_reakcii(sled) is None or den_reakcii(sled) > e3) \
                    and np.isfinite(C[e3, j]):
                zapis("E3", e3, j, 20, -1)

    rez = {}
    for kod, h in (("E1", 5), ("E2", 20), ("E3", 20)):
        s = [(int(dt.date.fromisoformat(d).toordinal()) * P.DEN, float(np.mean(v)), None) for d, v in sorted(sob[kod].items())]
        it = P.itog(s, s_kontrolem=False, lag=h)
        it["sobytiy"] = sum(len(v) for v in sob[kod].values())
        if it["verdikt"] == "SURVIVED" and it["t"] < POROG:
            it["verdikt"] = "KILLED"; it["prichina"] = f"t {it['t']} < {POROG} (поправка на 3 проверки)"
        rez[kod] = it
        print(f"{kod} {'ПОДТВ' if podtv else 'ПОИСК'} {it}")
    json.dump(rez, open(P.D / f"discovery_paket6{'_podtv' if podtv else ''}.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
