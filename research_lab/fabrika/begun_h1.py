#!/usr/bin/env python3
"""begun_h1.py — прогонщик фабрики для часовых сигнальных стратегий.

Это random_control.py, развёрнутый на ТРИ окна и с выводом в JSON.
Механика сделки и контроля взята из random_control без изменений
(sim_geo, та же монета, случайный час в том же месяце, та же геометрия,
20 розыгрышей, seed 7, блок hold//4 после сигнала).

Окна:
    O1  2024-03 … 2025-09   история
    O2  2023-01 … 2024-02   история
    O3  2025-10 … конец данных   бывшая печать (уже не слепая, но
        для новых конструкций ни разу не просмотрена)

Издержки: 6 б.п. на сторону, как в random_control. Фандинг НЕ вычтен.

Запуск (его делает fabrika.py, руками не нужно):
    python3 begun_h1.py --param '<json>' --vyhod rez.json [--limit N]
"""
from __future__ import annotations
import argparse, glob, hashlib, importlib, importlib.util, json, math, os, sys
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
ROOT = LAB.parent
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(ROOT))
from random_control import sim_geo, ema, FLAT, LOOKBACK, DRAWS  # noqa: E402
from research_machine import Store, pervyy_dlya, zapisat_sboy  # noqa: E402

OKNA = {"O1": (1709251200000, 1759276800000),
        "O2": (1672531200000, 1709251200000),
        "O3": (1759276800000, 10**14)}


def rezhim_fn(regime, reg_src):
    d = np.load(reg_src)
    c = d["ohlcv"][:, 3].astype(float); em = ema(c, 200)
    bts, bdist = d["ts"], (c - em) / em

    def ok(t):
        if regime == "любой":
            return True
        j = max(0, int(np.searchsorted(bts, t, side="right")) - 1)
        v = float(bdist[j]) if j < len(bdist) else 0.0
        return {"флет-": -FLAT <= v < 0, "флет+": 0 <= v < FLAT,
                "тренд-": v < -FLAT, "тренд+": v >= FLAT,
                "падает": v < 0, "растёт": v >= 0}[regime]
    return ok


def okno_itog(R, C):
    R = np.array(R)
    cm = np.array([np.mean(x) for x in C if len(x) > 20])
    out = {"n": int(len(R))}
    if len(R) < 2 or len(cm) < 5:
        out["kontrol_sobran"] = False
        return out
    edge = float(R.mean() - cm.mean())
    se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
    out.update(kontrol_sobran=True, mean=float(R.mean()), ctrl=float(cm.mean()),
               ctrl_sd=float(cm.std(ddof=1)), edge=edge, se=se,
               z=edge / se if se > 0 else 0.0, summa_R=float(R.sum()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True)
    ap.add_argument("--vyhod", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    p = json.loads(a.param)
    mod, cls, pfx = p["mod"], p["cls"], p["pfx"]
    side, mult, hold = p["side"], float(p["mult"]), int(p["hold"])
    regime, cd = p["regime"], str(p.get("cd", "0"))
    data_dir = str(LAB / "data" / "h1")
    files = sorted(glob.glob(f"{data_dir}/*.npz"))
    if a.limit:
        files = files[: a.limit]
    os.environ.update({f"{pfx}_SYMBOL_ALLOWLIST": ",".join(Path(f).stem for f in files),
                       f"{pfx}_ALLOW_LONGS": "1", f"{pfx}_ALLOW_SHORTS": "1"})
    if cd != "0":
        os.environ[f"{pfx}_COOLDOWN_BARS_5M"] = cd
    if p.get("modul_fayl"):
        # эталонная версия стратегии из git (для паритета со старым журналом)
        import strategies  # noqa: F401
        fp_mod = Path(__file__).resolve().parent / p["modul_fayl"]
        sp = importlib.util.spec_from_file_location(f"strategies._etalon_{Path(fp_mod).stem}", fp_mod)
        m = importlib.util.module_from_spec(sp); sys.modules[sp.name] = m; sp.loader.exec_module(m)
        S = getattr(m, cls)
    else:
        S = getattr(importlib.import_module(f"strategies.{mod}"), cls)
    reg_ok = rezhim_fn(regime, f"{data_dir}/BTCUSDT.npz")
    short = side == "short"
    real = {w: [] for w in OKNA}
    ctrl = {w: [[] for _ in range(DRAWS)] for w in OKNA}
    # ПАРИТЕТ С random_control: O1/O2 считаются на данных, обрезанных по
    # началу печати, и общим генератором seed 7 — ровно как там. O3 идёт
    # на полных данных со своим генератором, чтобы не сдвигать случайную
    # последовательность исторических окон.
    rng_ist = np.random.default_rng(7)
    rng_o3 = np.random.default_rng(8)
    CUT = OKNA["O3"][0]
    sboev = 0
    for k, fp in enumerate(files):
        dd = np.load(fp); ts, o = dd["ts"], dd["ohlcv"].astype(float)
        if len(ts) < LOOKBACK + 300:
            continue
        bars = [[int(ts[x]), o[x, 0], o[x, 1], o[x, 2], o[x, 3], o[x, 4]] for x in range(len(ts))]
        ncut = int((ts < CUT).sum())
        ist_ok = ncut >= LOOKBACK + 300
        bars_c, ts_c = bars[:ncut], ts[:ncut]
        month = (ts // (30 * 86400000)).astype(np.int64)
        month_c = month[:ncut]
        idx = np.arange(len(ts)); idx_c = np.arange(ncut)
        st = Store(Path(fp).stem); strat = S()
        pervyy = pervyy_dlya(S, st, Path(fp).stem)
        block = -1
        for i in range(LOOKBACK, len(bars) - 1):
            st.rows = bars[: i + 1]; b = bars[i]
            try:
                s = strat.maybe_signal(pervyy, b[0], b[1], b[2], b[3], b[4], b[5])
            except Exception as e:
                sboev += 1; zapisat_sboy("fabrika_begun_h1", e); continue
            if s is None or s.side != side or i <= block or not reg_ok(b[0]):
                continue
            pre = b[0] < CUT
            if pre and (not ist_ok or i >= ncut - 1):
                continue
            B, M, I, T, rng = ((bars_c, month_c, idx_c, ts_c, rng_ist) if pre
                               else (bars, month, idx, ts, rng_o3))
            entry0 = float(B[i + 1][1])
            sl = entry0 + (float(s.sl) - entry0) * mult
            risk = abs(sl - entry0)
            tps = [float(x) for x in (s.tps or [])]
            if risk <= 0 or len(tps) < 2:
                continue
            stop_pct = risk / entry0
            rr1 = abs(tps[0] - entry0) / risk; rr2 = abs(tps[1] - entry0) / risk
            f1 = float((s.tp_fracs or [0.55])[0])
            r = sim_geo(B, i, short, stop_pct, rr1, rr2, f1, hold)
            if r is None:
                continue
            block = i + hold // 4
            for w, (lo, hi) in OKNA.items():
                if lo <= b[0] < hi:
                    real[w].append(r)
                    pool = np.flatnonzero((M == M[i]) & (I >= LOOKBACK) & (I < len(T) - 1))
                    if len(pool) >= 5:
                        for dr in range(DRAWS):
                            rc = sim_geo(B, int(rng.choice(pool)), short, stop_pct, rr1, rr2, f1, hold)
                            if rc is not None:
                                ctrl[w][dr].append(rc)
        if (k + 1) % 20 == 0:
            print(f"... {k+1}/{len(files)}", flush=True)
    rez = {"param": p, "monet": len(files), "limit": a.limit, "sboev": sboev,
           "okna": {w: okno_itog(real[w], ctrl[w]) for w in OKNA}}
    Path(a.vyhod).write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print("готово, сделок по окнам:", {w: v["n"] for w, v in rez["okna"].items()})


if __name__ == "__main__":
    main()
