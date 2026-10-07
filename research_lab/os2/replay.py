#!/usr/bin/env python3
"""os2/replay.py — исторический прогон портфеля Trading OS v2 на СУЩЕСТВУЮЩЕМ роутере bot/strategy_priority_router.
Две руки при одинаковых капитале/риске/издержках/слотах: always_on (все ноги всегда) и routed (нога только в разрешённых
режимах REZHIM_V1). Различие ровно одно — regime_fit 1/0. Сделка = 1R риска; R потоков уже после издержек (orchestrator.simulate).
Запечатанное окно (ts ≥ 2025-10-01) читается ТОЛЬКО с final=True и хэшем замороженной политики.
    prognat(sdelki, metki_po_chasu, politika|None, okno=(s, po), slotov=12) -> dict"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT))
from bot.strategy_priority_router import StrategyCandidate, rank_candidates
SEALED = 1759276800000; H = 3600000

def hesh_politiki(p): return hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def prognat(sdelki, metki, politika=None, okno=(0, SEALED), slotov=12, final=False, hesh_zamka=None):
    s0, s1 = okno
    if s1 > SEALED and not (final and politika is not None and hesh_zamka == hesh_politiki(politika)):
        raise PermissionError("запечатанное окно: только final=True с хэшем замороженной политики")
    tr = sorted((t for t in sdelki if s0 <= t["ts"] < s1), key=lambda t: t["ts"])
    po_chasu = {}
    for i, t in enumerate(tr): po_chasu.setdefault(t["ts"] // H * H, []).append((i, t))
    otkr = []; vzyato = []; prichiny = {}
    for chas in sorted(po_chasu):
        otkr = [p for p in otkr if p[0] > chas]
        kand = []
        for i, t in po_chasu[chas]:
            rez = metki.get(chas)
            fit = 1.0 if politika is None else (1.0 if (rez is not None and rez in politika.get(t["leg"], ())) else 0.0)
            kand.append(StrategyCandidate(decision_id=f"{t['leg']}:{t['sym']}:{t['ts']}:{i}", ts=int(t["ts"]) // 1000, symbol=t["sym"],
                        strategy=t["leg"], side=t["side"], expected_net_r=1.0, regime_fit=fit, extra={"t": t}))
        res = rank_candidates(kand, now_ts=(int(chas) + H) // 1000, max_age_sec=2 * 3600, max_slots=slotov, max_same_side=slotov,
                              max_same_cluster=slotov, open_symbols=[p[1] for p in otkr], open_sides=[p[2] for p in otkr])
        for d in res:
            prichiny[d.reason] = prichiny.get(d.reason, 0) + 1
            if d.selected:
                t = d.candidate.extra["t"]; vzyato.append(t)
                otkr.append((t["ts"] + int(t.get("hours", 1)) * H, t["sym"].upper(), t["side"]))
    R = np.array([t["R"] for t in vzyato]) if vzyato else np.zeros(0)
    eq = np.cumsum(R) if len(R) else np.zeros(1)
    po_nogam = {}
    for t in vzyato:
        g = po_nogam.setdefault(t["leg"], [0, 0.0]); g[0] += 1; g[1] += t["R"]
    return dict(sdelok=int(len(R)), itogo_R=round(float(R.sum()), 3), na_sdelku_R=round(float(R.mean()), 4) if len(R) else None,
                prosadka_R=round(float((np.maximum.accumulate(eq) - eq).max()), 3), prichiny=prichiny,
                po_nogam={k: dict(sdelok=v[0], R=round(v[1], 3)) for k, v in po_nogam.items()})

def zagruzit_metki(put):
    d = json.loads(Path(put).read_text()); return {int(t): s for t, s in zip(d["ts"], d["s"])}
