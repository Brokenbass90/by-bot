from scripts.materialize_bybit_5m_preholdout import fetch_5m


def test_fetch_5m_is_sorted_unique_and_end_exclusive():
    def fake(_url, params):
        if int(params["end"]) >= 3999:
            rows = [[3000, "3", "4", "2", "3.5", "10", "35"],
                    [2000, "2", "3", "1", "2.5", "10", "25"]]
        else:
            rows = [[1000, "1", "2", ".5", "1.5", "10", "15"]]
        return {"retCode": 0, "result": {"list": rows}}

    rows = fetch_5m("ETHUSDT", start_ms=1000, end_exclusive_ms=4000, get_json=fake)
    assert [row["ts_ms"] for row in rows] == [1000, 2000, 3000]
