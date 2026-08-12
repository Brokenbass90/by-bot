from scripts.check_bybit_fee_rates import fetch_fee_rate


def test_fee_receipt_converts_rates_to_bps_without_account_fields():
    def fake(_base, _key, _secret, path, params):
        assert path == "/v5/account/fee-rate"
        assert params == {"category": "linear", "symbol": "ADAUSDT"}
        return {"retCode": 0, "result": {"list": [{
            "symbol": "ADAUSDT", "makerFeeRate": "0.0002", "takerFeeRate": "0.00055",
        }]}}

    row = fetch_fee_rate(
        category="linear", symbol="ADAUSDT", getter=fake,
        base="https://example.invalid", key="unused", secret="unused",
    )
    assert row == {
        "category": "linear", "symbol": "ADAUSDT",
        "maker_fee_rate": 0.0002, "taker_fee_rate": 0.00055,
        "maker_bps": 2.0, "taker_bps": 5.5,
    }
