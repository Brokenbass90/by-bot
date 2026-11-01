"""A live process / empty prefix is not completed source coverage."""
import copy,json
from pathlib import Path
import pytest
from research_lab import pump4_runtime_sources_v1 as R
from research_lab.pump4_bybit_sources_v1 import H,universe
from test_pump4_current_hour_candidate_v1 import index_case
from test_pump4_account_owner_v1 import create

def completed(root,pub):
    hour=pub['cursor_ms']+H
    rows=[copy.deepcopy(pub) if s==pub['symbol'] else dict(symbol=s,status='UNAVAILABLE_INSTRUMENT',instrument=None) for s in universe()]
    return dict(schema='PUMP4_WS_FULL137_DATA_RECEIPT_V1',source_hour_open_ms=hour,
        census=137,expected_trading=1,complete_pairs=1,within60s=1,disconnected=False,
        hour_pass=True,rows=rows,orders_allowed=False,money_authority=False,
        financial_owner_constructed=False,broker_writes=0)

@pytest.mark.parametrize('fault',['missing_receipt','failed','census','duplicate','missing_index','receipt_conflict','unavailable_claim'])
def test_unverified_completed_hour_blocks_instead_of_no_signal(tmp_path,fault):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        c,_,wire,root,obs,target,pub=index_case(tmp_path/'data')
        v=completed(root,pub);hour=pub['cursor_ms']+H;tick[0]=hour+120001
        if fault=='failed':v['hour_pass']=False
        elif fault=='census':v['census']=136
        elif fault=='duplicate':v['rows'][-1]=v['rows'][0]
        elif fault=='missing_index':target.unlink()
        elif fault=='receipt_conflict':next(r for r in v['rows'] if r['symbol']==pub['symbol'])['pair_received_ms']-=1
        elif fault=='unavailable_claim':v['rows'][-1]['instrument']=dict(symbol=v['rows'][-1]['symbol'],status='Trading',quoteCoin='USDT',contractType='LinearPerpetual')
        if fault!='missing_receipt':(target.parent.parent/'receipt.json').write_text(json.dumps(v))
        p=R.TrustedSources(c,owner,wire=lambda *a:pytest.fail('no late HTTP'),clock=lambda:tick[0])
        with pytest.raises((ValueError,OSError)):p.candidate()
        assert exchange.state['calls']==0 and obs.exists()
    finally:lease.close()

def test_full_completed_census_proves_coverage_not_absence_of_earlier_signal(tmp_path):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        c,_,wire,root,obs,target,pub=index_case(tmp_path/'data')
        (target.parent.parent/'receipt.json').write_text(json.dumps(completed(root,pub)))
        tick[0]=pub['cursor_ms']+H+60001
        p=R.TrustedSources(c,owner,wire=lambda *a:pytest.fail('no late HTTP'),clock=lambda:tick[0])
        assert p.candidate() is None
        assert p.candidate_scan['status']=='ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED'
        assert p.candidate_scan['coverage_complete'] is True
        assert p.candidate_scan['raw_signals']==1 and p.candidate_scan['checked_publications']==1
        assert exchange.state['calls']==0
    finally:lease.close()

def test_missing_current_index_during_window_is_pending_prefix_not_full_no_signal(tmp_path):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        c,_,wire,root,obs,target,pub=index_case(tmp_path/'data');target.unlink()
        p=R.TrustedSources(c,owner,wire=lambda *a:pytest.fail('no positive'),clock=lambda:tick[0])
        assert p.candidate() is None
        assert p.candidate_scan['status']=='WAITING_H1_PUBLICATION_PREFIX'
        assert p.candidate_scan['coverage_complete'] is False
    finally:lease.close()

@pytest.mark.parametrize('status,complete',[
    ('WAITING_H1_PUBLICATION_PREFIX',False),
    ('ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED',True),
    ('WAITING_H1_CENSUS_FINALIZATION',False),
])
def test_selected_supervisor_persists_honest_scan_status(tmp_path,monkeypatch,status,complete):
    from test_pump4_execution_supervisor_v1 import setup,module
    _,_,path,pin,_,_,_=setup(tmp_path,monkeypatch,
        overrides=dict(candidate_source='CURRENT_H1_PUBLICATIONS_V1'))
    class Sources:
        def __init__(self,*a):
            self.candidate_scan=dict(status=status,coverage_complete=complete)
        def candidate(self):return None
        def account(self,*a,**kw):pytest.fail('no candidate, no account/wire')
    rows=module().run(path,pin,orders_off=True,once=True,source_factory=Sources)
    assert rows[0]['result']['status']==status
    assert rows[0]['result']['source_scan']['coverage_complete'] is complete
    assert rows[0]['broker_writes']==0

def test_producer_finalization_grace_does_not_reopen_entry_window(tmp_path):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        c,_,wire,root,obs,target,pub=index_case(tmp_path/'data')
        tick[0]=pub['cursor_ms']+H+90000
        p=R.TrustedSources(c,owner,wire=lambda *a:pytest.fail('no late HTTP'),clock=lambda:tick[0])
        assert p.candidate() is None
        assert p.candidate_scan['status']=='WAITING_H1_CENSUS_FINALIZATION'
        assert p.candidate_scan['entry_window_closed'] is True
        tick[0]=pub['cursor_ms']+H+120001
        with pytest.raises(FileNotFoundError):p.candidate()
        assert exchange.state['calls']==0
    finally:lease.close()

def test_delisted_instrument_metadata_remains_explicitly_unavailable(tmp_path):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        c,_,wire,root,obs,target,pub=index_case(tmp_path/'data')
        v=completed(root,pub)
        absent=next(r for r in v['rows'] if r['status']=='UNAVAILABLE_INSTRUMENT')
        absent['instrument']=dict(symbol=absent['symbol'],status='Settled',quoteCoin='USDT',contractType='LinearPerpetual')
        (target.parent.parent/'receipt.json').write_text(json.dumps(v))
        tick[0]=pub['cursor_ms']+H+120001
        p=R.TrustedSources(c,owner,wire=lambda *a:pytest.fail('no late HTTP'),clock=lambda:tick[0])
        assert p.candidate() is None and p.candidate_scan['coverage_complete'] is True
    finally:lease.close()
