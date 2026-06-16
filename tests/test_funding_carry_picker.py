"""Tests for the funding-carry coin picker."""

from bot.funding_carry_picker import (
    annualized_funding, consistency, carry_score, rank_carry_candidates,
)


def test_annualized_and_consistency():
    pos = [0.0001] * 100  # 0.01%/8h, always positive
    assert abs(annualized_funding(pos) - 0.0001 * 3 * 365) < 1e-9
    assert consistency(pos) == 1.0
    mixed = [0.0002] * 70 + [-0.0002] * 30
    assert abs(consistency(mixed) - 0.70) < 1e-9


def test_carry_score_rewards_persistent_funding():
    strong = [0.0003] * 200            # ~33%/yr, never flips
    weak = [0.00001] * 200             # tiny funding
    flippy = [0.0003, -0.0003] * 100   # high mag but flips every bar
    assert carry_score(strong) > 0.5
    assert carry_score(weak) == 0.0    # below min_annual
    assert carry_score(flippy) == 0.0  # below min_consistency


def test_illiquid_scores_zero():
    strong = [0.0003] * 200
    assert carry_score(strong, liquid=False) == 0.0


def test_rank_picks_top_and_side():
    data = {
        "AAA": [0.0004] * 200,     # strong positive -> short_perp
        "BBB": [-0.0004] * 200,    # strong negative -> long_perp
        "CCC": [0.000005] * 200,   # too small -> excluded
    }
    out = rank_carry_candidates(data, k=5)
    syms = {s for s, _, _ in out}
    assert "AAA" in syms and "BBB" in syms and "CCC" not in syms
    side = {s: sd for s, _, sd in out}
    assert side["AAA"] == "short_perp"
    assert side["BBB"] == "long_perp"


def test_liquidity_filter_excludes():
    data = {"AAA": [0.0004] * 200}
    out = rank_carry_candidates(data, k=5, liquidity={"AAA": False})
    assert out == []
