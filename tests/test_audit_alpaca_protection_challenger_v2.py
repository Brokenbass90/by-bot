from pathlib import Path

from scripts.audit_alpaca_protection_challenger_v2 import audit


def test_committed_alpaca_v2_receipt_passes_independent_audit():
    root = Path("research_lab/results/alpaca_protection_challenger_v2_20260813")
    receipt = audit(root)
    assert receipt["passed"] is True
    assert receipt["recomputed_gates"]["entry_relative_stop"] is True
    assert receipt["recomputed_gates"]["entry_stop_gap2"] is False
    assert receipt["capital_authorized"] is False
