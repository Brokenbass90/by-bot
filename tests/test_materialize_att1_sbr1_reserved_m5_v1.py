from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.materialize_att1_sbr1_reserved_m5_v1 import (
    END_EXCLUSIVE_MS,
    EXPECTED_ROWS_PER_SYMBOL,
    START_MS,
    MaterializationError,
    materialize,
    validate_rows,
)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT"]


def _rows(*, count: int = EXPECTED_ROWS_PER_SYMBOL) -> list[dict[str, object]]:
    return [
        {
            "ts_ms": START_MS + index * 300_000,
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 1.0,
            "turnover": 11.0,
        }
        for index in range(count)
    ]


def _candidate(path: Path) -> Path:
    path.write_text(json.dumps({"universe": SYMBOLS}), encoding="utf-8")
    return path


def test_validate_rows_rejects_gap_duplicate_and_bad_ohlc() -> None:
    rows = _rows()
    rows[5]["ts_ms"] = START_MS + 5 * 300_000 + 1
    with pytest.raises(MaterializationError, match="contiguous"):
        validate_rows(rows, symbol="BTCUSDT")

    duplicate = _rows()
    duplicate[5]["ts_ms"] = duplicate[4]["ts_ms"]
    with pytest.raises(MaterializationError, match="unique"):
        validate_rows(duplicate, symbol="BTCUSDT")

    bad_ohlc = _rows()
    bad_ohlc[0]["high"] = 1.0
    with pytest.raises(MaterializationError, match="OHLC"):
        validate_rows(bad_ohlc, symbol="BTCUSDT")


def test_materialize_requires_acknowledgement_before_fetch(tmp_path: Path) -> None:
    calls = 0

    def fetcher(_symbol: str, **_kwargs: object) -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        return _rows()

    with pytest.raises(MaterializationError, match="allow-reserved-public-network"):
        materialize(
            out_dir=tmp_path / "payloads",
            manifest_path=tmp_path / "manifest.json",
            candidate_manifest=_candidate(tmp_path / "candidate.json"),
            allow_reserved_public_network=False,
            fetcher=fetcher,
        )
    assert calls == 0


def test_complete_payload_is_reused_without_network_and_manifest_is_exact(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "candidate.json")
    calls: list[str] = []

    def fetcher(symbol: str, **_kwargs: object) -> list[dict[str, object]]:
        calls.append(symbol)
        return _rows()

    payload_dir = tmp_path / "payloads"
    manifest_path = tmp_path / "manifest.json"
    first = materialize(
        out_dir=payload_dir,
        manifest_path=manifest_path,
        candidate_manifest=candidate,
        allow_reserved_public_network=True,
        fetcher=fetcher,
    )
    assert calls == SYMBOLS
    assert [row["symbol"] for row in first["inputs"]] == SYMBOLS
    assert first["window"] == {
        "start_utc": "2025-10-01T00:00:00Z",
        "end_utc_exclusive": "2026-07-01T00:00:00Z",
    }
    assert first["market_rows_decoded_by_preflight"] == 0
    assert first["performance_computed"] is False
    assert first["money_authority"] is False
    assert all(set(row) == {"symbol", "source_path", "sha256", "bytes", "rows", "first_ts_ms", "last_ts_ms"} for row in first["inputs"])
    assert all("price" not in json.dumps(row).lower() for row in first["inputs"])

    def no_network(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("network must not be used for verified reuse")

    reused = materialize(
        out_dir=payload_dir,
        manifest_path=manifest_path,
        candidate_manifest=candidate,
        allow_reserved_public_network=False,
        fetcher=no_network,
    )
    assert reused["inputs"] == first["inputs"]


def test_interruption_keeps_completed_payload_and_writes_no_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"

    def fetcher(symbol: str, **_kwargs: object) -> list[dict[str, object]]:
        if symbol == "ETHUSDT":
            raise MaterializationError("synthetic interruption")
        return _rows()

    with pytest.raises(MaterializationError, match="synthetic interruption"):
        materialize(
            out_dir=tmp_path / "payloads",
            manifest_path=manifest_path,
            candidate_manifest=_candidate(tmp_path / "candidate.json"),
            allow_reserved_public_network=True,
            fetcher=fetcher,
        )
    assert (tmp_path / "payloads" / "BTCUSDT.json").is_file()
    assert not manifest_path.exists()


def test_corrupt_existing_payload_fails_closed_without_acknowledgement(tmp_path: Path) -> None:
    payload_dir = tmp_path / "payloads"
    payload_dir.mkdir()
    (payload_dir / "BTCUSDT.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MaterializationError, match="corrupt or drifted"):
        materialize(
            out_dir=payload_dir,
            manifest_path=tmp_path / "manifest.json",
            candidate_manifest=_candidate(tmp_path / "candidate.json"),
            allow_reserved_public_network=False,
            fetcher=lambda *_args, **_kwargs: _rows(),
        )


def test_exact_reserved_constants_are_closed_interval_boundaries() -> None:
    assert END_EXCLUSIVE_MS - START_MS == 273 * 86_400_000
    assert EXPECTED_ROWS_PER_SYMBOL == 273 * 288
