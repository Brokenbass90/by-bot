#!/usr/bin/env python3
"""rezhimnyy_carry.py — судья PREREG_REZHIMNYY_CARRY_2026_10_05.md (дешёвый экран). Один прогон; повтор запрещён.
    python3 research_lab/rezhimnyy_carry.py
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np

D = Path(__file__).resolve().parent / "data" / "binance_kity"
REZ = D / "carry_rezultat.json"
NACH, KON = dt.date(2021, 12, 2), dt.date(2026, 9, 23)
SETKA = [dt.date(2021, 7, 1) + dt.timedelta(days=7 * k) for k in range(400)]
SETKA = [d for d in SETKA if NACH <= d <= KON]
POROG, KORZ, IZD, IZD_SPR, KAP = 0.15, 10, 0.0051, 0.0031, 2.0
DEN = 86_400_000


def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    if REZ.exists():
        sys.exit("результат carry уже есть — прогон один")
    met = {f.stem: json.loads(f.read_text()) for f in (D / "metrics").glob("*.json")}
    fr = {}
    for f in (D / "funding").glob("*.json"):
        a = np.array(json.loads(f.read_text()) or [[0, 0.0]], dtype=float)
        fr[f.stem] = (a[:, 0].astype(np.int64), a[:, 1])
    def okno(s, t0, t1):
        if s not in fr:
            return None
        ts, r = fr[s]; i, j = np.searchsorted(ts, [t0, t1], side="right")
        return r[i:j] if j > i else None
    korzina, ned = set(), []
    for d in SETKA:
        vch = (d - dt.timedelta(days=1)).isoformat()
        U = [s for _, s in sorted([(v[vch][4], s) for s, v in met.items() if vch in v and v[vch][4]], reverse=True)[:50]]
        t = ms(d); sr = {}
        for s in U:
            x = okno(s, t - 7 * DEN, t)
            if x is not None and len(x):
                sr[s] = float(x.sum()) * 365 / 7          # годовые: сумма выплат за 7 дней (верно и для 4-ч/1-ч интервалов)
        on = len(sr) >= 30 and float(np.median(list(sr.values()))) > POROG
        nova = set(s for s, v in sorted(sr.items(), key=lambda z: -z[1])[:KORZ] if v > 0) if on else set()
        oborot = (len(nova - korzina) + len(korzina - nova)) / (2 * KORZ)   # доля полного круга
        dohod = 0.0
        if nova:
            vyp = [float(okno(s, t, t + 7 * DEN).sum()) if okno(s, t, t + 7 * DEN) is not None else 0.0 for s in nova]
            dohod = float(np.mean(vyp))
        ned.append(dict(d=d.isoformat(), on=on, n=len(nova), med_godovyh=round(float(np.median(list(sr.values()))), 4) if sr else None,
                        dohod=dohod, oborot=oborot))
        korzina = nova
    def itog(izd):
        r = np.array([w["dohod"] - w["oborot"] * izd for w in ned])
        return dict(godovyh_na_kapital=round(float(r.mean()) * 52 / KAP * 100, 2),
                    godovyh_na_kapital_tolko_ON=round(float(r[[w["on"] for w in ned]].mean()) * 52 / KAP * 100, 2) if any(w["on"] for w in ned) else None)
    dolya_on = sum(w["on"] for w in ned) / len(ned)
    osn = itog(IZD)
    verdikt = "KILL" if (osn["godovyh_na_kapital"] < 4 or dolya_on < 0.15) else "FEASIBILITY_PASS"
    po_godam = {}
    for w in ned:
        g = w["d"][:4]; po_godam.setdefault(g, [0, 0]); po_godam[g][0] += 1; po_godam[g][1] += w["on"]
    rez = dict(prereg="PREREG_REZHIMNYY_CARRY_2026_10_05.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               nedel=len(ned), dolya_ON=round(dolya_on, 3), ON_po_godam={g: f"{v[1]}/{v[0]}" for g, v in po_godam.items()},
               pri_51bps=osn, spravka_31bps=itog(IZD_SPR), verdikt=verdikt)
    REZ.write_text(json.dumps(dict(rez, nedeli=ned), ensure_ascii=False, indent=1))
    (D / "CARRY_KVITANCIYA.json").write_text(json.dumps(dict(rezultat_sha256=hashlib.sha256(REZ.read_bytes()).hexdigest(),
        manifest_kity_sha256=hashlib.sha256((D / "manifest.json").read_bytes()).hexdigest(), rezultat=rez), ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
