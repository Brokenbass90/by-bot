#!/usr/bin/env python3
"""PREREG_ALPACA_WEEKLY_FILL_2026_10_26 (a7c9426). Запуск из дерева Alpaca:
  cd <alpaca-wt> && python3 <this> --vyvod out.json --ruki MONTHLY,WEEKLY_FILL,SPY  |  --ruki RANDOM --zerna 0-4
Monthly v6 (_decisions v38_successor_gated) без изменений; дозаполнение — функция поверх dvizhok_x."""
import argparse, bisect, json, math, random, statistics as st, sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, ".")
from backtest.alpaca_bakeoff_v2_contract import spy200_gate
from backtest.alpaca_honest_portfolio import LiveProtectionDailyProxy, Candidate
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_mehaniki_v1 import _sobrat
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
from research_lab.alpaca_ustoychivost_v1 import _godovyh
from scripts.run_alpaca_honest_diagnostic import _decisions
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

NACH, KON = date(2016, 1, 4), date(2026, 9, 4)


def sdelat_fill(p, clusters, sessii, vhody_mes, rng=None, zhurnal=None):
    idx = {s: {r.session_date: i for i, r in enumerate(rows)} for s, rows in p.items()}
    sled = {sessii[i]: sessii[i + 1] for i in range(len(sessii) - 1)}
    nomer = {s: i for i, s in enumerate(sessii)}
    sost = {"prev": set(), "stop_i": -10**9}
    vsel = [s for s in p if s not in ("SPY", "QQQ")]

    def podbor(session, derzhim, blok):
        # выходы вне сессий входа Monthly = стоп (ротация бывает только в сессию решения)
        ushli = sost["prev"] - set(derzhim)
        if ushli and session not in vhody_mes:
            sost["stop_i"] = nomer[session]
        sost["prev"] = set(derzhim)
        n = sled.get(session)
        if n is None or n.isocalendar()[:2] == session.isocalendar()[:2]:
            return ()
        svob = 4 - len(derzhim)
        zap = {"session": session.isoformat(), "svobodno": svob}
        if zhurnal is not None: zhurnal.append(zap)
        if svob <= 0:
            zap["prichina"] = "net_mest"; return ()
        sp = p["SPY"]; i = idx["SPY"].get(session)
        z = [r.close for r in sp[:i + 1]]
        if not spy200_gate(z) or z[-1] < sum(z[-50:]) / 50:
            zap["prichina"] = "rynok"; return ()
        if nomer[session] - sost["stop_i"] < 5:
            zap["prichina"] = "pauza_posle_stopa"; return ()
        r5, sila = {}, {}
        for s in vsel:
            j = idx[s].get(session)
            if j is None or j < 252: continue
            c = p[s]
            r5[s] = c[j].close / c[j - 5].close - 1
            m = c[j - 21].close / c[j - 252].close - 1
            if m > 0: sila[s] = m
        if len(r5) < 10:
            zap["prichina"] = "malo_dannyh"; return ()
        porog = sorted(r5.values())[int(0.9 * len(r5))]
        dop = [s for s in sila if r5[s] < porog and s not in derzhim and session >= blok.get(s, date.min)]
        zap["dopustimo"] = len(dop)
        if not dop:
            zap["prichina"] = "net_kandidatov"; return ()
        hist, syrye = {}, []
        for s in set(dop) | set(derzhim):
            j = idx[s].get(session)
            if j is not None: hist[s] = p[s][:j + 1]
        for s in dop:
            h = hist[s]
            atr = sum(max(h[k].high - h[k].low, abs(h[k].high - h[k - 1].close), abs(h[k].low - h[k - 1].close))
                      for k in range(len(h) - 20, len(h))) / 20
            sc = sila[s] if rng is None else rng.random()
            syrye.append(Candidate(s, sc, atr, atr / h[-1].close * 100, h[-1].close))
        syrye.sort(key=lambda c: c.score, reverse=True)
        uzhe = [Candidate(s, 0.0, 1.0, 1.0, 1.0) for s in derzhim if s in hist]
        nov = list(_sobrat(syrye, hist, SECTOR_MAP, clusters, 4, uzhe))[:svob]
        zap["vybor"] = [c.symbol for c in nov]
        zap["prichina"] = "vhod" if nov else "ogranicheniya_portfelya"
        return tuple(nov)
    return podbor


def svodka(z, okno, bp):
    eq = z["daily_equity"]; tr = z["trades"]
    let = (okno[-1] - okno[0]).days / 365.25
    sr_kap = st.mean(float(r["equity"]) for r in eq)
    oborot = sum(t["qty"] * (t["entry_fill"] + t["exit_fill"]) for t in tr)
    pos = [len(r["positions"]) for r in eq]
    return {"godovyh_pct": round(_godovyh(float(z["return_pct"]), okno[0], okno[-1]), 2),
            "dohod_pct": round(z["return_pct"], 1), "maxDD_pct": round(z["daily_max_drawdown_pct"], 2),
            "pf": round(z["profit_factor_realized"], 3), "sdelok": z["realized_trades"],
            "dozapolneno": len(z["dozapolneno"]), "ekspoziciya_pct": round(z["average_gross_exposure_pct"], 1),
            "oborot_v_god_x": round(oborot / sr_kap / let, 2), "komissii_usd": round(oborot * bp / 1e4, 1),
            "sred_pozicij": round(st.mean(pos), 2), "dolya_dney_so_svobodnym_mestom": round(sum(x < 4 for x in pos) / len(pos), 3),
            "vyhody": {k: sum(t["reason"] == k for t in tr) for k in sorted({t["reason"] for t in tr})}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vyvod", required=True); ap.add_argument("--ruki", default="MONTHLY,WEEKLY_FILL,SPY")
    ap.add_argument("--zerna", default="0-19"); ap.add_argument("--bps", default="20,10,30")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    syrye, _ = chasovye(Path(a.dannye)); p = v_dnevnye(syrye)
    sessii = [b.session_date for b in p["SPY"]]
    okno = [s for s in sessii if NACH <= s <= KON]
    posl = {}
    for i, s in enumerate(sessii): posl[s.strftime("%Y-%m")] = i
    rasp = [(sessii[i], sessii[i + 1]) for i in sorted(posl.values()) if i + 1 < len(sessii) and okno[0] <= sessii[i + 1] <= okno[-1]]
    resh = _decisions("v38_successor_gated", p, rasp, clusters)
    vhody = {d.entry_session for d in resh}
    pol = LiveProtectionDailyProxy(initial_stop_anchor="entry_fill")
    out = json.loads(Path(a.vyvod).read_text()) if Path(a.vyvod).exists() else {"prereg": "PREREG_ALPACA_WEEKLY_FILL_2026_10_26", "ruki": {}}
    R = out["ruki"]
    def run(kw, bp):
        return dvizhok_x(p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                         policy=pol, mest=4, **kw)
    bpsy = [float(x) for x in a.bps.split(",")]
    for r in a.ruki.split(","):
        t0 = time.time()
        if r == "SPY":
            c = [b.close for b in p["SPY"] if NACH <= b.session_date <= KON]
            pk, dd = c[0], 0
            for x in c: pk = max(pk, x); dd = max(dd, 1 - x / pk)
            R["SPY_100"] = {"godovyh_pct": round(_godovyh((c[-1] / c[0] - 1) * 100, okno[0], okno[-1]), 2), "maxDD_pct": round(dd * 100, 2)}
            ek = R.get("WEEKLY_FILL", {}).get("20bps", {}).get("ekspoziciya_pct")
            if ek:
                w = ek / 100; eqv, pk, dd = 1.0, 1.0, 0
                for k in range(1, len(c)):
                    eqv *= 1 + w * (c[k] / c[k - 1] - 1); pk = max(pk, eqv); dd = max(dd, 1 - eqv / pk)
                R["SPY_na_ekspoziciyu_WF"] = {"dolya": w, "godovyh_pct": round(_godovyh((eqv - 1) * 100, okno[0], okno[-1]), 2), "maxDD_pct": round(dd * 100, 2)}
        elif r == "MONTHLY":
            R["MONTHLY"] = {f"{bp:.0f}bps": svodka(run({}, bp), okno, bp) for bp in bpsy}
        elif r == "WEEKLY_FILL":
            R["WEEKLY_FILL"] = {}
            for bp in bpsy:
                zh = []
                z = run(dict(dozapolnenie=sdelat_fill(p, clusters, sessii, vhody, None, zh)), bp)
                s = svodka(z, okno, bp); R["WEEKLY_FILL"][f"{bp:.0f}bps"] = s
                if bp == 20:
                    dz = {(d["session"], d["symbol"]) for d in z["dozapolneno"]}
                    tz = [t for t in z["trades"] if (t["entry_session"], t["symbol"]) in dz]
                    sek = {}
                    for t in tz: sek[SECTOR_MAP.get(t["symbol"], "unknown")] = sek.get(SECTOR_MAP.get(t["symbol"], "unknown"), 0) + 1
                    prich = {}
                    for w in zh: prich[w["prichina"]] = prich.get(w["prichina"], 0) + 1
                    dop = [w["dopustimo"] for w in zh if "dopustimo" in w]
                    R["WEEKLY_FILL_diag"] = {
                        "nedel": len(zh), "nedel_so_svobodnym": sum(w["svobodno"] > 0 for w in zh),
                        "sred_svobodnyh_mest": round(st.mean(w["svobodno"] for w in zh), 2), "prichiny": prich,
                        "dopustimyh_kandidatov": {"med": st.median(dop) if dop else 0, "min": min(dop, default=0), "max": max(dop, default=0)},
                        "sdelki_dozapolneniya": {"n": len(tz), "sred_pct": round(st.mean(t["return_pct"] for t in tz), 2) if tz else None,
                                                 "pnl_usd": round(sum(t["pnl"] for t in tz), 1),
                                                 "dolya_plyus": round(sum(t["pnl"] > 0 for t in tz) / len(tz), 3) if tz else None},
                        "sektory_dozapolneniy": dict(sorted(sek.items(), key=lambda x: -x[1])),
                        "po_godam_dozap_usd": {}}
                    for t in tz:
                        y = t["entry_session"][:4]; R["WEEKLY_FILL_diag"]["po_godam_dozap_usd"][y] = round(R["WEEKLY_FILL_diag"]["po_godam_dozap_usd"].get(y, 0) + t["pnl"], 1)
        elif r == "RANDOM":
            lo, hi = map(int, a.zerna.split("-"))
            R.setdefault("RANDOM_20bps", {})
            for sd in range(lo, hi + 1):
                if str(sd) in R["RANDOM_20bps"]: continue
                z = run(dict(dozapolnenie=sdelat_fill(p, clusters, sessii, vhody, random.Random(20261026 + sd))), 20.0)
                s = svodka(z, okno, 20.0); R["RANDOM_20bps"][str(sd)] = {k: s[k] for k in ("godovyh_pct", "maxDD_pct", "pf", "dozapolneno")}
                Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1))
                print("random", sd, s["godovyh_pct"], s["maxDD_pct"], flush=True)
        print(r, round(time.time() - t0, 1), "с", flush=True)
        Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in R.items() if k != "RANDOM_20bps"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
