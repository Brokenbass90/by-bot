#!/usr/bin/env python3
"""ETF_OBEM_UCHASTIE — измерения БЕЗ доходностей BTC (17.10.2026). Критерии зафиксированы здесь ДО расчёта.

obem_t = долларовый объём IBIT (v × vw) / медиана 20 ПРОШЛЫХ сессий; событие: obem ≥ 2.0, знак = знак дневного хода IBIT
(close/open − 1) — участие институционалов в направлении дня.
И1 (содержание): Spearman ρ(log obem_t, |поток Farside_t+1|) > 0, p < 0.01.
И2 (независимость от ETF_PREMIYA): доля событий ОБЪЁМА, совпавших по дню с событиями ETF_PREMIYA_BTC, < 50 %.
И3 (число): событий ≥ 30 в периоде с BTC-барами (≤ 2026-08-10).
"""
import json, glob, sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import etf_premiya_izmereniya as M
LAB = M.LAB

def main():
    rows = {}
    for f in sorted(glob.glob(str(LAB / "data/akcii_grouped/20*.json"))):
        d = json.load(open(f)); r = [x for x in d["rows"] if x[0] == "IBIT"]
        if r and r[0][5] and r[0][6]: rows[d["date"]] = r[0]
    dni = sorted(rows); obem = {}
    for i, d in enumerate(dni):
        if i < 20: continue
        dv = rows[d][5] * rows[d][6]; med = float(np.median([rows[x][5] * rows[x][6] for x in dni[i - 20:i]]))
        obem[d] = dv / med
    potok = {r["date"]: abs(r["last_total_musd"]) for r in json.load(open(LAB / "data/etf_potoki/btc.json")) if r.get("last_total_musd") is not None}
    dp = sorted(potok); x, y = [], []
    for d, v in obem.items():
        nxt = [q for q in dp if q > d][:1]
        if nxt: x.append(np.log(v)); y.append(potok[nxt[0]])
    rho, p = M.spearmanr(x, y)
    ev = {d for d, v in obem.items() if v >= 2.0 and d <= "2026-08-10"}
    prem = {e["den"] for e in json.load(open(LAB / "data/etf_premiya/sobytiya_IBIT_v1_detali.json"))}
    sovp = len(ev & prem) / len(ev) if ev else 1.0
    rez = dict(I1_rho=round(float(rho), 3), I1_p=float(p), I1=bool(rho > 0 and p < 0.01), I2_sovpadenie=round(sovp, 3),
               I2=bool(sovp < 0.5), I3_sobytiy=len(ev), I3=bool(len(ev) >= 30), par=len(x))
    (LAB / "data/etf_premiya/IZMERENIYA_OBEM.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(rez)

if __name__ == "__main__":
    main()
