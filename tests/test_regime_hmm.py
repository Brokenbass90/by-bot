"""Tests for bot.regime_hmm — sticky probabilistic regime + trade gate."""
import random
from bot.regime_hmm import regime_probs, regime_gate, RegimeState, STATES


def _uptrend(n=120, start=100.0, slope=0.6):
    return [[i, start + i * slope, start + i * slope + 0.3, start + i * slope - 0.3,
             start + i * slope + 0.1, 1000] for i in range(n)]


def _flat(n=120):
    random.seed(1); r = []; p = 100.0
    for i in range(n):
        c = 100 + random.uniform(-0.5, 0.5)
        r.append([i, p, max(p, c) + 0.2, min(p, c) - 0.2, c, 1000]); p = c
    return r


def _expansion():
    rows = [[i, 100, 100.2, 99.8, 100, 1000] for i in range(100)]
    for j in range(15):
        p = 100 + (1 if j % 2 else -1) * 3
        rows.append([100 + j, 100, 105, 95, p, 1000])
    return rows


def test_insufficient_data():
    st = regime_probs(_uptrend(10))
    assert isinstance(st, RegimeState) and st.ok is False


def test_probabilities_sum_to_one():
    st = regime_probs(_uptrend())
    assert abs(sum(st.probs.values()) - 1.0) < 1e-3
    assert set(st.probs) == set(STATES)


def test_uptrend_is_bull():
    assert regime_probs(_uptrend()).dominant == "bull"


def test_downtrend_is_bear():
    assert regime_probs(_uptrend(start=300, slope=-0.6)).dominant == "bear"


def test_flat_is_range():
    assert regime_probs(_flat()).dominant == "range"


def test_expansion_is_high_vol_and_gate_blocks():
    st = regime_probs(_expansion())
    assert st.dominant == "high_vol"
    g = regime_gate(st)
    assert g["allow"] is False and g["risk_scalar"] == 0.0


def test_gate_allows_normal_regime():
    g = regime_gate(regime_probs(_uptrend()))
    assert g["allow"] is True and g["risk_scalar"] > 0


def test_stickiness_biases_toward_prior():
    st = regime_probs(_flat(), prior={"bull": 0.9, "bear": 0.03, "range": 0.03, "high_vol": 0.04})
    # with a strong bull prior, bull prob is lifted vs no prior
    assert st.probs["bull"] > regime_probs(_flat()).probs["bull"]
