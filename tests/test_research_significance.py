import math

import pytest

from research_lab.significance import (
    assess,
    expected_max_sharpe_under_null,
    power_of_sample,
    required_trades,
)


def test_one_preregistered_trial_has_no_selection_hurdle() -> None:
    assert expected_max_sharpe_under_null(1, 0.25) == 0.0


def test_more_trials_raise_the_null_winner_hurdle() -> None:
    small = expected_max_sharpe_under_null(10, 0.05)
    large = expected_max_sharpe_under_null(1_000, 0.05)

    assert 0.0 < small < large


def test_required_trades_and_power_are_consistent() -> None:
    need = required_trades(0.10, 1.0, power=0.80)

    assert need > 2
    assert power_of_sample(need, 0.10, 1.0) >= 0.80
    assert power_of_sample(need - 1, 0.10, 1.0) < 0.80


def test_assess_rejects_too_small_or_flat_sample() -> None:
    verdict = assess([0.0], n_trials=1)

    assert verdict.ok is False
    assert verdict.n == 1
    assert verdict.dsr == 0.0
    assert any("слишком мала" in note for note in verdict.notes)


def test_assess_does_not_hide_non_finite_min_track_record() -> None:
    verdict = assess([-1.0, 0.0, 1.0], n_trials=1)

    assert verdict.ok is False
    assert math.isinf(verdict.min_trl)
    assert verdict.need_n == -1
