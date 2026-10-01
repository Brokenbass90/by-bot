#!/usr/bin/env python3
"""discovery_paket9.py — пачка 9: подразумеваемая волатильность Deribit (DVOL), класс данных №3.
Правила заморожены 2026-10-01 ДО загрузки DVOL.

Данные: data/deribit/dvol_{BTC,ETH}.json (часовые), цены и фандинг — pit_daily BTCUSDT/ETHUSDT (перпы Bybit).
Сигнал дня — закрытие DVOL в часовой свече 23:00 UTC (до закрытия дневного бара). Сделка — discovery_paket1.sobytiya:
вход закрытием дня, 7 дней, фандинг, 12 bps на круг, без перекрытия событий одной монеты, контроль — случайные
входы той же монеты в ±15 дней (снимает общий тренд). Окна: поиск — вход до 2026-04-01; 2026-04-01…2026-09-30 —
подтверждение ОДИН раз для выживших (цены этого окна видели другие механизмы, DVOL — впервые; сказано заранее).
Порог: itog с контролем, t Ньюи–Уэста лаг 7, поправка на 2 проверки: t ≥ 2.24.

  V1 PREMIYA_ZA_STRAH   спред DVOL − реализованная волатильность 30 дн (годовая, %) в верхних 20% своих значений
                        за прошлые 365 дней → лонг 7 дней (продавцы страховки получают премию, страх преувеличен)
  V2 VSPLESK_STRAHA     DVOL вырос ≥ 25% за 3 дня → лонг 7 дней (паника и принудительное хеджирование откатываются)

    python3 research_lab/discovery_paket9.py [--podtv]
"""
import datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

OKNO = "2026-04-01"; KONEC = "2026-09-30"; POROG = 2.24; HOLD = 7


def main():
    podtv = "--podtv" in sys.argv
    M = {s: x for s, x in P.zagruzit_kripto().items() if s in ("BTCUSDT", "ETHUSDT")}
    den = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date().isoformat()
    for s, x in M.items():
        r = {int(z[0]): z[4] for z in json.load(open(P.D / f"deribit/dvol_{s[:3]}.json"))["ryad"]}
        iv = np.array([r.get(int(t) + 23 * 3_600_000, np.nan) for t in x["ts"]])
        lr = np.full(len(x["c"]), np.nan); lr[1:] = np.diff(np.log(x["c"]))
        rv = np.array([np.nanstd(lr[i - 29:i + 1]) * np.sqrt(365) * 100 if i >= 30 else np.nan for i in range(len(lr))])
        sp = iv - rv
        pct = np.array([np.mean(sp[i - 365:i][np.isfinite(sp[i - 365:i])] < sp[i])
                        if i >= 365 and np.isfinite(sp[i]) and np.isfinite(sp[i - 365:i]).sum() >= 200 else np.nan
                        for i in range(len(sp))])
        ch3 = np.full(len(iv), np.nan); ch3[3:] = iv[3:] / iv[:-3] - 1
        okno = np.array([(OKNO <= den(t) <= KONEC) if podtv else den(t) < OKNO for t in x["ts"]])
        x["v1"] = okno & (pct >= 0.8); x["v2"] = okno & (ch3 >= 0.25)
        x["pokr"] = float(np.isfinite(iv).mean())
    rez = {}
    for kod in ("v1", "v2"):
        sob = P.sobytiya(M, lambda x, k=kod: x[k], HOLD, +1)
        it = P.itog(sob, s_kontrolem=True, lag=HOLD)
        if it["verdikt"] == "SURVIVED" and it["t"] < POROG:
            it["verdikt"] = "KILLED"; it["prichina"] = f"t {it['t']} < {POROG} (поправка на 2 проверки)"
        rez[kod.upper()] = it
        print(f"{kod.upper()} {'ПОДТВ' if podtv else 'ПОИСК'} {it}")
    print("покрытие DVOL по дням:", {s: round(x["pokr"], 2) for s, x in M.items()})
    json.dump(rez, open(P.D / f"discovery_paket9{'_podtv' if podtv else ''}.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
