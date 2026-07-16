from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

import scripts.materialize_horizontal_breakout_long_72h_funding_v1 as builder
import scripts.run_horizontal_breakout_long_72h_sealed_v1 as scorer


def _history() -> dict[str, list[tuple[int, float]]]:
    first = scorer.HOLDOUT_START_MS - scorer.MAX_FUNDING_GAP_MS
    last = scorer.HOLDOUT_END_MS + scorer.MAX_FUNDING_GAP_MS
    result: dict[str, list[tuple[int, float]]] = {}
    for symbol_index, symbol in enumerate(scorer.EXPECTED_SYMBOLS):
        rows = []
        ts = first
        while ts <= last:
            rows.append((ts, 0.0001 + symbol_index * 0.0000001))
            ts += scorer.MAX_FUNDING_GAP_MS
        result[symbol] = rows
    return result


class FakeBybit:
    def __init__(self) -> None:
        self.rows = _history()
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> dict[str, object]:
        assert timeout > 0
        self.calls.append(url)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        symbol = query["symbol"][0]
        end_time = int(query["endTime"][0])
        limit = int(query["limit"][0])
        selected = sorted(
            (row for row in self.rows[symbol] if row[0] <= end_time),
            reverse=True,
        )[:limit]
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "fundingRate": format(rate, ".10f"),
                        "fundingRateTimestamp": str(ts),
                    }
                    for ts, rate in selected
                ],
            },
            "retExtInfo": {},
            "time": scorer.HOLDOUT_END_MS,
        }


def test_public_url_is_exact_get_surface_without_credentials() -> None:
    url = builder.build_public_url("BTCUSDT", builder.FIRST_END_TIME)
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.bybit.com"
    assert parsed.path == "/v5/market/funding/history"
    assert query == {
        "category": ["linear"],
        "symbol": ["BTCUSDT"],
        "endTime": [str(builder.FIRST_END_TIME)],
        "limit": ["200"],
    }
    assert "key" not in url.lower()
    assert "sign" not in url.lower()
    assert "startTime" not in query


def test_materializer_resumes_and_final_manifest_replays_raw_pages(tmp_path: Path) -> None:
    fake = FakeBybit()
    work = tmp_path / "funding"
    manifest = work / "manifest.json"

    partial = builder.materialize(
        tmp_path,
        work,
        manifest,
        fetcher=fake,
        retries=0,
        page_budget=1,
        request_interval_seconds=0,
    )
    assert partial["status"] == "INCOMPLETE_RESUMABLE"
    assert partial["network_requests_this_run"] == 1
    assert not manifest.exists()

    complete = builder.materialize(
        tmp_path,
        work,
        manifest,
        fetcher=fake,
        retries=0,
        request_interval_seconds=0,
    )
    assert complete["status"] == "COMPLETE"
    assert complete["symbols_complete"] == 13
    assert complete["api_pages"] == 26
    assert complete["network_requests_this_run"] == 25
    assert complete["price_snapshots_opened"] == 0
    assert complete["performance_computed"] is False
    assert len(fake.calls) == 26

    gate = {
        "manifest_path": manifest.relative_to(tmp_path).as_posix(),
        "manifest_sha256": scorer.sha256_file(manifest),
    }
    histories, validation = scorer.validate_funding_manifest(tmp_path, gate)
    assert len(histories) == 13
    assert validation["symbols_complete"] == 13

    reused = builder.materialize(
        tmp_path,
        work,
        manifest,
        fetcher=lambda *_: pytest.fail("complete manifest must not use network"),
        retries=0,
        request_interval_seconds=0,
    )
    assert reused["status"] == "COMPLETE_REUSED"
    assert reused["network_requests_this_run"] == 0


def test_tampered_raw_page_blocks_reuse(tmp_path: Path) -> None:
    fake = FakeBybit()
    work = tmp_path / "funding"
    manifest = work / "manifest.json"
    result = builder.materialize(
        tmp_path,
        work,
        manifest,
        fetcher=fake,
        retries=0,
        request_interval_seconds=0,
    )
    assert result["status"] == "COMPLETE"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    first_page = tmp_path / payload["histories"]["BTCUSDT"]["api_pages"][0]["raw_path"]
    first_page.write_text("{}\n", encoding="utf-8")

    with pytest.raises(scorer.SealedScoringError, match="raw funding page hash"):
        builder.materialize(
            tmp_path,
            work,
            manifest,
            fetcher=lambda *_: pytest.fail("tampered evidence must not refetch silently"),
            retries=0,
            request_interval_seconds=0,
        )


def test_gap_failure_never_publishes_final_manifest(tmp_path: Path) -> None:
    fake = FakeBybit()
    # One missing in-window 8h event creates a 16h gap while both sealed
    # boundaries remain bracketed.  Candidate validation must fail before the
    # immutable final name is linked.
    del fake.rows[scorer.EXPECTED_SYMBOLS[0]][100]
    work = tmp_path / "funding"
    manifest = work / "manifest.json"

    with pytest.raises(scorer.SealedScoringError, match="funding gap exceeds 8h"):
        builder.materialize(
            tmp_path,
            work,
            manifest,
            fetcher=fake,
            retries=0,
            request_interval_seconds=0,
        )

    assert not manifest.exists()


def test_builder_source_has_no_private_live_or_price_access() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "api_key",
        "api_secret",
        "Authorization",
        "load_dotenv",
        "os.environ",
        "place_order",
        "smart_pump_reversal_bot",
        "load_uniform_symbol_rows",
        "data_cache/immutable/pump_exhaustion",
    ):
        assert forbidden not in source
