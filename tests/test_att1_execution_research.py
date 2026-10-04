import pytest
from research_lab import att1_execution_research as study


def test_missing_cts_never_uses_outer_timestamp_as_freshness():
    raw={'time':1000,'result':{'s':'SUIUSDT','ts':999,'u':7,'seq':9}}
    p=study.book_projection(raw,kind='rest',received_ms=1001,used_ms=1002)
    assert p['cts'] is None and p['freshness']=='UNKNOWN_CTS'
    assert p['u']==7 and p['seq']==9 and p['use_delay_ms']==1


@pytest.mark.parametrize('age,expected',[(2000,'FRESH'),(2001,'STALE')])
def test_use_clock_retains_exact_two_second_boundary(age,expected):
    raw={'cts':1000,'ts':1001,'data':{'s':'SEIUSDT','u':5,'seq':8}}
    p=study.book_projection(raw,kind='ws',received_ms=1001,used_ms=1000+age)
    assert p['freshness']==expected and p['cts']==1000


def test_candidate_costs_cannot_grant_money_or_offset_unresolved_liabilities():
    x=study.funding_comparison(qty='0.1',entry='100',stop='101',lower_rate='-0.0058',
          interval_minutes=480,taker_rate='0.00055',historical43_adverse='0.00636935')
    assert x['old_required_usdt']=='2.64005'
    base=x['scenarios'][0]
    assert base['total_required_usdt']=='0.442762175' and base['fits_draft_budget']
    assert x['scenarios'][-1]['fits_draft_budget'] is False
    assert x['orders_allowed'] is False and x['candidate_money_ready'] is False
    assert x['quantity_changed'] is False and x['liquidation_bound_proven'] is False


def test_candidate_rejects_zero_quantity_instead_of_rounding_up():
    with pytest.raises(ValueError,match='positive'):
        study.funding_comparison(qty='0',entry='100',stop='101',lower_rate='-0.0058',
          interval_minutes=480,taker_rate='0.00055',historical43_adverse='0.00636935')


def test_positive_funding_is_not_netted_against_adverse_costs():
    x=study.funding_comparison(qty='0.1',entry='100',stop='101',lower_rate='0.0001',
          interval_minutes=480,taker_rate='0.00055',historical43_adverse='0.00636935')
    assert x['old_funding_rate_envelope']=='0'
    assert x['old_required_usdt']=='0.12111'
    assert x['scenarios'][0]['total_required_usdt']=='0.442762175'


def test_changed_settlement_interval_blocks_historical_candidate():
    x=study.funding_comparison(qty='0.1',entry='100',stop='101',lower_rate='-0.0058',
          interval_minutes=60,taker_rate='0.00055',historical43_adverse='0.00636935')
    assert x['historical_interval_compatible'] is False
    assert all(s['candidate_status']=='BLOCKED_INTERVAL_CHANGED' and not s['fits_draft_budget']
               for s in x['scenarios'])
