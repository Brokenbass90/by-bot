#!/usr/bin/env python3
"""pogloshchenie_h1.py — построитель событий и единственный тест PREREG_POGLOSHCHENIE_H1_2026_10_14.
    python3 research_lab/fabrika/pogloshchenie_h1.py --izmereniya     # покрытие + независимость от KITY (без доходностей)
    python3 research_lab/fabrika/pogloshchenie_h1.py --test           # один раз: OpportunityRecord + результат + реестр
"""
import argparse, bisect, datetime as dt, json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
for p in (LAB, LAB / "factory_v3"): sys.path.insert(0, str(p))
import opportunity_v1 as O       # noqa: E402

H = 3_600_000; DEN = 86_400_000; OKNO, MIN_OKNO, HOLD = 720, 500, 24; KOM = 12e-4
D = LAB / "data"; OUT = D / "pogloshchenie_h1"; OPP = D / "opportunities" / "POGLOSHCHENIE_H1_v1.csv.gz"
EPOHI = [("2021H2-22", "2021-07-01", "2023-01-01"), ("2023", "2023-01-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"),
         ("2025-26", "2025-01-01", "2026-10-01")]


def ms(s): return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def vselennaya_i_kity():
    import kity_sudya as K
    M = K.zagruzit(); per = defaultdict(list)
    for s, x in M.items():
        for vch, v in x["met"].items():
            if v[4]: per[vch].append((v[4], s))
    snimki = sorted(per); top = {v: {s for _, s in sorted(per[v], reverse=True)[:50]} for v in snimki}
    taker = {}
    for f in (K.B / "taker").glob("*.json"):
        taker[f.stem] = {K.den(t).isoformat(): tq / qv for t, qv, tq in json.loads(f.read_text()) if qv > 0}
    rang = {}
    for v in snimki:                                     # KITY m3: процентиль доли тейкера на снимке среди топ-50
        vals = sorted((taker.get(s, {}).get(v), s) for s in top[v] if taker.get(s, {}).get(v) is not None)
        rang[v] = {s: (k + 0.5) / len(vals) for k, (_, s) in enumerate(vals)}
    return snimki, top, rang


def snimok_dlya(snimki, ts):
    d = (dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    k = bisect.bisect_right(snimki, d) - 1
    return snimki[k] if k >= 0 else None


def fanding(s):
    p = D / "binance_kity" / "funding" / f"{s}.json"
    if not p.exists(): return np.zeros(0, np.int64), np.zeros(0)
    a = np.array(json.loads(p.read_text()) or [[0, 0.0]], float); return a[:, 0].astype(np.int64), a[:, 1]


def _kat(x, w):
    """Скользящие среднее и sd по w ПРЕДЫДУЩИМ значениям (без текущего): индекс h → окно [h−w, h)."""
    c1 = np.concatenate([[0.0], np.cumsum(x)]); c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    m = np.full(len(x), np.nan); sd = np.full(len(x), np.nan)
    h = np.arange(w, len(x)); s1 = c1[h] - c1[h - w]; s2 = c2[h] - c2[h - w]
    m[h] = s1 / w; sd[h] = np.sqrt(np.maximum(s2 / w - m[h] ** 2, 0)); return m, sd


def sobytiya(s, rows, snimki, top, rang):
    """zN = z(N/среднийОбъём) по 720 предыдущим часам — нормировка на средний объём окна в z сокращается, т.е. zN = z(N)."""
    a = np.array(rows, float); ts = a[:, 0].astype(np.int64); o, c, qv, tb = a[:, 1], a[:, 2], a[:, 3], a[:, 4]
    r = np.where(o > 0, c / o - 1, 0.0); N = 2 * tb - qv
    mN, sN = _kat(N, OKNO); mr, sr = _kat(r, OKNO)
    with np.errstate(divide="ignore", invalid="ignore"):
        zN = (N - mN) / sN; zr = (r - mr) / sr
    ok_okno = np.zeros(len(ts), bool); hh = np.arange(OKNO, len(ts)); ok_okno[hh] = (ts[hh] - ts[hh - OKNO]) <= int(OKNO * 1.05) * H
    kand = np.flatnonzero(ok_okno & np.isfinite(zN) & (np.abs(zN) >= 3) & (sr > 0))
    out = {"ABSORB": [], "NORMAL": []}; poka = {"ABSORB": -1, "NORMAL": -1}
    for h in kand:
        if h + HOLD >= len(ts): break
        t_res = int(ts[h]) + H
        v = snimok_dlya(snimki, t_res)
        if v is None or s not in top[v]: continue
        storona = 1 if zN[h] <= -3 else -1
        gr = None
        if (zN[h] <= -3 and r[h] >= 0) or (zN[h] >= 3 and r[h] <= 0): gr = "ABSORB"
        elif (zN[h] <= -3 and zr[h] <= -1) or (zN[h] >= 3 and zr[h] >= 1): gr = "NORMAL"
        if gr is None or h <= poka[gr]: continue
        j = h + HOLD
        if ts[j] != ts[h] + HOLD * H: continue
        poka[gr] = j
        out[gr].append(dict(h=int(h), t_res=t_res, t_vyh=int(ts[j]) + H, c0=float(c[h]), c1=float(c[j]), storona=storona,
                            zN=round(float(zN[h]), 3), zr=round(float(zr[h]), 3), r=round(float(r[h]), 6), kity=rang[v].get(s), snimok=v))
    return out


def vse_sobytiya():
    snimki, top, rang = vselennaya_i_kity(); vse = {"ABSORB": [], "NORMAL": []}
    for f in sorted((D / "binance_h1").glob("*.json")):
        rows = json.loads(f.read_text())
        if len(rows) < OKNO + HOLD + 10: continue
        for g, lst in sobytiya(f.stem, rows, snimki, top, rang).items():
            for e in lst: e["sym"] = f.stem; vse[g].append(e)
    return vse


def izmereniya():
    vse = vse_sobytiya(); rez = {}
    for g, lst in vse.items():
        po_ep = {n: sum(ms(a) <= e["t_res"] < ms(b) for e in lst) for n, a, b in EPOHI}
        k = [(e["storona"], e["kity"]) for e in lst if e["kity"] is not None]
        def rk(x): return np.argsort(np.argsort(np.asarray(x, float)))
        korr = float(np.corrcoef(rk([x[0] for x in k]), rk([x[1] for x in k]))[0, 1]) if len(k) > 30 else None
        rez[g] = dict(sobytiy=len(lst), monet=len({e["sym"] for e in lst}), po_epoham=po_ep,
                      dolya_long=round(sum(e["storona"] == 1 for e in lst) / max(1, len(lst)), 3),
                      korr_storona_x_kity_rang=None if korr is None else round(korr, 3))
    k = rez["ABSORB"]["korr_storona_x_kity_rang"]
    rez["reshenie"] = "СНЯТЬ как дубликат KITY" if k is not None and abs(k) > 0.5 else "НЕЗАВИСИМО — к одному тесту"
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "IZMERENIYA.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1))


def statistika(lst, kom):
    import discovery_paket1 as P
    po_dnyam = defaultdict(list)
    for e in lst: po_dnyam[e["t_res"] // DEN].append(e["net0"] - kom)
    dni = sorted(po_dnyam); v = np.array([np.mean(po_dnyam[d]) for d in dni])
    if len(v) < 20: return dict(n=len(lst), dney=len(v), mean_bps=None, t=0.0)
    h = len(v) // 2
    return dict(n=len(lst), dney=len(v), mean_bps=round(float(v.mean()) * 1e4, 1), t=round(float(P.t_nw(v, 1)), 2),
                polovinki_bps=[round(float(v[:h].mean()) * 1e4, 1), round(float(v[h:].mean()) * 1e4, 1)],
                _dnevnye=v)


def test():
    if (OUT / "ITOG.json").exists(): sys.exit("ITOG.json уже есть — тест один")
    vse = vse_sobytiya(); zapisi = []
    for g, lst in vse.items():
        for e in lst:
            fts, fr = fanding(e["sym"]); m = (fts > e["t_res"]) & (fts <= e["t_vyh"])
            e["net0"] = e["storona"] * (e["c1"] / e["c0"] - 1) - e["storona"] * float(fr[m].sum())   # без комиссии
            if g == "ABSORB":
                zapisi.append(O.zapis(e["t_res"], e["t_res"], e["t_res"], e["sym"], "POGLOSHCHENIE_H1", "v1", e["storona"], e["c0"],
                                      KOM, dict(zN=e["zN"], zr=e["zr"], r=e["r"], kity_rang=e["kity"]),
                                      e["t_vyh"], e["c1"], -e["storona"] * float(fr[m].sum()), e["net0"] - KOM))
    O.zapisat(OPP, zapisi)
    def v_okne(lst, a, b): return [e for e in lst if ms(a) <= e["t_res"] < ms(b)]
    glav = {g: v_okne(vse[g], "2023-01-01", "2026-10-01") for g in vse}; repl = {g: v_okne(vse[g], "2021-07-01", "2023-01-01") for g in vse}
    sA, sN = statistika(glav["ABSORB"], KOM), statistika(glav["NORMAL"], KOM)
    d_t = None
    if sA.get("_dnevnye") is not None and sN.get("_dnevnye") is not None:
        a, b = sA["_dnevnye"], sN["_dnevnye"]
        d_t = round(float((a.mean() - b.mean()) / math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))), 2)
    rA = statistika(repl["ABSORB"], KOM)
    epohi = {n: {k: v for k, v in statistika(v_okne(vse["ABSORB"], a, b), KOM).items() if k != "_dnevnye"} for n, a, b in EPOHI}
    izd = {f"{int(k * 1e4)}_bps": {kk: vv for kk, vv in statistika(glav["ABSORB"], k).items() if kk in ("mean_bps", "t")} for k in (0, 12e-4, 24e-4)}
    # реестр: две попытки (главное окно и репликация)
    from reestr_v1 import Reestr
    R = Reestr(); spec = dict(prereg="PREREG_POGLOSHCHENIE_H1_2026_10_14.md", kod="fabrika/pogloshchenie_h1.py")
    R.perehod("POGLOSHCHENIE_H1_V1", "SCREEN", "PREREG_POGLOSHCHENIE_H1 + IZMERENIYA")
    for pid, ok, s_ in (("POGLOSHCHENIE_H1_V1_S1", "KRIPTO_H1M5_2023_2026Q3", sA), ("POGLOSHCHENIE_H1_V1_R1", "KRIPTO_D1_2021H2_2022", rA)):
        R.zaregistrirovat_popytku(pid, "POGLOSHCHENIE_H1_V1", ok, "SCREEN", spec, dict(min_n=200, znak="+"))
        z = R.zapisat_rezultat(pid, spec, t=s_["t"], n=s_["n"], metrika={k: v for k, v in s_.items() if k != "_dnevnye"})
        s_["t_req"] = z["trebuemyy_t"]
    pas = (sA["mean_bps"] or 0) > 0 and sA["t"] >= sA["t_req"] and min(sA.get("polovinki_bps", [0])) > 0 \
        and d_t is not None and d_t >= 1.0
    rep_ok = (rA["mean_bps"] or 0) > 0
    clean = lambda s_: {k: v for k, v in s_.items() if k != "_dnevnye"}
    itog = dict(prereg="PREREG_POGLOSHCHENIE_H1_2026_10_14.md", glavnoe_okno=dict(ABSORB=clean(sA), NORMAL=clean(sN), raznica_t=d_t),
                replikaciya_2021H2_22=clean(rA), epohi=epohi, izderzhki=izd, opportunity=str(OPP.relative_to(LAB)), zapisey=len(zapisi),
                verdikt=("PASS → только форвард (CONFIRM)" if pas and rep_ok else "FAIL"),
                kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    (OUT / "ITOG.json").write_text(json.dumps(itog, ensure_ascii=False, indent=1)); print(json.dumps(itog, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--izmereniya", action="store_true"); ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.izmereniya: izmereniya()
    elif a.test: test()
