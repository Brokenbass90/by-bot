#!/usr/bin/env python3
"""begun_xsec.py — XSEC_EXACT_TARGET_WEIGHTS_PIT: ровно формула тени, честная вселенная.

Веса и плечо — функции target_weights() и leverage() из research_lab/xsec_v3_reference.py
(хеш сверяется). Три подпортфеля (фазы), каждый ребалансируется раз в 3 дня со
сдвигом на день, капитал фазы = 1/3. Зрелость: первая дневная свеча не позже
t − 390 дней; если первая свеча совпадает с началом загрузки (2023-01-01),
инструмент считается запущенным раньше (зрелым).
Издержки: 7 б.п. на сторону с РЕАЛЬНОГО оборота фазы + фандинг за период
(лонг платит положительный, шорт получает).
Контроль: тот же вектор весов и то же плечо, раздаются случайным инструментам из той
же вселенной на ту же дату; у каждой случайной фазы свой оборот. 20 розыгрышей.

Вселенные (param "vselennaya"):
  pit50 — топ-50 по OI в долларах на дату (вердикт);
  ten62 — замороженные 62 монеты живой тени (только диагностика: мера смещения выживших).
Этапы: discovery обрезает данные на 2025-10-01; confirmation — периоды после.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent; LAB = DIR.parent; ROOT = LAB.parent
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(DIR))
import xsec_v3_reference as X  # noqa: E402
import portfeli  # noqa: E402

XSEC_HESH = "см. PREREG_PAKET_V3"          # фактический хеш пишет фабрика в вердикт
DEN, FEE, DRAWS = 86400000, 7.0, 20
RAZDEL = portfeli._ms("2025-10-01")


def zagruzit(vsel):
    if vsel == "pit50":
        return portfeli.zagruzit_kripto_pit("basis/vselennaya_pit_usd50.json")
    u = json.load(open(ROOT / "runtime/xsec_v3_shadow/universe.json"))
    syms = set(u.get("symbols") or [])
    R = portfeli.zagruzit_kripto_pit(vse_chleny=sorted(syms))
    M = R["M"]
    R["M"] = M; R["ten62_naydeno"] = int(sum(np.isfinite(R["C"][:, j]).any() for j in range(len(R["simvoly"])))); R["ten62_vsego"] = len(syms)
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True); ap.add_argument("--vyhod", required=True)
    a = ap.parse_args(); p = json.loads(a.param); etap = p.get("etap", "discovery")
    try:
        R = zagruzit(p.get("vselennaya", "pit50"))
    except FileNotFoundError as e_:
        tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps({"param": p, "okna": {"VSE": {"n": 0}, "H1": {}, "H2": {}},
        "chlenov_s_cenoy_mediana": 0.0, "net_dannyh": str(e_)}, ensure_ascii=False)); tmp.replace(a.vyhod)
        print("нет данных:", e_); return
    dates, C, M, F = R["dates"], R["C"], R["M"], R["F"]
    if etap == "discovery":
        k = int(np.searchsorted(dates, RAZDEL)); dates, C, M, F = dates[:k], C[:k], M[:k], F[:k]
    n, N = C.shape
    fin = np.isfinite(C)
    first = np.array([np.argmax(fin[:, j]) if fin[:, j].any() else n for j in range(N)])
    zrelyy_s_nachala = first <= 2
    need = max(X.LOOKBACKS) + 1
    rng = np.random.default_rng(7)
    faza_hist = {f: [] for f in range(X.PHASES)}
    prev_w = {f: {} for f in range(X.PHASES)}
    prev_rw = {f: [dict() for _ in range(DRAWS)] for f in range(X.PHASES)}
    strat, rand, edge, tday, propuskov = [], [], [], [], 0

    def period_ret(w, t, H, prev):
        r = 0.0; oborot = sum(abs(w.get(s, 0) - prev.get(s, 0)) for s in set(w) | set(prev))
        for j, wj in w.items():
            seg = C[t + 1:t + H + 1, j]; ok = np.flatnonzero(np.isfinite(seg))
            if not len(ok):
                continue
            r += wj * (seg[ok[-1]] / C[t, j] - 1) - wj * F[t + 1:t + H + 1, j].sum()
        return r - oborot * FEE / 1e4

    for t in range(need, n - X.REBALANCE_DAYS):
        if etap == "confirmation" and dates[t] < RAZDEL:
            continue
        f = t % X.PHASES
        el = [j for j in range(N) if M[t, j] and fin[t, j] and (zrelyy_s_nachala[j] or t - first[j] >= X.MATURITY_DAYS)
              and np.isfinite(C[t - need + 1:t + 1, j]).all()]
        hist = {j: list(C[t - need + 1:t + 1, j]) for j in el}
        w = X.target_weights(hist)
        if not w:
            propuskov += 1; continue
        lev = X.leverage(faza_hist[f]) / X.PHASES
        wl = {j: v * lev for j, v in w.items()}
        s_ = period_ret(wl, t, X.REBALANCE_DAYS, prev_w[f]); prev_w[f] = wl
        faza_hist[f].append(s_ * X.PHASES)
        vals = list(wl.values()); rr = []
        for d_ in range(DRAWS):
            vyb = rng.choice(el, size=len(vals), replace=False)
            rw = {int(j): v for j, v in zip(vyb, rng.permutation(vals))}
            rr.append(period_ret(rw, t, X.REBALANCE_DAYS, prev_rw[f][d_])); prev_rw[f][d_] = rw
        strat.append(s_); rand.append(float(np.mean(rr))); edge.append(s_ - float(np.mean(rr))); tday.append(int(dates[t]))

    def stat(e):
        e = np.asarray(e); m = len(e)
        if m < 2:
            return {"n": m, "n_eff": m / 3}
        sd = e.std(ddof=1)
        return {"n": m, "n_eff": round(m / 3, 1), "edge": float(e.mean()),
                "t": float(e.mean() / sd * math.sqrt(m / 3)) if sd > 0 else 0.0}
    h = len(edge) // 2
    rez = {"param": p, "etap": etap, "okna": {"VSE": stat(edge), "H1": stat(edge[:h]), "H2": stat(edge[h:])},
           "propushcheno_rebalansov": propuskov, "rebalansov": len(edge),
           "godovyh_strategiya": float(np.mean(strat) * 365) if strat else None,
           "chlenov_s_cenoy_mediana": 1.0 if edge else 0.0,
           "xsec_reference_sha256": hashlib.sha256((LAB / "xsec_v3_reference.py").read_bytes()).hexdigest()[:16],
           **({"ten62_naydeno": R["ten62_naydeno"], "ten62_vsego": R["ten62_vsego"]} if "ten62_naydeno" in R else {})}
    tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); tmp.replace(a.vyhod)
    print("готово, ребалансов:", len(edge), "пропущено:", propuskov)


if __name__ == "__main__":
    main()
