import pytest
from bot.bybit_liquidation_source_v2 import normalize_liquidation, normalize_ws_message, SCHEMA
from scripts.collect_bybit_liquidations import normalize_liquidation as legacy


@pytest.mark.parametrize('side,expected,old',[('Buy','long','short'),('Sell','short','long')])
def test_official_position_side_is_not_forced_order_side(side,expected,old):
    raw={'T':1700000000000,'s':'BTCUSDT','S':side,'v':'0.5','p':'40000'}
    event=normalize_liquidation(raw,recv_ts_ms=1700000000100)
    assert event['side']==event['liquidated_position_side']==expected
    assert event['raw_position_side']==side and event['schema']==SCHEMA
    assert event['usd']==20000 and event['price_basis']=='bankruptcy_price'
    assert legacy(raw)['side']==old  # Sealed V1 is preserved, never reinterpreted.


def test_batch_binds_topic_and_raw_event_time():
    frame={'topic':'allLiquidation.BTCUSDT','ts':1700000000200,
           'data':[{'T':1700000000000,'s':'BTCUSDT','S':'Buy','v':'1','p':'40000'}]}
    assert normalize_ws_message(frame,recv_ts_ms=1700000000300)[0]['ts_ms']==1700000000000
    assert normalize_ws_message({**frame,'topic':'publicTrade.BTCUSDT'},recv_ts_ms=1700000000300)==[]
    frame['data'][0]['s']='ETHUSDT'
    assert normalize_ws_message(frame,recv_ts_ms=1700000000300)==[]


@pytest.mark.parametrize('change',[{'S':'unknown'},{'S':None},{'T':None},{'T':True},{'v':'nan'},{'p':'0'}])
def test_unknown_source_fields_never_become_guessed_side_or_receive_time(change):
    raw={'T':1700000000000,'s':'BTCUSDT','S':'Buy','v':'1','p':'40000'}
    assert normalize_liquidation({**raw,**change},recv_ts_ms=1700000000100) is None


def test_canonical_raw_identity_preserved_and_receive_unknown_explicit():
    raw={'T':1700000000000,'s':'BTCUSDT','S':'Buy','v':'1','p':'40000'}
    event=normalize_liquidation(raw)
    reordered=normalize_liquidation(dict(reversed(list(raw.items()))))
    assert event['raw_item_canonical_sha256']==reordered['raw_item_canonical_sha256']
    assert event['recv_ts_ms'] is None
    assert event['usd_basis']=='bankruptcy_notional_proxy'
    assert normalize_liquidation({**raw,'v':'1e308','p':'1e308'}) is None
    assert normalize_ws_message({'topic':'allLiquidation.BTCUSDT','ts':1700000000200,
        'data':[{**raw,'T':None}]},recv_ts_ms=1700000000300)==[]
