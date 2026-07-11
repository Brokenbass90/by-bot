from types import SimpleNamespace

import bot.fx_setups_v2 as v2
from bot.fx_instruments import get_instrument


def _rows(n=180, current=None, event=None):
    out = []
    for i in range(n):
        px = 100.0 + 0.01 * i
        out.append([1_750_000_000 + i * 3600, px, px + 0.4, px - 0.4, px + 0.05, 10.0])
    if event is not None:
        out[-2] = [out[-2][0], *event]
    if current is not None:
        out[-1] = [out[-1][0], *current]
    return out


def _prepare_unbroken_resistance_break(rows):
    for i in range(len(rows) - 14, len(rows) - 2):
        ts = rows[i][0]
        rows[i] = [ts, 99.5, 99.8, 99.2, 99.6, 10.0]


def test_impulse_and_retest_are_different_bars(monkeypatch):
    rows = _rows(
        event=[100.0, 101.7, 99.9, 101.5, 20.0],
        current=[100.1, 100.5, 99.7, 100.35, 12.0],
    )
    _prepare_unbroken_resistance_break(rows)
    monkeypatch.setattr(v2, "_liquid_and_news_ok", lambda *a, **k: True)
    monkeypatch.setattr(v2, "atr", lambda *a, **k: 1.0)
    monkeypatch.setattr(v2, "_trend_side", lambda *a, **k: "long")
    monkeypatch.setattr(v2, "_break_levels", lambda *a, **k: [
        {"kind": "horizontal", "event_level": 100.0, "slope": 0.0, "touches": 3}
    ])
    monkeypatch.setattr(v2, "_respect_meta", lambda *a, **k: (True, {"respect_rated": True}))
    cfg = v2.ImpulseBreakoutRetestConfig(trend_slow=30, level_lookback=24, context_bars=180)
    plan = v2.impulse_breakout_retest_v2(
        rows, instrument=get_instrument("EURUSD"), side_mode="long", cfg=cfg
    )
    assert plan is not None and plan.side == "long"
    assert plan.event.metadata["impulse_ts"] < plan.event.signal_ts
    assert plan.entry_type == "market_next_open"


def test_impulse_side_mode_is_hard_separation(monkeypatch):
    rows = _rows(
        event=[100.0, 101.7, 99.9, 101.5, 20.0],
        current=[100.1, 100.5, 99.7, 100.35, 12.0],
    )
    _prepare_unbroken_resistance_break(rows)
    monkeypatch.setattr(v2, "_liquid_and_news_ok", lambda *a, **k: True)
    monkeypatch.setattr(v2, "atr", lambda *a, **k: 1.0)
    monkeypatch.setattr(v2, "_trend_side", lambda *a, **k: "long")
    assert v2.impulse_breakout_retest_v2(
        rows, instrument=get_instrument("EURUSD"), side_mode="short",
        cfg=v2.ImpulseBreakoutRetestConfig(trend_slow=30, level_lookback=24),
    ) is None


def test_sweep_reclaim_builds_structural_plan(monkeypatch):
    rows = _rows(current=[100.2, 100.4, 98.8, 100.1, 30.0])
    monkeypatch.setattr(v2, "_liquid_and_news_ok", lambda *a, **k: True)
    monkeypatch.setattr(v2, "atr", lambda *a, **k: 1.0)
    monkeypatch.setattr(v2, "liquidity_sweep", lambda *a, **k: SimpleNamespace(
        event="sweep_reversal", side="long", pool_level=99.0, penetration_atr=0.2
    ))
    monkeypatch.setattr(v2, "failed_breakout", lambda *a, **k: SimpleNamespace(failed=False))
    monkeypatch.setattr(v2, "sloped_level", lambda *a, **k: None)
    monkeypatch.setattr(v2, "regime_probs", lambda *a, **k: SimpleNamespace(ok=True, dominant="range", confidence=0.6))
    monkeypatch.setattr(v2, "elder_bias", lambda *a, **k: SimpleNamespace(allow_long=True, allow_short=True, tide="flat"))
    monkeypatch.setattr(v2, "structure_break", lambda *a, **k: SimpleNamespace(event="none", side="none"))
    monkeypatch.setattr(v2, "_respect_meta", lambda *a, **k: (True, {"respect_rated": True}))
    plan = v2.sweep_reclaim_bounce_v2(
        rows, instrument=get_instrument("EURUSD"), side_mode="long"
    )
    assert plan is not None and plan.stop_price < plan.reference_price
    assert plan.event.level_kind == "liquidity"


def test_failed_break_reclaim_keeps_one_event_id_across_later_inside_bars(monkeypatch):
    rows = _rows()
    rows[-2] = [rows[-2][0], 99.2, 99.3, 98.7, 98.8, 30.0]
    rows[-1] = [rows[-1][0], 98.9, 100.4, 98.8, 100.1, 20.0]
    monkeypatch.setattr(v2, "_liquid_and_news_ok", lambda *a, **k: True)
    monkeypatch.setattr(v2, "atr", lambda *a, **k: 1.0)
    monkeypatch.setattr(v2, "liquidity_sweep", lambda *a, **k: SimpleNamespace(event="none"))
    monkeypatch.setattr(v2, "failed_breakout", lambda source, *a, **k: SimpleNamespace(
        failed=True, side="long", level=99.0 if len(source) % 2 == 0 else 99.05
    ))
    monkeypatch.setattr(v2, "sloped_level", lambda *a, **k: None)
    monkeypatch.setattr(v2, "regime_probs", lambda *a, **k: SimpleNamespace(
        ok=True, dominant="range", confidence=0.6
    ))
    monkeypatch.setattr(v2, "elder_bias", lambda *a, **k: SimpleNamespace(
        allow_long=True, allow_short=True, tide="flat"
    ))
    monkeypatch.setattr(v2, "structure_break", lambda *a, **k: SimpleNamespace(
        event="none", side="none"
    ))
    monkeypatch.setattr(v2, "_respect_meta", lambda *a, **k: (True, {"respect_rated": True}))

    first = v2.sweep_reclaim_bounce_v2(
        rows, instrument=get_instrument("EURUSD"), side_mode="long"
    )
    later_rows = rows + [[rows[-1][0] + 3600, 98.9, 100.3, 98.7, 100.0, 18.0]]
    second = v2.sweep_reclaim_bounce_v2(
        later_rows, instrument=get_instrument("EURUSD"), side_mode="long"
    )
    assert first is not None and second is not None
    assert first.event.event_id == second.event.event_id
    assert first.event.signal_ts != second.event.signal_ts


def test_range_plan_freezes_edge_and_uses_limit(monkeypatch):
    rows = _rows(current=[100.2, 100.4, 98.9, 100.1, 20.0])
    monkeypatch.setattr(v2, "_liquid_and_news_ok", lambda *a, **k: True)
    monkeypatch.setattr(v2, "atr", lambda *a, **k: 1.0)
    monkeypatch.setattr(v2, "range_state", lambda *a, **k: SimpleNamespace(
        ok=True, is_range=True, width_atr=4.0, regime="flat", lower_now=99.0,
        upper_now=103.0, nearest_support=float("nan"), nearest_resistance=float("nan"),
        votes=3, ci=65.0, vp=20.0, adx=12.0,
    ))
    monkeypatch.setattr(v2, "regime_probs", lambda *a, **k: SimpleNamespace(ok=True, dominant="range"))
    plan = v2.regime_range_reversion_v2(
        rows, instrument=get_instrument("EURUSD"), side_mode="long"
    )
    assert plan is not None and plan.entry_type == "limit"
    assert plan.target_price == 101.0
    assert plan.side == "long"
