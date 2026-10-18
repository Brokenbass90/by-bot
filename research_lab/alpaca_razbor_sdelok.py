#!/usr/bin/env python3
"""Диагностика (не правило, параметры не меняются): где Weekly Dynamic и EventReselection теряют против Monthly.
Те же руки, данные и движок, что PREREG_ALPACA_SRAVNENIE_DINAMIKI_2026_10_18; полное окно, 20 bps.
Запуск из копии дерева Alpaca: python3 <this> --vyvod out/razbor.json"""
import argparse, bisect, json, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from backtest.alpaca_honest_portfolio import LiveProtectionDailyProxy
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
from research_lab.alpaca_governor_v1 import shirota_rynka
from scripts.run_alpaca_honest_diagnostic import _decisions
import alpaca_sravnenie_dinamiki as S


def sma(x, n): return float(np.mean(x[-n:])) if len(x) >= n else float("nan")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--vyvod", required=True); a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    syrye, _ = chasovye(Path("data_cache/equities_daily_10y")); p = v_dnevnye(syrye)
    sessii = [b.session_date for b in p["SPY"]]; shirota = shirota_rynka(p)
    okno = [s for s in sessii if date(2016, 1, 4) <= s <= date(2026, 9, 4)]
    posl = {}
    for i, s in enumerate(sessii): posl[s.strftime("%Y-%m")] = i
    rasp = [(sessii[i], sessii[i + 1]) for i in sorted(posl.values()) if i + 1 < len(sessii) and okno[0] <= sessii[i + 1] <= okno[-1]]
    resh = _decisions("v38_successor_gated", p, rasp, clusters)
    pol = LiveProtectionDailyProxy(initial_stop_anchor="entry_fill")
    spy = p["SPY"]; spy_d = [r.session_date for r in spy]; spy_c = [r.close for r in spy]
    bars = {s: {r.session_date: r for r in rows} for s, rows in p.items()}
    daty = {s: [r.session_date for r in rows] for s, rows in p.items()}
    sh_vals = sorted(shirota.values()); t1, t2 = np.percentile(sh_vals, [33, 67])
    RUKI = {"MONTHLY": (resh, {}), "EVENT": (resh, dict(dozapolnenie=S.podbor_svezhiy(p, clusters))),
            "WEEKLY_DYN": ([], dict(dozapolnenie=S.podbor_svezhiy(p, clusters, True, sessii)))}
    out = {}
    for ruka, (r_, kw) in RUKI.items():
        z = dvizhok_x(p, okno, r_, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=20.0, policy=pol, mest=4, **kw)
        refill = {(d["symbol"], d["session"]) for d in z["dozapolneno"]}
        stop_dni = sorted(date.fromisoformat(t["exit_session"]) for t in z["trades"] if t["reason"].startswith("protective_stop"))
        grp = defaultdict(list)
        for t in z["trades"]:
            e = date.fromisoformat(t["entry_session"]); x = date.fromisoformat(t["exit_session"]); s = t["symbol"]
            k = bisect.bisect_left(spy_d, e)                           # режим на закрытии ПЕРЕД входом
            c = spy_c[:k]; s50, s200 = sma(c, 50), sma(c, 200)
            rez = ("SPY>SMA50" if c[-1] > s50 else "SPY<SMA50") + ("/50>200" if s50 > s200 else "/50<200")
            pred = spy_d[k - 1] if k else e; shv = shirota.get(pred, float("nan"))
            shir = "shirota_niz" if shv <= t1 else ("shirota_verh" if shv >= t2 else "shirota_sred")
            ist = "refill" if (s, t["entry_session"]) in refill else "reshenie"
            j = bisect.bisect_left(stop_dni, e)
            posle_stopa = (e - stop_dni[j - 1]).days if j else 999
            if t["reason"].startswith("protective_stop") or t["reason"].startswith("entry_gap"):
                vyh = "stop_v_plyus" if t["return_pct"] > 0 else "stop_v_minus"
            else:
                vyh = "rotaciya"
            hi = max((bars[s][d].high for d in daty[s][bisect.bisect_left(daty[s], e):bisect.bisect_right(daty[s], x)]), default=t["entry_fill"])
            pik = (hi / t["entry_fill"] - 1) * 100
            uderzh = t["return_pct"] / pik if pik > 1 else None
            row = dict(pnl=t["pnl"], r=t["return_pct"], dni=(x - e).days, pik=pik, uderzh=uderzh)
            for kl in (f"istochnik:{ist}", f"vyhod:{vyh}", f"rezhim:{rez}", f"shirota:{shir}", "vse") + \
                      ((f"refill_posle_stopa:{'<=5d' if posle_stopa <= 5 else '>5d'}",) if ist == "refill" else ()):
                grp[kl].append(row)
        def sv(rows):
            r = np.array([x["r"] for x in rows]); u = [x["uderzh"] for x in rows if x["uderzh"] is not None]
            return dict(n=len(rows), pnl_usd=round(sum(x["pnl"] for x in rows), 1), sredn_pct=round(float(r.mean()), 2),
                        dolya_plyus=round(float((r > 0).mean()), 3), sredn_dney=round(float(np.mean([x["dni"] for x in rows])), 1),
                        uderzh_ot_pika_med=round(float(np.median(u)), 3) if u else None,
                        sredn_pik_pct=round(float(np.mean([x["pik"] for x in rows])), 2))
        out[ruka] = {k: sv(v) for k, v in sorted(grp.items())}
        out[ruka]["itog"] = dict(return_pct=round(z["return_pct"], 1), dd=round(z["daily_max_drawdown_pct"], 2), ekspoz=round(z["average_gross_exposure_pct"], 1))
    Path(a.vyvod).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for ruka, d in out.items():
        print("==", ruka, d["itog"])
        for k, v in d.items():
            if k != "itog": print(f"  {k:<34} n {v['n']:>4}  pnl {v['pnl_usd']:>8}  ср {v['sredn_pct']:>6}%  плюс {v['dolya_plyus']}  дней {v['sredn_dney']}  удерж {v['uderzh_ot_pika_med']}  пик {v['sredn_pik_pct']}")


if __name__ == "__main__":
    main()
