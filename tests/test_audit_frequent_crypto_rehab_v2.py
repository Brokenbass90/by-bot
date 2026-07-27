from scripts.audit_frequent_crypto_rehab_v2 import build_receipt


def test_receipt_is_research_only_and_evidence_backed():
    receipt = build_receipt()

    assert receipt["research_only"] is True
    assert receipt["live_or_broker_calls"] is False
    assert receipt["findings"]["pump_exhaustion_unwind_short_v1"]["trades"] == 39
    assert receipt["findings"]["level_memory_sweep_reclaim"]["legacy_cost_contract_valid"] is False
    assert receipt["findings"]["level_memory_sweep_reclaim"]["cost_repair_trades"] == 189
    assert receipt["findings"]["level_memory_sweep_reclaim"]["cost_repair_profit_factor"] < 1.0
    assert receipt["findings"]["sloped_break_retest_v1"]["passed_cases"] == 0
