#!/usr/bin/env python3
"""brain_povtor.py — детерминированный повтор политик Brain с одинакового старта (PREREG_BRAIN_V2_DET_V1_2_2026_10_17).

Все политики из brain_shadow_v1.POLITIKI получают ОДИН поток записанных возможностей с t_decision_ms ≥ T0,
стартуют с ПУСТОГО портфеля, проходят через ОДИН risk_engine (RISK одинаковый) и одно правило причинности.
Исходы не читаются: из записи берутся только поля решения (POLYA_RESHENIYA). Живой decisions.jsonl не используется.

    python3 research_lab/factory_v3/brain_povtor.py                 # T0 по prereg, печать сводки решений
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import brain_shadow_v1 as B                                    # noqa: E402

T0_MS = int(dt.datetime(2026, 10, 31, 14, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
POLYA_RESHENIYA = ("opp_id", "t_decision_ms", "t_available_ms", "t_observation_ms", "late", "horizon_ms", "sleeve", "symbol",
                   "side", "mechanism", "prior_status", "exp_net_bps", "uncertainty_bps", "cost_fee_bps", "cost_spread_bps",
                   "cost_slip_bps", "cost_funding_bps", "context", "features")


def ochistit(z):
    return {k: z[k] for k in POLYA_RESHENIYA if k in z}


def povtor(zapisi, t0_ms=T0_MS, politiki=None):
    """→ {policy: [(opp_id, units, ogranicheniya)]}. Старт: пустой портфель у всех политик в t0."""
    politiki = politiki or B.POLITIKI
    potok = sorted((ochistit(z) for z in zapisi if z["t_decision_ms"] >= t0_ms),
                   key=lambda v: (v["t_decision_ms"], v["sleeve"], v["symbol"], v["opp_id"]))
    otkr = {p: [] for p in politiki}; out = {p: [] for p in politiki}
    for v in potok:
        t = v["t_decision_ms"]
        for p, f in politiki.items():
            otkr[p] = [(o, a) for o, a in otkr[p] if o["t_decision_ms"] + o["horizon_ms"] > t]
            zh, o1 = (f(v, otkr[p]) if B.prichinno(v) else (0.0, ["ne_prichinno"]))
            u, o2 = B.risk_engine(v, zh, otkr[p])
            out[p].append((v["opp_id"], u, o1 + o2))
            if u > 0: otkr[p].append((v, u))
    return out


def kod_sha():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(B.__file__).read_bytes()
                          + (HERE / "brain_v2.py").read_bytes()).hexdigest()[:16]


if __name__ == "__main__":
    z = [json.loads(s) for s in (B.PAPKA / "opportunities.jsonl").read_text().splitlines() if s.strip()]
    r = povtor(z)
    print(json.dumps(dict(kod_sha=kod_sha(), t0_ms=T0_MS, vozmozhnostey=len(next(iter(r.values()))),
                          po_politikam={p: dict(vzyato=sum(1 for _, u, _ in d if u > 0), edinic=round(sum(u for _, u, _ in d), 3))
                                        for p, d in r.items()}), ensure_ascii=False))
