import copy
import pytest
from research_lab import alpaca_live_readiness_v1 as api

# Break caught: rejecting unchanged fills when REST rounds an order timestamp.
def sample():
    old=dict(id='owned',client_order_id='owned-cid',symbol='NET',side='sell',type='market',
        qty='0.325167779',filled_qty='0.325167779',filled_avg_price='349.344',status='filled',
        time_in_force='day',source=None,filled_at='2026-10-13T13:35:33.960224931Z',
        updated_at='2026-10-13T13:35:33.960999804Z')
    actual={**old,'source':'access_key','filled_at':'2026-10-13T13:35:33.960225Z',
        'updated_at':'2026-10-13T13:35:33.961Z'}
    return old,actual

def test_same_owned_fill_with_api_precision_and_added_source_is_equivalent():
    old,actual=sample();saved=copy.deepcopy((old,actual))
    assert hasattr(api,'execution_identity_v1'), 'semantic comparator missing'
    proof=api.execution_identity_v1(old,actual)
    assert proof['status']=='EXECUTION_IDENTITY_MATCH'
    assert proof['retained_raw_sha256']!=proof['broker_raw_sha256']
    assert (old,actual)==saved

@pytest.mark.parametrize('field,value',[('id','other'),('client_order_id','foreign'),('symbol','META'),
    ('side','buy'),('qty','.4'),('filled_qty','.2'),('filled_avg_price','349.345'),
    ('type','limit'),('status','partially_filled'),('time_in_force','gtc'),
    ('filled_at','2026-10-13T13:35:33.960226Z'),('updated_at','2026-10-13T13:35:33.961001Z'),
    ('source','manual'),('asset_id','new-authority')])
def test_material_order_or_time_or_unreviewed_metadata_difference_blocks(field,value):
    old,actual=sample();actual[field]=value
    with pytest.raises(ValueError):api.execution_identity_v1(old,actual)

@pytest.mark.parametrize('value',['bad','2026-10-13T13:35:33','2026-10-13T13:35:33.9602249310Z'])
def test_unknown_timestamp_precision_never_passes(value):
    old,actual=sample();old['filled_at']=actual['filled_at']=value
    with pytest.raises(ValueError):api.execution_identity_v1(old,actual)

def test_microsecond_boundary_carry_is_exact():
    old,actual=sample();old['filled_at']='2026-10-13T13:35:33.999999931Z';actual['filled_at']='2026-10-13T13:35:34Z'
    assert api.execution_identity_v1(old,actual)['status']=='EXECUTION_IDENTITY_MATCH'
