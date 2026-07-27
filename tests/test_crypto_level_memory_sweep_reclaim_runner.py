from scripts.run_crypto_level_memory_sweep_reclaim_20260707 import _pick_best


def test_pick_best_prefers_gate_pass_over_higher_failed_score():
    rows = [
        {"id": "failed", "pass_exploration": 0, "score": 100.0},
        {"id": "passed", "pass_exploration": 1, "score": 20.0},
    ]

    assert _pick_best(rows)["id"] == "passed"


def test_pick_best_uses_score_within_same_gate_status():
    rows = [
        {"id": "lower", "pass_exploration": 1, "score": 20.0},
        {"id": "higher", "pass_exploration": 1, "score": 25.0},
    ]

    assert _pick_best(rows)["id"] == "higher"
