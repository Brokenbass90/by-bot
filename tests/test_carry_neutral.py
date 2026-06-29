import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.carry_neutral import (basis_pct, net_delta_usd, evaluate_carry,
                               CarryConfig, CarryPosition, CarryMarket)


def test_basis_and_delta():
    assert abs(basis_pct(100.0, 100.5) - 0.005) < 1e-9
    # spot long 1@100 (+100), perp short 1@100 (-100) => delta 0
    assert abs(net_delta_usd(1.0, 100.0, 1.0, 100.0, "short")) < 1e-9


def _pos(**kw):
    base = dict(perp_side="short", spot_qty=10.0, perp_qty=10.0,
                entry_basis_pct=0.0005, funding_accrued_pct=0.2)
    base.update(kw); return CarryPosition(**base)


def _mkt(**kw):
    base = dict(spot_price=10.0, perp_price=10.0005, funding_8h_pct=0.03,
                liq_distance_pct=0.30)
    base.update(kw); return CarryMarket(**base)


def test_hold_when_neutral_and_collecting():
    r = evaluate_carry(_pos(), _mkt())
    assert r["action"] == "hold"
    assert r["reason"] == "neutral_and_collecting"


def test_liquidation_guard_exits_first():
    r = evaluate_carry(_pos(), _mkt(liq_distance_pct=0.05))
    assert r["action"] == "exit"
    assert "liq_distance" in r["reason"]


def test_funding_flip_exits():
    r = evaluate_carry(_pos(), _mkt(funding_8h_pct=-0.01))
    assert r["action"] == "exit"
    assert "funding_flip" in r["reason"]


def test_basis_widening_exits_when_above_cushion():
    # entry basis 0.0005; now perp much richer -> basis ~0.01 (1%), adverse ~0.95%
    # funding cushion = 0.2% -> adverse > max(0.6%) and > cushion -> exit
    r = evaluate_carry(_pos(), _mkt(perp_price=10.10))
    assert r["action"] == "exit"
    assert "basis widened" in r["reason"]


def test_basis_widening_tolerated_if_cushion_large():
    # big funding cushion absorbs the adverse basis -> not exit on basis
    pos = _pos(funding_accrued_pct=2.0)  # 2% collected
    r = evaluate_carry(pos, _mkt(perp_price=10.05), CarryConfig(max_adverse_basis_pct=0.006,
                                                                basis_cushion_mult=1.0))
    # adverse ~0.45% < cushion 2% -> basis guard does NOT exit (may hold/rebalance)
    assert r["action"] != "exit" or "basis" not in r["reason"]


def test_rebalance_on_delta_drift():
    # uneven legs: spot 10 @10 (=100), perp short 8 @10 (=-80) -> delta +20 = 20%
    r = evaluate_carry(_pos(perp_qty=8.0), _mkt())
    assert r["action"] == "rebalance"
    assert "delta" in r["reason"]


def test_long_perp_negative_carry_mirror():
    # negative-carry: perp long, funding negative (longs receive). funding -0.03 => eff +0.03 ok
    pos = _pos(perp_side="long", entry_basis_pct=-0.0005)
    r = evaluate_carry(pos, _mkt(perp_side if False else None) if False else
                       CarryMarket(spot_price=10.0, perp_price=9.9995,
                                   funding_8h_pct=-0.03, liq_distance_pct=0.30))
    assert r["action"] in ("hold", "rebalance")


def test_price_unavailable_safe():
    r = evaluate_carry(_pos(), _mkt(spot_price=0.0))
    assert r["action"] == "hold" and r["reason"] == "price_unavailable"
