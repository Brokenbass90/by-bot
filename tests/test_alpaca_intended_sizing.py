import math
import sys

import pytest

from scripts import equities_alpaca_paper_bridge as bridge


def _pick(symbol, weight):
    return bridge.Pick(
        month="2026-09", ticker=symbol, entry_day="2026-09-20", score=1,
        atr20_pct=2, momentum20_pct=3, momentum60_pct=4, pullback60_pct=-1,
        universe_score=1, entry_price=100, stop_price=95, weight=weight,
    )


def test_frozen_weights_do_not_redistribute_when_one_pick_is_removed():
    # Re-normalizing surviving picks would turn BBB's frozen 20% into a larger allocation.
    weights = bridge._intended_frozen_weights([_pick("AAA", 0.40), _pick("BBB", 0.20)])
    surviving = {symbol: weights[symbol] * 1_000 for symbol in ["BBB"]}

    assert surviving == {"BBB": 200.0}


@pytest.mark.parametrize("weight", [None, 0.0, -0.1, 0.6000001, math.nan, math.inf])
def test_invalid_frozen_weight_fails_closed(weight):
    with pytest.raises(bridge.IntendedPaperProtectionError):
        bridge._intended_frozen_weights([_pick("AAA", weight)])


def test_duplicate_frozen_symbol_fails_closed():
    with pytest.raises(bridge.IntendedPaperProtectionError, match="duplicate"):
        bridge._intended_frozen_weights([_pick("AAA", 0.2), _pick("AAA", 0.2)])


def test_frozen_weight_total_above_one_fails_closed():
    with pytest.raises(bridge.IntendedPaperProtectionError, match="total"):
        bridge._intended_frozen_weights([_pick("AAA", 0.60), _pick("BBB", 0.60)])


def test_empty_frozen_pick_set_is_a_valid_no_signal_cycle():
    assert bridge._intended_frozen_weights([]) == {}


def test_tiny_frozen_allocation_is_skipped_without_buy(tmp_path, monkeypatch, capsys):
    # Reinstating max(minimum_order, allocation) would trigger the fake buyer.
    picks = tmp_path / "picks.csv"
    picks.write_text(
        "month,ticker,entry_day,score,atr20_pct,momentum20_pct,momentum60_pct,pullback60_pct,entry_price,stop_price,weight\n"
        "2026-09,SCHW,2026-09-20,1,2,3,4,-1,100,95,0.10\n"
    )

    class Client:
        buy_calls = 0
        def __init__(self, *_args): pass
        def get_account(self): return {"id": "acct-1", "buying_power": "100", "cash": "100"}
        def list_positions(self): return []
        def list_orders(self, **_kwargs): return []
        def get_clock(self): return {"is_open": True}
        def submit_market_buy_qty(self, *_args):
            type(self).buy_calls += 1
            raise AssertionError("tiny frozen allocation must not buy")

    for key, value in {
        "ALPACA_INTENDED_PAPER": "1", "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        "ALPACA_API_KEY_ID": "key", "ALPACA_API_SECRET_KEY": "secret",
        "ALPACA_SEND_ORDERS": "1", "ALPACA_ALLOW_NEW_ENTRIES": "1",
        "ALPACA_BROKER_PROTECTION_ENABLE": "1", "ALPACA_BROKER_PROTECTION_REQUIRED": "1",
        "ALPACA_BROKER_PROTECTION_ORDER_CLASS": "simple_stop",
        "ALPACA_BROKER_PROTECTION_SIZE_MODE": "qty", "ALPACA_EARNINGS_FILTER": "0",
        "ALPACA_MIN_DOLLAR_ORDER": "50", "ALPACA_BRIDGE_LOCK_PATH": str(tmp_path / "lock"),
        "ALPACA_PROTECTIVE_EXIT_HWM_PATH": str(tmp_path / "floor.json"),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["bridge", "--picks-csv", str(picks)])
    monkeypatch.setattr(bridge, "AlpacaClient", Client)

    assert bridge._main_unlocked() == 0
    assert Client.buy_calls == 0
    report = __import__("json").loads(capsys.readouterr().out.strip().splitlines()[-1])
    result = next(row for row in report["results"] if row["ticker"] == "SCHW")
    assert result["status"] == "skipped_below_minimum_order"
    assert result["notional"] == 4.5
