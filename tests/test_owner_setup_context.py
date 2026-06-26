from __future__ import annotations

from bot.owner_setup_context import OwnerSetupConfig, score_owner_retest_context


def _row(ts: int, o: float, h: float, l: float, c: float, v: float):
    return [ts, o, h, l, c, v]


def _rows_5m(*, high_volume: bool = True, current: float = 101.0):
    rows = []
    for i in range(72):
        rows.append(_row(i * 300_000, 101.0, 101.2, 100.8, 101.0, 1_000.0))
    recent_v = 10_000.0 if high_volume else 1_000.0
    for j in range(3):
        i = 72 + j
        close = current + j * 0.03
        rows.append(_row(i * 300_000, close, close + 0.25, close - 0.25, close, recent_v))
    return rows


def _rows_1h(*, current: float = 101.0):
    rows = []
    for i in range(90):
        close = 105.0
        high = 107.0
        low = 103.0
        if i in {12, 32, 52}:
            low = 100.0
            close = 102.0
            high = 106.0
        if i in {22, 42, 62}:
            high = 110.0
            close = 108.0
            low = 104.0
        rows.append(_row(i * 3_600_000, close, high, low, close, 1_000.0))
    rows[-1] = _row(89 * 3_600_000, current, current + 0.4, current - 0.4, current, 1_000.0)
    return rows


def _cfg(require_volume: bool = True):
    return OwnerSetupConfig(
        min_recent_quote_usd=2_000.0,
        min_inflow_mult=2.0,
        min_inflow_z=1.0,
        max_entry_dist_atr=1.0,
        min_room_atr=0.8,
        min_rr_proxy=1.0,
        require_inplay_volume=require_volume,
    )


def test_owner_retest_accepts_volume_first_support_retest():
    ctx = score_owner_retest_context(_rows_5m(high_volume=True), _rows_1h(current=101.0), side="long", cfg=_cfg())

    assert ctx.ok, ctx.rejects
    assert ctx.inplay_ok
    assert ctx.level_price is not None and abs(ctx.level_price - 100.0) < 1.0
    assert ctx.target_price is not None and ctx.target_price > ctx.price
    assert ctx.rr_proxy is not None and ctx.rr_proxy >= 1.0
    assert ctx.score > 0.5


def test_owner_retest_rejects_when_coin_is_not_inplay():
    ctx = score_owner_retest_context(_rows_5m(high_volume=False), _rows_1h(current=101.0), side="long", cfg=_cfg())

    assert not ctx.ok
    assert any(r.startswith("volume:") for r in ctx.rejects)


def test_owner_retest_rejects_when_entry_is_far_from_level():
    ctx = score_owner_retest_context(
        _rows_5m(high_volume=True, current=106.0),
        _rows_1h(current=106.0),
        side="long",
        cfg=_cfg(),
    )

    assert not ctx.ok
    assert "entry_far_from_level" in ctx.rejects


def test_owner_retest_can_score_without_hard_volume_gate_for_diagnostics():
    ctx = score_owner_retest_context(
        _rows_5m(high_volume=False),
        _rows_1h(current=101.0),
        side="long",
        cfg=_cfg(require_volume=False),
    )

    assert ctx.inplay_ok is False
    assert not any(r.startswith("volume:") for r in ctx.rejects)
    assert ctx.level_price is not None
