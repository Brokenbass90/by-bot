from backtest.engine import Candle, KlineStore


def _candles(start_ms: int, count: int) -> list[Candle]:
    return [
        Candle(ts=start_ms + idx * 300_000, o=100, h=101, l=99, c=100, v=1)
        for idx in range(count)
    ]


def test_funding_rate_uses_only_events_known_by_current_bar() -> None:
    start_ms = 1_700_000_000_000
    store = KlineStore(
        "BTCUSDT",
        _candles(start_ms, 4),
        funding_rates=[
            (start_ms + 300_000, 0.001),
            (start_ms + 900_000, 0.002),
        ],
    )

    store.set_index(0)
    assert store.fetch_funding_rate("BTCUSDT") == 0.001

    store.set_index(1)
    assert store.fetch_funding_rate("BTCUSDT") == 0.001

    store.set_index(2)
    assert store.fetch_funding_rate("BTCUSDT") == 0.002


def test_funding_rate_returns_none_before_first_event() -> None:
    start_ms = 1_700_000_000_000
    store = KlineStore(
        "BTCUSDT",
        _candles(start_ms, 2),
        funding_rates=[(start_ms + 900_000, 0.002)],
    )

    store.set_index(0)
    assert store.fetch_funding_rate("BTCUSDT") is None
