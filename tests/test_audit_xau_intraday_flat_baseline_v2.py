from scripts import audit_xau_intraday_flat_baseline_v2 as audit


def test_committed_xau_v2_receipts_pass_independent_audit():
    assert audit.main() == 0
