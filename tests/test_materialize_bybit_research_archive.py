from pathlib import Path

from scripts.materialize_bybit_research_archive import build_archive


def test_public_archive_is_resumable_and_records_listing_intervals(tmp_path: Path):
    calls = {"funding": 0}

    def fake_get(url, params):
        if url.endswith("/instruments-info"):
            status = params["status"]
            rows = []
            if status == "Trading":
                rows = [{
                    "symbol": "AAAUSDT",
                    "status": "Trading",
                    "contractType": "LinearPerpetual",
                    "symbolType": "innovation",
                    "launchTime": "1672531200000",
                    "deliveryTime": "0",
                    "fundingInterval": 480,
                }]
            return {"retCode": 0, "result": {"list": rows, "nextPageCursor": ""}}
        if url.endswith("/funding/history"):
            calls["funding"] += 1
            if calls["funding"] == 1:
                return {"retCode": 0, "result": {"list": [
                    {"fundingRateTimestamp": "1672588800000", "fundingRate": "0.0001"},
                    {"fundingRateTimestamp": "1672560000000", "fundingRate": "0.0002"},
                ]}}
            return {"retCode": 0, "result": {"list": []}}
        raise AssertionError(url)

    kwargs = dict(
        symbols=["AAAUSDT", "MISSINGUSDT"],
        out_dir=tmp_path / "archive",
        start_ms=1_672_531_200_000,
        as_of_ms=1_672_617_600_000,
        min_free_gb=0,
        sleep_seconds=0,
        get_json=fake_get,
    )
    first = build_archive(**kwargs)
    assert first["completed"] == ["AAAUSDT"]
    assert first["missing_instrument"] == ["MISSINGUSDT"]
    assert (tmp_path / "archive/listing_intervals.json").is_file()
    assert (tmp_path / "archive/funding/AAAUSDT.json").is_file()

    funding_calls = calls["funding"]
    second = build_archive(**kwargs)
    assert second["skipped_current"] == ["AAAUSDT"]
    assert calls["funding"] == funding_calls
