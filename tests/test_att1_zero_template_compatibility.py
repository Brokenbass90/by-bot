"""Explicit source-retaining exception; never authorizes orders or hedge mode."""
from copy import deepcopy

import pytest

from bot import att1_coordinator_adapter as a
from test_att1_symbol_input_evidence import inputs, envelope, NOW

POLICY='FLAT_IDX0_HISTORICAL_PLUS_ZERO_TEMPLATE_V1'


def data():
    d=inputs();row=d['position_pages'][0]['result']['list'][0]
    row.update(seq=123,createdTime='1000',updatedTime='2000',positionStatus='Normal',
               stopLoss='',takeProfit='',trailingStop='0')
    d['position_pages'][0]['result']['nextPageCursor']='next'
    d['position_pages'].append(envelope([{'symbol':'LINKUSDT','positionIdx':0,'side':'','size':'0',
        'seq':-1,'createdTime':'','updatedTime':'','positionStatus':'',
        'stopLoss':'','takeProfit':'','trailingStop':''}]))
    rule={'policy_id':POLICY,'flat_broker_snapshot':{
        'schema_id':'att1_broker_snapshot_v1','account':d['broker_identity'].account,
        'observed_ms':NOW,'position_count':0,'order_count':0,'flat_no_orders':True,'source_sha256':'a'*64}}
    return d,rule


def test_explicit_rule_retains_both_idx0_sources_with_flat_same_account():
    d,rule=data();original=deepcopy(d['position_pages'])
    out=a.validate_att1_symbol_input_evidence(**d,zero_template_rule=rule)
    assert out['input_status']=='COMPLETE_ONEWAY_INPUTS' and out['position_mode']=='ONEWAY'
    assert out['compatibility_rule']['policy_id']==POLICY
    assert out['compatibility_rule']['raw_row_count']==2
    assert out['compatibility_rule']['rows_discarded']==0
    assert len(out['compatibility_rule']['row_sources'])==2
    assert out['orders_allowed'] is False and out['money_ready'] is False
    assert d['position_pages']==original
    with pytest.raises(a.AdapterViolation):a.validate_att1_symbol_input_evidence(**d)


@pytest.mark.parametrize('change',['policy','account','stale','orders','not_flat','nonzero','template','normal','time','extra','hedge'])
def test_rule_rejects_conflicting_or_incomplete_compatibility_inputs(change):
    d,rule=data();snapshot=rule['flat_broker_snapshot']
    if change=='policy':rule['policy_id']='unknown'
    if change=='account':snapshot['account']='foreign'
    if change=='stale':snapshot['observed_ms']=NOW-60001
    if change=='orders':snapshot['order_count']=1
    if change=='not_flat':snapshot['flat_no_orders']=False
    if change=='nonzero':d['position_pages'][0]['result']['list'][0].update(size='1',side='Sell')
    if change=='template':d['position_pages'][1]['result']['list'][0]['seq']=0
    if change=='normal':d['position_pages'][0]['result']['list'][0]['positionStatus']='Liq'
    if change=='time':d['position_pages'][0]['result']['list'][0]['updatedTime']=str(NOW+1)
    if change=='extra':d['position_pages'][0]['result']['list'].append(deepcopy(d['position_pages'][0]['result']['list'][0]))
    if change=='hedge':d['position_pages'][0]['result']['list']=[{'symbol':'LINKUSDT','positionIdx':i,'size':'0','side':''} for i in (1,2)]
    with pytest.raises(a.AdapterViolation):a.validate_att1_symbol_input_evidence(**d,zero_template_rule=rule)
