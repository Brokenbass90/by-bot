from research_lab.result_receipt_validator import validate_receipt


def test_validator_accepts_consistent_fx_ledger() -> None:
    verdict = {"best_stress": {"trades": 1, "net_bps": 8.0, "fold_net_bps": [0, 0, 0, 8]}}
    trades = [{
        "symbol": "EURUSD", "entry_ts": "1", "exit_ts": "2", "side": "long",
        "average_entry": "1.0", "exit_price": "1.001", "cost_bps": "2.0", "pnl_bps": "8.0",
    }]

    receipt = validate_receipt(verdict, trades)

    assert receipt["passed"]


def test_validator_rejects_overlong_and_mispriced_pair_trade() -> None:
    verdict = {"best": {"trades": 1, "net_bps": 1.0, "max_hold_days": 5, "fold_net_bps": [0, 0, 0, 1]}}
    trades = [{
        "pair": "A/B", "entry_day": "1", "exit_day": "10", "held_days": "9",
        "gross_bps": "10", "cost_bps": "4", "pnl_bps": "1",
    }]

    receipt = validate_receipt(verdict, trades)

    assert not receipt["passed"]
    assert receipt["arithmetic_failures"] == 1
    assert receipt["lifecycle_failures"] == 1
