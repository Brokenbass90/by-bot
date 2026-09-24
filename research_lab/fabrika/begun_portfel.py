#!/usr/bin/env python3
"""begun_portfel.py — портфельный прогонщик фабрики.

Каждый день t (после прогрева) строится корзина по сигналу из portfeli.py
по бумагам, входящим во вселенную НА ДАТУ t, и держится H дней.
  ls   : лонг верхней доли kv, шорт нижней, доходность = лонг − шорт
  long : лонг верхней доли
Издержки: fee_bps на сторону × 2 (вход+выход) × число ног — за каждый период.
Крипта: фандинг за период вычитается у лонга и прибавляется шорту.
Делистинг внутри периода: выход по последней известной цене (не выкидываем).

КОНТРОЛЬ: в тот же день те же количества бумаг, выбранные СЛУЧАЙНО из той же
вселенной, 50 розыгрышей, seed 7. Эдж дня = корзина − среднее случайных.
Корзины пересекаются (старт каждый день, держим H), поэтому t-статистика
считается с эффективным числом периодов n/H.

ЭТАПЫ (обнаружение и подтверждение разведены):
  discovery    — данные ОБРЕЗАЮТСЯ на дате раздела рынка, после неё прогонщик
                 не видит ни одной цены;
  confirmation — считаются только периоды, начинающиеся после раздела.
"""
from __future__ import annotations
import argparse, json, math, sys, warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
from portfeli import RYNKI_P, SIGNALY  # noqa: E402

DRAWS = 50
PROGREV = {"akcii_pit": 130, "kripto_pit": 50, "kripto_pit50": 50, "kripto_pit50_poly": 50}


def vyhod_cena(C, t, H, j):
    seg = C[t + 1:t + H + 1, j]
    ok = np.flatnonzero(np.isfinite(seg))
    return seg[ok[-1]] if len(ok) else np.nan


def stat(e, H):
    e = np.asarray(e, dtype=float); n = len(e)
    if n < 2:
        return {"n": n, "n_eff": n / H}
    sd = e.std(ddof=1); neff = n / H
    return {"n": n, "n_eff": round(neff, 1), "edge": float(e.mean()),
            "t": float(e.mean() / sd * math.sqrt(neff)) if sd > 0 else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True); ap.add_argument("--vyhod", required=True)
    ap.add_argument("--etap", default=None)
    a = ap.parse_args(); p = json.loads(a.param)
    etap = a.etap or p.get("etap", "discovery")
    S = SIGNALY[p["signal"]]; ry = S["rynok"]
    try:
        R = RYNKI_P[ry]()
    except FileNotFoundError as e_:
        tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps({"param": p, "okna": {"VSE": {"n": 0}, "H1": {}, "H2": {}},
        "chlenov_s_cenoy_mediana": 0.0, "net_dannyh": str(e_)}, ensure_ascii=False)); tmp.replace(a.vyhod)
        print("нет данных:", e_); return
    dates, C, DV, M, F = R["dates"], R["C"], R["DV"], R["M"], R["F"]
    H, kv, fee = S["H"], S.get("kv", 0.0), R["fee_bps"]
    HH, VV = R.get("HH"), R.get("VV")
    if etap == "discovery":                     # физически обрезать всё после раздела
        k = int(np.searchsorted(dates, R["razdel"]))
        dates, C, M = dates[:k], C[:k], M[:k]
        DV = DV[:k] if DV is not None else None; F = F[:k] if F is not None else None
        HH = HH[:k] if HH is not None else None; VV = VV[:k] if VV is not None else None
    nogi = 2 if S["napr"] == "ls" else 1
    cost = 2 * fee / 1e4 * nogi
    rng = np.random.default_rng(7)
    strat, rand, edge, tday, pokr = [], [], [], [], []
    chlenov_s_cenoy = []
    for t in range(PROGREV[ry], len(dates) - H):
        if etap == "confirmation" and dates[t] < R["razdel"]:
            continue
        el = M[t] & np.isfinite(C[t])
        if M[t].sum():
            chlenov_s_cenoy.append(el.sum() / M[t].sum())
        if el.sum() < 10:
            continue
        args = (C[:t + 1], DV[:t + 1] if DV is not None else None)
        if S.get("ctx"):
            ctx = {"M": M[:t + 1], "F": F[:t + 1] if F is not None else None,
                   "POLY": R["POLY"][:t + 1] if R.get("POLY") is not None else None,
                   "HH": HH[:t + 1] if HH is not None else None, "VV": VV[:t + 1] if VV is not None else None,
                   "simvoly": R["simvoly"]}
            sc = S["fn"](*args, ctx)
        else:
            sc = S["fn"](*args, F[:t + 1]) if S.get("nuzhen_fanding") else S["fn"](*args)
        ok = np.flatnonzero(el & np.isfinite(sc))
        if len(ok) < 10:
            continue
        r = np.array([vyhod_cena(C, t, H, j) for j in ok]) / C[t, ok] - 1
        f = F[t + 1:t + H + 1, ok].sum(axis=0) if F is not None else np.zeros(len(ok))
        good = np.isfinite(r); ok, r, f = ok[good], r[good], f[good]
        if len(ok) < 10:
            continue
        if S.get("vybor"):                      # событийный отбор: берём всех отмеченных
            top = np.flatnonzero(sc[ok] > 0); bot = top[:0]; k = len(top)
            if k == 0:
                continue
        else:
            k = max(1, int(kv * len(ok)))
            order = np.argsort(sc[ok])
            top, bot = order[-k:], order[:k]
        def ret(tp, bt):
            v = (r[tp] - f[tp]).mean()
            if S["napr"] == "ls":
                v -= (r[bt] - f[bt]).mean()
            return v - cost
        s_ = ret(top, bot)
        rr = []
        for _ in range(DRAWS):
            perm = rng.permutation(len(ok)); rr.append(ret(perm[:k], perm[k:2 * k]))
        strat.append(s_); rand.append(float(np.mean(rr))); edge.append(s_ - float(np.mean(rr)))
        tday.append(int(dates[t])); pokr.append(len(ok) / max(1, int(M[t].sum())))
    po_rezh = None
    if ry.startswith("kripto_pit") and edge:
        try:
            from regime_v1 import metki
            mt = metki(); grp = {}
            for td, e in zip(tday, edge):
                st = (mt.get(td) or {}).get("sost")
                if st: grp.setdefault(st, []).append(e)
            po_rezh = {st: stat(v, H) for st, v in grp.items()}
        except Exception as e_:
            po_rezh = {"oshibka": str(e_)}
    h = len(edge) // 2
    rez = {"param": p, "etap": etap, "rynok": ry, "H": H,
           "okna": {"VSE": stat(edge, H), "H1": stat(edge[:h], H), "H2": stat(edge[h:], H)},
           "po_rezhimam_REGIME_V1_diagnostika": po_rezh,
           "strategiya_srednee": float(np.mean(strat)) if strat else None,
           "sluchay_srednee": float(np.mean(rand)) if rand else None,
           "godovyh_strategiya": float(np.mean(strat) * 252 / H) if strat else None,
           "pokrytie_vselennoy_mediana": float(np.median(pokr)) if pokr else 0.0,
           "chlenov_s_cenoy_mediana": float(np.median(chlenov_s_cenoy)) if chlenov_s_cenoy else 0.0,
           "period": [tday[0], tday[-1]] if tday else None}
    tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); tmp.replace(a.vyhod)
    print("готово, дней:", len(edge), "эфф. периодов:", rez["okna"]["VSE"].get("n_eff"),
          "у членов вселенной есть цена:", round(rez["chlenov_s_cenoy_mediana"], 2))


if __name__ == "__main__":
    main()
