from __future__ import annotations

import pytest

import bot.fx_setups_v3 as v3
from bot.fx_instruments import get_instrument


HOUR = 3600
ORIGINAL_SESSION_NEWS_OK = v3._session_news_ok


def _row(i: int, o: float, h: float, l: float, c: float, v: float = 100.0) -> list[float]:
    return [float(1_750_000_000 + i * HOUR), float(o), float(h), float(l), float(c), float(v)]


def _base(n: int = 130) -> list[list[float]]:
    rows = []
    for i in range(n):
        close = 105.0 + (0.25 if i % 4 in (1, 2) else -0.25)
        rows.append(_row(i, close - 0.1, close + 0.9, close - 0.9, close))
    return rows


def _frozen(last_ts: int = 0) -> v3.FrozenHorizontalRange:
    return v3.FrozenHorizontalRange(
        support=100.0,
        resistance=110.0,
        midpoint=105.0,
        width=10.0,
        width_atr=5.0,
        atr_value=2.0,
        support_touches=3,
        resistance_touches=3,
        range_votes=3,
        ci=62.0,
        vp=30.0,
        adx=18.0,
        source_last_ts=last_ts,
    )


@pytest.fixture(autouse=True)
def _allow_session_and_unrated_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v3, "_session_news_ok", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        v3,
        "_respect",
        lambda *_args, **_kwargs: (True, {"respect_rated": False}),
    )


def test_side_split_rejects_combined_mode() -> None:
    with pytest.raises(ValueError, match="separate long or short"):
        v3.horizontal_range_rejection_v3(
            _base(),
            instrument=get_instrument("EURUSD"),
            side_mode="both",
        )


def test_session_news_gate_fails_closed_when_calendar_is_missing() -> None:
    assert not ORIGINAL_SESSION_NEWS_OK(
        1_750_000_000,
        1.10,
        allowed_sessions=("london", "london_ny_overlap", "newyork", "asian"),
        events=None,
    )
    with pytest.raises(ValueError, match="separate long or short"):
        v3.range_edge_expansion_retest_v3(
            _base(),
            instrument=get_instrument("EURUSD"),
            side_mode="both",
        )


def test_failed_break_short_requires_break_then_reclaim_then_later_retest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _base()
    frozen_inputs: list[int] = []

    def freeze(base_rows, _cfg):
        frozen_inputs.append(int(base_rows[-1][0]))
        return _frozen(int(base_rows[-1][0]))

    monkeypatch.setattr(v3, "freeze_horizontal_range", freeze)
    cfg = v3.FailedBreakRetestShortConfig(
        min_structural_rr=0.5,
        require_volume_fade=True,
    )
    spec = get_instrument("EURUSD")

    rows.append(_row(130, 109.0, 112.0, 108.5, 111.5, 300.0))
    assert v3.failed_break_retest_short_v3(rows, instrument=spec, cfg=cfg, events=[]) is None
    rows.append(_row(131, 111.0, 111.2, 108.5, 109.0, 100.0))
    assert v3.failed_break_retest_short_v3(rows, instrument=spec, cfg=cfg, events=[]) is None
    rows.append(_row(132, 109.6, 110.2, 108.7, 109.3, 120.0))
    plan = v3.failed_break_retest_short_v3(rows, instrument=spec, cfg=cfg, events=[])
    assert plan is not None
    assert plan.side == "short"
    assert plan.entry_type == "market_next_open"
    assert plan.event.family == "failed_break_retest_short_v3"
    assert plan.event.metadata["break_ts"] == int(rows[130][0])
    assert plan.event.metadata["reclaim_ts"] == int(rows[131][0])
    assert plan.event.signal_ts == int(rows[132][0]) + HOUR
    assert int(rows[129][0]) in frozen_inputs
    assert max(frozen_inputs) <= int(rows[129][0])


def test_failed_break_first_retest_is_consumed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v3, "freeze_horizontal_range", lambda *_args, **_kwargs: _frozen())
    rows = _base()
    rows.extend(
        [
            _row(130, 109.0, 112.0, 108.5, 111.5, 300.0),
            _row(131, 111.0, 111.2, 108.5, 109.0, 100.0),
            _row(132, 109.5, 110.1, 108.7, 109.2, 100.0),  # consumed first retest
            _row(133, 109.6, 110.2, 108.7, 109.3, 100.0),
        ]
    )
    plan = v3.failed_break_retest_short_v3(
        rows,
        instrument=get_instrument("EURUSD"),
        cfg=v3.FailedBreakRetestShortConfig(min_structural_rr=0.5),
        events=[],
    )
    assert plan is None


@pytest.mark.parametrize(
    ("side", "signal", "expected"),
    [
        ("long", _row(130, 101.0, 102.5, 99.7, 102.0), "long"),
        ("short", _row(130, 109.0, 110.3, 107.5, 108.0), "short"),
    ],
)
def test_horizontal_rejection_is_horizontal_and_side_pure(
    monkeypatch: pytest.MonkeyPatch,
    side: str,
    signal: list[float],
    expected: str,
) -> None:
    monkeypatch.setattr(v3, "freeze_horizontal_range", lambda *_args, **_kwargs: _frozen())
    rows = _base() + [signal]
    cfg = v3.HorizontalRangeRejectionConfig(min_structural_rr=0.5)
    plan = v3.horizontal_range_rejection_v3(
        rows,
        instrument=get_instrument("GBPUSD"),
        side_mode=side,
        cfg=cfg,
        events=[],
    )
    assert plan is not None
    assert plan.side == expected
    assert plan.event.level_kind == "horizontal_range_edge"
    assert plan.entry_type == "market_next_open"
    assert plan.target_price == pytest.approx(105.0)


def test_range_expansion_retest_is_later_and_freezes_before_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _base()
    frozen_last_ts: list[int] = []

    def freeze(base_rows, _cfg):
        frozen_last_ts.append(int(base_rows[-1][0]))
        return _frozen(int(base_rows[-1][0]))

    monkeypatch.setattr(v3, "freeze_horizontal_range", freeze)
    cfg = v3.RangeEdgeExpansionRetestConfig(min_structural_rr=0.5)
    spec = get_instrument("USDJPY")
    rows.append(_row(130, 109.0, 112.0, 108.5, 111.5, 250.0))
    assert v3.range_edge_expansion_retest_v3(
        rows, instrument=spec, side_mode="long", cfg=cfg, events=[]
    ) is None
    rows.append(_row(131, 111.0, 111.2, 109.8, 110.7, 120.0))
    plan = v3.range_edge_expansion_retest_v3(
        rows,
        instrument=spec,
        side_mode="long",
        cfg=cfg,
        events=[],
    )
    assert plan is not None
    assert plan.side == "long"
    assert plan.event.family == "range_edge_expansion_retest_v3"
    assert plan.event.metadata["event_ts"] == int(rows[130][0])
    assert plan.event.metadata["retest_age_bars"] == 1
    assert plan.event.signal_ts == int(rows[131][0]) + HOUR
    assert max(frozen_last_ts) <= int(rows[129][0])


def test_range_expansion_short_is_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v3, "freeze_horizontal_range", lambda *_args, **_kwargs: _frozen())
    rows = _base()
    rows.extend(
        [
            _row(130, 101.0, 101.5, 98.0, 98.5, 250.0),
            _row(131, 99.0, 100.2, 98.8, 99.3, 120.0),
        ]
    )
    plan = v3.range_edge_expansion_retest_v3(
        rows,
        instrument=get_instrument("GBPJPY"),
        side_mode="short",
        cfg=v3.RangeEdgeExpansionRetestConfig(min_structural_rr=0.5),
        events=[],
    )
    assert plan is not None
    assert plan.side == "short"
    assert plan.target_price is not None and plan.target_price < plan.reference_price


@pytest.mark.parametrize("side", ["long", "short"])
def test_range_expansion_scores_level_respect_from_candidate_side(
    monkeypatch: pytest.MonkeyPatch,
    side: str,
) -> None:
    monkeypatch.setattr(v3, "freeze_horizontal_range", lambda *_args, **_kwargs: _frozen())
    seen: list[str] = []

    def respect_spy(*_args, **kwargs):
        seen.append(str(kwargs["side"]))
        return True, {"respect_rated": False}

    monkeypatch.setattr(v3, "_respect", respect_spy)
    rows = _base()
    if side == "long":
        rows.extend(
            [
                _row(130, 109.0, 112.0, 108.5, 111.5, 250.0),
                _row(131, 111.0, 111.2, 109.8, 110.7, 120.0),
            ]
        )
    else:
        rows.extend(
            [
                _row(130, 101.0, 101.5, 98.0, 98.5, 250.0),
                _row(131, 99.0, 100.2, 98.8, 99.3, 120.0),
            ]
        )
    plan = v3.range_edge_expansion_retest_v3(
        rows,
        instrument=get_instrument("GBPJPY"),
        side_mode=side,
        cfg=v3.RangeEdgeExpansionRetestConfig(min_structural_rr=0.5),
        events=[],
    )
    assert plan is not None
    assert seen == [side]
