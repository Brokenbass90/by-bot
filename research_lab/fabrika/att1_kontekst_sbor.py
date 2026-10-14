#!/usr/bin/env python3
"""att1_kontekst_sbor.py — сбор настоящих исторических сигналов ATT1 (шорт, все режимы) с замороженным набором признаков
для PREREG_ATT1_KONTEKST_2026_10_14.md. Только сбор: ничего не агрегирует и не печатает по исходам.

Механика сигналов, стоп x6, удержание 336 ч, случайный контроль (3 розыгрыша, тот же режим монеты, та же геометрия, rng 43) —
ровно как vskrytie_att1.py (ATT1_FILTER), режим BTC «любой». Признаки — только из баров ≤ i (вход — открытие i+1).
    python3 research_lab/fabrika/att1_kontekst_sbor.py [--ot N --do M]      # кусками по монетам; дописывает JSONL
"""
import argparse, glob, json, os, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import vskrytie_att1 as V                       # noqa: E402  (делает chdir в корень репо и грузит машину исследований)
import numpy as np                              # noqa: E402
from osi import rezhim_ryad, metka_rezhima      # noqa: E402
import importlib                                # noqa: E402

OUT = LAB / "data" / "att1_kontekst" / "sdelki.jsonl"
STOP, HOLD, STORONA = 6.0, 336, "short"


def bary(fp):
    d = np.load(fp); t, o = d["ts"], d["ohlcv"].astype(float); m = t < V.SEAL; t, o = t[m], o[m]
    return [[int(t[k]), o[k, 0], o[k, 1], o[k, 2], o[k, 3], o[k, 4]] for k in range(len(t))]


def main(ot, do):
    fayly = sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz")))
    btc_b = bary([f for f in fayly if Path(f).stem.upper() == "BTCUSDT"][0])
    btc_ts = np.array([r[0] for r in btc_b]); btc_c = np.array([r[4] for r in btc_b]); btc_rz = rezhim_ryad(btc_b)
    Klass = getattr(importlib.import_module(V.MODUL), V.KLASS)
    uzhe = set()
    if OUT.exists():
        with open(OUT) as f: uzhe = {json.loads(l)["sym"] for l in f if l.strip()}
    for nomer, fp in enumerate(fayly[ot:do], ot):
        sym = Path(fp).stem.upper()
        if sym in uzhe: continue
        rng = np.random.default_rng(43 + nomer)            # детерминированно по номеру файла
        b = bary(fp)
        if len(b) < 3000: continue
        rz = rezhim_ryad(b); metki = np.array([metka_rezhima(x) for x in rz]); c = np.array([r[4] for r in b])
        out = []
        for i, s in V.sobrat(b, Klass, sym, STORONA, "ATT1"):
            e = float(b[i + 1][1]); sl_w = e + (float(s.sl) - e) * STOP; risk = abs(e - sl_w)
            if risk <= 0 or e <= 0: continue
            sp = risk / e
            if 1.0 / sp > V.MAX_LEV: continue
            tl = list(s.tps or []); rr1 = abs(tl[0] - e) / risk if tl else 999.0; rr2 = abs(tl[1] - e) / risk if len(tl) > 1 else 999.0
            f1 = float((s.tp_fracs or [0.55])[0])
            R = V.sim_geo(b, i, True, sp, rr1, rr2, f1, HOLD)
            if R is None: continue
            pool = np.flatnonzero(metki == metki[i]); pool = pool[(pool > 200) & (pool < len(b) - HOLD - 2)]
            ctrl = [x for x in (V.sim_geo(b, int(rng.choice(pool)), True, sp, rr1, rr2, f1, HOLD) for _ in range(V.ROZYGRYSHEY)
                                if len(pool) >= 10) if x is not None]
            if not ctrl: continue
            pr = str(getattr(s, "reason", "") or ""); pb, voz = V._probitiy(b, i, V._yakorya(pr), STORONA)
            o_, h_, l_, c_ = b[i][1], b[i][2], b[i][3], b[i][4]
            okno = b[max(0, i - 14):i + 1]
            k = int(np.searchsorted(btc_ts, b[i][0], side="right")) - 1          # бар BTC с тем же или более ранним открытием
            tr = {w: (float(c[i] / c[i - w] - 1.0) if i - w >= 0 and c[i - w] > 0 else None) for w in (24, 72, 168)}
            out.append(dict(sym=sym, i=i, ts=int(b[i][0]), R=float(R), ctrl=float(np.mean(ctrl)),
                            f_vozrast_linii=voz, f_probitiy=pb, f_entrydist=V._chislo(pr, "entrydist"), f_r2=V._chislo(pr, "r2"),
                            f_vozrast_pivota=V._chislo(pr, "age"), f_naklon=V._naklon(pr),
                            f_body=V._chislo(pr, "body") if V._chislo(pr, "body") is not None else float(abs(c_ - o_) / max(1e-12, h_ - l_)),
                            f_atrpct=V._chislo(pr, "atrpct") if V._chislo(pr, "atrpct") is not None else
                                     float(np.mean([r[2] - r[3] for r in okno]) / max(1e-12, c_) * 100.0),
                            f_trend24=tr[24], f_trend72=tr[72], f_trend168=tr[168], f_rezhim_monety=float(rz[i]),
                            f_btc_rezhim=float(btc_rz[k]) if k >= 0 else None,
                            f_btc_trend72=float(btc_c[k] / btc_c[k - 72] - 1.0) if k >= 72 else None))
        with open(OUT, "a") as f:
            for x in out: f.write(json.dumps(x) + "\n")
        print(f"{nomer} {sym}: сигналов {len(out)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ot", type=int, default=0); ap.add_argument("--do", type=int, default=999)
    a = ap.parse_args(); t0 = time.time(); main(a.ot, a.do); print(f"готово за {time.time() - t0:.0f} с")
