#!/usr/bin/env python3
"""pump4_v2_vpered.py — судья вперёд PREREG_PUMP4_FILTR_ROST24_VPERED_2026_10_27 (28.10.2026, Claude). Хук сторожа, раз в сутки и только ночью
(01–05 UTC, Mac свободен; ~20–30 мин сети Bybit). Повторяет PUMP4 V1 без изменений (логика pump4_shirokaya.progon) на вселенной V1 (137) и
250 новых монетах только для сигналов с ts ≥ 2026-10-27 19:00 UTC; закрытые сделки дописываются в data/pump4_v2_vpered.jsonl один раз.
Сводка data/pump4_v2_vpered_svodka.json: отфильтрованные (rost24 ≥ 0.0599) против остальных, вклад к контролю, t по дням; вердикт с 30 отфильтрованных."""
import collections, json, math, statistics as st, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB.parent))
GRAN = 1793127600000; POROG = 0.0599
ZH, SV, SOST = LAB / "data" / "pump4_v2_vpered.jsonl", LAB / "data" / "pump4_v2_vpered_svodka.json", LAB / "data" / "pump4_v2_vpered_sost.json"

def svod(g):
    if not g: return dict(n=0)
    po = collections.defaultdict(list)
    for x in g: po[time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000))].append(x["R"] - (x["ctrl"] or 0))
    m = [st.mean(v) for v in po.values()]
    t = st.mean(m) / (st.stdev(m) / math.sqrt(len(m))) if len(m) > 2 and st.stdev(m) > 0 else None
    return dict(n=len(g), R=round(st.mean(x["R"] for x in g), 4), vklad=round(st.mean(x["R"] - (x["ctrl"] or 0) for x in g), 4), t_dni=round(t, 2) if t else None)

def prohod(sila=False):
    now = time.gmtime(); s = json.loads(SOST.read_text()) if SOST.exists() else {}
    den = time.strftime("%Y-%m-%d", now)
    if not sila and (s.get("den") == den or not 1 <= now.tm_hour <= 5): return {"status": "ne_seychas"}
    import pump4_shirokaya as PS, pump4_polnyy_povtor as PP
    PP.START = GRAN
    v1 = json.load(open(LAB / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    tk = PS.get("https://api.bybit.com/v5/market/tickers?category=linear")["result"]["list"]
    nov = [t["symbol"] for t in sorted(tk, key=lambda t: -float(t.get("turnover24h") or 0)) if t["symbol"].endswith("USDT") and t["symbol"] not in v1][:250]
    vse = PS.progon(v1, "V1") + PS.progon(nov, "NOVYE")
    bylo = {(r["sym"], r["ts"]) for r in map(json.loads, ZH.open())} if ZH.exists() else set()
    with ZH.open("a") as f:
        for x in vse:
            if (x["sym"], x["ts"]) not in bylo and x["ts"] >= GRAN: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    L = [json.loads(l) for l in ZH.open()] if ZH.exists() else []
    fil = [x for x in L if (x.get("rost24") or -1) >= POROG]; ost = [x for x in L if (x.get("rost24") or -1) < POROG]
    a, b = svod(fil), svod(ost)
    st_ = "NAKOPLENIE" if a["n"] < 30 else ("PASS" if a["R"] > 0 and a["R"] > b.get("R", -9) and a["vklad"] > 0 and (a["t_dni"] or 0) >= 2 else "FAIL")
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", now), vsego=len(L), filtr=a, ostalnye=b,
               po_vselennoy={v: svod([x for x in fil if x["vyborka"] == v]) for v in ("V1", "NOVYE")}, status=st_)
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1)); s["den"] = den; SOST.write_text(json.dumps(s))
    return dict(vsego=len(L), filtr=a["n"], status=st_)

if __name__ == "__main__":
    print(prohod(sila="--sila" in sys.argv))
