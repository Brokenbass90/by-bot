#!/usr/bin/env python3
"""alpaca_pead.py — prereg/PREREG_ALPACA_PEAD_2026_10_29.md. Только чтение.  python3 research_lab/alpaca_pead.py <папка дневок>"""
import collections, csv, datetime as dt, hashlib, json, math, statistics as st, sys, time
from pathlib import Path
from zoneinfo import ZoneInfo
HERE = Path(__file__).resolve().parent; ET = ZoneInfo("America/New_York")
def zag(p): return {dt.datetime.utcfromtimestamp(int(float(r["ts"]))).date(): float(r["c"]) for r in csv.DictReader(open(p))}
def main():
    sha = hashlib.sha256((HERE / "prereg/PREREG_ALPACA_PEAD_2026_10_29.md").read_bytes()).hexdigest()
    D = Path(sys.argv[1]); C = {p.stem.replace("_M5", ""): zag(p) for p in D.glob("*_M5.csv") if p.stem not in ("SPY_M5", "QQQ_M5")}
    E = json.loads((HERE / "data" / "alpaca_sobytiya" / "otchetnosti.json").read_text()); ev = []
    for t, sob in E.items():
        c = C.get(t)
        if not c: continue
        dni = sorted(c); idx = {d: i for i, d in enumerate(dni)}
        for s in sob:
            if s["data"] < "2015-01-01": continue
            a = dt.datetime.fromisoformat(s["prinyato"].replace("Z", "+00:00")).astimezone(ET)
            d0 = a.date() if (a.hour, a.minute) < (9, 30) else a.date() + dt.timedelta(days=1)
            k = next((idx[d] for d in dni[max(0, idx.get(d0, 0) - 1):] if d >= d0), None) if d0 <= dni[-1] else None
            if k is None or k < 1 or k + 20 >= len(dni): continue
            reak = c[dni[k]] / c[dni[k - 1]] - 1
            if reak < 0.04: continue
            vh, vy = dni[k], dni[k + 20]
            vse = [C[s2][vy] / C[s2][vh] - 1 for s2 in C if vh in C[s2] and vy in C[s2]]
            ev.append(dict(t=t, d=str(vh), reak=round(reak, 4), izb=(c[vy] / c[vh] - 1 - 0.002) - st.mean(vse)))
    po = collections.defaultdict(list)
    for e in ev: po[e["d"]].append(e["izb"])
    m = [st.mean(v) for v in po.values()]; tt = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    h1 = [e["izb"] for e in ev if e["d"] < "2021-01-01"]; h2 = [e["izb"] for e in ev if e["d"] >= "2021-01-01"]
    out = dict(prereg_sha=sha, sobytiy=len(ev), dat=len(m), sred_izbytok_pct=round(st.mean(x["izb"] for x in ev) * 100, 2) if ev else None, t_daty=round(tt, 2) if tt else None,
               polovina_2015_2020_pct=round(st.mean(h1) * 100, 2) if h1 else None, polovina_2021_2026_pct=round(st.mean(h2) * 100, 2) if h2 else None,
               dolya_plus=round(sum(x["izb"] > 0 for x in ev) / len(ev), 3) if ev else None, v_god_sobytiy=round(len(ev) / 11.7, 1))
    out["vyvod"] = "PASS_V_TEN" if ev and len(ev) >= 100 and out["sred_izbytok_pct"] > 0 and (tt or 0) >= 2 and (out["polovina_2015_2020_pct"] or 0) > 0 and (out["polovina_2021_2026_pct"] or 0) > 0 else "FAIL"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("alpaca_pead_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(out, sobytiya=ev), ensure_ascii=False))
if __name__ == "__main__":
    main()
