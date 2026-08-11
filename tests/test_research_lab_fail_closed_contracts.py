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
