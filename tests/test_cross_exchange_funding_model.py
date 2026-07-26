from scripts.cross_exchange_funding_shadow import (
    MODEL_VERSION,
    _aligned_next_epoch,
    _cooldown_pair_keys,
    _pair_price_pnl_pct,
    _settle_funding,
    _update_validation_evidence,
)
from scripts import cross_exchange_funding_scan as scan


def test_delta_neutral_price_pnl_uses_executable_prices():
    pos = {
        "long_entry_exec": 100.0,
        "short_entry_exec": 100.0,
    }
    assert abs(_pair_price_pnl_pct(pos, 101.0, 101.0)) < 1e-9


def test_funding_is_not_accrued_before_settlement():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    current = {
        "short_funding_event_pct": 0.1,
        "long_funding_event_pct": -0.1,
    }
    assert _settle_funding(pos, current, 1999.0) == 0.0


def test_funding_is_credited_only_after_settlement():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    current = {
        "short_funding_event_pct": 0.1,
        "long_funding_event_pct": -0.1,
    }
    assert round(_settle_funding(pos, current, 2001.0), 6) == 0.2
    assert len(pos["funding_events"]) == 2


def test_missing_current_snapshot_uses_last_pre_settlement_rate_then_clears_it():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    assert round(_settle_funding(pos, None, 2001.0), 6) == 0.2
    assert pos["short_pending_funding_event_pct"] == 0.0
    assert pos["long_pending_funding_event_pct"] == 0.0


def test_model_version_is_explicit():
    assert MODEL_VERSION == "settlement_execution_v2"
    assert _aligned_next_epoch(0.0, 8.0) == 8.0 * 3600.0


def test_missing_top_n_candidate_is_not_counted_as_validation_failure():
    pos = {"validation_fail_streak": 2}
    _update_validation_evidence(
        pos,
        {
            "ts_utc": "2026-07-26T12:00:00+00:00",
            "current_observed": False,
            "current_validated": False,
        },
    )
    assert pos["validation_fail_streak"] == 2
    assert pos["validation_missing_streak"] == 1


def test_explicit_validation_failures_need_consecutive_evidence():
    pos = {}
    failed = {
        "ts_utc": "2026-07-26T12:00:00+00:00",
        "current_observed": True,
        "current_validated": False,
    }
    _update_validation_evidence(pos, failed)
    _update_validation_evidence(pos, failed)
    assert pos["validation_fail_streak"] == 2

    _update_validation_evidence(
        pos,
        {
            "ts_utc": "2026-07-26T12:10:00+00:00",
            "current_observed": True,
            "current_validated": True,
        },
    )
    assert pos["validation_fail_streak"] == 0
    assert pos["last_validated_at_utc"] == "2026-07-26T12:10:00+00:00"


def test_recently_closed_pair_enters_reentry_cooldown():
    closed = [
        {
            "pair_key": "ERAUSDT:binance->bybit",
            "closed_at_utc": "2026-07-26T12:00:00+00:00",
        },
        {
            "pair_key": "OLDUSDT:binance->bybit",
            "closed_at_utc": "2026-07-25T12:00:00+00:00",
        },
    ]
    keys = _cooldown_pair_keys(
        closed,
        now=1785074400.0,
        cooldown_hours=6.0,
    )
    assert keys == {"ERAUSDT:binance->bybit"}


def test_esports_uses_bitget_one_hour_interval_and_is_not_old_false_positive(monkeypatch):
    def fake_get(url: str, timeout: float = 20.0):
        if "/market/tickers" in url:
            return {
                "data": [
                    {
                        "symbol": "ESPORTSUSDT",
                        "markPrice": "0.02728",
                        "usdtVolume": "25000000",
                        # Deliberately different: funding must come from the
                        # authoritative current-fund-rate response below.
                        "fundingRate": "0.999",
                    }
                ]
            }
        if "/market/contracts" in url:
            return {
                "data": [
                    {
                        "symbol": "ESPORTSUSDT",
                        "quoteCoin": "USDT",
                        "symbolType": "perpetual",
                        "symbolStatus": "normal",
                        "isRwa": "NO",
                        "fundInterval": "1",
                    }
                ]
            }
        if "/market/current-fund-rate" in url:
            return {
                "data": [
                    {
                        "symbol": "ESPORTSUSDT",
                        "fundingRate": "0.000329",
                        "fundingRateInterval": "1",
                        "nextUpdate": "1784656800000",
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(scan, "_get_json", fake_get)
    bitget = scan.fetch_bitget()
    assert len(bitget) == 1
    assert bitget[0].funding_interval_hours == 1.0
    assert bitget[0].funding_rate == 0.000329

    bybit = scan.FundingRow(
        exchange="bybit",
        symbol="ESPORTSUSDT",
        funding_rate=0.00031116,
        funding_interval_hours=1.0,
        annualized_pct=scan._annualized_pct(0.00031116, 1.0),
        mark_price=0.02726,
        quote_volume_24h=25_000_000.0,
        open_interest_usd=0.0,
        next_funding_ms=1784656800000,
    )
    opportunities = scan.build_opportunities(
        [bybit, bitget[0]],
        min_volume_usd=10_000_000.0,
        min_spread_apr_pct=36.0,
        top=20,
    )
    # With the old hardcoded Bitget 8h interval this snapshot appeared as a
    # 236.55% APR opportunity.  With the real 1h interval its spread is only
    # ~15.63% APR and cannot pass the validator's 36% gate.
    assert opportunities == []


def test_skhynix_stock_and_rwa_contracts_are_excluded(monkeypatch):
    def fake_get(url: str, timeout: float = 20.0):
        if "bybit.com/v5/market/instruments-info" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "SKHYNIXUSDT",
                            "contractType": "LinearPerpetual",
                            "status": "Trading",
                            "quoteCoin": "USDT",
                            "settleCoin": "USDT",
                            "symbolType": "stock",
                            "fundingInterval": "480",
                        }
                    ],
                    "nextPageCursor": "",
                }
            }
        if "bybit.com/v5/market/tickers" in url:
            return {
                "result": {
                    "list": [
                        {
                            "symbol": "SKHYNIXUSDT",
                            "fundingRate": "0.00088812",
                            "markPrice": "1320.29",
                            "turnover24h": "25000000",
                            "nextFundingTime": "1784678400000",
                        }
                    ]
                }
            }
        if url.endswith("/premiumIndex"):
            return [
                {
                    "symbol": "SKHYNIXUSDT",
                    "lastFundingRate": "0.00082531",
                    "markPrice": "1321.00",
                    "nextFundingTime": "1784664000000",
                }
            ]
        if url.endswith("/ticker/24hr"):
            return [{"symbol": "SKHYNIXUSDT", "quoteVolume": "25000000"}]
        if url.endswith("/exchangeInfo"):
            return {
                "symbols": [
                    {
                        "symbol": "SKHYNIXUSDT",
                        "contractType": "TRADIFI_PERPETUAL",
                        "status": "TRADING",
                        "underlyingType": "KR_EQUITY",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                    }
                ]
            }
        if url.endswith("/fundingInfo"):
            return [{"symbol": "SKHYNIXUSDT", "fundingIntervalHours": 4}]
        if "/market/tickers" in url:
            return {
                "data": [
                    {
                        "symbol": "SKHYNIXUSDT",
                        "markPrice": "1322.99",
                        "usdtVolume": "25000000",
                    }
                ]
            }
        if "/market/contracts" in url:
            return {
                "data": [
                    {
                        "symbol": "SKHYNIXUSDT",
                        "quoteCoin": "USDT",
                        "symbolType": "perpetual",
                        "symbolStatus": "normal",
                        "isRwa": "YES",
                        "fundInterval": "4",
                    }
                ]
            }
        if "/market/current-fund-rate" in url:
            return {
                "data": [
                    {
                        "symbol": "SKHYNIXUSDT",
                        "fundingRate": "0",
                        "fundingRateInterval": "4",
                        "nextUpdate": "1784664000000",
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(scan, "_get_json", fake_get)
    assert scan.fetch_bybit() == []
    assert scan.fetch_binance() == []
    assert scan.fetch_bitget() == []


def test_binance_interval_is_fail_closed_without_authoritative_metadata(monkeypatch):
    def fake_get(url: str, timeout: float = 20.0):
        if url.endswith("/premiumIndex"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "lastFundingRate": "0.0001",
                    "markPrice": "100000",
                    "nextFundingTime": "1784678400000",
                }
            ]
        if url.endswith("/ticker/24hr"):
            return [{"symbol": "BTCUSDT", "quoteVolume": "1000000000"}]
        if url.endswith("/exchangeInfo"):
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "underlyingType": "COIN",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                    }
                ]
            }
        if url.endswith("/fundingInfo"):
            return []
        raise AssertionError(url)

    monkeypatch.setattr(scan, "_get_json", fake_get)
    assert scan.fetch_binance() == []
