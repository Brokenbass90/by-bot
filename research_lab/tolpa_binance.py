#!/usr/bin/env python3
"""tolpa_binance.py — судья PREREG_TOLPA_BINANCE_REPLICATION_2021_2022.md. Закоммичен ДО скачивания данных.
ОДИН прогон: результат пишется в data/binance/tolpa_binance_rezultat.json; повторный запуск отказывается.

Правила (перенос с discovery_paket7 L1 / discovery_paket8 TOLPA_1D, отличия — в prereg):
  бар d: ts = 00:00 UTC дня d, вход закрытием дня d; удержание L1 7 дней, 1D — 1 день;
  вселенная дня d: PIT топ-50 по sum_open_interest_value в 23:55 дня d−1 (строго до даты), снятые включены;
  допуск монеты: ≥ 60 дневных баров истории до входа (как на Bybit);
  L1: признак r00 дня d−1; даты 2021-07-01 + 7k ≤ 2022-12-31;
  1D: признак r22 дня d; каждый день 2021-07-01…2022-12-31;
  шорт верхнего дециля count_long_short_ratio, лонг нижнего (k = n//10), ≥ 30 монет с признаком;
  сделка: закрытие→закрытие, фандинг Binance, 12 bps на круг (discovery_paket1.KOM_KRIPTO);
  монета исчезла в удержании → выход по последнему закрытию.
Вердикт: discovery_paket1.itog (t Ньюи–Уэста лаг 1, обе половины > 0, сырой > 0) + ≥ 52 недель для L1
(для 1D — ≥ 52 дат тоже, формально). PRIMARY = L1, SECONDARY = 1D (поддерживающая, не спасает primary).

    python3 research_lab/tolpa_binance.py
"""
import datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

B = P.D / "binance"
REZ = B / "tolpa_binance_rezultat.json"
NACH, KON = dt.date(2021, 7, 1), dt.date(2022, 12, 31)
DATA_DO = dt.date(2023, 1, 15)


def den(t): return dt.datetime.fromtimestamp(int(t) / 1000, dt.timezone.utc).date()


def zagruzit():
    M = {}
    for f in sorted((B / "klines").glob("*.json")):
        s = f.stem
        kl = np.array(json.loads(f.read_text()), dtype=float)
        if len(kl) < 61:
            continue
        fr = json.loads((B / "funding" / f"{s}.json").read_text()) if (B / "funding" / f"{s}.json").exists() else []
        fr = np.array(fr or [[0, 0.0]], dtype=float)
        met = json.loads((B / "metrics" / f"{s}.json").read_text())
        M[s] = dict(ts=kl[:, 0].astype(np.int64), c=kl[:, 4], fts=fr[:, 0].astype(np.int64), fr=fr[:, 1], met=met)
    return M


def sdelka(x, i, hold, side):
    """как discovery_paket1.sdelka, но выход по календарю; монета исчезла → выход по последнему закрытию"""
    t_vyh = int(x["ts"][i]) + hold * P.DEN
    j = int(np.searchsorted(x["ts"], t_vyh, side="right")) - 1     # последнее закрытие не позже цели
    if j <= i:
        return None
    if x["ts"][j] != t_vyh and den(x["ts"][-1]) >= DATA_DO - dt.timedelta(days=1):
        return None                    # дыра в данных живой монеты, а не снятие — сделку не выдумываем
    return side * (x["c"][j] / x["c"][i] - 1) - side * P.fand(x, x["ts"][i], x["ts"][j]) - P.KOM_KRIPTO


def main():
    if REZ.exists():
        sys.exit(f"результат уже есть ({REZ}) — прогон один, повтор запрещён prereg")
    g = B / "gotovo.json"
    if not g.exists():
        sys.exit("нет data/binance/gotovo.json — загрузка не закончена")
    M = zagruzit()
    print("загрузка:", json.loads(g.read_text()), "| монет с барами:", len(M))

    def vselennaya(d):
        vchera = (d - dt.timedelta(days=1)).isoformat()
        oi = [(x["met"][vchera][2], s) for s, x in M.items() if vchera in x["met"] and x["met"][vchera][2]]
        return {s for _, s in sorted(oi, reverse=True)[:50]}

    def xs(daty, priznak, hold):
        sob, pustyh = [], 0
        for d in daty:
            t = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
            U = vselennaya(d); rows = []
            for s in U:
                x = M[s]; i = int(np.searchsorted(x["ts"], t))
                if i >= len(x["ts"]) or x["ts"][i] != t or i < 60:
                    continue
                v = priznak(x, d)
                if v is not None and np.isfinite(v):
                    rows.append((v, s, i))
            if len(rows) < 30:
                pustyh += 1; continue
            rows.sort(); k = len(rows) // 10
            leg = [sdelka(M[s], i, hold, +1) for _, s, i in rows[:k]] + [sdelka(M[s], i, hold, -1) for _, s, i in rows[-k:]]
            leg = [r for r in leg if r is not None]
            if leg:
                sob.append((t, float(np.mean(leg)), None))
        it = P.itog(sob, s_kontrolem=False, lag=1)
        it["dat_propushcheno_lt30"] = pustyh
        if it["verdikt"] == "SURVIVED" and it.get("dney", 0) < 52:
            it["verdikt"] = "KILLED"; it["prichina"] = f"дат {it.get('dney')} < 52"
        return it

    def r_vchera(x, d):
        v = x["met"].get((d - dt.timedelta(days=1)).isoformat()); return v[0] if v else None

    def r_22(x, d):
        v = x["met"].get(d.isoformat()); return v[1] if v else None

    ned = [NACH + dt.timedelta(days=7 * k) for k in range(200) if NACH + dt.timedelta(days=7 * k) <= KON]
    dni = [NACH + dt.timedelta(days=k) for k in range((KON - NACH).days + 1)]
    L1 = xs(ned, r_vchera, 7)
    D1 = xs(dni, r_22, 1)
    status = "CROSS_VENUE_HISTORICAL_REPLICATION_PASS" if L1["verdikt"] == "SURVIVED" else "TOLPA_FAMILY_KILLED"
    rez = dict(prereg="PREREG_TOLPA_BINANCE_REPLICATION_2021_2022.md",
               kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               PRIMARY_L1=L1, SECONDARY_1D=D1, status=status,
               primechanie="1D поддерживающая и не спасает primary; деньги — только решением владельца")
    REZ.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print("PRIMARY L1 :", L1); print("SECONDARY 1D:", D1); print("СТАТУС:", status)


if __name__ == "__main__":
    main()
