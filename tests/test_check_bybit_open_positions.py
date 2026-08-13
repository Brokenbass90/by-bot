from scripts.check_bybit_open_positions import _position_snapshot


def test_api_error_never_looks_flat():
    result = _position_snapshot({"retCode": 33004, "retMsg": "expired", "result": {"list": []}})
    assert result["broker_state"] == "NOT_CONFIRMED"
    assert result["open_position_count"] is None
    assert result["positions"] is None


def test_successful_empty_snapshot_is_confirmed_flat():
    result = _position_snapshot({"retCode": 0, "retMsg": "OK", "result": {"list": []}})
    assert result["broker_state"] == "CONFIRMED"
    assert result["open_position_count"] == 0
    assert result["positions"] == []
