from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.materialize_att1_sbr1_reserved_m5_v1 import (
    END_EXCLUSIVE_MS,
    EXPECTED_ROWS_PER_SYMBOL,
    START_MS,
    START_UTC,
    END_UTC_EXCLUSIVE,
    MaterializationError,
    canonical_sha,
    fetch_m5,
    materialize,
    main,
    utc_ms,
    validate_production_paths,
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


def test_direct_public_fetch_requires_acknowledgement_before_get() -> None:
    calls = 0

    def get_json(_url: str, _params: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"retCode": 0, "result": {"list": []}}

    with pytest.raises(MaterializationError, match="allow-reserved-public-network"):
        fetch_m5("BTCUSDT", get_json=get_json)
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
    manifest_before_reuse = manifest_path.read_bytes()

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
    assert manifest_path.read_bytes() == manifest_before_reuse


@pytest.mark.parametrize(
    ("target", "field"),
    [("payload", "private_trade_result"), ("record", "performance_bps")],
)
def test_reuse_rejects_extra_payload_or_record_fields_even_with_recomputed_checksum(
    tmp_path: Path, target: str, field: str,
) -> None:
    candidate = _candidate(tmp_path / "candidate.json")
    payload_dir = tmp_path / "payloads"
    materialize(
        out_dir=payload_dir, manifest_path=tmp_path / "manifest.json",
        candidate_manifest=candidate, allow_reserved_public_network=True,
        fetcher=lambda *_args, **_kwargs: _rows(),
    )
    path = payload_dir / "BTCUSDT.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if target == "payload":
        payload[field] = 1
    else:
        payload["records"][0][field] = 1
        payload["records_sha256"] = canonical_sha(payload["records"])
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MaterializationError, match="corrupt or drifted"):
        materialize(
            out_dir=payload_dir, manifest_path=tmp_path / "manifest.json",
            candidate_manifest=candidate, allow_reserved_public_network=False,
            fetcher=lambda *_args, **_kwargs: _rows(),
        )


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
    assert utc_ms(START_UTC) == 1_759_276_800_000
    assert utc_ms(END_UTC_EXCLUSIVE) == 1_782_864_000_000
    assert END_EXCLUSIVE_MS - START_MS == 273 * 86_400_000
    assert EXPECTED_ROWS_PER_SYMBOL == 273 * 288


def test_production_fixed_path_rejects_symlink_ancestor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.materialize_att1_sbr1_reserved_m5_v1 as module

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "unsafe-link"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "DEFAULT_OUT_DIR", link / "payloads")
    monkeypatch.setattr(module, "DEFAULT_MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(module, "DEFAULT_CANDIDATE_MANIFEST", tmp_path / "candidate.json")
    with pytest.raises(MaterializationError, match="contains symlink"):
        validate_production_paths()


def test_cli_rejects_destination_override_before_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["materializer", "--out-dir", "/tmp/not-allowed"])
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == 2
