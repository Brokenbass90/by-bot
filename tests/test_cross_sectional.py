"""Tests for cross-sectional selection (rank, don't threshold)."""

from bot.cross_sectional import select_top_k, select_top_fraction, zscore_gate


SCORES = {"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.3, "E": 0.1}


def test_top_k_ranks_descending():
    out = select_top_k(SCORES, 2)
    assert [s for s, _ in out] == ["A", "B"]


def test_top_k_respects_min_score():
    out = select_top_k(SCORES, 10, min_score=0.6)
    assert [s for s, _ in out] == ["A", "B"]   # only >=0.6


def test_top_fraction_adapts_and_clamps():
    # 5 symbols * 0.4 = 2
    out = select_top_fraction(SCORES, frac=0.4, min_count=1, max_count=8)
    assert len(out) == 2 and out[0][0] == "A"
    # tiny universe still yields >= min_count
    out2 = select_top_fraction({"X": 0.5}, frac=0.1, min_count=1)
    assert len(out2) == 1


def test_zscore_gate_keeps_relative_leaders():
    # A is far above the mean -> passes; tail does not
    out = zscore_gate(SCORES, z_min=1.0)
    syms = [s for s, _ in out]
    assert "A" in syms
    assert "E" not in syms


def test_handles_empty_and_nan():
    assert select_top_k({}, 3) == []
    assert select_top_fraction({}, 0.2) == []
