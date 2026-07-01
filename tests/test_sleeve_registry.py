"""Tests for bot.sleeve_registry — (strategy x side) as the atomic unit."""
from bot.sleeve_registry import (sleeve_id, group_by_sleeve, sleeve_health,
                                 SleeveRegistry, Sleeve)
from bot.decision_bus import build_decision, attach_outcome


def _recs():
    recs = []
    for rm in [2.5, -1, 2.5, -1, -1] * 4:            # long healthy-ish
        r = build_decision(ts=1, symbol="X", strategy="arf2", side="long", decision="enter")
        attach_outcome(r, filled=True, r_multiple=rm); recs.append(r.to_dict())
    for rm in [-1, -1, -1, 0.5, -1] * 4:             # short losing
        r = build_decision(ts=1, symbol="X", strategy="arf2", side="short", decision="enter")
        attach_outcome(r, filled=True, r_multiple=rm); recs.append(r.to_dict())
    return recs


def test_sleeve_id_format():
    assert sleeve_id("arf2", "Short") == "arf2:short"


def test_group_splits_sides():
    g = group_by_sleeve(_recs())
    assert set(g) == {"arf2:long", "arf2:short"}
    assert len(g["arf2:long"]) == 20 and len(g["arf2:short"]) == 20


def test_side_specific_health_diverges():
    h = sleeve_health(_recs(), baselines={"arf2:long": 0.4, "arf2:short": 0.4},
                      min_trades=15, max_dd_R=8)
    assert h["arf2:long"].status == "healthy"
    assert h["arf2:short"].status == "halt"          # losing short caught separately


def test_register_bidirectional_makes_two_sleeves():
    reg = SleeveRegistry()
    sleeves = reg.register_bidirectional("arf2")
    assert len(sleeves) == 2
    assert reg.get("arf2", "long") and reg.get("arf2", "short")


def test_set_risk_and_live_sleeves():
    reg = SleeveRegistry()
    reg.register_bidirectional("arf2")
    reg.set_risk("arf2", "long", 0.1)
    live = reg.live_sleeves()
    assert [s.sleeve_id for s in live] == ["arf2:long"]
    assert isinstance(live[0], Sleeve)


def test_apply_lifecycle_demotes_bad_side_only():
    reg = SleeveRegistry()
    reg.register("arf2", "long", stage="canary", risk_mult=0.1)
    reg.register("arf2", "short", stage="canary", risk_mult=0.1)
    tr = reg.apply_lifecycle(_recs(), baselines={"arf2:long": 0.4, "arf2:short": 0.4},
                             canary_min_trades=15, max_dd_R=8)
    assert tr["arf2:short"].to_stage == "demoted"
    assert reg.get("arf2", "short").risk_mult == 0.0   # demoted side risk zeroed
    assert reg.get("arf2", "long").risk_mult == 0.1    # good side untouched
