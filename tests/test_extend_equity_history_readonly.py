import datetime as dt
import pytest
from scripts.extend_equity_history_readonly import normalize

def row(**changes):
    return {'t':'2016-01-04T05:00:00Z','o':100,'h':102,'l':99,'c':101,'v':50,'vw':100.5,'n':20,**changes}

def test_preserves_bar_fields_units_and_values():
    result=normalize([row()],dt.date(2016,1,1),dt.date(2016,1,10))
    assert result==[{'t':1451883600000,'o':100.,'h':102.,'l':99.,'c':101.,'v':50.,'vw':100.5,'n':20}]

@pytest.mark.parametrize('rows',[ [row(),row()], [row(t='2015-12-31T05:00:00Z')], [row(c=float('nan'))], [row(h=90)], [row(t='2016-01-04T05:00:00')]])
def test_invalid_rows_are_rejected_without_repair(rows):
    with pytest.raises(ValueError):normalize(rows,dt.date(2016,1,1),dt.date(2016,1,10))

def test_zero_trade_provider_observation_is_preserved_not_fabricated():
    result=normalize([row(v=0,vw=0,n=0)],dt.date(2016,1,1),dt.date(2016,1,10))
    assert result[0]['v']==result[0]['vw']==result[0]['n']==0

def test_traded_bar_with_missing_vwap_is_rejected():
    with pytest.raises(ValueError):
        normalize([row(v=184,vw=0,n=11)],dt.date(2016,1,1),dt.date(2016,1,10))

def test_saved_raw_pages_cannot_cross_request_identities(tmp_path):
    from scripts.extend_equity_history_readonly import bind_raw_cache
    bind_raw_cache(tmp_path,{'start':'2016-01-01','asof':'-'})
    bind_raw_cache(tmp_path,{'start':'2016-01-01','asof':'-'})
    with pytest.raises(ValueError,match='raw_cache_identity_changed'):
        bind_raw_cache(tmp_path,{'start':'2018-01-01','asof':'-'})

def test_unidentified_saved_raw_cache_is_rejected(tmp_path):
    from scripts.extend_equity_history_readonly import bind_raw_cache
    (tmp_path/'AAPL.0.json').write_text('{}')
    with pytest.raises(ValueError,match='unbound_existing_raw_cache'):
        bind_raw_cache(tmp_path,{'start':'2016-01-01'})
