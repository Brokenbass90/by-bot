"""Tests for bot/liquidity_map.py (Claude 2026-06-11)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.liquidity_map import (
    LiqMapConfig, LiquidityMap, LiquiditySweepReversalV1, find_pivots,
)


def _flat(n, px=100.0):
    return [px] * n, [px] * n, [px] * n  # h, l, c


def _series_with_equal_lows():
    """База 100, два чётких свинг-лоя на 95 (equal lows) + текущий бар, снявший их."""
    h, l, c = [], [], []
    base = [100, 101, 102, 101, 100]
    def bar(hi, lo, cl):
        h.append(hi); l.append(lo); c.append(cl)
    for px in base * 7:                 # разогрев 35 баров (need=40 c хвостом)
        bar(px + 0.5, px - 0.5, px)
    bar(99, 95.0, 98)                    # свинг-лоу #1 @95
    for px in [99, 100, 101, 100, 99]:
        bar(px + 0.5, px - 0.5, px)
    bar(99, 95.1, 98)                    # свинг-лоу #2 @95.1 (equal low)
    for px in [99, 100, 101, 100, 99]:
        bar(px + 0.5, px - 0.5, px)
    return h, l, c


def test_find_pivots_basic():
    h = [1, 2, 5, 2, 1, 1, 1]
    l = [1, 1, 1, 1, 0.5, 1, 1]
    ph, pl = find_pivots(h, l, 2, 2)
    assert any(p[1] == 5 for p in ph)
    assert any(p[1] == 0.5 for p in pl)


def test_pool_clusters_equal_lows():
    h, l, c = _series_with_equal_lows()
    pools = LiquidityMap(LiqMapConfig(cluster_tol_pct=0.5)).build(h, l)
    below = pools["below"]
    assert below, "должен найтись нижний пул из equal lows"
    assert any(abs(p.price - 95.05) < 0.5 and p.touches >= 2 for p in below)


def test_sweep_long_signal():
    h, l, c = _series_with_equal_lows()
    # текущий бар: фитиль под пул 95, закрытие выше — снятие
    h.append(99.0); l.append(94.4); c.append(97.0)
    s = LiquiditySweepReversalV1()
    s.cfg.map.cluster_tol_pct = 0.5
    s.cfg.min_pool_touches = 2          # синтетический пул из 2 касаний
    s.cfg.htf_factor = 1                # пулы на базовом ТФ (тест геометрии)
    sig = s.signal(h, l, c)
    assert sig is not None and sig["side"] == "long"
    assert sig["sl"] < 94.4              # стоп за экстремум фитиля
    assert sig["tp"] > sig["entry"]


def test_deep_break_is_not_sweep():
    h, l, c = _series_with_equal_lows()
    h.append(95.5); l.append(85.0); c.append(95.2)   # пролёт на 10 — это пробой
    s = LiquiditySweepReversalV1()
    s.cfg.map.cluster_tol_pct = 0.5
    sig = s.signal(h, l, c)
    assert sig is None


def test_close_below_pool_no_signal():
    h, l, c = _series_with_equal_lows()
    h.append(96.0); l.append(94.4); c.append(94.6)   # закрылся ПОД пулом — не возврат
    s = LiquiditySweepReversalV1()
    s.cfg.map.cluster_tol_pct = 0.5
    assert s.signal(h, l, c) is None


def test_flat_series_no_pools_no_crash():
    h, l, c = _flat(120)
    s = LiquiditySweepReversalV1()
    assert s.signal(h, l, c) is None


def test_htf_factor_aggregates_pools():
    """htf_factor=2: пулы строятся на агрегированных барах, сигнал-механика жива."""
    h, l, c = _series_with_equal_lows()
    h.append(99.0); l.append(94.4); c.append(97.0)
    s = LiquiditySweepReversalV1()
    s.cfg.map.cluster_tol_pct = 1.0
    s.cfg.min_pool_touches = 1
    s.cfg.map.min_touches = 1
    s.cfg.htf_factor = 2
    s.signal(h, l, c)  # не должно падать; сигнал зависит от агрегации
    assert s.last_reason != ""
