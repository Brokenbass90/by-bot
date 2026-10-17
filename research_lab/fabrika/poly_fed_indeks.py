#!/usr/bin/env python3
"""POLY_FED_SDVIG: индекс ожиданий ФРС из Polymarket и события-скачки (без доходностей).

E(t) = Σ p_i·bps_i по рынкам ДВУХ ближайших заседаний (диагностика 17.10: ближайшее почти всегда предрешено) (снижение −, повышение +; 25→25, 50/50+→50, 75+→75),
p_i — последняя цена с меткой ≤ t. Заседание = рынки «… after <Month YYYY> meeting»; дата = konec.
Скачок: ΔE = E(t) − E(t−24ч) на ОДНОМ и том же наборе заседаний, |ΔE| ≥ porog_bps, до заседания ≥ 48 ч.
Момент события = t + 1 ч (запас доступности). Дедуп: следующее событие не раньше чем через dedup_ch после предыдущего.
Знак: ΔE < 0 (рынок ждёт больше смягчения) → +1 (BTC вверх); ΔE > 0 → −1.
"""
import json, glob, re, sys, bisect, datetime as dt
from pathlib import Path
from collections import defaultdict
LAB = Path(__file__).resolve().parents[1]
H = 3600

def bps(vopros, kat):
    m = re.search(r"by (\d+)\+? ?bps", vopros)
    if not m: return None
    v = int(m.group(1)); v = 75 if v >= 75 else v
    return -v if kat == "fed_snizhenie" else v

def zasedaniya():
    z = defaultdict(list)
    for f in glob.glob(str(LAB / "data/poly/istoriya/*.json")):
        d = json.load(open(f))
        if not d.get("kat", "").startswith("fed"): continue
        m = re.search(r"after (?:the )?([A-Z][a-z]+ \d{4}) meeting", d["vopros"])
        b = bps(d["vopros"], d["kat"])
        if not m or b is None or not d.get("ryad"): continue
        z[m.group(1)].append(dict(bps=b, ts=[int(x[0]) for x in d["ryad"]], p=[float(x[1]) for x in d["ryad"]],
                                  konec=d["konec"]))
    out = []
    for k, rs in z.items():
        konec = max(dt.datetime.fromisoformat(r["konec"].replace("Z", "+00:00")).timestamp() for r in rs)
        out.append(dict(imya=k, konec=int(konec), rynki=rs))
    return sorted(out, key=lambda x: x["konec"])

def E(zas, t):
    s = 0.0
    for r in zas["rynki"]:
        i = bisect.bisect_right(r["ts"], t) - 1
        if i < 0 or t - r["ts"][i] > 6 * H: return None      # нет свежей цены — индекс не определён
        s += r["p"][i] * r["bps"]
    return s

def sobytiya(porog_bps, dedup_ch=72, do_zasedaniya_ch=48, zasedaniy=2):
    """Сумма E по `zasedaniy` ближайшим заседаниям (каждое ≥ do_zasedaniya_ch впереди); ΔE за 24 ч на ТОМ ЖЕ наборе заседаний."""
    zs = zasedaniya(); ev = []; posl = -10**12
    t0 = min(min(r["ts"][0] for r in z["rynki"]) for z in zs) // H * H + 24 * H
    t1 = max(z["konec"] for z in zs)
    def Ek(t):
        bud = [z for z in zs if z["konec"] - t >= do_zasedaniya_ch * H][:zasedaniy]
        if len(bud) < zasedaniy: return None, None
        v = [E(z, t) for z in bud]
        return (None, None) if None in v else (sum(v), tuple(z["imya"] for z in bud))
    for t in range(t0, t1, H):
        a, ka = Ek(t); b, kb = Ek(t - 24 * H)
        if a is None or b is None or ka != kb: continue
        d = a - b
        if abs(d) >= porog_bps and t - posl >= dedup_ch * H:
            ev.append(dict(t_ms=(t + H) * 1000, simvol="BTCUSDT", znak=1 if d < 0 else -1, dE_bps=round(d, 2),
                           E_bps=round(a, 2), zasedaniya=list(ka)))
            posl = t
    return ev

if __name__ == "__main__":
    for T in (5, 10, 15, 20, 25):
        ev = sobytiya(T); g = defaultdict(int)
        for e in ev: g[dt.datetime.utcfromtimestamp(e["t_ms"] / 1000).year] += 1
        print(T, len(ev), dict(g), "смягч", sum(e["znak"] == 1 for e in ev), "ужест", sum(e["znak"] == -1 for e in ev))
