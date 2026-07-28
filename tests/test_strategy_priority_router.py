from bot.strategy_priority_router import StrategyCandidate, priority_score, rank_candidates


def _candidate(
    decision_id: str,
    *,
    symbol: str,
    side: str = "long",
    expected: float = 0.2,
    regime: float = 1.0,
    health: float = 1.0,
    cluster: str = "",
    authorized: bool = True,
    ts: int = 1_000,
) -> StrategyCandidate:
    return StrategyCandidate(
        decision_id=decision_id,
        ts=ts,
        symbol=symbol,
        strategy=f"strategy_{decision_id}",
        side=side,
        expected_net_r=expected,
        regime_fit=regime,
        health_mult=health,
        beta_cluster=cluster,
        money_authorized=authorized,
    )


def test_score_discounts_expected_r_but_never_creates_edge():
    good = _candidate("good", symbol="BTCUSDT", expected=0.4, regime=0.5)
    bad = _candidate("bad", symbol="ETHUSDT", expected=-0.4)
    assert priority_score(good) == 0.15
    assert priority_score(bad) == 0.0


def test_highest_ev_gets_slot_not_first_input():
    low = _candidate("low", symbol="BTCUSDT", expected=0.1)
    high = _candidate("high", symbol="ETHUSDT", expected=0.5)
    decisions = rank_candidates([low, high], now_ts=1_010, max_slots=1)
    assert decisions[0].candidate.decision_id == "high"
    assert decisions[0].selected is True
    assert {d.reason for d in decisions} == {"selected", "portfolio_slots_full"}


def test_money_mode_requires_external_authorization():
    candidate = _candidate("shadow_only", symbol="BTCUSDT", authorized=False)
    shadow = rank_candidates([candidate], now_ts=1_010, mode="shadow")
    money = rank_candidates([candidate], now_ts=1_010, mode="money")
    assert shadow[0].selected is True
    assert money[0].selected is False
    assert money[0].reason == "money_not_authorized"


def test_symbol_side_and_beta_cluster_caps_are_enforced():
    candidates = [
        _candidate("best", symbol="BTCUSDT", side="long", expected=0.5, cluster="crypto_beta_long"),
        _candidate("same_symbol", symbol="BTCUSDT", side="short", expected=0.4),
        _candidate("same_cluster", symbol="ETHUSDT", side="long", expected=0.3, cluster="crypto_beta_long"),
        _candidate("independent", symbol="XAUUSD", side="short", expected=0.2, cluster="gold_short"),
    ]
    decisions = rank_candidates(candidates, now_ts=1_010, max_slots=3, max_same_side=2, max_same_cluster=1)
    by_id = {d.candidate.decision_id: d for d in decisions}
    assert by_id["best"].selected is True
    assert by_id["same_symbol"].reason == "symbol_overlap"
    assert by_id["same_cluster"].reason == "beta_cluster_cap"
    assert by_id["independent"].selected is True


def test_hard_gate_reasons_are_replayable():
    candidates = [
        _candidate("stale", symbol="BTCUSDT", ts=1_000),
        _candidate("unhealthy", symbol="ETHUSDT", health=0.0, ts=1_900),
        _candidate("no_edge", symbol="SOLUSDT", expected=0.0, ts=1_900),
    ]
    decisions = rank_candidates(candidates, now_ts=2_000, max_age_sec=300)
    reasons = {d.candidate.decision_id: d.reason for d in decisions}
    assert reasons == {
        "stale": "stale_or_future_candidate",
        "unhealthy": "strategy_health_block",
        "no_edge": "non_positive_expected_net_r",
    }

