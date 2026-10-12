#!/usr/bin/env python3
"""spot_potok_izmereniya.py — экран БЕЗ доходностей по PREREG_SPOT_POTOK_TEZIS_2026_10_12.md (M1, M2, M3).
Цены не читаются вовсе: только metrics (OI для PIT топ-50), перп-доля тейкеров (KITY M3) и спот-доля тейкеров.
Решение по правилу prereg пишется в data/binance_kity/SPOT_IZMERENIYA.json. Запуск после spot_taker_gotovo.json.

    python3 research_lab/spot_potok_izmereniya.py
"""
import datetime as dt, json, sys
import numpy as np
import kity_sudya as K

B = K.B; OUT = B / "SPOT_IZMERENIYA.json"


def doli(papka):
    r = {}
    for f in (B / papka).glob("*.json"):
        d = {}
        for t, qv, tq in json.loads(f.read_text()):
            if qv > 0:
                d[K.den(t).isoformat()] = tq / qv
        r[f.stem] = d
    return r


def rangi(a): return np.argsort(np.argsort(a)).astype(float)


def spirmen(a, b):
    if len(a) < 10: return None
    c = np.corrcoef(rangi(np.array(a)), rangi(np.array(b)))[0, 1]
    return float(c) if np.isfinite(c) else None


def main():
    if not (B / "spot_taker_gotovo.json").exists():
        sys.exit("нет spot_taker_gotovo.json — загрузка спота не закончена")
    M = K.zagruzit(); perp = doli("taker"); spot = doli("spot_taker")
    rez = dict(prereg="PREREG_SPOT_POTOK_TEZIS_2026_10_12.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    for imya, (a, b) in dict(PRIMARY=K.PRIMARY, REPLICATION=K.REPLIK).items():
        kA, kB, nmon, pokr = [], [], [], 0
        ned = [d for d in K.SETKA if a <= d <= b]
        for d in ned:
            vch = (d - dt.timedelta(days=1)).isoformat()
            oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
            sp = [s for _, s in oi if vch in spot.get(s, {})]
            pokr += len(sp) >= 30; nmon.append(len(sp))
            para = [(spot[s][vch], perp[s][vch]) for s in sp if vch in perp.get(s, {})]
            if len(para) >= 10:
                A = [x for x, _ in para]; P = [y for _, y in para]; D = [x - y for x, y in para]
                ca, cb = spirmen(A, P), spirmen(D, P)
                if ca is not None: kA.append(ca)
                if cb is not None: kB.append(cb)
        rez[imya] = dict(nedel=len(ned), pokrytie=round(pokr / max(1, len(ned)), 3), med_monet=int(np.median(nmon)) if nmon else 0,
                         M1_korr_spot_s_M3=round(float(np.mean(kA)), 3) if kA else None,
                         M2_korr_raznica_s_M3=round(float(np.mean(kB)), 3) if kB else None, nedel_s_korr=len(kA))
    p = rez["PRIMARY"]; kand = {k: v for k, v in (("A_spot", p["M1_korr_spot_s_M3"]), ("B_spot_minus_perp", p["M2_korr_raznica_s_M3"]))
                               if v is not None}
    if p["pokrytie"] < 0.9:
        rez["reshenie"] = "BLOCKED_DATA"
    elif not kand or min(abs(v) for v in kand.values()) >= 0.7:
        rez["reshenie"] = "KILL_BEZ_PNL_DUBL_KITY_M3"
    else:
        rez["reshenie"] = "VYBRAN_" + min(kand, key=lambda k: abs(kand[k]))
    OUT.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
