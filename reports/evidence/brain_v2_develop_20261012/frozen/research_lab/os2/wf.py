#!/usr/bin/env python3
"""B3: walk-forward ORCHESTRATOR_V1 по замороженному os2/B3_KONFIG.json (sha256 в квитанции). Один прогон: после квитанции отказ.
Три руки (A always_on / B leg_filter / C routed) на существующем роутере через os2/replay.prognat."""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np
OS2 = Path(__file__).resolve().parent; LAB = OS2.parent
sys.path.insert(0, str(OS2))
import replay as P, rezhim_v1 as RV
KONF = OS2 / "B3_KONFIG.json"; KV = OS2 / "B3_KVITANCIYA.json"
def ms(s): return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)

def potoki(konf):
    tr = []
    orch = json.loads((LAB / "orch_signals.json").read_text())
    for leg, src in konf["nogi"].items():
        if src.startswith("orch_signals"):
            tr += [dict(t) for t in orch if t["leg"] == leg]
        else:
            p = LAB / src
            if not p.exists(): raise FileNotFoundError(f"нет потока {leg}: {p} — B3 BLOCKED_DATA")
            tr += [dict(t, leg=leg) for t in json.loads(p.read_text())]
    return [t for t in tr if t["ts"] < P.SEALED]

def metki_v1():
    d = np.load(LAB / "data/h1/BTCUSDT.npz"); ts = d["ts"].astype(np.int64); o = d["ohlcv"].astype(float)
    m = ts < P.SEALED; s = RV.metki(ts[m], o[m])
    return {int(t) + P.H: x for t, x in zip(ts[m], s)}   # состояние, известное к началу следующего часа

def vyhod(t): return t["ts"] + (int(t.get("hours", 1)) + 1) * P.H   # вход на следующем баре + удержание

def nepreryvnaya_prosadka(R):
    eq = np.concatenate([[0.0], np.cumsum(R)]); return round(float((np.maximum.accumulate(eq) - eq).max()), 3)

def srodstvo(tr, metki, s0, s1, min_n=30):
    po = {}
    for t in tr:
        if s0 <= t["ts"] and vyhod(t) <= s1:          # A1: только исходы, известные к концу train
            st = metki.get(t["ts"] // P.H * P.H)
            if st is not None: po.setdefault(t["leg"], {}).setdefault(st, []).append(t["R"])
    return {leg: sorted(s for s, r in d.items() if len(r) >= min_n and np.mean(r) > 0) for leg, d in po.items()}

def filtr_nog(tr, s0, s1, min_n=30):
    po = {}
    for t in tr:
        if s0 <= t["ts"] and vyhod(t) <= s1: po.setdefault(t["leg"], []).append(t["R"])
    return {leg: list(RV.SOSTOYANIYA) for leg, r in po.items() if len(r) >= min_n and np.mean(r) > 0}

def prognat(tr, metki, konf):
    sg = []
    for a, b, c in konf["sgiby"]:
        s0, s1, s2 = ms(a), ms(b), ms(c)
        pol_b = filtr_nog(tr, s0, s1); pol_c = srodstvo(tr, metki, s0, s1)
        r = {k: P.prognat(tr, metki, pol, okno=(s1, s2), slotov=konf["slotov"])
             for k, pol in (("A", None), ("B", pol_b), ("C", pol_c))}
        sg.append(dict(test=[b, c], politika_B=pol_b, politika_C=pol_c, **r))
    sum_ = {k: round(sum(s[k]["itogo_R"] for s in sg), 3) for k in "ABC"}
    dd = {k: nepreryvnaya_prosadka([x for s in sg for x in s[k]["R_posledovatelno"]]) for k in "ABC"}   # A1: сквозная просадка
    c_ge_b = sum(1 for s in sg if s["C"]["itogo_R"] >= s["B"]["itogo_R"])
    ok = sum_["C"] > sum_["A"] and sum_["C"] > sum_["B"] and c_ge_b >= 3 and dd["C"] <= 1.2 * dd["A"]
    return dict(sgiby=sg, summa_R=sum_, maks_prosadka_R=dd, C_ge_B_sgibov=c_ge_b, verdikt="B3_PASS" if ok else "B3_FAIL")

def main():
    if KV.exists(): sys.exit("квитанция B3 уже есть — повтор запрещён")
    if not RV.proverit(): sys.exit("замок REZHIM_V1 не сходится — BLOCKED_IMPLEMENTATION")
    konf_b = KONF.read_bytes(); konf = json.loads(konf_b); tr = potoki(konf)
    res = prognat(tr, metki_v1(), konf)
    res.update(konfig_sha256=hashlib.sha256(konf_b).hexdigest(), sdelok_vsego=len(tr),
               kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    for s_ in res["sgiby"]:
        for k in "ABC": s_[k].pop("R_posledovatelno", None)
    KV.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "sgiby"}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
