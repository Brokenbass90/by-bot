from scripts.materialize_bybit_daily_preholdout import fetch_daily, materialize


def test_daily_fetch_is_sorted_and_strictly_before_holdout():
    pages = [
        [[3000, "3", "4", "2", "3.5", "10", "35"], [2000, "2", "3", "1", "2.5", "10", "25"]],
        [[1000, "1", "2", "0.5", "1.5", "10", "15"]],
    ]
    calls = []

    def fake(_url, params):
        calls.append(params)
        rows = pages[0] if int(params["end"]) >= 3999 else pages[1]
        return {"retCode": 0, "result": {"list": rows}}

    rows = fetch_daily("AAAUSDT", start_ms=1000, end_exclusive_ms=4000, get_json=fake)
    assert [row["ts_ms"] for row in rows] == [1000, 2000, 3000]
    assert all(row["ts_ms"] < 4000 for row in rows)


def test_materializer_records_zero_holdout_rows(tmp_path):
    def fake(_url, _params):
        return {"retCode": 0, "result": {"list": [[1000, "1", "2", "0.5", "1.5", "10", "15"]]}}

    status = materialize(
        ["AAAUSDT"], out_dir=tmp_path / "daily", start_ms=1000,
        end_exclusive_ms=2000, min_free_gb=0, sleep_seconds=0, get_json=fake,
    )
    assert status["state"] == "complete"
    assert status["sealed_holdout_rows_decoded"] == 0
    assert status["failed"] == {}
