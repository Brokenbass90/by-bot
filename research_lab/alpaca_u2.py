#!/usr/bin/env python3
"""Прогон PREREG_ALPACA_U2_NEZAVISIMAYA_VSELENNAYA_2026_10_18 (a212281).
Запуск из копии дерева Alpaca:  python3 research_lab/alpaca_u2.py --u2 <alpaca_pit_daily_deep_20260925> --sprav <akcii_grouped>
   --vyvod out/u2.json [--ruki ...] [--vselennaya U2|U58] [--sidy 400]
Движок `dvizhok_x`, отбор `select_v38_successor`, защита — без изменений. Новое — только загрузчик U2, причинный фильтр
допустимости, руки-обёртки (M_H2, E_H1, W_MR) и случайные контроли."""
from __future__ import annotations

import argparse, bisect, json, math, random, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from backtest.alpaca_bakeoff_v2_contract import spy200_gate
from backtest.alpaca_exact_parity_contract import DailyBar
from backtest.alpaca_honest_portfolio import (Candidate, LiveProtectionDailyProxy, MonthlyDecision,
                                              _v38_candidate, _atr20, select_v38_successor)
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
from research_lab.alpaca_mehaniki_v1 import _sobrat
from research_lab.alpaca_ustoychivost_v1 import _godovyh
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

HVOST = 300            # все функции отбора смотрят назад ≤ 201 бар; хвост 300 даёт тот же результат (проверено тестом)
MIN_CENA, MIN_DV, MIN_BAROV, DV_OKNO = 10.0, 25e6, 260, 60
import os
OKNO = (os.environ.get("OKNO_START", "2016-06-01"), "2026-09-04")
PODPERIODY = {"P1": ("2016-06-01", "2019-12-31"), "P2": ("2020-01-01", "2022-12-31"), "P3": ("2023-01-01", "2026-09-04")}
POL = LiveProtectionDailyProxy(initial_stop_anchor="entry_fill")


# ------------------------------------------------------------------ данные
class Vselennaya:
    def __init__(self, p: dict, sessii: list[date], realnye: dict[str, set], obem: dict[str, dict], sektora: dict,
                 filtr: bool):
        self.p, self.sessii, self.sektora, self.filtr = p, sessii, sektora, filtr
        self.i_sessii = {s: i for i, s in enumerate(sessii)}
        self.daty = {s: [r.session_date for r in rows] for s, rows in p.items()}
        simv = [s for s in p if s not in ("SPY", "QQQ")]
        self.simv = simv
        if filtr:
            idx = pd.Index(sessii)
            C = pd.DataFrame({s: pd.Series({r.session_date: r.close for r in p[s] if r.session_date in realnye[s]})
                              for s in simv}).reindex(idx)
            V = pd.DataFrame({s: pd.Series(obem[s]) for s in simv}).reindex(idx)
            dv = (C * V).rolling(DV_OKNO, min_periods=40).median()
            cnt = C.notna().cumsum()
            ok = C.notna() & (C >= MIN_CENA) & (dv >= MIN_DV) & (cnt >= MIN_BAROV)
            self.dopusk = {sessii[i]: set(np.array(simv)[ok.values[i]]) for i in range(len(sessii))}
        else:
            self.dopusk = None

    def dopustimye(self, session: date) -> set:
        if self.dopusk is None:
            # U58: как денежный Monthly — бар на дату сигнала обязателен, других фильтров нет
            return {s for s in self.simv if self._k(s, session) and self.p[s][self._k(s, session) - 1].session_date == session}
        return self.dopusk.get(session, set())

    def _k(self, s, session):
        return bisect.bisect_right(self.daty[s], session)

    def istoriya(self, session: date, simvoly) -> dict:
        out = {}
        for s in list(simvoly) + ["SPY"]:
            k = self._k(s, session)
            if k and self.p[s][k - 1].session_date == session:
                out[s] = self.p[s][max(0, k - HVOST):k]
        return out


def zagruzit_u2(katalog: Path, sprav: Path, spy_p: dict) -> Vselennaya:
    sessii = [r.session_date for r in spy_p["SPY"]]
    mi = json.loads((katalog / "membership_intervals.json").read_text())
    karantin = {q["symbol"] if isinstance(q, dict) else q for q in mi.get("quarantined", [])}
    uni = json.loads((katalog / "universe.json").read_text())
    tip = {r["ticker"]: r.get("type") for r in uni.get("reference", [])}
    cs = set()
    for f in ("spravochnik_active.json", "spravochnik_inactive.json"):
        cs |= {r["ticker"] for r in json.loads((sprav / f).read_text()) if r.get("type") == "CS"}
    isklyucheno = {"vselennaya58": 0, "karantin": 0, "ne_CS": 0, "pusto": 0}
    p, realnye, obem = {"SPY": spy_p["SPY"]}, {}, {}
    for f in sorted((katalog / "bars").glob("*.json")):
        s = f.stem
        if "." in s and s.split(".")[-1].isdigit():
            continue
        if s in SECTOR_MAP or s in ("SPY", "QQQ", "TSM"):
            isklyucheno["vselennaya58"] += 1; continue
        if s in karantin:
            isklyucheno["karantin"] += 1; continue
        t = tip.get(s)
        if not (t == "CS" or (t is None and s in cs)):
            isklyucheno["ne_CS"] += 1; continue
        rec = json.loads(f.read_text()).get("records") or []
        bary = {}
        for r in rec:
            d = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).date()
            if all(math.isfinite(float(r[k])) and float(r[k]) > 0 for k in "ohlc"):
                bary[d] = r
        bary = {d: r for d, r in bary.items() if d in set(sessii)} if False else {d: r for d, r in bary.items()}
        if not bary:
            isklyucheno["pusto"] += 1; continue
        d0 = min(bary)
        ryad, prev = [], None
        for d in sessii:
            if d < d0:
                continue
            r = bary.get(d)
            if r is not None:
                prev = float(r["c"])
                ryad.append(DailyBar(session_date=d, open=float(r["o"]), high=float(r["h"]), low=float(r["l"]), close=prev))
            elif prev is not None:     # пауза торгов / после последнего бара — плоский бар по последнему закрытию
                ryad.append(DailyBar(session_date=d, open=prev, high=prev, low=prev, close=prev))
        if len(ryad) < 2:
            isklyucheno["pusto"] += 1; continue
        p[s] = ryad
        realnye[s] = {d for d in bary if d >= d0}
        obem[s] = {d: float(r["v"]) for d, r in bary.items()}
    sektora = {s: s for s in p}          # секторов в архиве нет: у каждой бумаги свой
    U = Vselennaya(p, sessii, realnye, obem, sektora, filtr=True)
    U.isklyucheno = isklyucheno
    return U


def zagruzit_u58(dannye: Path, bez_sektorov: bool) -> Vselennaya:
    syrye, _ = chasovye(dannye); p = v_dnevnye(syrye)
    sessii = [r.session_date for r in p["SPY"]]
    sektora = {s: s for s in p} if bez_sektorov else SECTOR_MAP
    U = Vselennaya(p, sessii, {}, {}, sektora, filtr=False)
    U.isklyucheno = {}
    return U


# ------------------------------------------------------------------ решения
def raspisanie(sessii, okno):
    posl = {}
    for i, s in enumerate(sessii):
        posl[s.strftime("%Y-%m")] = i
    return [(sessii[i], sessii[i + 1]) for i in sorted(posl.values())
            if i + 1 < len(sessii) and okno[0] <= sessii[i + 1] <= okno[-1]]


def mesyachnye(U: Vselennaya, rasp, clusters):
    out = []
    for sig, vh in rasp:
        hist = U.istoriya(sig, U.dopustimye(sig))
        sp = hist.get("SPY") or []
        if not sp or not spy200_gate([r.close for r in U.p["SPY"][:U._k("SPY", sig)]]):
            out.append(MonthlyDecision(sig, vh, (), "spy200_gate_cash")); continue
        bez_spy = {k: v for k, v in hist.items() if k != "SPY"}
        bez_spy["SPY"] = sp
        picks = select_v38_successor(bez_spy, sectors=U.sektora, clusters=clusters)
        out.append(MonthlyDecision(sig, vh, picks, "ok" if picks else "no_qualifying_names"))
    return out


def spy_nizhe_sma50(U, sig):
    c = [r.close for r in U.p["SPY"][:U._k("SPY", sig)]]
    return len(c) >= 50 and c[-1] < sum(c[-50:]) / 50.0


def mesyachnye_h2(U, rasp, clusters, okno, bp):
    """M_H2: при SPY<SMA50 на закрытии сигнала новые позиции не открываются, прежние держатся (состояние — из движка)."""
    baza = mesyachnye(U, rasp, clusters)
    out = []
    for d in baza:
        if d.reason != "spy200_gate_cash" and spy_nizhe_sma50(U, d.signal_session):
            do = [s for s in okno if s <= d.signal_session]
            z = dvizhok_x(U.p, do, out, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                          policy=POL, mest=4) if do and out else None
            derzhim = set(z["daily_equity"][-1]["positions"]) if z and z["daily_equity"] else set()
            stary = [c for c in d.picks if c.symbol in derzhim]
            # держим прежние: взять их Candidate из предыдущего решения, где они были выбраны
            pred = {c.symbol: c for dd in out for c in dd.picks}
            stary_vse = [pred[s] for s in sorted(derzhim) if s in pred and s not in {c.symbol for c in stary}]
            out.append(MonthlyDecision(d.signal_session, d.entry_session, tuple(stary) + tuple(stary_vse), "h2_spy_lt_sma50"))
        else:
            out.append(d)
    return out


def sluchaynye(U, baza, clusters, sid, setap: bool):
    rnd = random.Random(sid); out = []
    for d in baza:
        k = len(d.picks)
        if k == 0:
            out.append(MonthlyDecision(d.signal_session, d.entry_session, (), d.reason)); continue
        sig = d.signal_session
        pul = sorted(U.dopustimye(sig))
        hist = U.istoriya(sig, pul)
        kand = []
        for s in pul:
            if s not in hist:
                continue
            if setap:
                c = _v38_candidate(s, hist[s])
                if c is None:
                    continue
            else:
                a = _atr20(hist[s])
                if not (a > 0 and math.isfinite(a)):
                    continue
                cl = hist[s][-1].close
                c = Candidate(s, 0.0, a, a / cl * 100.0, cl)
            kand.append(c)
        vyb = rnd.sample(kand, min(k, len(kand)))
        w = 1.0 / max(1, len(vyb))
        out.append(MonthlyDecision(sig, d.entry_session,
                                   tuple(Candidate(c.symbol, c.score, c.atr_at_signal, c.atr_pct_at_signal,
                                                   c.signal_close, w) for c in vyb), "random"))
    return out


# ------------------------------------------------------------------ дозаполнение
def dozapolnitel(U, clusters, rezhim: str, sessii):
    """rezhim: EVENT | E_H1 | WEEKLY."""
    sled = {sessii[i]: sessii[i + 1] for i in range(len(sessii) - 1)}
    def podbor(session, derzhim, blok):
        if rezhim == "WEEKLY":
            n = sled.get(session)
            if n is None or n.isocalendar()[:2] == session.isocalendar()[:2]:
                return ()
        if rezhim == "E_H1" and blok:
            posl_stop = max(blok.values()) - timedelta(days=POL.reentry_block_calendar_days)
            i0, i1 = U.i_sessii.get(posl_stop), U.i_sessii.get(session)
            if i0 is not None and i1 is not None and i1 - i0 <= 5:
                return ()
        if not spy200_gate([r.close for r in U.p["SPY"][:U._k("SPY", session)]]):
            return ()
        hist = U.istoriya(session, U.dopustimye(session) | set(derzhim))
        syrye = [c for c in select_v38_successor(hist, sectors=U.sektora, clusters=clusters, top_n=8)
                 if c.symbol not in derzhim and session >= blok.get(c.symbol, date.min) and c.symbol in hist]
        uzhe = [Candidate(s, 0.0, 1.0, 1.0, 1.0) for s in derzhim if s in hist]
        return tuple(_sobrat(syrye, hist, U.sektora, clusters, 4, uzhe))[:1]
    return podbor


def progon(U, okno, resh, bp, doz=None):
    t0 = time.time()
    z = dvizhok_x(U.p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                  policy=POL, mest=4, **({"dozapolnenie": doz} if doz else {}))
    eq = {r["session"]: r["equity"] for r in z["daily_equity"]}
    return {"godovyh_pct": _godovyh(float(z["return_pct"]), okno[0], okno[-1]), "dohod_pct": z["return_pct"],
            "maxDD_pct": z["daily_max_drawdown_pct"], "sdelok": z["realized_trades"], "krasnyh": z["red_months"],
            "mesyacev": z["months"], "ekspoziciya_pct": z["average_gross_exposure_pct"],
            "dozapolneno": len(z["dozapolneno"]), "sekund": round(time.time() - t0, 1),
            "podperiody": podperiody(eq), "_trades": z["trades"]}


def podperiody(eq: dict):
    out = {}
    ds = sorted(eq)
    for k, (a, b) in PODPERIODY.items():
        ss = [d for d in ds if a <= d <= b]
        if len(ss) < 30:
            continue
        v = [eq[d] for d in ss]
        pik, dd = v[0], 0.0
        for x in v:
            pik = max(pik, x); dd = min(dd, x / pik - 1)
        let = (date.fromisoformat(ss[-1]) - date.fromisoformat(ss[0])).days / 365.25
        out[k] = {"godovyh_pct": ((v[-1] / v[0]) ** (1 / let) - 1) * 100, "maxDD_pct": -dd * 100}
    return out


def spy_bh(U, okno):
    c = {r.session_date: r.close for r in U.p["SPY"]}
    a, b = c[okno[0]], c[okno[-1]]
    let = (okno[-1] - okno[0]).days / 365.25
    return ((b / a) ** (1 / let) - 1) * 100


# ------------------------------------------------------------------ V5 по бумагам
def v5(U, baza, sid=20261018):
    rnd = random.Random(sid); rows = []
    for d in baza:
        if not d.picks:
            continue
        sig = d.signal_session; i = U.i_sessii[sig]
        if i + 21 >= len(U.sessii):
            continue
        s21 = U.sessii[i + 21]
        pul = sorted(U.dopustimye(sig)); hist = U.istoriya(sig, pul)
        def vol(s):
            r = [hist[s][j].close / hist[s][j - 1].close - 1 for j in range(len(hist[s]) - 20, len(hist[s]))]
            return float(np.std(r))
        def fwd(s):
            k0 = U._k(s, sig); k1 = U._k(s, s21)
            return U.p[s][k1 - 1].close / U.p[s][k0 - 1].close - 1
        vv = {s: vol(s) for s in pul if s in hist and len(hist[s]) > 21}
        if len(vv) < 50:
            continue
        kr = np.quantile(list(vv.values()), np.linspace(0, 1, 11))
        decil = lambda x: int(np.clip(np.searchsorted(kr, x, side="right") - 1, 0, 9))
        po_dec = {}
        for s, x in vv.items():
            po_dec.setdefault(decil(x), []).append(s)
        spy_ok = spy200_gate([r.close for r in U.p["SPY"][:U._k("SPY", sig)]])
        for c in d.picks:
            if c.symbol not in vv:
                continue
            gr = [s for s in po_dec[decil(vv[c.symbol])] if s != c.symbol]
            kontr = rnd.sample(gr, min(5, len(gr)))
            if not kontr:
                continue
            rows.append({"sig": sig.isoformat(), "s": c.symbol, "r": fwd(c.symbol),
                         "k": float(np.mean([fwd(s) for s in kontr])), "spy200": spy_ok})
    x = np.array([r["r"] - r["k"] for r in rows]) if rows else np.array([0.0])
    t = float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")
    return {"n": len(rows), "srednee_prevyshenie_pct": float(x.mean() * 100), "t": t,
            "dolya_luchshe": float((x > 0).mean()), "_rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U2"); ap.add_argument("--vyvod", required=True)
    ap.add_argument("--ruki", default="MONTHLY,M_H2,EVENT,E_H1,WEEKLY_DYN,W_MR"); ap.add_argument("--bps", default="20,10,30")
    ap.add_argument("--sidy", type=int, default=0); ap.add_argument("--kontroli", default="R1,R2"); ap.add_argument("--v5", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    syrye, _ = chasovye(Path(a.dannye)); spy_p = v_dnevnye(syrye)
    if a.vselennaya == "U2":
        U = zagruzit_u2(Path(a.u2), Path(a.sprav), spy_p)
    else:
        U = zagruzit_u58(Path(a.dannye), bez_sektorov=(a.vselennaya == "U58_NOSEC"))
    okno = [s for s in U.sessii if date.fromisoformat(OKNO[0]) <= s <= date.fromisoformat(OKNO[1])]
    rasp = raspisanie(U.sessii, okno)
    vyvod = Path(a.vyvod)
    out = json.loads(vyvod.read_text()) if vyvod.exists() else {"prereg": "PREREG_ALPACA_U2_NEZAVISIMAYA_VSELENNAYA_2026_10_18",
                                                                 "vselennaya": a.vselennaya, "ruki": {}, "kontroli": {}}
    out["simvolov"] = len(U.p) - 1; out["isklyucheno"] = U.isklyucheno
    out["dopustimyh_srednee"] = float(np.mean([len(U.dopustimye(s)) for s, _ in rasp]))
    out["spy_bh_godovyh_pct"] = spy_bh(U, okno)
    def sohr():
        vyvod.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    baza = mesyachnye(U, rasp, clusters)
    out["mesyachnye_resheniya"] = [{"sig": d.signal_session.isoformat(), "picks": [c.symbol for c in d.picks],
                                    "reason": d.reason} for d in baza]
    sohr()
    for bp in [float(x) for x in a.bps.split(",")]:
        kl = f"{bp:.0f}bps"
        for r in a.ruki.split(","):
            if r in out["ruki"].get(kl, {}):
                continue
            if r == "MONTHLY":   z = progon(U, okno, baza, bp)
            elif r == "M_H2":    z = progon(U, okno, mesyachnye_h2(U, rasp, clusters, okno, bp), bp)
            elif r == "EVENT":   z = progon(U, okno, baza, bp, dozapolnitel(U, clusters, "EVENT", U.sessii))
            elif r == "E_H1":    z = progon(U, okno, baza, bp, dozapolnitel(U, clusters, "E_H1", U.sessii))
            elif r == "WEEKLY_DYN": z = progon(U, okno, [], bp, dozapolnitel(U, clusters, "WEEKLY", U.sessii))
            elif r == "W_MR":    z = progon(U, okno, baza, bp, dozapolnitel(U, clusters, "WEEKLY", U.sessii))
            else: raise SystemExit(r)
            tr = z.pop("_trades")
            z["sdelki_po_prichine"] = {}
            for t in tr:
                q = z["sdelki_po_prichine"].setdefault(t["reason"], {"n": 0, "pnl": 0.0})
                q["n"] += 1; q["pnl"] += t["pnl"]
            out["ruki"].setdefault(kl, {})[r] = z; sohr()
            print(kl, r, round(z["godovyh_pct"], 2), round(z["maxDD_pct"], 2), z["sdelok"], z["sekund"], flush=True)
    if a.sidy:
        for nazv, setap in [x for x in (("R1", False), ("R2", True)) if x[0] in a.kontroli.split(",")]:
            uzhe = out["kontroli"].get(nazv, {}).get("godovyh", [])
            for sid in range(len(uzhe), a.sidy):
                z = progon(U, okno, sluchaynye(U, baza, clusters, sid, setap), float(a.bps.split(",")[0])); z.pop("_trades")
                k = out["kontroli"].setdefault(nazv, {"godovyh": [], "maxDD": []})
                k["godovyh"].append(z["godovyh_pct"]); k["maxDD"].append(z["maxDD_pct"])
                if sid % 20 == 19:
                    sohr(); print(nazv, sid + 1, round(float(np.median(k["godovyh"])), 2), flush=True)
            sohr()
    if a.v5:
        z = v5(U, baza); rows = z.pop("_rows")
        z["po_spy200"] = {str(f): float(np.mean([r["r"] - r["k"] for r in rows if r["spy200"] == f]) * 100)
                          for f in (True, False) if any(r["spy200"] == f for r in rows)}
        out["V5"] = z; sohr(); print("V5", z, flush=True)


if __name__ == "__main__":
    main()
