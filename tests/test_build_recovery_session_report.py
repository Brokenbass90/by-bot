from scripts.build_recovery_session_report import build_artifact


def test_report_separates_scenarios_from_money_authority():
    artifact = build_artifact()
    assert artifact["answer_first"]["promotion_ready_new_legs"] == 0
    rows = {row["name"]: row for row in artifact["scenarios"]}
    assert rows["ATT1 Bybit canary"]["stage"] == "CANARY"
    assert rows["XSEC neutral crypto"]["admissibility"] == "NOT_ADMISSIBLE"
    assert rows["MPL / inplay next leg"]["illustrative_end_usd"] is None
    assert artifact["xsec_evidence"]["modern_keys_excluded"] is True
