from scripts import fetch_bybit_universe as fetcher


def _bar(ts: int) -> list[str]:
    return [str(ts), "1", "2", "0.5", "1.5", "10"]


def test_klines_pages_through_bounded_forward_windows(monkeypatch):
    start = 1_000_000
    calls: list[dict] = []

    monkeypatch.setattr(fetcher, "PAGE", 3)
    monkeypatch.setattr(fetcher, "PAUSE", 0.0)

    def fake_get(path: str, params: dict) -> dict:
        calls.append(dict(params))
        timestamps = list(
            range(int(params["start"]), int(params["end"]) + 1, fetcher.BAR_MS)
        )
        return {"list": [_bar(ts) for ts in reversed(timestamps)]}

    monkeypatch.setattr(fetcher, "get", fake_get)
    end = start + 7 * fetcher.BAR_MS

    rows = fetcher.klines("BTCUSDT", start, end)

    assert [row[0] for row in rows] == [start + i * fetcher.BAR_MS for i in range(8)]
    assert len(calls) == 3
    assert calls[0]["start"] == start
    assert calls[0]["end"] == start + 2 * fetcher.BAR_MS
    assert calls[-1]["end"] == end


def test_klines_rejects_api_page_outside_requested_window(monkeypatch):
    monkeypatch.setattr(fetcher, "PAUSE", 0.0)
    monkeypatch.setattr(
        fetcher,
        "get",
        lambda path, params: {"list": [_bar(int(params["end"]) + fetcher.BAR_MS)]},
    )

    try:
        fetcher.klines("BTCUSDT", 1_000_000, 1_000_000 + fetcher.BAR_MS)
    except RuntimeError as exc:
        assert "outside requested window" in str(exc)
    else:
        raise AssertionError("out-of-window page must fail closed")
