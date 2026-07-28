import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "run_att1_a3_3r_exact_replay.py"
SPEC = importlib.util.spec_from_file_location("att1_exact_replay", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_capital_gate_requires_all_quantitative_checks_and_never_authorizes_money():
    spec = {
        "fold_method": {"folds": 4},
        "capital_gate": {
            "evaluated_at_round_trip_bps": 11.0,
            "min_trades": 100,
            "min_positive_folds": 3,
            "min_profit_factor": 1.05,
            "min_expectancy_r": 0.03,
            "min_single_fold_expectancy_r": -0.15,
        },
        "comparison_gate": {
            "challenger_must_improve_expectancy_r_at_11bps": True,
            "challenger_must_not_increase_negative_months": True,
        },
    }
    champion = {
        "trades": 120,
        "profit_factor": 1.1,
        "expectancy_r": 0.04,
        "folds_positive": 3,
        "negative_months": 3,
        "folds": [{"expectancy_r": 0.01}] * 4,
    }
    challenger = {
        "trades": 110,
        "profit_factor": 1.2,
        "expectancy_r": 0.05,
        "folds_positive": 3,
        "negative_months": 2,
        "folds": [{"expectancy_r": 0.02}] * 4,
    }
    result = MODULE._capital_gate(
        spec,
        {
            "champion": {"11.0": champion},
            "a3_fixed_3r": {"11.0": challenger},
        },
    )
    assert result["quantitative_pass"] is True
    assert result["verdict"] == "BLOCKED_FORWARD_SHADOW"
    assert result["capital_authorized"] is False


def test_capital_gate_fails_when_challenger_does_not_improve_champion():
    spec = {
        "fold_method": {"folds": 4},
        "capital_gate": {
            "evaluated_at_round_trip_bps": 11.0,
            "min_trades": 100,
            "min_positive_folds": 3,
            "min_profit_factor": 1.05,
            "min_expectancy_r": 0.03,
            "min_single_fold_expectancy_r": -0.15,
        },
        "comparison_gate": {
            "challenger_must_improve_expectancy_r_at_11bps": True,
            "challenger_must_not_increase_negative_months": True,
        },
    }
    champion = {
        "trades": 120,
        "profit_factor": 1.2,
        "expectancy_r": 0.06,
        "folds_positive": 4,
        "negative_months": 2,
        "folds": [{"expectancy_r": 0.02}] * 4,
    }
    challenger = {
        "trades": 120,
        "profit_factor": 1.1,
        "expectancy_r": 0.04,
        "folds_positive": 4,
        "negative_months": 2,
        "folds": [{"expectancy_r": 0.01}] * 4,
    }
    result = MODULE._capital_gate(
        spec,
        {
            "champion": {"11.0": champion},
            "a3_fixed_3r": {"11.0": challenger},
        },
    )
    assert result["quantitative_pass"] is False
    assert result["checks"]["improves_champion_expectancy"] is False
    assert result["verdict"] == "FAIL"
