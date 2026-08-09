from pathlib import Path


def test_auditor_checks_atomic_live_mirror_not_historical_local_context() -> None:
    source = Path("research_lab/ai_auditor.py").read_text(encoding="utf-8")

    assert '"runtime/live_mirror/ai_context/full_context.json": 0.05' in source
    assert '"runtime/ai_context/full_context.json": 2.0' not in source
