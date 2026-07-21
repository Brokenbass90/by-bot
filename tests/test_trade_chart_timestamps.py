import asyncio
import urllib.parse

from web.routes import data_routes


def test_epoch_ms_preserves_milliseconds_and_converts_seconds():
    assert data_routes._epoch_ms(1_753_000_000) == 1_753_000_000_000
    assert data_routes._epoch_ms(1_753_000_000_000) == 1_753_000_000_000
    assert data_routes._epoch_ms(0) == 0


def test_trade_chart_normalizes_mixed_live_position_timestamps(monkeypatch, tmp_path):
    requested = {}

    def unavailable(request, *args, **kwargs):
        requested["url"] = request.full_url
        raise OSError("offline test")

    monkeypatch.setattr(data_routes, "_ROOT", tmp_path)
    monkeypatch.setattr(data_routes.urllib.request, "urlopen", unavailable)

    entry_seconds = 1_753_000_000
    exit_milliseconds = 1_753_000_600_000
    result = asyncio.run(data_routes.trade_chart(
        symbol="BTCUSDT",
        entry_ts=entry_seconds,
        exit_ts=exit_milliseconds,
        interval="5",
        entry_price=100.0,
        exit_price=101.0,
        sl_price=None,
        tp_price=None,
        _="test-auth",
    ))

    expected_entry_ms = entry_seconds * 1000
    assert result["entry_ts"] == expected_entry_ms
    assert result["exit_ts"] == exit_milliseconds
    assert result["source"] == "synthetic_trade_path"
    assert all(expected_entry_ms - 8 * 3_600_000 <= candle["time_ms"]
               for candle in result["candles"])

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(requested["url"]).query)
    assert query["start"] == [str(expected_entry_ms - 8 * 3_600_000)]
    assert query["end"] == [str(exit_milliseconds + 4 * 3_600_000)]
