from scripts.audit_inplay_prospective_parity import (
    FROZEN_BASELINE_RAW_COUNTS,
    frozen_baseline_errors,
)


def _result(counts=FROZEN_BASELINE_RAW_COUNTS, *, hashes=True, sealed=0):
    return {
        "sealed_holdout_rows_decoded": sealed,
        "current_code_matches_reference": hashes,
        "slices": [{"raw_signals": value} for value in counts],
    }


def test_frozen_baseline_accepts_exact_identity_and_frequency():
    assert frozen_baseline_errors(_result()) == []


def test_frozen_baseline_rejects_code_or_frequency_drift():
    errors = frozen_baseline_errors(_result((32, 40, 62, 80), hashes=False))
    assert "code_hash_mismatch" in errors
    assert any(error.startswith("historical_frequency_mismatch") for error in errors)


def test_frozen_baseline_rejects_any_sealed_decode():
    assert "sealed_holdout_was_decoded" in frozen_baseline_errors(_result(sealed=1))
