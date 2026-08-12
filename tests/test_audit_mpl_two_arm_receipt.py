from scripts.audit_mpl_two_arm_receipt import expected_arm_verdict, expected_choice


def test_expected_arm_verdict_is_fail_closed():
    assert expected_arm_verdict({"death_gates": {"a": False}, "acceptance_gates": {}}) == "REJECT"
    assert expected_arm_verdict({"death_gates": {"a": True}, "acceptance_gates": {"b": False}}) == "NO_PROMOTION"
    assert expected_arm_verdict({"death_gates": {"a": True}, "acceptance_gates": {"b": True}}) == "SHADOW_CANDIDATE_ONLY"


def test_expected_choice_prefers_preregistered_primary():
    passed = {"verdict": "SHADOW_CANDIDATE_ONLY"}
    rejected = {"verdict": "REJECT"}
    assert expected_choice({"V4_stop_x2.0": passed, "V3_stop_x1.0": passed}) == "V4"
    assert expected_choice({"V4_stop_x2.0": rejected, "V3_stop_x1.0": passed}) == "V3"
    assert expected_choice({"V4_stop_x2.0": rejected, "V3_stop_x1.0": rejected}) is None
