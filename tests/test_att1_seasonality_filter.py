import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "analyze_att1_seasonality_filter.py"
SPEC = importlib.util.spec_from_file_location("att1_seasonality_filter", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_split_rows_is_chronological_and_sealed():
    rows = [{"entry_ts": str(i)} for i in range(10)]
    result = MODULE._split_rows(rows, 0.6, 0.2)
    assert [row["entry_ts"] for row in result["discovery"]] == [str(i) for i in range(6)]
    assert [row["entry_ts"] for row in result["validation"]] == ["6", "7"]
    assert [row["entry_ts"] for row in result["holdout"]] == ["8", "9"]


def test_benjamini_hochberg_is_monotone_in_sorted_p_values():
    adjusted = MODULE._benjamini_hochberg({"a": 0.001, "b": 0.01, "c": 0.04})
    assert adjusted["a"] <= adjusted["b"] <= adjusted["c"]
    assert adjusted == {"a": 0.003, "b": 0.015, "c": 0.04}


def test_negative_mean_sign_flip_is_deterministic():
    values = [-0.1, -0.2, -0.3, -0.4]
    first = MODULE._sign_flip_negative_mean_p(values, draws=1000, seed=17)
    second = MODULE._sign_flip_negative_mean_p(values, draws=1000, seed=17)
    assert first == second
    assert 0.0 < first < 0.2
