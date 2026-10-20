#!/usr/bin/env python3
"""brain_pump4_noga.py — теневая нога PUMP4 в Brain: ТОЛЬКО измерение портфельного риска (20.10.2026, PM «PUMP4 V1 TO TINY»).
Прав над LIVE, ордерами и риском нет. Замороженные политики brain_shadow_v1 не меняются (это отдельный измеритель).

Входы: последний пересчёт PUMP4 (`results/pump4_pereschet_*.json`: решения, выходы), тени шорт-ног ETS2S (`data/ten_ETS2S.jsonl`)
и ATT1 (`data/ten_ATT1.jsonl`). Выход: `data/brain_shadow_v1/pump4_noga.json` (перезаписывается, производный).
Меры: одновременно открытые шорты PUMP4 (максимум, медиана, доля часов с ≥ 5), сколько решений PUMP4 пришлось на часы с уже
открытыми ≥ 5 (их бы отрезал лимит 5), совпадения с ETS2S/ATT1 по той же монете в ±24 ч (двойной шорт одной монеты),
средний R решений в «толпе» (≥ 5 открытых) против остальных — описательно, не правило."""
import glob, json, statistics as st
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
H = 3_600_000
OUT = D / "brain_shadow_v1" / "pump4_noga.json"


def _jl(p):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def prohod():
    fs = sorted(glob.glob(str(LAB / "results" / "pump4_pereschet_*.json")))
    if not fs:
        return {"status": "NET_PERESCHETA"}
    rez = json.loads(Path(fs[-1]).read_text())["resheniya"]
    pos = [(x["ts"] + H, x["ts"] + H * (2 + (x.get("barov") if x.get("barov") is not None else 168)), x) for x in rez
           if x.get("status") in ("ZAKRYTA", "OTKRYTA")]
    if not pos:
        return {"status": "PUSTO"}
    t0, t1 = min(p[0] for p in pos), max(p[1] for p in pos)
    chasy = []
    for t in range(t0 - t0 % H, t1, H):
        chasy.append(sum(1 for a, b, _ in pos if a <= t < b))
    tolpa_r, ostalnye_r, v_tolpe = [], [], 0
    for a, b, x in pos:
        otkr = sum(1 for a2, b2, _ in pos if a2 < a <= b2 - 1 and a2 != a)
        if otkr >= 5:
            v_tolpe += 1
            if x.get("R") is not None: tolpa_r.append(x["R"])
        elif x.get("R") is not None:
            ostalnye_r.append(x["R"])
    drugie = {}
    for imya in ("ten_ETS2S", "ten_ATT1"):
        sig = [(z["sym"], z["ts"]) for z in _jl(D / f"{imya}.jsonl") if z.get("side") == "short"]
        po = {}
        for s, t in sig: po.setdefault(s, []).append(t)
        drugie[imya] = sum(1 for _, _, x in pos if any(abs(t - x["ts"]) <= 24 * H for t in po.get(x["sym"], [])))
    out = {"istochnik": Path(fs[-1]).name, "resheniy": len(pos),
           "odnovremenno_max": max(chasy), "odnovremenno_mediana": st.median(chasy),
           "dolya_chasov_ge5": round(sum(c >= 5 for c in chasy) / len(chasy), 3),
           "resheniy_pri_ge5_otkrytyh": v_tolpe,
           "sredniy_R_v_tolpe": round(st.mean(tolpa_r), 4) if tolpa_r else None, "n_tolpa": len(tolpa_r),
           "sredniy_R_ostalnye": round(st.mean(ostalnye_r), 4) if ostalnye_r else None, "n_ostalnye": len(ostalnye_r),
           "sovpadeniy_ta_zhe_moneta_24ch": drugie,
           "prava": "только измерение; LIVE/ордера/риск не меняет"}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False, indent=1))
