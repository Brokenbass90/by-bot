from research_lab.fx_smart_grid_v2 import (
    ParamsV2,
    alternating_boundary_touches,
    regression_slope,
)


def _row(index: int, high: float, low: float, close: float) -> list[float]:
    return [float(index * 3600), close, high, low, close, 100.0]


def test_regression_slope_detects_directional_drift() -> None:
    assert regression_slope([1.0, 2.0, 3.0, 4.0]) > 0
    assert regression_slope([4.0, 3.0, 2.0, 1.0]) < 0


def test_boundary_touches_require_alternation_and_separation() -> None:
    rows = [
        _row(0, 5.2, 4.0, 4.2),
        _row(1, 5.1, 4.1, 4.3),
        _row(4, 6.0, 4.8, 5.8),
        _row(8, 5.1, 4.0, 4.2),
    ]

    touches = alternating_boundary_touches(rows, 4.0, 6.0, 0.2, 0.25, min_separation=1)

    assert touches == ["L", "H", "L"]


def test_v2_is_equal_layer_not_martingale() -> None:
    params = ParamsV2(48, 0.2, 0.12, 0.75, 3)

    assert params.max_layers == 3
    assert not hasattr(params, "size_multiplier")
