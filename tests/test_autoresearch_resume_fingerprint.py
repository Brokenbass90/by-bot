from scripts.run_strategy_autoresearch import (
    _candidate_metadata,
    _resume_matches,
    _write_candidate_metadata,
)


def test_resume_requires_matching_full_candidate_fingerprint(tmp_path) -> None:
    spec = {
        "name": "package_test",
        "cache_only": True,
        "command": ["python", "runner.py", "--tag", "{tag}"],
        "base_env": {"ARF1_MIN_RSI": "52.0"},
    }
    first = _candidate_metadata(spec, {"PFS1_PUMP_MIN_PCT": "2.5"})
    _write_candidate_metadata(tmp_path, first)

    assert _resume_matches(tmp_path, first) is True

    changed_base = {
        **spec,
        "base_env": {"ARF1_MIN_RSI": "48.0"},
    }
    second = _candidate_metadata(changed_base, {"PFS1_PUMP_MIN_PCT": "2.5"})

    assert _resume_matches(tmp_path, second) is False


def test_legacy_run_without_fingerprint_is_not_reused(tmp_path) -> None:
    metadata = _candidate_metadata({"name": "package_test"}, {})

    assert _resume_matches(tmp_path, metadata) is False
