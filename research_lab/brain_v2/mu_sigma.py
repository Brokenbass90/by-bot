#!/usr/bin/env python3
"""Brain V2 addendum A1 §3: закреплённая таблица μ̂/σ̂ скорера. Чистая функция от (потоки B3, метки REZHIM_V1 A1, H1 цены, cutoff).
    .venv/bin/python research_lab/brain_v2/mu_sigma.py [--cutoff 2025-10-01] [--out brain_v2/MU_SIGMA_V1.json]
Сделка учитывается ⇔ выход (вход след. бар + часы удержания) ≤ cutoff. Ячейка = REZHIM × VOL на час floor(t_signal) (как в wf.py)."""
import argparse, datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "os2"))
import wf as W, replay as P
K0, K1 = 300, 150; WIN = 90 * 24; H = 3600000
# A2: ts в потоках B3 = время ОТКРЫТИЯ сигнального бара; сигнал известен на его закрытии → t_available = ts + длина бара базы ноги
BAR_MS = {"ATT1": H, "SBR1": H, "ASR1": H, "BOUNCE1": H, "ETS2": 15 * 60000, "SF3": 15 * 60000}   # из os2/signaly.py NOGI (база 60/15)
def t_available(t): return int(t["ts"]) + BAR_MS[t["leg"]]

def natr_series(ts, o):
    h, l, c = o[:, 1], o[:, 2], o[:, 3]
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    atr = np.full(len(c), np.nan)
    if len(c) >= 14:
        atr[13] = tr[:14].mean()
        for i in range(14, len(c)): atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
    ok = np.ones(len(ts), bool); ok[1:] = np.diff(ts) == H          # непрерывность
    return atr / c, ok

def vol_bucket(natr, ok, i):
    """перцентиль natr[i] среди последних WIN значений (включая i), midrank; нужна непрерывная сетка WIN часов"""
    if i + 1 < WIN or not np.isfinite(natr[i - WIN + 1:i + 1]).all() or not ok[i - WIN + 2:i + 1].all(): return "UNKNOWN"
    w = natr[i - WIN + 1:i + 1]; x = natr[i]
    p = 100.0 * ((w < x).sum() + 0.5 * (w == x).sum()) / WIN
    return "LOW" if p < 33 else ("HIGH" if p > 67 else "MID")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cutoff", default="2025-10-01"); ap.add_argument("--out", default=str(LAB / "brain_v2/MU_SIGMA_V1.json"))
    a = ap.parse_args(); cut = W.ms(a.cutoff)
    konf = json.loads(W.KONF.read_text()); tr = [t for t in W.potoki(konf) if W.vyhod(t) <= cut]
    metki = W.metki_v1(); kesh = {}
    po = {}
    for t in tr:
        s = t["sym"]
        if s not in kesh:
            f = LAB / "data/h1" / f"{s}.npz"
            if f.exists():
                z = np.load(f); ts = z["ts"].astype(np.int64); n, ok = natr_series(ts, z["ohlcv"].astype(float))
                kesh[s] = (ts, n, ok)
            else: kesh[s] = None
        chas = t_available(t) // H * H; rez = metki.get(chas) or "UNKNOWN"   # A2: floor(t_available)
        vb = "UNKNOWN"
        if kesh[s] is not None:
            ts, n, ok = kesh[s]; i = int(np.searchsorted(ts, chas - H, side="right")) - 1   # последний ЗАКРЫТЫЙ час до chas
            if i >= 0 and ts[i] == chas - H: vb = vol_bucket(n, ok, i)
        cell = "UNKNOWN" if "UNKNOWN" in (rez, vb) else f"{rez}|{vb}"
        po.setdefault(t["leg"], {}).setdefault(cell, []).append(t["R"])
    tab = {}
    for leg, d in po.items():
        allr = np.concatenate([np.array(v) for v in d.values()]); ns = len(allr); ms = float(allr.mean())
        mu_s = ns * ms / (ns + K0); sd = float(allr.std(ddof=1))
        cells = {}
        for c, v in d.items():
            if c == "UNKNOWN": continue
            v = np.array(v); cells[c] = dict(n=len(v), mean=float(v.mean()), mu=(len(v) * float(v.mean()) + K1 * mu_s) / (len(v) + K1))
        tab[leg] = dict(n=ns, mean=ms, mu=mu_s, sigma=sd, n_unknown=len(d.get("UNKNOWN", [])), cells=cells)
    out = dict(versiya="MU_SIGMA_V1_A2", cutoff=a.cutoff, kappa0=K0, kappa1=K1, vol=dict(atr="Wilder 14 на закрытых H1", okno_ch=WIN, percentil="midrank", granicy=[33, 67]),
               istochnik=dict(b3_konfig_sha256=hashlib.sha256(W.KONF.read_bytes()).hexdigest(), rezhim="REZHIM_V1 A1"), nogi=tab)
    b = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True).encode(); Path(a.out).write_bytes(b)
    print("sha256", hashlib.sha256(b).hexdigest()); print({k: (v["n"], round(v["mu"], 4), round(v["sigma"], 3), v["n_unknown"]) for k, v in tab.items()})

if __name__ == "__main__":
    main()
