from pathlib import Path

from scripts.audit_att1_pivot_sequence_v1 import audit


def test_committed_att1_pivot_sequence_receipt_passes():
    root = Path("research_lab/results/att1_pivot_sequence_preholdout_v1_20260813")
    receipt = audit(root)
    assert receipt["passed"] is True
    assert receipt["breadth"]["improved_symbol_count"] >= 5
    assert receipt["capital_authorized"] is False
