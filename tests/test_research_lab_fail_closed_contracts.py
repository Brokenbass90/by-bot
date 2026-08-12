import json

from research_lab import strategy_adapter


def test_explicit_disallowed_symbol_is_rejected_not_substituted():
    result = strategy_adapter.open_strategy(
        "alt_elder_revived_v1",
        symbol="AVAXUSDT",
        limit=500,
    )
    assert result["ok"] is False
    assert result["symbol"] == "AVAXUSDT"
    assert "явная проба отклонена" in result["note"]


def test_explicit_physical_input_is_used_without_scanning_shared_cache(tmp_path):
    path = tmp_path / "ETHUSDT.json"
    path.write_text(json.dumps({
        "symbol": "ETHUSDT",
        "records": [
            {"ts_ms": 1000, "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 3},
            {"ts_ms": 2000, "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 4},
        ],
    }), encoding="utf-8")
    candles = strategy_adapter.load_candles("ETHUSDT", 10, input_path=path, end_ms=1500)
    assert [row.ts for row in candles] == [1000]
