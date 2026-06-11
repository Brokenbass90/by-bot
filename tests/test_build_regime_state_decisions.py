import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import build_regime_state as brs  # noqa: E402


def test_bear_chop_disables_att1_longs_and_legacy_breakdown():
    decision = brs._REGIME_DECISIONS[brs.REGIME_BEAR_CHOP]
    overrides = decision["overrides"]

    assert overrides["ENABLE_ATT1_TRADING"] == "1"
    assert overrides["ATT1_ALLOW_LONGS"] == "0"
    assert overrides["ATT1_ALLOW_SHORTS"] == "1"
    assert overrides["ENABLE_BREAKDOWN_TRADING"] == "0"


def test_bear_chop_notes_match_risk_policy():
    notes = " ".join(brs._REGIME_DECISIONS[brs.REGIME_BEAR_CHOP]["notes"])

    assert "ATT1 short-only" in notes
    assert "legacy BD1 off" in notes
