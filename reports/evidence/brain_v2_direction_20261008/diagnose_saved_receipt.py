#!/usr/bin/env python3
"""Aggregate the spent B3 receipt only. Never import/run its judge or streams."""
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "reports/evidence/alpaca_b3_gate_closure_20261008/B3_KVITANCIYA.json"
PIN = "4f36a1c0d3360967876c58908eef5b603ec501b34c43658c8344b08644d8a87e"


def diagnose():
    raw = (ROOT / SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != PIN:
        raise ValueError("BLOCKED_SOURCE: spent receipt hash changed")
    src = json.loads(raw, parse_float=Decimal)
    if src["verdikt"] != "B3_FAIL" or len(src["sgiby"]) != 4:
        raise ValueError("BLOCKED_SOURCE: unexpected receipt contract")
    legs = defaultdict(lambda: {a: {"selected": 0, "R": Decimal(0)} for a in "ABC"})
    reasons = {a: Counter() for a in "ABC"}
    counts = Counter()
    totals = {a: Decimal(0) for a in "ABC"}
    folds = []
    checks = []
    for fold in src["sgiby"]:
        populations = []
        row = {"window": fold["test"], "arms": {}, "policy_B": fold["politika_B"],
               "policy_C": fold["politika_C"]}
        for arm in "ABC":
            data = fold[arm]
            n = sum(x["sdelok"] for x in data["po_nogam"].values())
            if n != data["sdelok"] or data["prichiny"]["selected"] != n:
                raise ValueError("BLOCKED_RECEIPT: selected count does not reconcile")
            rounding_delta = sum((x["R"] for x in data["po_nogam"].values()), Decimal(0)) - data["itogo_R"]
            # Each independently rounded sleeve/arm total contributes <= 0.0005R.
            bound = Decimal("0.0005") * (len(data["po_nogam"]) + 1)
            if abs(rounding_delta) > bound:
                raise ValueError("BLOCKED_RECEIPT: sleeve totals exceed rounding bound")
            populations.append(sum(data["prichiny"].values()))
            counts[arm] += n
            totals[arm] += data["itogo_R"]
            reasons[arm].update(data["prichiny"])
            for leg, val in data["po_nogam"].items():
                legs[leg][arm]["selected"] += val["sdelok"]
                legs[leg][arm]["R"] += val["R"]
            row["arms"][arm] = {"selected": n, "R": data["itogo_R"],
                                 "reported_DD_R": data["prosadka_R"],
                                 "reason_counts": data["prichiny"],
                                 "sleeves": data["po_nogam"],
                                 "rounding_delta_R": rounding_delta}
        if len(set(populations)) != 1:
            raise ValueError("BLOCKED_RECEIPT: different per-fold opportunity counts")
        row["opportunities"] = populations[0]
        row["delta_B_minus_A_R"] = fold["B"]["itogo_R"] - fold["A"]["itogo_R"]
        row["delta_C_minus_B_R"] = fold["C"]["itogo_R"] - fold["B"]["itogo_R"]
        folds.append(row)
    for arm in "ABC":
        if totals[arm] != src["summa_R"][arm]:
            raise ValueError("BLOCKED_RECEIPT: fold sum does not match arm total")
        checks.append(f"{arm}: selected/fold-total/reason-population/rounding reconciliation PASS")
    c_ge_b = sum(f["C"]["itogo_R"] >= f["B"]["itogo_R"] for f in src["sgiby"])
    if c_ge_b != src["C_ge_B_sgibov"]:
        raise ValueError("BLOCKED_RECEIPT: frozen fold criterion mismatch")
    sums = {a: {"selected": counts[a], "R": totals[a],
                "reported_DD_R": src["maks_prosadka_R"][a],
                "reason_counts": dict(sorted(reasons[a].items()))} for a in "ABC"}
    return {
        "status": "SAVED_RECEIPT_DIAGNOSIS_ONLY", "source": SOURCE, "sha256": PIN,
        "source_verdict": src["verdikt"], "source_observed_at": src["kogda"],
        "all_input_trades_reported": src["sdelok_vsego"],
        "test_opportunities": sum(f["opportunities"] for f in folds),
        "arms": sums, "sleeves": dict(sorted(legs.items())), "folds": folds,
        "deltas_R": {"B_minus_A": totals["B"] - totals["A"],
                     "C_minus_B": totals["C"] - totals["B"],
                     "C_minus_A": totals["C"] - totals["A"]},
        "criteria_from_saved_totals": {"C_gt_A": totals["C"] > totals["A"],
            "C_gt_B": totals["C"] > totals["B"], "C_ge_B_folds": c_ge_b,
            "required_folds": 3,
            "C_DD_le_1_2_A": src["maks_prosadka_R"]["C"] <= Decimal("1.2") * src["maks_prosadka_R"]["A"]},
        "not_identifiable_from_receipt": ["rejected_winner_events", "accepted_loser_events",
            "selected_R_by_regime", "slot_hours", "event_counterfactual_opportunity_cost",
            "diversification_correlation", "USD_margin_MTM_equity"],
        "interpretation_guard": "Arm selected sets are not nested; aggregate differences are not rejected-winner PnL.",
        "checks": checks,
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2,
                     default=lambda x: format(x, "f") if isinstance(x, Decimal) else str(x)))
