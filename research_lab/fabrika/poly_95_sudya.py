#!/usr/bin/env python3
"""poly_95_sudya.py — судья PREREG_POLY_95_VPERED_2026_10_28 (28.10.2026, Claude). Хук сторожа, только чтение data/poly_monitor/*.jsonl.
Сделка: первая минута, когда середина стороны ≥ 0.95 при наблюдении ≥ 5 мин до неё; покупка по ask (≤ 0.985); до расчёта; комиссия rate × (1 − цена).
Только рынки, вышедшие с исходом после 2026-10-28 06:30 UTC. Вердикт при ≥ 150 сделок. Выход data/poly_95_svodka.json."""
import collections, datetime as dt, json, math, statistics as st, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; M = LAB / "data" / "poly_monitor"; OUT = LAB / "data" / "poly_95_svodka.json"
OT = dt.datetime(2026, 10, 28, 6, 30, tzinfo=dt.timezone.utc); MIN_N = 150

def prohod():
    if not (M / "knigi.jsonl").exists(): return {"status": "net_monitora"}
    kn = collections.defaultdict(list)
    for l in (M / "knigi.jsonl").open(): z = json.loads(l); kn[z["id"]].append(z)
    ish, vop = {}, {}
    for l in (M / "rynki.jsonl").open():
        z = json.loads(l)
        if z["sob"] == "dobavlen": vop[z["id"]] = z.get("vopros", "")
        if z["sob"] == "vybyl" and z.get("closed") and dt.datetime.fromisoformat(z["t"]) >= OT:
            try: pr = json.loads(z["outcomePrices"]) if isinstance(z["outcomePrices"], str) else z["outcomePrices"]; ish[z["id"]] = 1 if str(pr[0]) == "1" else 0
            except Exception: pass
    sd = []
    for i, y in ish.items():
        r = sorted(kn.get(i, []), key=lambda z: z["t"])
        if not r: continue
        for z in r:
            if z["bid"] is None or z["ask"] is None: continue
            mid = (z["bid"] + z["ask"]) / 2; side = 1 if mid >= 0.95 else (0 if mid <= 0.05 else None)
            if side is None: continue
            if z["t"] - r[0]["t"] < 300: break
            ask = z["ask"] if side == 1 else 1 - z["bid"]
            if ask > 0.985: break
            q = vop.get(i, "").lower(); rate = 0.04 if any(w in q for w in ("elect", "president", "senate", "governor", "party")) else 0.05
            win = side == y; sd.append(dict(id=i, cena=ask, win=win, dohod=(1 if win else 0) / ask - 1 - rate * (1 - ask),
                                            glubina=z["gl_ask"] if side == 1 else z["gl_bid"]))
            break
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), sdelok=len(sd), proigryshey=sum(not x["win"] for x in sd))
    if sd:
        d = [x["dohod"] for x in sd]; m = st.mean(d); t = m / (st.stdev(d) / math.sqrt(len(d))) if len(d) > 2 and st.stdev(d) > 0 else None
        cena = st.mean(x["cena"] for x in sd)
        out.update(sred_dohod=round(m, 4), t=round(t, 2) if t else None, sred_cena=round(cena, 4), glubina_med=sorted(x["glubina"] or 0 for x in sd)[len(sd) // 2])
        ok = len(sd) >= MIN_N and m > 0 and (t or 0) >= 2 and out["proigryshey"] / len(sd) < 1 - cena
        out["status"] = "NAKOPLENIE" if len(sd) < MIN_N else ("PASS_V_TEN" if ok else "FAIL")
    else: out["status"] = "NAKOPLENIE"
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out

if __name__ == "__main__":
    print(prohod())
