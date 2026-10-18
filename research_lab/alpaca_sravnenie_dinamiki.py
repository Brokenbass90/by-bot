#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_SRAVNENIE_DINAMIKI_2026_10_18 (7198e1b). Запуск из копии канонического дерева Alpaca:
    cd <alpaca-tree> && python3 <this> --dannye data_cache/equities_daily_10y --vyvod out/sravnenie.json [--ruki ...] [--srezy ...]
Движок и отбор не меняются; руки EVENT и WEEKLY_DYN — только функции дозаполнения поверх dvizhok_x."""
import argparse, bisect, json, sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, ".")
from backtest.alpaca_bakeoff_v2_contract import spy200_gate
from backtest.alpaca_honest_portfolio import LiveProtectionDailyProxy, Candidate, select_v38_successor
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_governor_v1 import sdelat_podbor, shirota_rynka
from research_lab.alpaca_mehaniki_v1 import _sobrat
from research_lab.alpaca_ustoychivost_v1 import progon
from scripts.run_alpaca_honest_diagnostic import _decisions
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

KRIZISY = {"2018_Q4": ("2018-10-01", "2019-01-31"), "2020_covid": ("2020-02-15", "2020-05-31"),
           "2022_bear": ("2022-01-01", "2022-12-31"), "2025_fevral": ("2025-02-19", "2025-05-07")}
SPOKOYNYE = {"2019": ("2019-02-01", "2019-12-31"), "2021": ("2021-01-01", "2021-12-31"), "2023_2024": ("2023-01-01", "2024-12-31")}
POLNOE = {"polnoe": ("2016-01-04", "2026-09-04")}


def bystraya_istoriya(p):
    daty = {s: [r.session_date for r in rows] for s, rows in p.items()}
    def hist(session):
        out = {}
        for s, rows in p.items():
            k = bisect.bisect_right(daty[s], session)
            if k and rows[k - 1].session_date == session: out[s] = rows[:k]
        return out
    return hist


def podbor_svezhiy(p, clusters, tolko_pervaya_nedeli=False, sessii=None):
    """EVENT: свежий v38/SPY200 на закрытии session, ≤1. WEEKLY_DYN: только если следующая сессия — первая в ISO-неделе."""
    hist_f = bystraya_istoriya(p); sled = {sessii[i]: sessii[i + 1] for i in range(len(sessii) - 1)} if sessii else {}
    def podbor(session, derzhim, blok):
        if tolko_pervaya_nedeli:
            n = sled.get(session)
            if n is None or n.isocalendar()[:2] == session.isocalendar()[:2]: return ()
        hist = hist_f(session); sp = hist.get("SPY") or []
        if not sp or not spy200_gate([r.close for r in sp]): return ()
        syrye = [c for c in select_v38_successor(hist, sectors=SECTOR_MAP, clusters=clusters, top_n=8)
                 if c.symbol not in derzhim and session >= blok.get(c.symbol, date.min) and c.symbol in hist]
        uzhe = [Candidate(s, 0.0, 1.0, 1.0, 1.0) for s in derzhim if s in hist]
        return tuple(_sobrat(syrye, hist, SECTOR_MAP, clusters, 4, uzhe))[:1]
    return podbor


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vyvod", required=True); ap.add_argument("--ruki", default="MONTHLY,EVENT,WEEKLY_DYN,A+G2+gov")
    ap.add_argument("--srezy", default="all"); ap.add_argument("--bps", default="10,20,30")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    syrye, _ = chasovye(Path(a.dannye)); p = v_dnevnye(syrye)
    sessii = [b.session_date for b in p["SPY"]]; shirota = shirota_rynka(p)
    pol = LiveProtectionDailyProxy(initial_stop_anchor="entry_fill")
    RUKI = {"MONTHLY": ("mes", {}), "EVENT": ("mes", dict(dozapolnenie=podbor_svezhiy(p, clusters))),
            "WEEKLY_DYN": ("net", dict(dozapolnenie=podbor_svezhiy(p, clusters, True, sessii))),
            "A+G2+gov": ("mes", dict(dozapolnenie=sdelat_podbor(p, clusters, shirota)))}
    ruki = a.ruki.split(","); bpsy = [float(x) for x in a.bps.split(",")]
    vse = {**POLNOE, **KRIZISY, **SPOKOYNYE}
    srezy = vse if a.srezy == "all" else {k: vse[k] for k in a.srezy.split(",")}
    posl = {}
    for i, s in enumerate(sessii): posl[s.strftime("%Y-%m")] = i
    out = json.loads(Path(a.vyvod).read_text()) if Path(a.vyvod).exists() else {"prereg": "PREREG_ALPACA_SRAVNENIE_DINAMIKI_2026_10_18", "srezy": {}}
    for metka, (n, k) in srezy.items():
        nach, kon = date.fromisoformat(n), date.fromisoformat(k); okno = [s for s in sessii if nach <= s <= kon]
        rasp = [(sessii[i], sessii[i + 1]) for i in sorted(posl.values()) if i + 1 < len(sessii) and okno[0] <= sessii[i + 1] <= okno[-1]]
        resh = _decisions("v38_successor_gated", p, rasp, clusters)
        for bp in bpsy:
            for r in ruki:
                kl = f"{bp:.0f}bps"
                if r in out["srezy"].get(metka, {}).get(kl, {}): continue
                t0 = time.time(); vid, kw = RUKI[r]
                z = progon(p, okno, resh if vid == "mes" else [], bp, kw, pol)
                z["sekund"] = round(time.time() - t0, 1)
                out["srezy"].setdefault(metka, {}).setdefault(kl, {})[r] = z
                Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
                print(metka, kl, r, round(z["godovyh_pct"], 2), round(z["maxDD_pct"], 2), z["sdelok"], z["sekund"], flush=True)


if __name__ == "__main__":
    main()
