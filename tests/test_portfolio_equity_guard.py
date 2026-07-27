import math

from bot.portfolio_equity_guard import initialize_equity_anchors, is_valid_equity


def _state() -> dict:
    return {
        "start_equity": None,
        "day_equity_start": None,
        "day": None,
        "daily_pnl_usd": 0.0,
        "disabled": False,
    }


def test_cold_start_missing_equity_does_not_store_zero_anchor() -> None:
    state = _state()

    assert initialize_equity_anchors(
        state,
        today="2026-07-27",
        equity=0.0,
    ) is False
    assert state["start_equity"] is None
    assert state["day_equity_start"] is None


def test_valid_equity_initializes_both_drawdown_anchors() -> None:
    state = _state()

    assert initialize_equity_anchors(
        state,
        today="2026-07-27",
        equity=1020.5,
    ) is True
    assert state["start_equity"] == 1020.5
    assert state["day_equity_start"] == 1020.5


def test_day_roll_waits_for_valid_equity() -> None:
    state = _state()
    initialize_equity_anchors(
        state,
        today="2026-07-26",
        equity=1000.0,
    )
    state["disabled"] = True

    assert initialize_equity_anchors(
        state,
        today="2026-07-27",
        equity=0.0,
    ) is False
    assert state["day"] == "2026-07-26"
    assert state["day_equity_start"] == 1000.0
    assert state["disabled"] is True

    assert initialize_equity_anchors(
        state,
        today="2026-07-27",
        equity=990.0,
    ) is True
    assert state["day"] == "2026-07-27"
    assert state["day_equity_start"] == 990.0
    assert state["disabled"] is False


def test_non_finite_equity_is_rejected_after_valid_initialization() -> None:
    state = _state()
    assert initialize_equity_anchors(
        state,
        today="2026-07-27",
        equity=1000.0,
    ) is True

    assert is_valid_equity(float("nan")) is False
    assert is_valid_equity(float("inf")) is False
    assert is_valid_equity(-math.inf) is False
