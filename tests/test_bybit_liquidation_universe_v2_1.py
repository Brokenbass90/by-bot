"""Source census tests: no post-outcome selection, incomplete census or pin drift."""
import hashlib
import json

import pytest

from research_lab.bybit_liquidation_universe_v2_1 import UniverseBlocked, freeze, verify


def capture(endpoint, result, params=None):
    raw = dict(retCode=0, result=dict(category="linear", **result))
    text = json.dumps(raw, separators=(",", ":"))
    return dict(endpoint=endpoint, params=params or dict(category="linear"),
                request_ms=1791964800000, receive_ms=1791964800010, raw_text=text,
                raw_sha256=hashlib.sha256(text.encode()).hexdigest())


def instruments(n=30):
    return [dict(symbol=f"COIN{i:02}USDT", status="Trading", contractType="LinearPerpetual",
                 quoteCoin="USDT", settleCoin="USDT", isPreListing=False) for i in range(n)]


def source(n=30):
    ins = capture("/v5/market/instruments-info", dict(list=instruments(n), nextPageCursor=""),
                  dict(category="linear", status="Trading", limit=1000))
    tick = capture("/v5/market/tickers", dict(list=[dict(symbol=f"COIN{i:02}USDT",
                   turnover24h=str(50000000 + i * 1000000)) for i in range(n)]))
    return [ins], tick


def test_top25_by_turnover_uses_lexical_ties_and_fixed_eligibility():
    pages, tick = source()
    m = freeze(pages, tick, prereg_sha256="d" * 64)
    assert m["symbols"] == [f"COIN{i:02}USDT" for i in range(29, 4, -1)]
    assert len(m["symbols"]) == 25
    assert m["strategy_runs"] == 0 and m["orders_allowed"] is False
    assert verify(m)["symbols"] == m["symbols"]


def test_ties_are_symbol_sorted_not_api_response_order():
    pages, _ = source()
    tick = capture("/v5/market/tickers", dict(list=[dict(symbol=f"COIN{i:02}USDT", turnover24h="25000000") for i in reversed(range(30))]))
    m = freeze(pages, tick, prereg_sha256="d" * 64)
    assert m["symbols"] == [f"COIN{i:02}USDT" for i in range(25)]


def test_nontrading_nonusdt_prelaunch_and_nonperpetual_are_excluded_before_ranking():
    rows = instruments()
    rows[29]["isPreListing"] = True
    rows[28]["status"] = "PreLaunch"
    rows[27]["settleCoin"] = "USDC"
    rows[26]["contractType"] = "LinearFutures"
    p = capture("/v5/market/instruments-info", dict(list=rows, nextPageCursor=""),
                dict(category="linear", status="Trading", limit=1000))
    _, tick = source()
    m = freeze([p], tick, prereg_sha256="d" * 64)
    assert m["symbols"] == [f"COIN{i:02}USDT" for i in range(25, 0, -1)]
    assert sum(m["exclusion_counts"].values()) == 4


def test_thin_symbols_cannot_pad_the_frozen_count():
    pages, _ = source()
    tick = capture("/v5/market/tickers", dict(list=[dict(symbol=f"COIN{i:02}USDT", turnover24h="9999999") for i in range(30)]))
    with pytest.raises(UniverseBlocked, match="FEWER_THAN_25"):
        freeze(pages, tick, prereg_sha256="d" * 64)


def test_incomplete_instrument_pagination_blocks():
    pages, tick = source()
    pages[0] = capture("/v5/market/instruments-info", dict(list=instruments(), nextPageCursor="more"),
                       dict(category="linear", status="Trading", limit=1000))
    with pytest.raises(UniverseBlocked, match="PAGINATION"):
        freeze(pages, tick, prereg_sha256="d" * 64)


def test_page_cursor_chain_must_match_the_requested_cursor():
    _, tick = source()
    pages = [capture("/v5/market/instruments-info", dict(list=instruments(15), nextPageCursor="page2"),
                      dict(category="linear", status="Trading", limit=1000)),
             capture("/v5/market/instruments-info", dict(list=instruments()[15:], nextPageCursor=""),
                      dict(category="linear", status="Trading", limit=1000, cursor="wrong"))]
    with pytest.raises(UniverseBlocked, match="CURSOR"):
        freeze(pages, tick, prereg_sha256="d" * 64)


def test_duplicate_census_symbols_and_missing_ticker_are_blocked():
    pages, tick = source()
    pages[0] = capture("/v5/market/instruments-info", dict(list=instruments()+instruments(1), nextPageCursor=""),
                       dict(category="linear", status="Trading", limit=1000))
    with pytest.raises(UniverseBlocked, match="DUPLICATE"):
        freeze(pages, tick, prereg_sha256="d" * 64)
    pages, _ = source()
    tick = capture("/v5/market/tickers", dict(list=[]))
    with pytest.raises(UniverseBlocked, match="TICKER_MISSING"):
        freeze(pages, tick, prereg_sha256="d" * 64)


def test_rehashed_manifest_cannot_substitute_a_different_symbol():
    pages, tick = source()
    m = freeze(pages, tick, prereg_sha256="d" * 64)
    m["symbols"][0] = "BTCUSDT"
    m["manifest_sha256"] = hashlib.sha256(json.dumps({k:v for k,v in m.items() if k!="manifest_sha256"},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(UniverseBlocked, match="RECONSTRUCTION"):
        verify(m)


def test_tampered_raw_capture_is_blocked_without_zero_substitution():
    pages, tick = source();tick["raw_text"] = tick["raw_text"].replace("50000000", "90000000")
    with pytest.raises(UniverseBlocked, match="RAW_HASH"):
        freeze(pages, tick, prereg_sha256="d" * 64)


@pytest.mark.parametrize("turnover", ["NaN", "Infinity", "bad"])
def test_invalid_turnover_is_a_source_failure(turnover):
    pages, _ = source()
    tick = capture("/v5/market/tickers", dict(list=[dict(symbol=f"COIN{i:02}USDT",turnover24h=turnover if i==0 else "50000000") for i in range(30)]))
    with pytest.raises(UniverseBlocked, match="TURNOVER_INVALID"):
        freeze(pages, tick, prereg_sha256="d" * 64)


def test_rehashed_rule_change_cannot_change_frozen_selector():
    pages, tick = source()
    m = freeze(pages, tick, prereg_sha256="d" * 64)
    m["rule"]["count"] = 20
    m["manifest_sha256"] = hashlib.sha256(json.dumps({k:v for k,v in m.items() if k!="manifest_sha256"},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(UniverseBlocked, match="RECONSTRUCTION"):
        verify(m)


def test_commodity_type_is_not_crypto_even_with_empty_region_and_ticker():
    rows=instruments();rows[29].update(symbolType='commodity',marketRegion='',underlyingTicker='')
    p=capture('/v5/market/instruments-info',dict(list=rows,nextPageCursor=''),
              dict(category='linear',status='Trading',limit=1000))
    _,tick=source()
    m=freeze([p],tick,prereg_sha256='d'*64)
    assert 'COIN29USDT' not in m['symbols']
    assert m['exclusion_counts']['TRADFI']==1
