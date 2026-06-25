"""Regression: the crypto promotion CLI must be FAIL-CLOSED.

Bug (CODEX_HANDOFF_2026_06_20 §3): ``scripts/evaluate_crypto_promotion.py``
exited 0 even when ``promotion_passed=false`` because ``main()`` returned 0
unconditionally. A machine consuming the exit code would treat a FAILED
candidate as promotable. The contract is: exit non-zero on failure so any
automation halts.

This test loads the script as a module, stubs the data loaders and the four
sub-gates, and asserts the exit code follows ``promotion_passed``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_crypto_promotion.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_crypto_promotion_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stub_common(mod, monkeypatch):
    # Loaders are irrelevant to the exit-code contract; return inert values.
    monkeypatch.setattr(mod, "_load_summary", lambda *a, **k: {"tag": "x"})
    monkeypatch.setattr(mod, "_load_monthly_metrics", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_load_walkforward", lambda *a, **k: {"tag": "wf"})
    monkeypatch.setattr(mod, "_load_json", lambda *a, **k: {})


def _run(mod, monkeypatch, *, all_pass: bool) -> int:
    verdict = {"passed": all_pass, "reasons": []}
    for name in ("_annual_gate", "_monthly_gate", "_walkforward_gate"):
        monkeypatch.setattr(mod, name, lambda *a, **k: dict(verdict))
    monkeypatch.setattr(mod, "_portfolio_compare", lambda *a, **k: {"passed": all_pass, "reasons": [], "winning_paths": []})
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate_crypto_promotion.py", "--annual-summary", "a.csv", "--walkforward-latest", "w.json", "--json"],
    )
    return mod.main()


def test_failed_candidate_exits_nonzero(monkeypatch):
    mod = _load_module()
    _stub_common(mod, monkeypatch)
    rc = _run(mod, monkeypatch, all_pass=False)
    assert rc != 0, "FAIL-CLOSED violated: failed candidate returned exit code 0"


def test_passing_candidate_exits_zero(monkeypatch):
    mod = _load_module()
    _stub_common(mod, monkeypatch)
    rc = _run(mod, monkeypatch, all_pass=True)
    assert rc == 0, "passing candidate must return exit code 0"
