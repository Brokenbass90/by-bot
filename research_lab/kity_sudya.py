#!/usr/bin/env python3
"""kity_sudya.py — судья PREREG_KITY_POZICII_2026_10_03.md. Закоммичен ДО загрузки данных.
ОДИН прогон (PRIMARY + REPLICATION + независимость): результат data/binance_kity/kity_rezultat.json, повтор запрещён.

    python3 research_lab/kity_sudya.py
"""
import datetime as dt, json, sys
import numpy as np
import discovery_paket1 as P

B = P.D / "binance_kity"
REZ = B / "kity_rezultat.json"
PRIMARY = (dt.date(2023, 1, 1), dt.date(2026, 9, 23))
REPLIK = (dt.date(2021, 7, 1), dt.date(2022, 12, 31))
DATA_DO = dt.date(2026, 9, 30)
SETKA = [dt.date(2021, 7, 1) + dt.timedelta(days=7 * k) for k in range(400)]
SETKA = [d for d in SETKA if d <= PRIMARY[1]]
TOLPA, M2 = 0, 1


def den(t): return dt.datetime.fromtimestamp(int(t) / 1000, dt.timezone.utc).date()


def zagruzit():
    M = {}
    for f in sorted((B / "klines").glob("*.json")):
        s = f.stem; kl = np.array(json.loads(f.read_text()), dtype=float)
        if len(kl) < 61:
            continue
        fp = B / "funding" / f"{s}.json"
        fr = np.array((json.loads(fp.read_text()) if fp.exists() else []) or [[0, 0.0]], dtype=float)
        M[s] = dict(ts=kl[:, 0].astype(np.int64), c=kl[:, 4], fts=fr[:, 0].astype(np.int64), fr=fr[:, 1],
                    met=json.loads((B / "metrics" / f"{s}.json").read_text()))
    return M


def sdelka(x, i, hold, side):
    t_vyh = int(x["ts"][i]) + hold * P.DEN
    j = int(np.searchsorted(x["ts"], t_vyh, side="right")) - 1
    if j <= i:
        return None
    if x["ts"][j] != t_vyh and den(x["ts"][-1]) >= DATA_DO - dt.timedelta(days=1):
        return None
    return side * (x["c"][j] / x["c"][i] - 1) - side * P.fand(x, x["ts"][i], x["ts"][j]) - P.KOM_KRIPTO


def main():
    if REZ.exists():
        sys.exit(f"результат уже есть ({REZ}) — прогон один")
    if not (B / "gotovo.json").exists():
        sys.exit("нет data/binance_kity/gotovo.json — загрузка не закончена")
    M = zagruzit()
    print("загрузка:", json.loads((B / "gotovo.json").read_text()), "| монет с ценами:", len(M))

    def nedelya(d, kol, znak):
        """znak +1: лонг верхнего дециля признака (за китами); −1: шорт верхнего (против толпы, как L1)"""
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        t = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 60:
                continue
            v = x["met"][vch][kol]
            if v is not None and np.isfinite(v):
                rows.append((v, s, i))
        if len(rows) < 30:
            return None
        rows.sort(); k = len(rows) // 10
        leg = [sdelka(M[s], i, 7, -znak) for _, s, i in rows[:k]] + [sdelka(M[s], i, 7, +znak) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    def okno(a, b, kol, znak):
        sob = []
        for d in SETKA:
            if a <= d <= b:
                r = nedelya(d, kol, znak)
                if r is not None:
                    sob.append((int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000), r, None))
        return sob

    rez = dict(prereg="PREREG_KITY_POZICII_2026_10_03.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    sp = okno(*PRIMARY, M2, +1); it = P.itog(sp, s_kontrolem=False, lag=1)
    if it["verdikt"] == "SURVIVED" and it.get("dney", 0) < 52:
        it["verdikt"] = "KILLED"; it["prichina"] = f"недель {it.get('dney')} < 52"
    rez["PRIMARY"] = it
    sr = okno(*REPLIK, M2, +1); ir = P.itog(sr, s_kontrolem=False, lag=1)
    ir["status"] = ("CROSS_PERIOD_PASS" if ir["verdikt"] == "SURVIVED" else
                    ("SAME_SIGN" if ir.get("edge_bps", 0) > 0 else "OPPOSITE"))
    rez["REPLICATION"] = ir
    tolpa = dict((t, r) for t, r, _ in okno(PRIMARY[0], PRIMARY[1], TOLPA, -1) + okno(*REPLIK, TOLPA, -1))
    para = [(r, tolpa[t]) for t, r, _ in sp + sr if t in tolpa]
    korr = float(np.corrcoef(*zip(*para))[0, 1]) if len(para) > 10 else None
    rez["nezavisimost"] = dict(korr_s_TOLPA_L1=None if korr is None else round(korr, 2), nedel=len(para),
                               nezavisima=korr is not None and abs(korr) < 0.5)
    pr_ok = it["verdikt"] == "SURVIVED"
    rez["status"] = ("CANDIDATE_FOR_COST_GATE" if pr_ok and ir["status"] != "OPPOSITE" and rez["nezavisimost"]["nezavisima"]
                     else ("PRIMARY_PASS_BUT_" + ("REPLICATION_OPPOSITE" if ir["status"] == "OPPOSITE" else "TOLPA_DEPENDENT")
                           if pr_ok else "PNL_FAIL → причинный постмортем (бюджет спасения: 1 вариант)"))
    REZ.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    for k in ("PRIMARY", "REPLICATION", "nezavisimost", "status"):
        print(k, ":", rez[k])


if __name__ == "__main__":
    main()
