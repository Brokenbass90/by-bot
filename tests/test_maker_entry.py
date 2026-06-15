"""Tests for maker/post-only entry helpers."""

import pytest
from bot.maker_entry import post_only_price, should_fallback_to_taker


def test_buy_sits_below_sell_sits_above():
    assert post_only_price("buy", 100.0, offset_bps=10) == pytest.approx(99.9)
    assert post_only_price("sell", 100.0, offset_bps=10) == pytest.approx(100.1)


def test_tick_rounding():
    px = post_only_price("buy", 100.07, offset_bps=0, tick=0.05)
    assert abs(px / 0.05 - round(px / 0.05)) < 1e-9


def test_tick_rounding_preserves_passive_side():
    buy = post_only_price("buy", 100.0, offset_bps=1, tick=0.05)
    sell = post_only_price("sell", 100.0, offset_bps=1, tick=0.05)
    assert buy < 100.0
    assert sell > 100.0


def test_invalid_inputs():
    with pytest.raises(ValueError):
        post_only_price("buy", 0)
    with pytest.raises(ValueError):
        post_only_price("sideways", 100.0)


def test_fallback_on_timeout():
    assert should_fallback_to_taker(bars_waited=5, max_wait_bars=5,
                                    price_now=100, entry_ref=100, side="buy") is True


def test_fallback_when_price_runs_away():
    # buy ref 100, price rose +0.2% (20bps) > 15bps -> cross spread
    assert should_fallback_to_taker(bars_waited=1, max_wait_bars=10,
                                    price_now=100.2, entry_ref=100.0, side="buy",
                                    max_adverse_bps=15.0) is True
    # price stayed near -> keep waiting
    assert should_fallback_to_taker(bars_waited=1, max_wait_bars=10,
                                    price_now=100.05, entry_ref=100.0, side="buy",
                                    max_adverse_bps=15.0) is False
