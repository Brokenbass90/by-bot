from __future__ import annotations

from bot.bybit_time_sync import BybitClock, is_auth_error, is_timestamp_error


def test_timestamp_error_is_not_auth_failure() -> None:
    payload = {
        "retCode": 10002,
        "retMsg": (
            "invalid request, please check your server timestamp or recv_window param: "
            "req_timestamp[1785468532818],server_timestamp[1785468547992],recv_window[5000]"
        ),
        "time": 1785468547992,
    }
    assert is_timestamp_error(payload) is True
    assert is_auth_error(payload) is False


def test_clock_learns_bounded_server_offset() -> None:
    clock = BybitClock(now_ms=lambda: 1_000_000)
    assert clock.learn({"time": 1_015_250}) is True
    assert clock.offset_ms == 15_250
    assert clock.timestamp() == "1015250"


def test_clock_rejects_implausible_or_missing_time() -> None:
    clock = BybitClock(now_ms=lambda: 1_000_000)
    assert clock.learn({"time": 2_000_000}) is False
    assert clock.learn({}) is False
    assert clock.offset_ms == 0


def test_real_auth_failures_remain_auth_failures() -> None:
    assert is_auth_error({"retCode": 10003, "retMsg": "API key is invalid"}) is True
    assert is_auth_error({"retCode": 1, "retMsg": "signature mismatch"}) is True

