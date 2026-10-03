from copy import deepcopy

import pytest

from bot import att1_coordinator_adapter as adapter

NOW = 1_700_000_060_000
CONFIG = {'name': 'att1', 'key': 'test-key', 'base': 'https://api.bybit.com'}


def envelope(rows, *, category=True, cursor=True):
    result = {'list': rows}
    if category: result['category'] = 'linear'
    if cursor: result['nextPageCursor'] = ''
    return {'retCode': 0, 'time': NOW-500, 'result': result}


def inputs():
    identity = adapter.validate_old_att1_broker_identity(CONFIG,
        {'retCode': 0, 'time': NOW-1000, 'result': {'apiKey': CONFIG['key'], 'userID': 731}},
        received_ms=NOW)
    instrument = {'symbol': 'LINKUSDT', 'status': 'Trading', 'contractType': 'LinearPerpetual',
                  'settleCoin': 'USDT', 'quoteCoin': 'USDT', 'priceFilter': {'tickSize': '0.001'},
                  'lotSizeFilter': {'qtyStep': '0.1', 'minOrderQty': '0.1', 'minNotionalValue': '5'}}
    return {'account_config': CONFIG, 'broker_identity': identity, 'symbol': 'LINKUSDT',
            'observed_ms': NOW, 'position_pages': [envelope([{'symbol': 'LINKUSDT', 'positionIdx': 0, 'size': '0', 'side': ''}])],
            'instrument_page': envelope([instrument]),
            'fee_page': envelope([{'symbol': 'LINKUSDT', 'takerFeeRate': '0.00055', 'makerFeeRate': '0.0002'}], category=False, cursor=False)}


def test_trading_oneway_inputs_are_source_bound_but_never_money_authority():
    out = adapter.validate_att1_symbol_input_evidence(**inputs())
    assert out['input_status'] == 'COMPLETE_ONEWAY_INPUTS'
    assert out['position_mode'] == 'ONEWAY'
    assert out['taker_fee_rate'] == '11/20000'
    assert out['orders_allowed'] is False
    assert out['money_ready'] is False
    assert len(out['source_sha256']) == 64


def test_flat_account_does_not_establish_oneway_and_hedge_rows_deny():
    value = inputs(); value['position_pages'] = [envelope([])]
    assert adapter.validate_att1_symbol_input_evidence(**value)['input_status'] == 'BLOCKED_MODE_UNKNOWN'
    value['position_pages'] = [envelope([{'symbol': 'LINKUSDT', 'positionIdx': i, 'size': '0', 'side': ''} for i in (1,2)])]
    out = adapter.validate_att1_symbol_input_evidence(**value)
    assert out['position_mode'] == 'HEDGE' and out['input_status'] == 'BLOCKED_MODE_HEDGE'


@pytest.mark.parametrize('change', ['foreign_symbol','duplicate','cursor','stale','future','boolean_idx','nonzero_no_side'])
def test_bad_position_sources_fail_closed(change):
    value = inputs(); page = value['position_pages'][0]; row = page['result']['list'][0]
    if change == 'foreign_symbol': row['symbol'] = 'BTCUSDT'
    if change == 'duplicate': page['result']['list'].append(deepcopy(row))
    if change == 'cursor': page['result']['nextPageCursor'] = 'unfinished'
    if change == 'stale': page['time'] = NOW-60001
    if change == 'future': page['time'] = NOW+1
    if change == 'boolean_idx': row['positionIdx'] = False
    if change == 'nonzero_no_side': row['size'] = '1'
    with pytest.raises(adapter.AdapterViolation): adapter.validate_att1_symbol_input_evidence(**value)


def test_actual_two_page_hedge_plus_zero_placeholder_is_conflict_never_oneway():
    data = inputs()
    first = envelope([{'symbol':'LINKUSDT','positionIdx':i,'size':'0','side':''} for i in (1,2)])
    first['result']['nextPageCursor'] = 'terminal-page'
    data['position_pages'] = [first, envelope([{'symbol':'LINKUSDT','positionIdx':0,'size':'0','side':''}])]
    result = adapter.validate_att1_symbol_input_evidence(**data)
    assert result['position_mode'] == 'CONFLICT'
    assert result['input_status'] == 'BLOCKED_MODE_CONFLICT'
    assert result['taker_fee_rate'] is None and result['orders_allowed'] is False


@pytest.mark.parametrize('field,value', [('status','Settling'),('contractType','LinearFutures'),('settleCoin','USDC'),('quoteCoin','USDC')])
def test_unavailable_contract_is_not_silently_removed_from_frozen_universe(field,value):
    data = inputs(); data['instrument_page']['result']['list'][0][field] = value
    out = adapter.validate_att1_symbol_input_evidence(**data)
    assert out['input_status'] == 'BLOCKED_CONTRACT_INELIGIBLE'
    assert out['symbol'] == 'LINKUSDT' and out['orders_allowed'] is False


@pytest.mark.parametrize('source', ['instrument_page','fee_page'])
def test_missing_source_blocks_and_unknown_fee_is_never_zero(source):
    data = inputs(); data[source] = None
    out = adapter.validate_att1_symbol_input_evidence(**data)
    assert out['input_status'].startswith('BLOCKED_') and out['taker_fee_rate'] is None


@pytest.mark.parametrize('source,field,value', [('fee_page','takerFeeRate','NaN'),('fee_page','takerFeeRate','-0.01'),('fee_page','symbol','BTCUSDT'),('instrument_page','symbol','BTCUSDT')])
def test_malformed_cost_or_symbol_inputs_deny(source,field,value):
    data = inputs(); data[source]['result']['list'][0][field] = value
    with pytest.raises(adapter.AdapterViolation): adapter.validate_att1_symbol_input_evidence(**data)


def test_source_hash_changes_when_fee_or_mode_evidence_changes():
    data = inputs(); first = adapter.validate_att1_symbol_input_evidence(**data)
    data['fee_page']['result']['list'][0]['takerFeeRate'] = '0.0006'
    assert adapter.validate_att1_symbol_input_evidence(**data)['source_sha256'] != first['source_sha256']


def test_collector_uses_exact_selected_symbol_gets_and_retains_rejected_fee_as_unknown():
    data = inputs()
    class Client:
        redacted_config = CONFIG
        last_received_ms = NOW
        calls = []
        def identity(self):
            self.calls.append('identity')
            return data['broker_identity']
        def pages(self, path, params):
            self.calls.append((path, params))
            return data['position_pages']
        def get(self, path, params):
            self.calls.append((path, params))
            if path == '/v5/account/fee-rate': raise ValueError('provider rejected')
            return data['instrument_page']
    client = Client()
    result = adapter.collect_att1_symbol_input_evidence(client, 'LINKUSDT')
    assert result['evidence']['input_status'] == 'BLOCKED_FEE_UNKNOWN'
    assert result['fee_page'] is None
    assert result['evidence']['taker_fee_rate'] is None
    assert result['orders_allowed'] is False
    assert client.calls == ['identity',
        ('/v5/position/list', {'category':'linear','symbol':'LINKUSDT','limit':200}),
        ('/v5/market/instruments-info', {'category':'linear','symbol':'LINKUSDT'}),
        ('/v5/account/fee-rate', {'category':'linear','symbol':'LINKUSDT'})]
