import ast
import re
from pathlib import Path

from scripts.audit_research_workbench import _risk_flags, classify_candidate


def test_candidate_classification_prefers_strongest_evidence():
    assert classify_candidate(syntax_ok=False, test_refs=9, prereg_refs=9, evidence_refs=9, other_refs=9) == "broken_code"
    assert classify_candidate(syntax_ok=True, test_refs=1, prereg_refs=0, evidence_refs=0, other_refs=0) == "test_backed_candidate"
    assert classify_candidate(syntax_ok=True, test_refs=0, prereg_refs=1, evidence_refs=0, other_refs=0) == "evidence_backed_needs_reproduction"
    assert classify_candidate(syntax_ok=True, test_refs=0, prereg_refs=0, evidence_refs=0, other_refs=1) == "referenced_needs_review"
    assert classify_candidate(syntax_ok=None, test_refs=0, prereg_refs=0, evidence_refs=0, other_refs=0) == "unreferenced_quarantine_candidate"


def test_reference_pattern_does_not_match_a_longer_identifier():
    pattern = re.compile(r"(?<![A-Za-z0-9_])xsec_v3(?![A-Za-z0-9_])")
    assert pattern.search("run xsec_v3 now")
    assert not pattern.search("xsec_v30")
    assert not pattern.search("old_xsec_v3_reference")


def test_python_risk_scan_ignores_literal_but_finds_actual_call():
    literal = 'RULE = r"place_order\\s*\\("\n'
    assert _risk_flags(Path("audit.py"), literal, ast.parse(literal)) == (False, False)
    actual = "client.place_order(symbol='BTCUSDT')\n"
    assert _risk_flags(Path("adapter.py"), actual, ast.parse(actual)) == (True, False)
