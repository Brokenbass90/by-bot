from __future__ import annotations

import json

import pytest

from backtest.run_portfolio import _load_symbol_base


def _rows(start_ms: int, count: int, step_ms: int = 300_000) -> list[list[float]]:
    return [
        [start_ms + idx * step_ms, 100.0, 101.0, 99.0, 100.5, 10.0]
        for idx in range(count)
    ]


def test_exact_cache_requirement_rejects_missing_slice(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_CACHE_ONLY", "1")
    monkeypatch.setenv("BACKTEST_REQUIRE_EXACT_CACHE", "1")

    with pytest.raises(FileNotFoundError, match="Exact cached slice required"):
        _load_symbol_base(
            "BTCUSDT",
            1_700_000_000,
            1_700_003_600,
            bybit_base="https://example.invalid",
            cache_dir=tmp_path,
        )


def test_exact_cache_requirement_rejects_gapped_slice(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_CACHE_ONLY", "1")
    monkeypatch.setenv("BACKTEST_REQUIRE_EXACT_CACHE", "1")
    start_ts = 1_700_000_000
    end_ts = start_ts + 3_600
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    rows = _rows(start_ms, 12)
    rows.pop(5)
    path = tmp_path / f"BTCUSDT_5_{start_ms}_{end_ms}.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ValueError, match="Exact cache validation failed"):
        _load_symbol_base(
            "BTCUSDT",
            start_ts,
            end_ts,
            bybit_base="https://example.invalid",
            cache_dir=tmp_path,
        )


def test_exact_cache_requirement_accepts_contiguous_slice(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_CACHE_ONLY", "1")
    monkeypatch.setenv("BACKTEST_REQUIRE_EXACT_CACHE", "1")
    start_ts = 1_700_000_000
    end_ts = start_ts + 3_600
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    path = tmp_path / f"BTCUSDT_5_{start_ms}_{end_ms}.json"
    path.write_text(json.dumps(_rows(start_ms, 12)), encoding="utf-8")

    rows = _load_symbol_base(
        "BTCUSDT",
        start_ts,
        end_ts,
        bybit_base="https://example.invalid",
        cache_dir=tmp_path,
    )

    assert len(rows) == 12
