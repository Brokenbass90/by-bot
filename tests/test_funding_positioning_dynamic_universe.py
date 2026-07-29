from pathlib import Path

from scripts import build_funding_positioning_dynamic_universe as universe
from scripts.funding_positioning_v4_shadow import _load_symbols


def test_dynamic_universe_is_liquidity_ranked_and_signal_free(monkeypatch) -> None:
    now_ms = 200 * 86_400_000
    monkeypatch.setattr(
        universe,
        "_instrument_rows",
        lambda: [
            {
                "symbol": symbol,
                "status": "Trading",
                "contractType": "LinearPerpetual",
                "settleCoin": "USDT",
                "launchTime": "0",
            }
            for symbol in ("BTCUSDT", "ETHUSDT", "NEWUSDT", "WIDEUSDT")
        ],
    )
    monkeypatch.setattr(
        universe,
        "_ticker_map",
        lambda: {
            "BTCUSDT": {"turnover24h": "100000000", "bid1Price": "100", "ask1Price": "100.01"},
            "ETHUSDT": {"turnover24h": "80000000", "bid1Price": "50", "ask1Price": "50.01"},
            "NEWUSDT": {"turnover24h": "70000000", "bid1Price": "10", "ask1Price": "10.01"},
            "WIDEUSDT": {"turnover24h": "90000000", "bid1Price": "1", "ask1Price": "1.01"},
        },
    )
    monkeypatch.setattr(universe, "_funding_coverage", lambda _symbol, _limit: 100)

    payload = universe.build_universe(
        top_n=2,
        min_listing_days=0,
        min_turnover_usd=20_000_000,
        max_spread_bps=12,
        now_ms=now_ms,
    )

    assert payload["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert payload["selection_contract"]["signal_or_pnl_used"] is False
    assert payload["capital_authorized"] is False


def test_dynamic_universe_rejects_non_crypto_linear_perpetuals(monkeypatch) -> None:
    monkeypatch.setattr(
        universe,
        "_instrument_rows",
        lambda: [
            {
                "symbol": "BTCUSDT",
                "status": "Trading",
                "contractType": "LinearPerpetual",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "symbolType": "",
                "launchTime": "0",
            },
            {
                "symbol": "XAUUSDT",
                "status": "Trading",
                "contractType": "LinearPerpetual",
                "quoteCoin": "USDT",
                "settleCoin": "USDT",
                "symbolType": "commodity",
                "launchTime": "0",
            },
        ],
    )
    monkeypatch.setattr(
        universe,
        "_ticker_map",
        lambda: {
            "BTCUSDT": {
                "turnover24h": "100000000",
                "bid1Price": "100",
                "ask1Price": "100.01",
            },
            "XAUUSDT": {
                "turnover24h": "100000000",
                "bid1Price": "3000",
                "ask1Price": "3000.01",
            },
        },
    )
    monkeypatch.setattr(universe, "_funding_coverage", lambda _symbol, _limit: 100)
    payload = universe.build_universe(
        top_n=2,
        min_listing_days=0,
        now_ms=200 * 86_400_000,
    )
    assert payload["symbols"] == ["BTCUSDT"]


def test_shadow_accepts_only_research_only_dynamic_universe(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(
        '{"authority":"research_only_no_orders","symbols":["BTCUSDT","ETHUSDT","BTCUSDT"]}',
        encoding="utf-8",
    )
    symbols, digest = _load_symbols(good)
    assert symbols == ("BTCUSDT", "ETHUSDT")
    assert digest

    bad = tmp_path / "bad.json"
    bad.write_text('{"authority":"money","symbols":["BTCUSDT"]}', encoding="utf-8")
    try:
        _load_symbols(bad)
    except ValueError as exc:
        assert "research_only_no_orders" in str(exc)
    else:
        raise AssertionError("money-authorized universe must be rejected")
