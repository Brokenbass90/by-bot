from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.preflight_horizontal_breakout_long_72h_sealed_v1 as preflight
from scripts.preflight_horizontal_breakout_long_72h_sealed_v1 import (
    BreakoutLongPreflightError,
    DEFAULT_CONFIG,
    canonical_sha256,
    validate_preregistration,
)


ROOT = Path(__file__).resolve().parents[1]


def _mutated_config(tmp_path: Path, mutate) -> Path:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    mutate(config)
    config.pop("preregistration_fingerprint_sha256", None)
    config["preregistration_fingerprint_sha256"] = canonical_sha256(config)
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_default_freeze_is_exactly_one_long_candidate_and_reads_no_market_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hashed: list[Path] = []
    original = preflight.sha256_file

    def recording_sha(path: Path) -> str:
        hashed.append(path)
        return original(path)

    monkeypatch.setattr(preflight, "sha256_file", recording_sha)
    receipt = validate_preregistration(ROOT, DEFAULT_CONFIG)

    assert receipt["integrity_pass"] is True
    assert receipt["candidate_count"] == 1
    assert receipt["physical_side"] == "long"
    assert receipt["sealed_holdout_rows_decoded"] == 0
    assert receipt["market_snapshots_opened"] == 0
    assert receipt["performance_computed"] is False
    assert all("data_cache" not in path.parts for path in hashed)


def test_freeze_preserves_atlas_parity_entry_exit_and_explicitly_no_retest() -> None:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    strategy = config["strategy_contract"]

    assert strategy["signal"]["lookback_h1"] == 20
    assert strategy["physical_side"] == "long"
    assert strategy["short_logic_present"] is False
    assert strategy["entry"]["time"] == "next_H1_open_after_completed_signal_bar"
    assert strategy["retest"]["required"] is False
    assert strategy["exit"]["holding_period_h1"] == 72
    assert strategy["exit"]["stop_loss"] is None
    assert strategy["exit"]["take_profit"] is None


@pytest.mark.parametrize(
    "mutate,error",
    [
        (
            lambda cfg: cfg["strategy_contract"].update(
                {"physical_side": "short", "short_logic_present": True}
            ),
            "physical long-only",
        ),
        (
            lambda cfg: cfg["strategy_contract"]["retest"].update({"required": True}),
            "retest policy",
        ),
        (
            lambda cfg: cfg["strategy_contract"]["exit"].update({"holding_period_h1": 48}),
            "fixed 72h exit",
        ),
        (
            lambda cfg: cfg["promotion_gates"]["aggregate"].update(
                {"stress_profit_factor_min": 1.01}
            ),
            "aggregate promotion gates",
        ),
    ],
)
def test_recomputed_fingerprint_cannot_hide_contract_mutation(
    tmp_path: Path,
    mutate,
    error: str,
) -> None:
    path = _mutated_config(tmp_path, mutate)
    with pytest.raises(BreakoutLongPreflightError, match=error):
        validate_preregistration(ROOT, path)


def test_plain_edit_without_new_fingerprint_fails_closed(tmp_path: Path) -> None:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["promotion_eligible_now"] = True
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(BreakoutLongPreflightError, match="fingerprint mismatch"):
        validate_preregistration(ROOT, path)


def test_funding_folds_embargo_and_concentration_are_frozen() -> None:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))

    funding = config["execution_and_cost_contract"]["funding"]
    assert funding["negative_rate_credit_bps"] == 0.0
    assert funding["missing_or_incomplete_history"] == "FAIL_CLOSED_NO_PERFORMANCE"
    assert len(config["temporal_partition"]["folds"]) == 4
    assert config["temporal_partition"]["embargo_h1"] == 72
    concentration = config["promotion_gates"]["breadth_and_concentration"]
    assert concentration["traded_symbols_min"] == 10
    assert concentration["top_symbol_positive_net_contribution_share_max"] == 0.35
    assert concentration["top_10pct_trades_positive_net_contribution_share_max"] == 0.65


def test_preflight_is_integrity_only_and_has_no_scoring_or_live_imports() -> None:
    source = Path(preflight.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "load_discovery_m5_rows",
        "load_uniform_symbol_rows",
        "aggregate_closed_m5_bars",
        "requests",
        "pybit",
        "ccxt",
        "place_order",
    ):
        assert forbidden not in source
