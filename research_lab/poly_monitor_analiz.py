#!/usr/bin/env python3
"""poly_monitor_analiz.py — разбор живого монитора Polymarket (27.10.2026, Claude). Только чтение data/poly_monitor/*.jsonl.
По каждому рынку, который выбыл с известным исходом: T95 — первая минута, когда середина победившей стороны ≥ 0.95;
дальше — сколько минут после T95 её ask был ≤ 0.97 и ≤ 0.98, и сколько $ стояло в стакане (глубина в 2 ¢) — это реальное окно покупки
«почти решённого» исхода. Плюс заголовки за 3 ч до T95 (первоисточник опередил цену или нет). Рынки без исхода — счётчик.
    python3 research_lab/poly_monitor_analiz.py"""
import collections, datetime as dt, json
from pathlib import Path
M = Path(__file__).resolve().parent / "data" / "poly_monitor"

def main():
    kn = collections.defaultdict(list)
    for l in (M / "knigi.jsonl").open(): z = json.loads(l); kn[z["id"]].append(z)
    nov = collections.defaultdict(list)
    for l in (M / "novosti.jsonl").open(): z = json.loads(l); nov[z["id"]].append(z)
    vop, ish = {}, {}
    for l in (M / "rynki.jsonl").open():
        z = json.loads(l)
        if z["sob"] == "dobavlen": vop[z["id"]] = z["vopros"]
        elif z["sob"] == "vybyl" and z.get("closed"):
            try: pr = json.loads(z["outcomePrices"]) if isinstance(z["outcomePrices"], str) else z["outcomePrices"]; ish[z["id"]] = 1 if str(pr[0]) == "1" else 0
            except Exception: pass
    out = []
    for i, y in ish.items():
        r = sorted(kn.get(i, []), key=lambda z: z["t"])
        def storona(z):
            if z["bid"] is None or z["ask"] is None: return None, None
            if y == 1: return (z["bid"] + z["ask"]) / 2, z["ask"]
            return 1 - (z["bid"] + z["ask"]) / 2, 1 - z["bid"]            # ask NO = 1 − bid YES
        t95 = next((z["t"] for z in r if (storona(z)[0] or 0) >= 0.95), None)
        if t95 is None: out.append(dict(id=i, vopros=vop.get(i, "")[:70], T95=None)); continue
        posle = [z for z in r if z["t"] >= t95]
        def okno(p):
            ts = [z["t"] for z in posle if (storona(z)[1] or 1) <= p]
            return round((max(ts) - t95) / 60, 1) if ts else 0.0
        gl = [z["gl_bid"] if y == 0 else z["gl_ask"] for z in posle[:30]]
        n3 = [n for n in nov.get(i, []) if n.get("pub") and t95 - 3 * 3600 <= dt.datetime.fromisoformat(n["pub"]).timestamp() <= t95]
        out.append(dict(id=i, vopros=vop.get(i, "")[:70], ishod=y, T95=dt.datetime.fromtimestamp(t95, dt.timezone.utc).isoformat(timespec="minutes"),
                        min_ask_le_097=okno(0.97), min_ask_le_098=okno(0.98), glubina_usd_med=sorted(gl)[len(gl) // 2] if gl else None,
                        novostey_za_3ch_do=len(n3), pervaya=n3[-1]["zagolovok"][:90] if n3 else None))
    print(json.dumps(dict(rynkov_v_monitore=len(vop), s_ishodom=len(ish), s_T95=sum(1 for o in out if o.get("T95")), rynki=out), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
