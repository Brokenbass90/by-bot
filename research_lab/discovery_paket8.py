#!/usr/bin/env python3
"""discovery_paket8.py — пачка 8: TOLPA_1D, производная от TOLPA_XS (L1) на часовых данных толпы.
Разрешена менеджером 01.10 как ОДИН производный механизм. Правила заморожены 2026-10-01 ДО загрузки
часовых данных до конца и до любого взгляда на результаты.

Одна семья с L1 (7 дней): доказательства не складываются. История часовых данных — только дешёвая
фальсификация/поиск, НЕ подтверждение. Выжил → только проспективное подтверждение (отдельная предрегистрация).

Механизм: та же гипотеза «толпа ошибается на краях», но сигнал свежее и горизонт короче.
  Каждый день: вселенная PIT топ-50 по OI в $ на эту дату; признак — доля лонг-аккаунтов Bybit в часовой
  точке 22:00 UTC этого дня (до закрытия дневного бара в 24:00); шорт верхнего дециля, лонг нижнего;
  вход закрытием дня, удержание 1 день; discovery_paket1.sdelka (фандинг, 12 bps на круг — дневной оборот
  дорог, это часть проверки). Окно — вся история до 2026-09-30. Правило — itog, t Ньюи–Уэста лаг 1, порог 2.0
  (одна проверка). Запуск только при покрытии ≥ 90% символов вселенной часовыми данными.

    python3 research_lab/discovery_paket8.py
"""
import datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

KONEC = "2026-09-30"; CHAS = 22


def main():
    sv = json.load(open(P.D / "basis/vselennaya_pit_usd50.json"))
    sostav = {d: set(v) for d, v in sv["sostav"].items()}
    est = {f.stem for f in (P.D / "poz_chas").glob("*USDT*.json")}
    pokr = len(est & set(sv["simvoly"])) / len(sv["simvoly"])
    if pokr < 0.9:
        sys.exit(f"покрытие часовыми данными {pokr:.0%} < 90% — дождаться окончания --poz-chas")
    M = P.zagruzit_kripto()
    for s, x in M.items():
        f = P.D / "poz_chas" / f"{s}.json"
        m = {int(t): v for t, v in json.load(open(f))["lsr"]} if f.exists() else {}
        x["lsr"] = np.array([m.get(int(t) + CHAS * 3_600_000, np.nan) for t in x["ts"]])
    den = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date().isoformat()
    ts_all = sorted({int(t) for x in M.values() for t in x["ts"]})
    sob = []
    for t in ts_all[60:]:
        if den(t) > KONEC:
            continue
        rows = []
        for s, x in M.items():
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60 or s not in sostav.get(den(t), ()):
                continue
            if np.isfinite(x["lsr"][i]):
                rows.append((x["lsr"][i], s, i))
        if len(rows) < 30:
            continue
        rows.sort(); k = len(rows) // 10
        leg = [P.sdelka(M[s], i, 1, +1) for _, s, i in rows[:k]] + [P.sdelka(M[s], i, 1, -1) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        if leg:
            sob.append((t, float(np.mean(leg)), None))
    it = P.itog(sob, s_kontrolem=False, lag=1)
    it["pokrytie"] = round(pokr, 3)
    print("TOLPA_1D ПОИСК:", it)
    json.dump(it, open(P.D / "discovery_paket8.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
