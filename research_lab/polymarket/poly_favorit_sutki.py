#!/usr/bin/env python3
"""Прогон PREREG_POLY_FAVORIT_SUTKI_2026_10_19 (14c12bd). Только исследование.
python3 research_lab/polymarket/poly_favorit_sutki.py [--qa]   (--qa: только ворота данных, без доходностей)"""
import datetime as dt, json, math, re, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
AKTIV = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT"}
RX = re.compile(r"^Will the price of (Bitcoin|Ethereum|Solana|XRP) be above \$([\d,]+(?:\.\d+)?) on [A-Z][a-z]+ \d{1,2}\?$")
SUTKI, SVEZH, C, C_STRESS, POLOSA = 86400, 6 * 3600, 0.01, 0.02, 0.003


def h1():
    out = {}
    for a, s in AKTIV.items():
        z = np.load(D / "h1" / f"{s}.npz"); ts = z["ts"].astype(np.int64)
        ts = ts // 1000 if ts[0] > 1e11 else ts
        out[a] = (ts, z["ohlcv"])
    return out


def cena_h1(H, a, k, konv):
    """konv 'close@ts': ts — метка закрытия бара → close бара с ts == k; 'open@ts': ts — открытие → open бара с ts == k."""
    ts, o = H[a]; i = np.searchsorted(ts, k)
    if i >= len(ts) or ts[i] != k:
        return None
    return float(o[i, 3] if konv == "close@ts" else o[i, 0])


def rynki():
    for f in sorted((D / "poly" / "istoriya").glob("*.json")):
        d = json.loads(f.read_text())
        if d.get("kat") != "kripto_cena" or not d.get("closed"):
            continue
        m = RX.match(d.get("vopros", ""))
        r = d.get("ryad") or []
        if not m or not r:
            continue
        k = int(dt.datetime.fromisoformat(d["konec"].replace("Z", "+00:00")).timestamp()); T = k - SUTKI
        do = [x for x in r if x[0] <= T]
        if not do or T - do[-1][0] > SVEZH or not any(T < x[0] < k for x in r):
            continue
        yield dict(id=d["id"], aktiv=m.group(1), X=float(m.group(2).replace(",", "")), konec=k, p=float(do[-1][1]),
                   posl=float(r[-1][1]), sobytie=f"{m.group(1)}|{d['konec'][:10]}")


def ishod(z, H, konv):
    c = cena_h1(H, z["aktiv"], z["konec"], konv)
    pin = 1 if z["posl"] >= 0.98 else (0 if z["posl"] <= 0.02 else None)
    if c is not None and abs(c / z["X"] - 1) >= POLOSA:
        return int(c > z["X"]), "h1", pin
    return pin, ("pin" if pin is not None else None), pin


def qa(R, H):
    out = {}
    for konv in ("close@ts", "open@ts"):
        sov = vse = 0
        for z in R:
            c = cena_h1(H, z["aktiv"], z["konec"], konv); pin = 1 if z["posl"] >= 0.98 else (0 if z["posl"] <= 0.02 else None)
            if c is None or pin is None or abs(c / z["X"] - 1) < POLOSA:
                continue
            vse += 1; sov += int((c > z["X"]) == bool(pin))
        out[konv] = dict(sravneno=vse, sovpalo=sov, dolya=sov / vse if vse else None)
    return out


def main():
    H = h1(); R = list(rynki())
    sdelki = [z for z in R if 0.80 <= z["p"] <= 0.95 or 0.05 <= z["p"] <= 0.20]
    q = qa(sdelki, H); konv = max(q, key=lambda k: q[k]["dolya"] or 0)
    out = {"prereg": "PREREG_POLY_FAVORIT_SUTKI_2026_10_19", "commit_prereg": "14c12bd", "rynkov_razobrano": len(R),
           "kandidatov": len(sdelki), "qa": q, "konvenciya_vremeni_h1": konv}
    if (q[konv]["dolya"] or 0) < 0.97:
        out["verdikt"] = "BLOCKED_DATA"; print(json.dumps(out, ensure_ascii=False, indent=1)); return out
    if "--qa" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1)); return out
    rez, isk = [], {"net_ishoda": 0}
    for z in sdelki:
        y, ist, _ = ishod(z, H, konv)
        if y is None:
            isk["net_ishoda"] += 1; continue
        yes = z["p"] >= 0.80; cena = z["p"] if yes else 1 - z["p"]; vyplata = y if yes else 1 - y
        for cc, kl in ((C, "r"), (C_STRESS, "r_stress")):
            z[kl] = (vyplata - (cena + cc)) / (cena + cc)
        z.update(y=y, istochnik_ishoda=ist, storona="YES" if yes else "NO"); rez.append(z)
    ev = {}
    for z in rez:
        ev.setdefault(z["sobytie"], []).append(z)
    sr = sorted(ev.items(), key=lambda kv: kv[1][0]["konec"])
    ser = lambda kl: np.array([np.mean([z[kl] for z in v]) for _, v in sr])
    a, b = ser("r"), ser("r_stress"); n = len(a); h = n // 2
    t = float(a.mean() / (a.std(ddof=1) / math.sqrt(n))) if n > 2 else None
    po = dict(srednee=float(a.mean()), t=t, sobytiy=n, sdelok=len(rez), polovina1=float(a[:h].mean()), polovina2=float(a[h:].mean()),
              srednee_stress=float(b.mean()), isklyucheno=isk, istochniki=dict(h1=sum(z["istochnik_ishoda"] == "h1" for z in rez),
              pin=sum(z["istochnik_ishoda"] == "pin" for z in rez)))
    kal = {}
    for lo, hi in ((0.05, 0.10), (0.10, 0.15), (0.15, 0.20), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95)):
        x = [z for z in rez if lo <= z["p"] <= hi]
        if x:
            kal[f"{lo:.2f}-{hi:.2f}"] = dict(n=len(x), cena_yes=float(np.mean([z["p"] for z in x])), dolya_yes=float(np.mean([z["y"] for z in x])))
    po["kalibrovka"] = kal
    ok = po["srednee"] > 0 and t is not None and t >= 2.5 and po["polovina1"] > 0 and po["polovina2"] > 0 and n >= 30 and po["srednee_stress"] > 0
    out.update(po, verdikt="POSITIVE_LEAD" if ok else ("NEGATIVE" if po["srednee"] <= 0 else "INCONCLUSIVE"))
    (LAB / "results").mkdir(exist_ok=True); (LAB / "results" / "poly_favorit_sutki_20261019.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1)); return out


if __name__ == "__main__":
    main()
