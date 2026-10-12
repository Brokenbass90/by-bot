#!/usr/bin/env python3
"""Ложный пробой | REZHIM_V1 = NEUTRAL — единственный причинный вариант (POSTMORTEM_LOZHNYY_PROBOY_I_VARIANT_2026_10_12).
Определение, фильтры (vol ≥ 1.5, lev ≤ 100), геометрия, издержки, фандинг A6 — из lozhnyy_proboy_pnl.py без изменений.
Отличия: (1) событие берётся ⇔ режим, известный на конец часа бара провала, = NEUTRAL; (2) контроль — случайные часы того же
месяца, у которых режим на момент входа тоже NEUTRAL; (3) окно 2026-07-01…2026-10-01 на data/h1_svezhie. Один прогон."""
import datetime as dt, glob, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika")); sys.path.insert(0, str(LAB / "os2"))
import lozhnyy_proboy_izmereniya as IZ
import lozhnyy_proboy_pnl as P
import rezhim_v1 as RV
H = P.H; DATA = LAB / "data/h1_svezhie"; OUT = LAB / "data/lozhnyy_proboy"
IZ.T0 = int(dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
IZ.T1 = int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
SER = int(dt.datetime(2026, 8, 16, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    if (OUT / "VARIANT_ITOG.json").exists(): print("уже выполнен — повтор запрещён"); return 1
    b = np.load(DATA / "BTCUSDT.npz"); bts = b["ts"].astype(np.int64)
    lab = dict(zip((int(t) for t in bts), RV.metki(bts, b["ohlcv"].astype(float))))          # состояние на конец часа t
    ym = lambda tt: dt.datetime.fromtimestamp(int(tt) / 1000, dt.timezone.utc).strftime("%Y-%m")
    rows = []; sch = defaultdict(int)
    for fpath in sorted(glob.glob(str(DATA / "*.npz"))):
        sym = Path(fpath).stem
        if sym in IZ.DEV13: continue
        z = np.load(fpath); ts = z["ts"].astype(np.int64); x = z["ohlcv"].astype(float)
        o, h, l, c, v = x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4]
        ev = P.sobytiya_s_indeksami(ts, o, h, l, c, v); sch["sobytiy"] += len(ev)
        pf = LAB / "data/pit_daily" / f"{sym}.json"
        FD = P.Fanding(sorted((int(a), float(q)) for a, q in json.load(open(pf))["funding"])) if pf.exists() else None
        mes = defaultdict(list)
        for k in range(1, len(ts) - P.HOLD):
            if lab.get(int(ts[k - 1])) == "NEUTRAL": mes[ym(ts[k])].append(k)
        for e in ev:
            if e["vr"] is None or e["vr"] < 1.5: sch["otkaz_vol"] += 1; continue
            lev = e["vhod"] / e["risk"]
            if lev > 100: sch["otkaz_lev"] += 1; continue
            rz = lab.get(int(ts[e["f"]]))
            if rz is None: sch["rezhim_unknown"] += 1; continue
            if rz != "NEUTRAL": sch["ne_neutral"] += 1; continue
            i = e["f"] + 1
            r = P.sdelka(ts, o, h, l, c, i, e["st"], e["vhod"], e["stop"], e["cel"])
            if r is None: sch["net_dannyh"] += 1; continue
            fr = FD.r(int(ts[i]), int(ts[r[1]]) + H, e["st"], lev) if FD else None
            if fr is None: sch["funding_unknown"] += 1; continue
            R = r[0] - lev * P.KOST + fr; ds, dc = e["risk"] / e["vhod"], abs(e["vhod"] - e["cel"]) / e["vhod"]
            rng = np.random.default_rng(int(hashlib.sha256(f"{sym}|{e['ts']}".encode()).hexdigest()[:12], 16))
            pool = mes[ym(ts[i])]; kr = []
            for _ in range(P.DRAWS * 3):
                if len(kr) >= P.DRAWS or not pool: break
                k = int(rng.choice(pool)); vk = o[k]
                stp = vk * (1 + ds) if e["st"] > 0 else vk * (1 - ds); cl = vk * (1 - dc) if e["st"] > 0 else vk * (1 + dc)
                rk = P.sdelka(ts, o, h, l, c, k, e["st"], vk, stp, cl)
                if rk is None: continue
                fk = FD.r(int(ts[k]), int(ts[rk[1]]) + H, e["st"], lev)
                if fk is None: continue
                kr.append(rk[0] - lev * P.KOST + fk)
            if len(kr) < 5: sch["net_kontrolya"] += 1; continue
            rows.append(dict(s=sym, ts=e["ts"], R=R, izb=R - float(np.mean(kr))))
    n = len(rows); R = np.array([x["R"] for x in rows]) if rows else np.array([0.0])
    def tk(idx):
        if not idx: return None
        sub = [rows[i] for i in idx]; m = float(np.mean([x["izb"] for x in sub])); g = defaultdict(float)
        for x in sub: g[x["s"]] += x["izb"] - m
        se = math.sqrt(sum(q * q for q in g.values())) / len(sub); return dict(n=len(sub), sred_izb=round(m, 4), t=round(m / se, 2) if se > 0 else None)
    vse = list(range(n)); a, h1, h2 = tk(vse), tk([i for i in vse if rows[i]["ts"] < SER]), tk([i for i in vse if rows[i]["ts"] >= SER])
    fu = sch["funding_unknown"] / max(1, n + sch["funding_unknown"])
    if fu > 0.05: verdikt = "BLOCKED_DATA"
    elif n >= 300 and R.mean() > 0 and a and a["t"] and a["t"] >= 2.5 and h1 and h2 and np.sign(h1["sred_izb"]) == np.sign(h2["sred_izb"]) == np.sign(a["sred_izb"]):
        verdikt = "PASS_KANDIDAT"
    else: verdikt = "FAIL_TERMINAL_KILL"
    rez = dict(postmortem="POSTMORTEM_LOZHNYY_PROBOY_I_VARIANT_2026_10_12.md", verdikt=verdikt, schetchiki=dict(sch), n=n,
               sred_net_R=round(float(R.mean()), 4) if n else None, pf=round(float(R[R > 0].sum() / -R[R < 0].sum()), 3) if n and (R < 0).any() else None,
               izbytok=a, polovina_1=h1, polovina_2=h2, data_manifest_sha256=hashlib.sha256((DATA / "MANIFEST.json").read_bytes()).hexdigest())
    (OUT / "VARIANT_ITOG.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
