from scripts.funding_positioning_v4_shadow import _signal, _strict_fill


def test_signal_uses_only_prior_history_and_strict_tail():
    history = [(i, 0.0001) for i in range(90)]
    history.append((90, 0.0001))
    assert _signal(history)["side"] == 0
    history[-1] = (90, 0.0002)
    assert _signal(history)["side"] == -1


def test_strict_fill_does_not_count_touch():
    rows = [
        [1, 100, 101, 99.95, 100, 1],
        [2, 100, 101, 99.94, 100, 1],
    ]
    assert _strict_fill(rows, side=1, limit_price=99.95) == 2
    assert _strict_fill(rows[:1], side=1, limit_price=99.95) is None
