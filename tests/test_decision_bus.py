"""Tests for bot.decision_bus — uniform AI-legible decision records + summary."""
import os
import tempfile

from bot.decision_bus import build_decision, attach_outcome, DecisionBus, summarize, DecisionRecord


def test_build_from_partial_states_is_serializable():
    rec = build_decision(ts=1, symbol="linkusdt", strategy="irv4", side="long",
                         decision="enter", reason="A",
                         range_state={"is_range": True, "regime": "flat", "votes": 3},
                         retest={"entry_ok": True, "quality": 0.7},
                         extra={"funding": 0.0001})
    assert isinstance(rec, DecisionRecord)
    assert rec.symbol == "LINKUSDT"
    assert rec.context["range"]["regime"] == "flat"
    assert rec.context["retest"]["quality"] == 0.7
    assert rec.context["funding"] == 0.0001
    assert isinstance(rec.to_json(), str)


def test_missing_states_do_not_crash():
    rec = build_decision(ts=1, symbol="X", strategy="s", side="short", decision="skip")
    assert rec.context == {} and rec.plan == {}


def test_plan_extracted_from_entry_plan():
    entry = {"limit_price": 100.0, "stop": 99.0, "tp1": 101.0, "tp2": 102.5, "rr2": 2.5}
    rec = build_decision(ts=1, symbol="X", strategy="s", side="long", decision="enter", entry=entry)
    assert rec.plan["entry"] == 100.0 and rec.plan["rr2"] == 2.5


def test_attach_outcome():
    rec = build_decision(ts=1, symbol="X", strategy="s", side="long", decision="enter")
    attach_outcome(rec, filled=True, r_multiple=2.5, exit_reason="tp2")
    assert rec.outcome["filled"] is True and rec.outcome["r_multiple"] == 2.5


def test_jsonl_roundtrip():
    path = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False).name
    try:
        bus = DecisionBus(path)
        r = build_decision(ts=1, symbol="X", strategy="s", side="long", decision="enter")
        attach_outcome(r, filled=True, r_multiple=1.0)
        bus.append(r)
        got = bus.read()
        assert len(got) == 1 and got[0]["strategy"] == "s"
    finally:
        os.unlink(path)


def test_read_missing_file_is_empty():
    bus = DecisionBus("/tmp/definitely_missing_bus_file_xyz.jsonl")
    assert bus.read() == []


def test_summarize_expectancy_with_asymmetric_rr():
    recs = []
    # 8 wins at +2.5R, 12 losses at -1R -> WR 40% but positive expectancy
    for i in range(8):
        r = build_decision(ts=i, symbol="X", strategy="sf", side="short", decision="enter")
        attach_outcome(r, filled=True, r_multiple=2.5)
        recs.append(r.to_dict())
    for i in range(12):
        r = build_decision(ts=100 + i, symbol="X", strategy="sf", side="short", decision="enter")
        attach_outcome(r, filled=True, r_multiple=-1.0)
        recs.append(r.to_dict())
    recs.append(build_decision(ts=999, symbol="X", strategy="sf", side="short", decision="skip").to_dict())
    s = summarize(recs)
    g = s["groups"]["sf"]
    assert g["n"] == 20 and g["wins"] == 8
    assert abs(g["win_rate"] - 0.4) < 1e-9
    assert abs(g["expectancy_R"] - 0.4) < 1e-9      # (8*2.5 - 12*1)/20 = 0.4
    assert s["skips"] == 1


def test_summarize_groups_by_regime():
    recs = []
    for reg, rm in [("flat", 2.0), ("flat", -1.0), ("ascending", 1.0)]:
        r = build_decision(ts=1, symbol="X", strategy="s", side="long", decision="enter",
                           range_state={"regime": reg})
        attach_outcome(r, filled=True, r_multiple=rm)
        recs.append(r.to_dict())
    s = summarize(recs, by="regime")
    assert "flat" in s["groups"] and "ascending" in s["groups"]
    assert s["groups"]["flat"]["n"] == 2
