from __future__ import annotations

from scripts.materialize_public_market_inputs import (
    fetch_bitget_funding_history,
    fetch_bybit_funding_history,
    fetch_bybit_linear_universe,
    fetch_cross_exchange_funding,
    fetch_mexc_funding_history,
)


def test_bybit_universe_collects_closed_and_paginates() -> None:
    calls: list[dict] = []

    def fake_get(_url: str, params: dict) -> dict:
        calls.append(dict(params))
        status = params["status"]
        cursor = params.get("cursor")
        if status == "Trading" and not cursor:
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "Trading",
                            "launchTime": "1",
                            "deliveryTime": "0",
                            "quoteCoin": "USDT",
                        }
                    ],
                    "nextPageCursor": "next",
                },
            }
        if status == "Trading" and cursor == "next":
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "ETHUSDT",
                            "status": "Trading",
                            "launchTime": "2",
                            "deliveryTime": "0",
                            "quoteCoin": "USDT",
                        }
                    ],
                    "nextPageCursor": "",
                },
            }
        if status == "Closed":
            return {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "DEADUSDT",
                            "status": "Closed",
                            "launchTime": "3",
                            "deliveryTime": "4",
                            "quoteCoin": "USDT",
                        }
                    ],
                    "nextPageCursor": "",
                },
            }
        raise AssertionError(params)

    result = fetch_bybit_linear_universe(
        fake_get,
        statuses=("Trading", "Closed"),
    )

    assert result["record_count"] == 3
    assert result["status_counts"] == {"Trading": 2, "Closed": 1}
    assert [row["symbol"] for row in result["records"]] == [
        "BTCUSDT",
        "DEADUSDT",
        "ETHUSDT",
    ]
    assert len(calls) == 3


def test_funding_history_pagination_and_cutoff() -> None:
    bybit_pages = [
        [
            {"fundingRateTimestamp": "5000", "fundingRate": "0.01"},
            {"fundingRateTimestamp": "4000", "fundingRate": "0.02"},
        ],
        [
            {"fundingRateTimestamp": "3000", "fundingRate": "0.03"},
            {"fundingRateTimestamp": "2000", "fundingRate": "0.04"},
        ],
    ]
    bitget_pages = [
        [
            {"fundingTime": "5000", "fundingRate": "0.01"},
            {"fundingTime": "4000", "fundingRate": "0.02"},
        ],
        [
            {"fundingTime": "3000", "fundingRate": "0.03"},
            {"fundingTime": "2000", "fundingRate": "0.04"},
        ],
    ]

    def fake_bybit(_url: str, params: dict) -> dict:
        page = 0 if int(params["endTime"]) >= 5000 else 1
        return {"retCode": 0, "result": {"list": bybit_pages[page]}}

    def fake_bitget(_url: str, params: dict) -> dict:
        page = int(params["pageNo"]) - 1
        rows = bitget_pages[page] if page < len(bitget_pages) else []
        return {"code": "00000", "data": rows}

    bybit = fetch_bybit_funding_history(
        "BTCUSDT",
        cutoff_ms=2500,
        as_of_ms=5000,
        get_json=fake_bybit,
    )
    bitget = fetch_bitget_funding_history(
        "BTCUSDT",
        cutoff_ms=2500,
        as_of_ms=5000,
        get_json=fake_bitget,
    )

    assert [row["funding_time_ms"] for row in bybit] == [3000, 4000, 5000]
    assert [row["funding_time_ms"] for row in bitget] == [4000, 5000]


def test_cross_exchange_bundle_requires_both_venues(monkeypatch) -> None:
    def fake_bybit(symbol: str, **_kwargs):
        return [
            {
                "venue": "bybit",
                "symbol": symbol,
                "funding_time_ms": 1000 + i * 1000,
                "funding_rate": 0.0001,
            }
            for i in range(3)
        ]

    def fake_mexc(symbol: str, **_kwargs):
        return [
            {
                "venue": "mexc",
                "symbol": symbol,
                "funding_time_ms": 1000 + i * 1000,
                "funding_rate": 0.0002,
            }
            for i in range(3)
        ]

    monkeypatch.setattr(
        "scripts.materialize_public_market_inputs.fetch_bybit_funding_history",
        fake_bybit,
    )
    monkeypatch.setattr(
        "scripts.materialize_public_market_inputs.fetch_mexc_funding_history",
        fake_mexc,
    )

    result = fetch_cross_exchange_funding(
        ["btcusdt"],
        days=30,
        as_of_ms=10_000,
        min_observations=3,
    )

    assert result["symbols"] == ["BTCUSDT"]
    assert result["record_count"] == 6
    assert set(result["coverage_by_venue_symbol"]) == {
        "bybit:BTCUSDT",
        "mexc:BTCUSDT",
    }


def test_mexc_history_normalizes_symbol_and_stops_at_cutoff() -> None:
    calls: list[dict] = []

    def fake_get(_url: str, params: dict) -> dict:
        calls.append(dict(params))
        return {
            "success": True,
            "code": 0,
            "data": {
                "totalPage": 3,
                "resultList": [
                    {"settleTime": 5000, "fundingRate": 0.01},
                    {"settleTime": 3000, "fundingRate": 0.02},
                    {"settleTime": 2000, "fundingRate": 0.03},
                ],
            },
        }

    rows = fetch_mexc_funding_history(
        "BTCUSDT",
        cutoff_ms=2500,
        as_of_ms=5000,
        get_json=fake_get,
    )

    assert calls == [
        {
            "symbol": "BTC_USDT",
            "page_num": 1,
            "page_size": 1000,
        }
    ]
    assert [row["funding_time_ms"] for row in rows] == [3000, 5000]
