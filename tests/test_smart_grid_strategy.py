"""Tests for strategies.smart_grid — portfolio adapter for bot.smart_grid."""
import math
import random

from strategies.smart_grid import SmartGridConfig, SmartGridStrategy


class _Store:
    symbol = "TESTUSDT"


def _range_rows(n=160, seed=7):
    random.seed(seed)
    rows = []
    prev = 100.0
    for i in range(n):
        c = 100.0 + math.sin(i / 4.0) * 2.0 + random.uniform(-0.4, 0.4)
        o = prev
        h = max(o, c) + 0.35
        l = min(o, c) - 0.35
        rows.append((i, o, h, l, c, 1000.0))
        prev = c
    return rows


def _trend_rows(n=160):
    rows = []
    prev = 100.0
    for i in range(n):
        c = 100.0 + i * 0.25
        o = prev
        rows.append((i, o, max(o, c) + 0.2, min(o, c) - 0.2, c, 1000.0))
        prev = c
    return rows


def test_adapter_emits_limit_signal_in_range():
    s = SmartGridStrategy(
        SmartGridConfig(
            lookback=40,
            n_levels=4,
            min_width_atr=1.0,
            require_strong_flat=False,
            min_rr=0.1,
            max_stop_pct=0.20,
            cooldown_bars=0,
        )
    )
    sig = None
    for r in _range_rows():
        sig = s.maybe_signal(_Store(), int(r[0]), *r[1:])
        if sig:
            break
    assert sig is not None
    assert sig.strategy == "smart_grid"
    assert sig.side in {"long", "short"}
    assert sig.validate()
    assert getattr(sig, "entry_order_type", "") == "limit"
    assert getattr(sig, "limit_validity_bars", 0) > 0


def test_adapter_blocks_trend_when_flat_required():
    s = SmartGridStrategy(
        SmartGridConfig(
            lookback=40,
            n_levels=4,
            min_width_atr=1.0,
            require_strong_flat=True,
            cooldown_bars=0,
        )
    )
    got = []
    for r in _trend_rows():
        sig = s.maybe_signal(_Store(), int(r[0]), *r[1:])
        if sig:
            got.append(sig)
    assert got == []


def test_duplicate_bar_blocked():
    s = SmartGridStrategy(SmartGridConfig(lookback=40, require_strong_flat=False))
    row = _range_rows(1)[0]
    assert s.maybe_signal(_Store(), int(row[0]), *row[1:]) is None
    assert s.maybe_signal(_Store(), int(row[0]), *row[1:]) is None
    assert s.last_no_signal_reason == "duplicate_bar"


def test_adapter_passes_side_split_to_planner():
    long_only = SmartGridStrategy(
        SmartGridConfig(
            lookback=40,
            n_levels=4,
            min_width_atr=1.0,
            require_strong_flat=False,
            side="long",
            min_rr=0.1,
            max_stop_pct=0.20,
            cooldown_bars=0,
        )
    )
    short_only = SmartGridStrategy(
        SmartGridConfig(
            lookback=40,
            n_levels=4,
            min_width_atr=1.0,
            require_strong_flat=False,
            side="short",
            min_rr=0.1,
            max_stop_pct=0.20,
            cooldown_bars=0,
        )
    )

    long_sides = set()
    short_sides = set()
    for r in _range_rows(seed=11):
        sig_l = long_only.maybe_signal(_Store(), int(r[0]), *r[1:])
        sig_s = short_only.maybe_signal(_Store(), int(r[0]), *r[1:])
        if sig_l:
            long_sides.add(sig_l.side)
        if sig_s:
            short_sides.add(sig_s.side)

    assert long_sides <= {"long"}
    assert short_sides <= {"short"}
    assert long_sides or short_sides
