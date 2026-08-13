from research_lab.funding_spot_perp_mapped_v1 import pair_return
from research_lab.funding_spot_perp_mapped_v2 import _basis_ok


def test_pair_return_is_delta_neutral_when_spot_and_perp_move_together() -> None:
    result = pair_return(100, 110, 100, 110, [0.001, 0.002], cost_bps=31)

    assert abs(result["basis_return"]) < 1e-12
    assert abs(result["net_return"] - (-0.0001)) < 1e-12


def test_pair_return_preserves_basis_and_funding_attribution() -> None:
    result = pair_return(100, 105, 100, 103, [-0.001], cost_bps=0)

    assert abs(result["basis_return"] - 0.02) < 1e-12
    assert abs(result["funding_received"] + 0.001) < 1e-12
    assert abs(result["net_return"] - 0.019) < 1e-12


def test_cross_market_parity_gate_quarantines_corrupted_mapping() -> None:
    assert _basis_ok(100, 102)
    assert not _basis_ok(1.16, 47.57)
