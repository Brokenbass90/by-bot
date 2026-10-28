#!/usr/bin/env python3
"""brain_portfel_v1.py — prereg/PREREG_BRAIN_PORTFEL_V1_2026_10_28.md. Только чтение результатов. python3 research_lab/brain_portfel_v1.py"""
import collections, glob, hashlib, json, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; H = 3600000; OT = 1788220800000

def dannye():
    p = json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]))["sdelki"]
    P = [dict(noga="PUMP4", sym=x["sym"], t0=x["ts"] + H, t1=x["ts"] + (x["barov"] + 2) * H, R=x["R"], stop=x["risk_pct"] / 100)
         for x in p if x.get("status") == "ZAKRYTA" and x.get("R") is not None and x["ts"] >= OT]
    s = json.load(open(sorted(glob.glob(str(HERE / "results" / "short_hvost_uderzhanie_*.json")))[-1]))["sdelki"]
    S = [dict(noga="SH", sym=x["sym"], t0=x["ts"], t1=x["16"]["kon"], bps=x["16"]["net_hedzh"]) for x in s if x["ts"] >= OT]
    return sorted(P + S, key=lambda x: x["t0"])

def sim(ev, dep, riskp, nomp, scen):
    otkr, res, prop = [], [], collections.Counter()
    for e in ev:
        if scen == "A" and e["noga"] != "PUMP4": continue
        if scen == "B" and e["noga"] != "SH": continue
        otkr = [o for o in otkr if o["t1"] > e["t0"]]
        if e["noga"] == "PUMP4":
            r = dep * riskp; nom = r / e["stop"]; m = nom / 10; pnl = e["R"] * r
        else:
            if sum(1 for o in otkr if o["noga"] == "SH") >= 3: prop["SH_limit3"] += 1; continue
            nom = dep * nomp; m = nom + nom / 10; pnl = nom * e["bps"] / 1e4
        if scen == "D" and any(o["sym"] == e["sym"] for o in otkr): prop[e["noga"] + "_dvoynaya"] += 1; continue
        if scen == "C":
            if sum(o["m"] for o in otkr if o["noga"] == e["noga"]) + m > dep * 0.5: prop[e["noga"] + "_marzha"] += 1; continue
        elif sum(o["m"] for o in otkr) + m > dep: prop[e["noga"] + "_marzha"] += 1; continue
        otkr.append(dict(e, m=m)); res.append(dict(e, pnl=pnl, m=m))
    eq = pik = dep; dd = 0; pik_m = 0; dni = collections.defaultdict(float)
    for x in sorted(res, key=lambda x: x["t1"]):
        eq += x["pnl"]; pik = max(pik, eq); dd = max(dd, pik - eq); dni[time.strftime("%Y-%m-%d", time.gmtime(x["t1"] / 1000))] += x["pnl"]
    for x in res:
        pik_m = max(pik_m, sum(y["m"] for y in res if y["t0"] <= x["t0"] < y["t1"]))
    vz = collections.Counter(x["noga"] for x in res)
    return dict(net=round(sum(x["pnl"] for x in res), 1), dd=round(dd, 1), dd_pct=round(dd / dep * 100, 1), vzyato=dict(vz), propushcheno=dict(prop),
                pik_marzhi=round(pik_m), hudshie_dni=[(d, round(v, 1)) for d, v in sorted(dni.items(), key=lambda kv: kv[1])[:3]])

def main():
    sha = hashlib.sha256((HERE / "prereg/PREREG_BRAIN_PORTFEL_V1_2026_10_28.md").read_bytes()).hexdigest()
    ev = dannye(); t0, t1 = ev[0]["t0"], max(e["t1"] for e in ev); mid = (t0 + t1) // 2
    print("prereg", sha[:12], "событий", collections.Counter(e["noga"] for e in ev), "дней", round((t1 - t0) / 864e5, 1),
          "граница половин", time.strftime("%Y-%m-%d", time.gmtime(mid / 1000)))
    out = {}
    for dep in (1000, 2500):
        out[dep] = {}
        for scen in ("A", "B", "C", "D"):
            for rp in (0.005, 0.01, 0.02):
                for npct in (0.05, 0.10, 0.20):
                    if scen == "A" and npct != 0.10: continue
                    if scen == "B" and rp != 0.01: continue
                    k = f"{scen} риск{rp*100:g}% ном{npct*100:g}%"
                    out[dep][k] = dict(vse=sim(ev, dep, rp, npct, scen), r1=sim([e for e in ev if e["t0"] < mid], dep, rp, npct, scen),
                                       r2=sim([e for e in ev if e["t0"] >= mid], dep, rp, npct, scen))
        dk = {k: v for k, v in out[dep].items() if k.startswith("D")}
        luch = max(dk, key=lambda k: dk[k]["r1"]["net"] / (dk[k]["r1"]["dd"] + 1))
        out[dep]["_vybor"] = dict(vybrano_na_1_polovine=luch, polovina1=dk[luch]["r1"], polovina2_otsenka=dk[luch]["r2"])
        print(f"\n=== депозит ${dep} ===")
        for k, v in out[dep].items():
            if k.startswith("_"): continue
            a = v["vse"]; print(f"{k:24s} net ${a['net']:7.1f}  просадка ${a['dd']:6.1f} ({a['dd_pct']}%)  взято {a['vzyato']}  пропуск {a['propushcheno']}  пик маржи ${a['pik_marzhi']}")
        print("ВЫБОР (по 1-й половине):", luch, "| 1-я:", dk[luch]["r1"]["net"], "/ просадка", dk[luch]["r1"]["dd"], "| 2-я (оценка):", dk[luch]["r2"]["net"], "/ просадка", dk[luch]["r2"]["dd"],
              "| худшие дни 2-й:", dk[luch]["r2"]["hudshie_dni"])
    (HERE / "results" / time.strftime("brain_portfel_v1_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(dict(prereg_sha=sha, rezultat=out), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
