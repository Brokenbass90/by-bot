from scripts import funding_positioning_v4_shadow as shadow
from scripts.funding_positioning_v4_shadow import _signal, _strict_fill


def test_signal_uses_only_prior_history_and_strict_tail():
    history = [(i, 0.0001) for i in range(90)]
    history.append((90, 0.0001))
    assert _signal(history)["side"] == 0
    history[-1] = (90, 0.0002)
    assert _signal(history)["side"] == -1


def test_strict_fill_does_not_count_touch():
    rows = [
        [1, 100, 101, 99.95, 100, 1],
        [2, 100, 101, 99.94, 100, 1],
    ]
    assert _strict_fill(rows, side=1, limit_price=99.95) == 2
    assert _strict_fill(rows[:1], side=1, limit_price=99.95) is None


def test_discover_fail_closes_second_active_trial_for_same_symbol(tmp_path, monkeypatch):
    def history(symbol, limit=100):
        rows = [(i, 0.0001) for i in range(90)]
        rows.append((100 if symbol == "BTCUSDT" else 101, 0.0002))
        return rows

    monkeypatch.setattr(shadow, "_funding_history", history)
    monkeypatch.setattr(shadow, "_reference_open", lambda _symbol, _ts: 100.0)
    state = {
        "started_at_ms": 0,
        "trials": {
            "existing": {
                "trial_id": "existing",
                "symbol": "BTCUSDT",
                "event_ts": 1,
                "side": -1,
                "status": "open",
            }
        },
    }
    shadow._discover(
        state,
        ledger=tmp_path / "ledger.jsonl",
        now_ms=200,
        offset_bps=5.0,
        timeout_minutes=60,
        max_positions=3,
        symbols=("BTCUSDT", "ETHUSDT"),
        universe_sha256="u",
    )
    created = [row for key, row in state["trials"].items() if key != "existing"]
    status_by_symbol = {row["symbol"]: row["status"] for row in created}
    assert status_by_symbol == {
        "BTCUSDT": "symbol_conflict_reject",
        "ETHUSDT": "pending_fill",
    }


def test_summary_quarantines_pre_contract_trials():
    state = {
        "started_at_ms": 1,
        "evidence_epoch_ms": 100,
        "evidence_contract": shadow.EVIDENCE_CONTRACT,
        "trials": {
            "legacy": {
                "event_ts": 99,
                "status": "closed",
                "side": 1,
                "symbol": "OLDUSDT",
                "net_raw_return": 99.0,
            },
            "valid": {
                "event_ts": 100,
                "status": "closed",
                "side": 1,
                "symbol": "BTCUSDT",
                "net_raw_return": 0.01,
                "net_btc_hedged_return": 0.005,
            },
        },
    }
    result = shadow._summary(state, symbols=("BTCUSDT",), universe_sha256="u")
    assert result["legacy_trials_quarantined"] == 1
    assert result["closed"] == 1
    assert result["mean_closed_raw_net_bps"] == 100.0
    assert result["mean_closed_btc_hedged_net_bps"] == 50.0
