#!/usr/bin/env python3
"""brain_metriki.py — сравнение политик Brain Shadow при одинаковых возможностях/капитале/исполнении/ограничениях (15.10.2026).

Считаются ТОЛЬКО причинные записи: возможность не late, решение записано не позже t_available + LAG, исход прикреплён.
Доход политики в день = Σ allocation_units × realized_net_bps по исходам, закрывшимся в этот день (единица риска = 1 позиция ноги).
Метрики: net (bps·ед.), MaxDD, CVaR95 (дневной), Sortino, Calmar, recovery (дней под водой, максимум), turnover (Σ ед.), издержки.
Пока исходов < MIN_ISHODOV у любой политики — статус NEDOSTATOCHNO, сравнения нет (без подглядывания в частичное).
"""
import json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import opportunity_v2 as V2                    # noqa: E402

MIN_ISHODOV = 30
DEN = 86_400_000


def metriki(dnevnye):
    x = np.asarray(dnevnye, float)
    if len(x) == 0: return {}
    kum = np.cumsum(x); pik = np.maximum.accumulate(np.concatenate([[0.0], kum]))[1:]; dd = pik - kum
    maxdd = float(dd.max()); pod_vodoy, tek = 0, 0
    for v in dd:
        tek = tek + 1 if v > 1e-12 else 0; pod_vodoy = max(pod_vodoy, tek)
    hvost = np.sort(x)[:max(1, int(math.ceil(0.05 * len(x))))]
    vniz = x[x < 0]; sd_vniz = float(np.sqrt(np.mean(vniz ** 2))) if len(vniz) else 0.0
    god = float(x.mean() * 365)
    return dict(dney=int(len(x)), net=float(x.sum()), sredniy_den=float(x.mean()), maxdd=maxdd, cvar95=float(hvost.mean()),
                sortino=float(x.mean() / sd_vniz * math.sqrt(365)) if sd_vniz > 0 else None,
                calmar=float(god / maxdd) if maxdd > 0 else None, recovery_dney_max=int(pod_vodoy))


def sravnit(papka):
    hr = V2.Hranilishche(papka)
    opp = {z["opp_id"]: z for z in hr.opp.zapisi if not z["late"]}
    po_politike = defaultdict(lambda: defaultdict(float)); n_ish = defaultdict(int); oborot = defaultdict(float); izd = defaultdict(float)
    for d in hr.dec.zapisi:
        o = opp.get(d["opp_id"]); ish = hr.ishody.get(d["opp_id"])
        if o is None or d["t_recorded_ms"] > o["t_available_ms"] + V2.LAG_MS: continue
        oborot[d["policy"]] += d["allocation_units"]
        if ish is None or ish["realized_net_bps"] == V2.UNKNOWN: continue
        den = ish["t_outcome_ms"] // DEN
        po_politike[d["policy"]][den] += d["allocation_units"] * ish["realized_net_bps"]; n_ish[d["policy"]] += 1
        z = [o[k] for k in ("cost_fee_bps", "cost_spread_bps", "cost_slip_bps", "cost_funding_bps")]
        if V2.UNKNOWN not in z: izd[d["policy"]] += d["allocation_units"] * sum(z)
    politiki = sorted(set(oborot) | set(n_ish))
    if not politiki or min(n_ish.get(p, 0) for p in politiki) < MIN_ISHODOV:
        return dict(status="NEDOSTATOCHNO", ishodov={p: n_ish.get(p, 0) for p in politiki}, min_ishodov=MIN_ISHODOV,
                    oborot={p: round(oborot[p], 3) for p in politiki})
    dni = sorted(set().union(*[set(po_politike[p]) for p in politiki]))
    return dict(status="SRAVNENIE", **{p: dict(metriki([po_politike[p].get(x, 0.0) for x in range(dni[0], dni[-1] + 1)]),
                                                ishodov=n_ish[p], oborot=round(oborot[p], 3), izderzhki_bps=round(izd[p], 3))
                                       for p in politiki})


if __name__ == "__main__":
    print(json.dumps(sravnit(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "data" / "brain_shadow_v1"), ensure_ascii=False, indent=1))
