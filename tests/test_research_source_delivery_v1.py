"""DATA_ONLY ingestion invariants. No real network or credentials."""
import json
from pathlib import Path
import pytest
from research_lab import research_source_delivery_v1 as m


def test_immutable_file_replay_and_conflict(tmp_path):
    p=tmp_path/'one.json';m.put(p,b'one');stamp=p.stat().st_mtime_ns
    m.put(p,b'one');assert p.stat().st_mtime_ns==stamp
    with pytest.raises(ValueError,match='CONFLICT'):m.put(p,b'two')
    assert p.read_bytes()==b'one'


def test_capture_binds_query_retains_raw_and_never_persists_headers(tmp_path):
    calls=[]
    def transport(url,headers):calls.append(url);return 200,b'{"history":[]}'
    c=m.Capture(tmp_path,transport=transport)
    p=c.get('https://clob.polymarket.com/prices-history',dict(market='123',interval='max',fidelity=60),headers={'SECRET':'fixture'})
    assert p['history']==[]
    c.get('https://clob.polymarket.com/prices-history',dict(market='123',interval='max',fidelity=60))
    assert len(calls)==1
    assert all(b'fixture' not in p.read_bytes() for p in tmp_path.rglob('*') if p.is_file())
    with pytest.raises(ValueError):c.get('https://evil.example/v2/orders',{})
    with pytest.raises(ValueError):c.get('https://clob.polymarket.com/order',{})


def test_changed_raw_capture_is_never_reused(tmp_path):
    c=m.Capture(tmp_path,transport=lambda *a:(200,b'{"history":[]}'))
    c.get('https://clob.polymarket.com/prices-history',dict(market='1'))
    next(tmp_path.glob('*.raw')).write_bytes(b'{}')
    with pytest.raises(ValueError,match='HASH'):c.get('https://clob.polymarket.com/prices-history',dict(market='1'))


def test_delivery_replay_rejects_unlisted_data_after_seal(tmp_path):
    m.put(tmp_path/'one.json',b'{}')
    m.seal(tmp_path,dict(schema='fixture'))
    assert m.verify_delivery(tmp_path)['schema']=='fixture'
    m.put(tmp_path/'two.json',b'{}')
    with pytest.raises(ValueError,match='INVENTORY'):m.verify_delivery(tmp_path)


def test_local_delivery_is_byte_identical_idempotent_and_conflict_closed(tmp_path):
    source=tmp_path/'source';target=tmp_path/'target'
    m.put(source/'one.json',b'{}');m.seal(source,dict(schema='fixture'))
    a=m.deliver_snapshot(source,target);assert a['already_imported'] is False
    stamp=(target/'delivery.json').stat().st_mtime_ns
    b=m.deliver_snapshot(source,target);assert b['already_imported'] is True
    assert b['first_local_seal_mtime_ns']==stamp
    (target/'one.json').write_bytes(b'changed')
    with pytest.raises(ValueError):m.deliver_snapshot(source,target)


def test_partial_delivery_never_writes_over_unexpected_files(tmp_path):
    source=tmp_path/'source';target=tmp_path/'target'
    m.put(source/'one.json',b'{}');m.seal(source,dict(schema='fixture'))
    m.put(target/'foreign.json',b'{}')
    with pytest.raises(ValueError,match='INVENTORY'):m.deliver_snapshot(source,target)
    assert not (target/'delivery.json').exists() and not (target/'one.json').exists()


def test_market_profile_does_not_equate_closure_or_price_to_settlement():
    market=dict(id='1',closed=True,closedTime='2026-10-16T20:00:00Z',endDate='2026-10-16T19:00:00Z',
        clobTokenIds='["1","2"]',outcomes='["Yes","No"]',outcomePrices='["0.999","0.001"]')
    out=m.market_profile(market,{'1':{'history':[]},'2':{'history':[]}})
    assert out['resolved_status']=='UNKNOWN' and out['authoritative_winner'] is None
    assert out['tokens_with_history']==0 and out['hourly_full_lifetime_proven'] is False
    assert out['historical_spread_status']=='UNKNOWN'


@pytest.mark.parametrize('history',[[{'t':2,'p':.5},{'t':1,'p':.4}],[{'t':1,'p':.5},{'t':1,'p':.4}],[{'t':1,'p':float('nan')}],[{'t':1,'p':1.1}]])
def test_history_bad_order_duplicate_nonfinite_or_outside_probability_rejected(history):
    with pytest.raises(ValueError):m.price_profile({'history':history})


def test_sparse_history_stays_sparse_and_terminal_price_not_invented():
    out=m.price_profile({'history':[{'t':1,'p':.5},{'t':20000,'p':.8}]})
    assert out['points']==2 and out['max_gap_seconds']==19999
    assert out['hourly_full_lifetime_proven'] is False


def test_explicit_history_uses_bounded_windows_and_reconciles_exact_overlap():
    calls=[]
    def get(url,params):
        calls.append(params)
        return {'history':[{'t':1,'p':.2},{'t':1209600,'p':.3}]} if len(calls)==1 else {'history':[{'t':1209600,'p':.3},{'t':1209601,'p':.4}]}
    out=m.explicit_history(get,'1',1,1209602)
    assert out['history']==[{'t':1,'p':.2},{'t':1209600,'p':.3},{'t':1209601,'p':.4}]
    assert len(calls)==2 and all('interval' not in p and p['fidelity']==60 for p in calls)
    assert calls[1]['startTs']<calls[0]['endTs']


def test_explicit_history_never_hides_conflicting_same_timestamp():
    calls=[]
    def get(*a):
        calls.append(1);return {'history':[{'t':1209600,'p':.2 if len(calls)==1 else .3}]}
    with pytest.raises(ValueError,match='HISTORY_OVERLAP_CONFLICT'):
        m.explicit_history(get,'1',1,1209602)


def test_alpaca_complete_pagination_and_adjustments_are_separate():
    calls=[]
    def get(url,params,headers=None):
        calls.append(dict(params));return dict(symbol='BIL',bars=[{'t':str(len(calls))}],next_page_token='next' if len(calls)==1 else None)
    out=m.alpaca_pages(get,'BIL','all',start='2016-01-01',end='2026-10-16')
    assert len(out)==2 and calls[1]['page_token']=='next'
    assert all(p['feed']=='sip' and p['adjustment']=='all' and p['asof']=='-' for p in calls)


def test_alpaca_pagination_loop_cannot_be_called_complete():
    get=lambda *a,**kw:dict(symbol='BIL',bars=[],next_page_token='same')
    with pytest.raises(ValueError,match='PAGE'):m.alpaca_pages(get,'BIL','split',start='2016-01-01',end='2026-10-16')


def test_pair_qa_detects_missing_sessions_and_adjustment_alignment():
    cal=['2020-01-02','2020-01-03','2020-01-06']
    from datetime import datetime,timezone
    a=[dict(t=int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()*1000))
       for d in ['2020-01-03','2020-01-06']]
    qa=m.bars_qa(a,a,cal)
    assert qa['pre_first_observation_sessions']==['2020-01-02']
    assert qa['missing_sessions_after_first']==[] and qa['adjustment_timestamps_match']
    bad=m.bars_qa(a,a[:-1],cal)
    assert not bad['adjustment_timestamps_match']
