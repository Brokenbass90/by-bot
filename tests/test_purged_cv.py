from __future__ import annotations

import pytest

from research_lab.purged_cv import PurgedKFold


def test_purged_folds_never_leak_overlapping_intervals():
    starts = list(range(40))
    ends = [value + 8 for value in starts]

    for train, test in PurgedKFold(n_splits=4, embargo_frac=0.05).split(starts, ends):
        test_start = min(starts[index] for index in test)
        test_end = max(ends[index] for index in test)
        assert set(train).isdisjoint(test)
        assert all(
            ends[index] < test_start or starts[index] > test_end
            for index in train
        )


def test_purged_folds_preserve_original_indices_after_time_sorting():
    starts = [30, 10, 20, 0]
    ends = starts.copy()
    folds = list(PurgedKFold(n_splits=2, embargo_frac=0.0).split(starts, ends))

    assert folds[0][1] == [3, 1]
    assert folds[1][1] == [2, 0]


@pytest.mark.parametrize(
    "starts,ends,n_splits",
    [
        ([1, 2], [1], 2),
        ([5, 1], [1, 2], 2),
        ([1], [1], 2),
        ([1, 2], [1, 2], 1),
    ],
)
def test_purged_folds_reject_invalid_inputs(starts, ends, n_splits):
    with pytest.raises(ValueError):
        list(PurgedKFold(n_splits=n_splits).split(starts, ends))
