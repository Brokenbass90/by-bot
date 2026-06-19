from __future__ import annotations

import json

from bot.unsupported_symbols import (
    is_unsupported_symbol_error,
    load_quarantined_symbols,
    quarantine_symbol,
)


def test_detects_bybit_unsupported_symbol_error() -> None:
    error = "Bybit POST error: {'retCode': 10001, 'retMsg': 'symbol is not supported CLUSDT'}"
    assert is_unsupported_symbol_error(error) is True
    assert is_unsupported_symbol_error("temporary timeout") is False


def test_quarantine_persists_without_raw_exchange_error(tmp_path) -> None:
    path = tmp_path / "unsupported_symbols.json"
    active = quarantine_symbol(path, "clusdt", now_ts=1_000.0)

    assert active == {"CLUSDT"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbols"]["CLUSDT"]["reason"] == "exchange_unsupported"
    assert "retMsg" not in path.read_text(encoding="utf-8")


def test_expired_quarantine_is_not_loaded(tmp_path) -> None:
    path = tmp_path / "unsupported_symbols.json"
    quarantine_symbol(path, "CLUSDT", now_ts=1_000.0)

    assert load_quarantined_symbols(path, now_ts=1_100.0, ttl_sec=200) == {"CLUSDT"}
    assert load_quarantined_symbols(path, now_ts=1_300.0, ttl_sec=200) == set()
