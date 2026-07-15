from bot.deepseek_overlay import _snapshot_truth_gate


def test_snapshot_truth_gate_requires_explicit_fresh_authority() -> None:
    ok, blockers = _snapshot_truth_gate({"ai_full_context": {}})

    assert ok is False
    assert blockers == ["critical_live_truth_missing_or_unverified"]


def test_snapshot_truth_gate_accepts_reviewed_live_truth() -> None:
    ok, blockers = _snapshot_truth_gate(
        {
            "ai_full_context": {
                "critical_truth_assessment": {
                    "control_recommendations_allowed": True,
                    "blockers": [],
                }
            }
        }
    )

    assert ok is True
    assert blockers == []
