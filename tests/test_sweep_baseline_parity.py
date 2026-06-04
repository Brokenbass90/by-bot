from scripts.validate_sweep_configs import _validate_baseline_env_parity


def test_baseline_parity_reports_missing_and_mismatched_keys(tmp_path) -> None:
    baseline = tmp_path / "baseline.env"
    baseline.write_text(
        "ENABLE_ATT1_TRADING=1\nARF1_MIN_RSI=52.0\nBREAKDOWN_RSI_MAX=55\n",
        encoding="utf-8",
    )
    spec = {"baseline_env_file": str(baseline)}

    errors = _validate_baseline_env_parity(
        spec,
        {"ARF1_MIN_RSI": "48.0"},
    )

    assert "base_env baseline mismatch: ARF1_MIN_RSI='48.0', expected '52.0'" in errors
    assert "base_env missing baseline key: BREAKDOWN_RSI_MAX" in errors
    assert not any("ENABLE_ATT1_TRADING" in error for error in errors)


def test_baseline_parity_accepts_matching_non_enable_keys(tmp_path) -> None:
    baseline = tmp_path / "baseline.env"
    baseline.write_text(
        "ENABLE_ATT1_TRADING=1\nARF1_MIN_RSI=52.0\n",
        encoding="utf-8",
    )
    spec = {"baseline_env_file": str(baseline)}

    assert _validate_baseline_env_parity(spec, {"ARF1_MIN_RSI": "52.0"}) == []
