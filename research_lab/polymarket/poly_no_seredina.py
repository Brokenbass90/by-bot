"""Прогон PREREG_POLY_NO_SEREDINA_ISTORIYA_2026_10_22. Только исследование, без кошелька."""
import collections, datetime as dt, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import poly_favorit_sutki as P
LAB = Path(__file__).resolve().parents[1]
C, C_S, F, F_S = 0.01, 0.02, 0.07, 0.10


def tt(x):
    x = np.array(x); return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else None


def main(out_path):
    H = P.h1(); R = list(P.rynki())
    sd = [z for z in R if 0.20 < z["p"] < 0.80]
    q = P.qa(sd, H); konv = max(q, key=lambda k: q[k]["dolya"] or 0)
    out = {"prereg": "PREREG_POLY_NO_SEREDINA_ISTORIYA_2026_10_22", "rynkov": len(sd), "qa": q, "konv": konv}
    if (q[konv]["dolya"] or 0) < 0.97:
        out["verdikt"] = "BLOCKED_DATA"; Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(out); return
    rez, isk = [], 0
    for z in sd:
        y, ist, _ = P.ishod(z, H, konv)
        if y is None: isk += 1; continue
        win = 1 - y
        for cc, ff, kl in ((C, F, "r"), (C_S, F_S, "r_s")):
            qq = (1 - z["p"]) + cc; cena = qq + ff * qq * (1 - qq)
            z[kl] = (win - cena) / cena
        z.update(y=y, ist=ist); rez.append(z)
    ev = collections.defaultdict(list)
    for z in rez: ev[z["sobytie"]].append(z)
    evs = sorted(ev.items(), key=lambda kv: kv[1][0]["konec"])
    a = [float(np.mean([z["r"] for z in v])) for _, v in evs]; b = [float(np.mean([z["r_s"] for z in v])) for _, v in evs]
    dates = collections.defaultdict(list)
    for (k, v), x in zip(evs, a): dates[k.split("|")[1]].append(x)
    ad = [float(np.mean(v)) for _, v in sorted(dates.items())]
    h = len(a) // 2
    kal = {}
    for lo, hi in ((0.20, 0.35), (0.35, 0.50), (0.50, 0.65), (0.65, 0.80)):
        x = [z for z in rez if lo < z["p"] <= hi]
        if x: kal[f"{lo:.2f}-{hi:.2f}"] = dict(n=len(x), cena_yes=float(np.mean([z["p"] for z in x])), dolya_yes=float(np.mean([z["y"] for z in x])),
                                               dohod_na_sdelku=float(np.mean([z["r"] for z in x])))
    out.update(sdelok=len(rez), isklyucheno=isk, sobytiy=len(a), dat=len(ad), srednee=float(np.mean(a)), t_sobytiya=tt(a), t_daty=tt(ad),
               dolya_dat_plyus=float(np.mean([x > 0 for x in ad])), polovina1=float(np.mean(a[:h])), polovina2=float(np.mean(a[h:])),
               srednee_stress=float(np.mean(b)), istochniki=dict(collections.Counter(z["ist"] for z in rez)), kalibrovka=kal,
               period=[str(dt.datetime.utcfromtimestamp(evs[0][1][0]["konec"]).date()), str(dt.datetime.utcfromtimestamp(evs[-1][1][0]["konec"]).date())])
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
