#!/usr/bin/env python3
"""elder_hist_sbor.py — сбор для PREREG_ELDER_ETS2M_HIST_DEV_2026_10_15.md. Только сбор, ничего не агрегирует.

Вход: ETS2S ровно как живая тень (ten.py): elder_triple_screen_v2, env 1440/240/60/240, шорт, стратегия НЕ вызывается
на заблокированных барах, стоп x4 от e_ref = open(i+1), MAX_LEV, k1/k2 = цели стратегии в R расширенного стопа, f1 0.55.
Исполнение и выходы: функции замороженного ядра судьи ETS2M (yadro.ispolnenie, yadro.prodvinut, yadro.DVIGATELI) —
лимит 0.002 / 6 баров, CONTROL / 24H / WIDE, издержки 1.5+5.5 bps * плечо внутри R.
Блокировка: block = i + zhdat + barov_CONTROL + 1 (как ten.py). Не исполнился — сделки нет, блока нет.
Информационный контроль (вторичный): 3 случайных бара того же режима монеты, тот же лимит и CONTROL-движок, rng 4300+номер.
    python3 research_lab/fabrika/elder_hist_sbor.py --ot N --do M     # кусками по монетам; дописывает JSONL
"""
import argparse, glob, json, os, sys, time, hashlib, importlib
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; KOREN = LAB.parent
os.chdir(KOREN); sys.path.insert(0, str(KOREN)); sys.path.insert(0, str(LAB))
os.environ.update({"ETS2_TREND_TF": "1440", "ETS2_WAVE_TF": "240", "ETS2_ENTRY_TF": "60", "ETS2_RISK_TF": "240"})
import numpy as np                                                  # noqa: E402
from research_machine import Store, MAX_LEV, pervyy_dlya            # noqa: E402
import yadro as Y                                                   # noqa: E402
from osi import rezhim_ryad, metka_rezhima                          # noqa: E402

OUT = LAB / "data" / "elder_hist_dev" / "sdelki.jsonl"
STOP, OTSTUP, ZHDAT, F1 = 4.0, Y.KONFIG["otstup"], Y.KONFIG["zhdat"], 0.55
FEE_V, FEE_VY = Y.KONFIG["fee_vhod"], Y.KONFIG["fee_vyhod"]
ROZ = 3


def bary(fp):
    d = np.load(fp); t, o = d["ts"], d["ohlcv"].astype(float)
    return [[int(t[k]), o[k, 0], o[k, 1], o[k, 2], o[k, 3], o[k, 4]] for k in range(len(t))]


def dvizhki(b, i, short, sp, k1, k2):
    r = Y.ispolnenie(b, i, short, OTSTUP, ZHDAT)
    if r is None or r[0] != "ispolnen":
        return None
    _, vh, cena = r
    cost = (1.0 / sp) * (FEE_V + FEE_VY) / 1e4
    out = {}
    for imya, d in Y.DVIGATELI.items():
        rr1, rr2 = (k1, k2) if d["rr"] is None else d["rr"]
        x = Y.prodvinut(b, vh, cena, short, sp, rr1, rr2, F1, d["hold"], cost)
        out[imya] = None if x is None else (float(x[0]), int(x[1]), x[2])
    out["_cost"] = cost
    return out


def main(ot, do):
    assert Y.KONFIG["otstup"] == 0.002 and Y.KONFIG["zhdat"] == 6 and FEE_V == 1.5 and FEE_VY == 5.5
    fayly = sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz")))
    syms = [Path(f).stem.upper() for f in fayly]
    os.environ.update({"ETS2_SYMBOL_ALLOWLIST": ",".join(syms), "ETS2_ALLOW_LONGS": "1", "ETS2_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module("strategies.elder_triple_screen_v2"), "ElderTripleScreenV2Strategy")
    uzhe = set()
    gotovo = OUT.with_suffix(".gotovo")
    if gotovo.exists():
        uzhe = set(gotovo.read_text().split())
    for nomer, fp in enumerate(fayly[ot:do], ot):
        sym = Path(fp).stem.upper()
        if sym in uzhe:
            continue
        t0 = time.time(); rng = np.random.default_rng(4300 + nomer)
        b = bary(fp)
        out = []
        if len(b) >= 300:
            metki = np.array([metka_rezhima(x) for x in rezhim_ryad(b)])
            strat = K(); st = Store(sym); pervyy = pervyy_dlya(K, st, sym)
            block = -1
            for i in range(200, len(b) - 1):
                if i <= block:
                    continue
                st.rows = b[: i + 1]; r_ = b[i]
                try:
                    s = strat.maybe_signal(pervyy, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
                except Exception:
                    continue
                if s is None or getattr(s, "side", None) != "short":
                    continue
                e_ref = float(b[i + 1][1]); sl_w = e_ref + (float(s.sl) - e_ref) * STOP; risk_w = abs(e_ref - sl_w)
                if risk_w <= 0 or e_ref <= 0:
                    continue
                sp = risk_w / e_ref
                if 1.0 / sp > MAX_LEV:
                    continue
                tl = list(s.tps or [])
                k1 = abs(tl[0] - e_ref) / risk_w if len(tl) > 0 else 999.0
                k2 = abs(tl[1] - e_ref) / risk_w if len(tl) > 1 else 999.0
                d = dvizhki(b, i, True, sp, k1, k2)
                if d is None:
                    out.append(dict(sym=sym, ts=int(r_[0]), i=i, ispolnen=False))
                    continue
                if any(d[k] is None for k in Y.DVIGATELI):     # конец истории — исхода нет, не выдумываем
                    out.append(dict(sym=sym, ts=int(r_[0]), i=i, ispolnen=True, nezaversheno=True))
                    break
                block = i + ZHDAT + d["CONTROL"][1] + 1
                pool = np.flatnonzero(metki == metki[i]); pool = pool[(pool > 200) & (pool < len(b) - 340)]
                ctrl = []
                if len(pool) >= 10:
                    for _ in range(ROZ):
                        x = dvizhki(b, int(rng.choice(pool)), True, sp, k1, k2)
                        if x is not None and x["CONTROL"] is not None:
                            ctrl.append(x["CONTROL"][0])
                out.append(dict(sym=sym, ts=int(r_[0]), i=i, ispolnen=True, sp=round(sp, 6), k1=round(k1, 4), k2=round(k2, 4),
                                cost=round(d["_cost"], 6), rezhim=str(metki[i]),
                                **{f"R_{k}": round(d[k][0], 6) for k in Y.DVIGATELI},
                                **{f"bar_{k}": d[k][1] for k in Y.DVIGATELI},
                                **{f"pr_{k}": d[k][2] for k in Y.DVIGATELI},
                                ctrl=round(float(np.mean(ctrl)), 6) if ctrl else None))
        with open(OUT, "a") as f:
            for x in out:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        with open(gotovo, "a") as f:
            f.write(sym + "\n")
        print(f"{nomer} {sym}: решений {len(out)} ({time.time() - t0:.0f} с)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ot", type=int, default=0); ap.add_argument("--do", type=int, default=999)
    ap.add_argument("--limit-s", type=float, default=0)
    a = ap.parse_args(); t0 = time.time(); main(a.ot, a.do); print(f"готово за {time.time() - t0:.0f} с")
