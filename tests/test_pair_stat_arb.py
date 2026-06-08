"""Tests for strategies.pair_stat_arb_v1 (Opus 2026-06-08)."""
import math, random, statistics
from strategies.pair_stat_arb_v1 import (
    PairStatArbV1, PairConfig, compute_spread, half_life, returns,
)


def gen_cointegrated(n=200, beta=1.0, seed=0):
    rng = random.Random(seed)
    logb = [math.log(30000.0)]
    for _ in range(n - 1):
        logb.append(logb[-1] + rng.gauss(0, 0.01))
    spread = [0.0]
    for _ in range(n - 1):
        spread.append(0.8 * spread[-1] + rng.gauss(0, 0.005))
    loga = [beta * lb + s + math.log(0.05) for lb, s in zip(logb, spread)]
    return [math.exp(x) for x in loga], [math.exp(x) for x in logb]


def gen_independent(n=200, seed=1):
    rng = random.Random(seed)
    a = [math.log(2000.0)]; b = [math.log(30000.0)]
    for _ in range(n - 1):
        a.append(a[-1] + rng.gauss(0, 0.01))
        b.append(b[-1] + rng.gauss(0, 0.01))
    return [math.exp(x) for x in a], [math.exp(x) for x in b]


def test_cointegrated_is_tradeable():
    a, b = gen_cointegrated()
    d = PairStatArbV1(PairConfig(lookback=168)).diagnostics(a, b)
    assert d["tradeable"], d
    assert math.isfinite(d["half_life"]) and d["half_life"] <= 72
    assert abs(d["beta"] - 1.0) < 0.3
    assert abs(d["corr"]) >= 0.6


def test_independent_is_not_tradeable():
    a, b = gen_independent()
    d = PairStatArbV1(PairConfig(lookback=168)).diagnostics(a, b)
    assert not d["tradeable"], d


def test_entry_legs_when_a_is_rich():
    a, b = gen_cointegrated()
    _, _, spread = compute_spread(a[-168:], b[-168:])
    sd = statistics.pstdev(spread)
    a2 = list(a)
    a2[-1] = a[-1] * math.exp(3.0 * sd)  # push A up -> spread up -> z>0
    s = PairStatArbV1(PairConfig(lookback=168, entry_z=1.5, stop_z=10.0))
    sig = s.signal("ETHUSDT", "BTCUSDT", a2, b)
    assert sig is not None, s.last_reason
    assert sig.z > 0
    assert sig.long_symbol == "BTCUSDT" and sig.short_symbol == "ETHUSDT"


def test_entry_legs_when_a_is_cheap():
    a, b = gen_cointegrated()
    _, _, spread = compute_spread(a[-168:], b[-168:])
    sd = statistics.pstdev(spread)
    a2 = list(a)
    a2[-1] = a[-1] * math.exp(-3.0 * sd)  # push A down -> spread down -> z<0
    s = PairStatArbV1(PairConfig(lookback=168, entry_z=1.5, stop_z=10.0))
    sig = s.signal("ETHUSDT", "BTCUSDT", a2, b)
    assert sig is not None, s.last_reason
    assert sig.z < 0
    assert sig.long_symbol == "ETHUSDT" and sig.short_symbol == "BTCUSDT"


def test_no_entry_when_z_small():
    a, b = gen_cointegrated()
    s = PairStatArbV1(PairConfig(lookback=168, entry_z=2.0))
    sig = s.signal("ETHUSDT", "BTCUSDT", a, b)  # unshocked -> z near 0
    assert sig is None
    assert "z_small" in s.last_reason or s.last_reason == "ok"


def test_blowout_returns_none():
    a, b = gen_cointegrated()
    _, _, spread = compute_spread(a[-168:], b[-168:])
    sd = statistics.pstdev(spread)
    a2 = list(a)
    a2[-1] = a[-1] * math.exp(12.0 * sd)  # huge -> beyond stop_z
    s = PairStatArbV1(PairConfig(lookback=168, entry_z=2.0, stop_z=3.5))
    sig = s.signal("ETHUSDT", "BTCUSDT", a2, b)
    assert sig is None
    assert "blowout" in s.last_reason


def test_history_short():
    s = PairStatArbV1(PairConfig(lookback=168))
    d = s.diagnostics([100, 101, 102], [200, 201, 202])
    assert not d["tradeable"] and "history_short" in d["reason"]


def test_should_exit():
    s = PairStatArbV1(PairConfig(exit_z=0.5, stop_z=3.5))
    assert s.should_exit(0.3)[0] is True       # reverted
    assert s.should_exit(4.0)[0] is True       # stop
    assert s.should_exit(2.0)[0] is False      # still open


def test_half_life_finite_for_mean_reverting():
    rng = random.Random(5)
    s = [0.0]
    for _ in range(300):
        s.append(0.7 * s[-1] + rng.gauss(0, 0.01))
    assert math.isfinite(half_life(s)) and half_life(s) > 0
