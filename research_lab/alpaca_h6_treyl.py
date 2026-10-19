#!/usr/bin/env python3
"""PREREG_ALPACA_H6_TREYL_UTECHKA_I_FORWARD_2026_10_19 (9112083), часть A: тест идентичности + разложение утечки.
python3 research_lab/alpaca_h6_treyl.py --vselennaya U58|U2 [--u2 ... --sprav ...] --vyvod out/h6_U58.json
Симулятор одной позиции `vesti_poziciyu` общий с forward-тенью (часть B)."""
from __future__ import annotations

import argparse, json, statistics as st, sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")
from backtest.alpaca_exact_parity_contract import adverse_fill_price
from backtest.alpaca_honest_portfolio import quantize_sell_stop


@dataclass(frozen=True)
class Ruka:
    activate_gain_pct: float = 3.5
    trail_pct: float = 3.5
    minimum_lock_gain_pct: float = 0.5
    market_gap_bps: float = 10.0


RUKI_B = {"A35": Ruka(3.5), "A25": Ruka(2.5), "A20": Ruka(2.0), "A15": Ruka(1.5),
          "K20_25": Ruka(2.0, 2.5), "BEZ_TREYLA": Ruka(1e12)}


def vesti_poziciyu(bars, i_vhod, entry_fill, stop0, ruka: Ruka, bp, i_prinud=None, i_konec=None):
    """Повтор правил dvizhok_x для одной позиции. bars — список DailyBar (o/h/l/c).
    i_prinud — индекс сессии принудительного выхода по open (ротация/горизонт) до проверок стопа.
    Возвращает dict: i_vyhod (None = позиция открыта к i_konec), ref, fill, reason, put."""
    stop, hwm, armed = stop0, entry_fill, False
    i_konec = len(bars) - 1 if i_konec is None else i_konec
    max_high, max_close = entry_fill, entry_fill
    i_arm = None
    for j in range(i_vhod, i_konec + 1):
        b = bars[j]
        if i_prinud is not None and j == i_prinud:
            return _vyhod(j, b.open, "prinuditelno_open", entry_fill, bp, stop, hwm, max_high, max_close, i_arm)
        if b.open <= stop:
            return _vyhod(j, b.open, "entry_gap" if j == i_vhod else "gap_open", entry_fill, bp, stop, hwm,
                          max_high, max_close, i_arm)
        if b.low <= stop:
            return _vyhod(j, stop, "stop_intraday", entry_fill, bp, stop, hwm, max_high, max_close, i_arm)
        max_high, max_close = max(max_high, b.high), max(max_close, b.close)
        hwm = max(hwm, b.close)
        if (hwm / entry_fill - 1.0) * 100.0 + 1e-12 >= ruka.activate_gain_pct:
            if i_arm is None:
                i_arm = j
            trail = hwm * (1.0 - ruka.trail_pct / 100.0)
            lock = entry_fill * (1.0 + ruka.minimum_lock_gain_pct / 100.0)
            ceil = b.close * (1.0 - ruka.market_gap_bps / 10_000.0)
            t = min(max(stop, trail, lock), ceil)
            if t > stop:
                stop = quantize_sell_stop(t)
    return {"i_vyhod": None, "stop": stop, "hwm": hwm, "max_high": max_high, "max_close": max_close, "i_arm": i_arm}


def _vyhod(j, ref, reason, entry_fill, bp, stop, hwm, mh, mc, i_arm):
    fill = adverse_fill_price(ref, side="sell", cost_bps=bp)
    return {"i_vyhod": j, "ref": ref, "fill": fill, "reason": reason, "stop": stop, "hwm": hwm,
            "max_high": mh, "max_close": mc, "i_arm": i_arm, "dohod_pct": (fill / entry_fill - 1) * 100}


def _q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))] if xs else None


def chast_a(U, okno, resh, bp):
    from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
    from research_lab.alpaca_h4 import POL_M
    z = dvizhok_x(U.p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=bp,
                  policy=POL_M, mest=4)
    kand = {}
    for d in resh:
        for c in d.picks:
            kand[(c.symbol, d.entry_session.isoformat())] = c
    idx = {s: {b.session_date: i for i, b in enumerate(rows)} for s, rows in U.p.items()}
    ruka_m = Ruka(POL_M.activate_gain_pct, POL_M.trail_pct, POL_M.minimum_lock_gain_pct, POL_M.market_gap_bps)
    rasx, stroki = [], []
    for t in z["trades"]:
        s = t["symbol"]; rows = U.p[s]
        c = kand[(s, t["entry_session"])]
        iv = idx[s][date.fromisoformat(t["entry_session"])]; ix = idx[s][date.fromisoformat(t["exit_session"])]
        ef = t["entry_fill"]
        sig = ef - 2.0 * c.atr_at_signal
        stop0 = quantize_sell_stop(sig if sig > 0 else ef * (1 - POL_M.fallback_stop_pct))
        rot = t["reason"].startswith("monthly_rotation")
        r = vesti_poziciyu(rows, iv, ef, stop0, ruka_m, bp, i_prinud=ix if rot else None, i_konec=ix)
        ok = r["i_vyhod"] == ix and abs(r["fill"] - t["exit_fill"]) <= 1e-9 * max(1.0, t["exit_fill"])
        if not ok:
            rasx.append({"t": t, "sim": {k: v for k, v in r.items()}})
            continue
        pk_h = (r["max_high"] / ef - 1) * 100; pk_c = (r["max_close"] / ef - 1) * 100
        st_ex = (r["stop"] / ef - 1) * 100
        posle = {}
        for h in (21, 42):
            if ix + h < len(rows):
                posle[h] = (rows[ix + h].close / r["fill"] - 1) * 100
        stroki.append({"sym": s, "vhod": t["entry_session"], "dni": ix - iv, "reason": t["reason"],
                       "vzveden": r["i_arm"] is not None, "pik_high": pk_h, "pik_close": pk_c, "itog": t["return_pct"],
                       "stop_pct": st_ex, "posle": posle})
    return z, rasx, stroki


def razlozhit(stroki):
    def sv(xs):
        xs = [x for x in xs if x is not None]
        return {"n": len(xs), "sred": st.mean(xs) if xs else None, "med": st.median(xs) if xs else None,
                "p10": _q(xs, .1), "p90": _q(xs, .9)}
    out = {"vsego": len(stroki)}
    for kl, f in (("vzveden", lambda r: r["vzveden"]), ("ne_vzveden", lambda r: not r["vzveden"])):
        g = [r for r in stroki if f(r)]
        stop_ex = [r for r in g if not r["reason"].startswith("monthly_rotation")]
        out[kl] = {"n": len(g), "dolya": len(g) / max(1, len(stroki)),
                   "pik_high": sv([r["pik_high"] for r in g]), "itog": sv([r["itog"] for r in g]),
                   "otdacha_pp": sv([r["pik_high"] - r["itog"] for r in g]),
                   "uderzhanie_med": st.median([r["itog"] / r["pik_high"] for r in g if r["pik_high"] > 0.5] or [0]),
                   "prichiny": {k: sum(r["reason"] == k for r in g) for k in sorted({r["reason"] for r in g})},
                   "stop_vyhodov": len(stop_ex),
                   "posle_stopa_21": sv([r["posle"].get(21) for r in stop_ex]),
                   "posle_stopa_42": sv([r["posle"].get(42) for r in stop_ex])}
        if kl == "vzveden":
            # отдача взведённых = (high−close пика) + (close пика − стоп) + (стоп − итог: разрыв+издержки)
            out[kl]["sostav_pp"] = {
                "high_minus_close_pika": sv([r["pik_high"] - r["pik_close"] for r in stop_ex]),
                "close_pika_minus_stop": sv([r["pik_close"] - r["stop_pct"] for r in stop_ex]),
                "stop_minus_itog": sv([r["stop_pct"] - r["itog"] for r in stop_ex])}
        else:
            out[kl]["pik_porogi"] = {f"ge_{p}": sum(r["pik_high"] >= p for r in g) / max(1, len(g))
                                     for p in (1.5, 2.0, 2.5, 3.5)}
            out[kl]["pik_close_porogi"] = {f"ge_{p}": sum(r["pik_close"] >= p for r in g) / max(1, len(g))
                                           for p in (1.5, 2.0, 2.5)}
    vse_p = [r["pik_high"] - r["itog"] for r in stroki]
    out["otdacha_vsego_pp"] = sv(vse_p)
    out["vklad_otdachi"] = {kl: sum(r["pik_high"] - r["itog"] for r in stroki if r["vzveden"] == (kl == "vzveden"))
                            / max(1e-9, sum(vse_p)) for kl in ("vzveden", "ne_vzveden")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--u2"); ap.add_argument("--sprav"); ap.add_argument("--dannye", default="data_cache/equities_daily_10y")
    ap.add_argument("--vselennaya", default="U58"); ap.add_argument("--vyvod", required=True); ap.add_argument("--bps", default="20,10,30")
    a = ap.parse_args()
    from research_lab.alpaca_dannye import chasovye, v_dnevnye
    import research_lab.alpaca_u2 as U2M
    cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
    clusters = [{str(x) for x in g} for g in cfg["clusters"]]
    if a.vselennaya == "U2":
        syrye, _ = chasovye(Path(a.dannye)); U = U2M.zagruzit_u2(Path(a.u2), Path(a.sprav), v_dnevnye(syrye))
    else:
        U = U2M.zagruzit_u58(Path(a.dannye), bez_sektorov=False)
    o0, o1 = date.fromisoformat(U2M.OKNO[0]), date.fromisoformat(U2M.OKNO[1])
    okno = [s for s in U.sessii if o0 <= s <= o1]
    resh = U2M.mesyachnye(U, U2M.raspisanie(U.sessii, okno), clusters)
    out = {"prereg": "PREREG_ALPACA_H6_TREYL_UTECHKA_I_FORWARD_2026_10_19", "commit_prereg": "9112083",
           "vselennaya": a.vselennaya, "bps": {}}
    vyv = Path(a.vyvod)
    for bp in [float(x) for x in a.bps.split(",")]:
        z, rasx, stroki = chast_a(U, okno, resh, bp)
        rez = {"sdelok_dvizhka": len(z["trades"]), "identichnost": "PASS" if not rasx else "FAIL",
               "rashozhdeniy": len(rasx), "primery_rashozhdeniy": rasx[:5]}
        if not rasx:
            rez["razlozhenie"] = razlozhit(stroki)
        out["bps"][f"{bp:.0f}"] = rez
        vyv.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        print(f"{bp:.0f}bps", rez["identichnost"], len(z["trades"]), len(rasx), flush=True)


if __name__ == "__main__":
    main()
