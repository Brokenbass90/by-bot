"""Opening controller tests: actual planner/adapter, synthetic broker only."""
import copy
import importlib
import json
from pathlib import Path
import pytest
from test_alpaca_dynamic_v1 import policy, calendar, snapshot, ranking, book, api
from test_alpaca_dynamic_paper import Broker

OPEN=1791379800000

def dispatcher_api():
    try:return importlib.import_module('research_lab.alpaca_open_dispatch_v2')
    except ImportError:return None

class Clock:
    def __init__(self,ms):self.ms=ms;self.mono=0
    def wall_ms(self):return self.ms
    def monotonic_ms(self):return self.mono
    def advance(self,ms):self.ms+=ms;self.mono+=ms

@pytest.fixture
def setup(tmp_path,policy,book,snapshot):
    m=dispatcher_api();assert m is not None,'opening controller missing'
    static=tmp_path/'static.json';static.write_text('{"prechecked":true}')
    clock=Clock(OPEN-900000)
    checks={k:{'status':'VERIFIED','source_sha256':'a'*64} for k in m.STATIC_CHECKS}
    checks['reservation_handoff']['status']='CLEAR_OR_REVIEWED'
    d=m.OpeningDispatcher(tmp_path/'dispatch',policy,OPEN,{'static.json':static},checks,clock,plan_store=book.path)
    ready=d.prepare();assert ready['status']=='STATIC_PREPARED'
    snapshot['quotes']['NET']['quote_ms']=snapshot['observed_ms']
    clock.advance(840000);assert d.ready()['status']=='READY_TO_DISPATCH'
    return m,d,clock,static,book,snapshot

def test_full_exact_path_has_one_adapter_invocation_and_native_stop(setup,policy,tmp_path):
    m,d,c,static,book,snapshot=setup;broker=Broker()
    c.advance(61000)
    result=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),
        execute=lambda p:m.existing_paper_path(p,policy,broker,broker.account_id,tmp_path/'paper',c.wall_ms(),send=True))
    assert result['status']=='OPENING_PATH_COMPLETED' and result['execution']['status']=='PAPER_PROTECTED'
    assert result['money_authority'] is False and result['evidence_kind']=='INPUT_PROVIDED_ENGINEERING'
    assert [x['side'] for x in broker.writes]==['buy','sell']
    assert result['timings'][0]['name']=='fresh' and result['timings'][1]['name']=='reserve'
    assert d._read('fresh.json')['value']==snapshot
    assert d.run(fresh=lambda:pytest.fail('repeated fresh'),reserve=lambda _:None,execute=lambda _:None)==result

def test_slow_fresh_capture_blocks_before_reservation(setup):
    m,d,c,_,book,snapshot=setup;c.advance(61000)
    def fresh():c.advance(m.FRESH_BUDGET_MS+1);return snapshot
    r=d.run(fresh=fresh,reserve=lambda _:pytest.fail('must not reserve'),execute=lambda _:pytest.fail('must not send'))
    assert r['status']=='BLOCKED_EXECUTION' and r['reason']=='FRESH_TIME_BUDGET'
    assert book.intent_count()==0

@pytest.mark.parametrize('offset',[-1,300000,299000])
def test_no_early_late_or_insufficient_budget_start(setup,offset):
    _,d,c,_,book,_=setup;c.advance(60000+offset)
    r=d.run(fresh=lambda:pytest.fail('outside start budget'),reserve=lambda _:None,execute=lambda _:None)
    assert r['status']=='BLOCKED_EXECUTION' and book.intent_count()==0

@pytest.mark.parametrize('change',['future','stale','unknown_owner','unknown_cash','missing_quote_clock'])
def test_bad_fresh_sources_cannot_be_reserved(setup,change):
    _,d,c,_,book,s=setup;c.advance(61000);s=copy.deepcopy(s)
    if change=='future':s['observed_ms']=c.wall_ms()+1
    if change=='stale':s['observed_ms']=c.wall_ms()-300001
    if change=='unknown_owner':s['single_owner_verified']=False
    if change=='unknown_cash':s['cash_finality_verified']=False
    if change=='missing_quote_clock':del s['quotes']['NET']['quote_ms']
    r=d.run(fresh=lambda:s,reserve=lambda _:pytest.fail('invalid source'),execute=lambda _:None)
    assert r['status']=='BLOCKED_DATA' and book.intent_count()==0

def test_changed_static_file_blocks_before_broker_work(setup):
    _,d,c,static,book,_=setup;static.write_text('changed');c.advance(61000)
    assert d.run(fresh=lambda:pytest.fail('changed static'),reserve=lambda _:None,execute=lambda _:None)['status']=='BLOCKED_DATA'
    assert book.intent_count()==0

def test_late_static_preparation_cannot_claim_ready(tmp_path,policy):
    m=dispatcher_api();assert m is not None
    clock=Clock(OPEN-899999)
    d=m.OpeningDispatcher(tmp_path/'late',policy,OPEN,{}, {},clock)
    assert d.prepare()['status']=='BLOCKED_DATA'

def test_not_ready_by_tminusone_is_terminal(tmp_path,policy,setup):
    m,_,_,static,book,_=setup;c=Clock(OPEN-900000)
    checks={k:{'status':'VERIFIED','source_sha256':'a'*64} for k in m.STATIC_CHECKS};checks['reservation_handoff']['status']='CLEAR_OR_REVIEWED'
    d=m.OpeningDispatcher(tmp_path/'late-ready',policy,OPEN,{'static':static},checks,c,plan_store=book.path);d.prepare();c.advance(840001)
    assert d.ready()['status']=='BLOCKED_EXECUTION'
    c.advance(60000);assert d.ready()['status']=='BLOCKED_EXECUTION'

def test_uncertain_adapter_invocation_has_no_second_call_after_restart(setup,policy,tmp_path):
    m,d,c,static,book,snapshot=setup;c.advance(61000);calls=[]
    def uncertain(plan):calls.append(plan);raise TimeoutError('lost after boundary')
    first=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),execute=uncertain)
    assert first['status']=='BLOCKED_EXECUTION' and len(calls)==1
    restarted=m.OpeningDispatcher(d.runtime,policy,OPEN,{'static.json':static},d.checks,c,plan_store=book.path)
    assert restarted.run(fresh=lambda:pytest.fail('restart read'),reserve=lambda _:None,execute=uncertain)==first
    assert len(calls)==1 and book.intent_count()==1

def test_prior_pending_reservation_is_preserved(setup,policy):
    _,d,c,_,book,snapshot=setup;c.advance(61000)
    prior=book.propose(snapshot,policy['calendar_sessions'],c.wall_ms())
    r=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),execute=lambda _:pytest.fail('cannot adopt existing plan'))
    assert r['status']=='BLOCKED_EXECUTION' and r['reason']=='PLAN_NOT_NEW_FOR_THIS_ATTEMPT'
    assert book.intent_count()==1 and prior['receipt_id']

def test_adapter_blocker_is_terminal_blocker_not_success(setup,policy):
    _,d,c,_,book,snapshot=setup;c.advance(61000)
    r=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),
            execute=lambda _:{'status':'BLOCKED_EXECUTION','reason':'broker422'})
    assert r['status']=='BLOCKED_EXECUTION' and r['reason']=='broker422'


def test_real_hard_budget_interrupts_stalled_pre_dispatch_work():
    import time
    m=dispatcher_api();assert m is not None
    start=time.monotonic()
    with pytest.raises(TimeoutError):
        with m.hard_budget(20):time.sleep(1)
    assert time.monotonic()-start<.5

class ReadOnlyLive:
    base_url='https://api.alpaca.markets'
    def __init__(self,account_id):self.account_id=account_id;self.reads=[];self.fail={}
    def get_account(self):
        self.reads.append('account')
        return {'id':self.account_id,'status':'ACTIVE','trading_blocked':False,'account_blocked':False,
                'cash':'100','non_marginable_buying_power':'100','pending_reg_taf_fees':'0','accrued_fees':'0',**self.fail}
    def list_positions(self):self.reads.append('positions');return []
    def list_orders(self,**kw):self.reads.append('orders');return []
    def _request(self,method,path):
        assert method=='GET' and path=='/v2/assets/NET'
        self.reads.append('asset');return {'symbol':'NET','status':'active','tradable':True,'fractionable':True}

def test_preloaded_fresh_publisher_deducts_cat_and_uses_exchange_clock(policy,snapshot):
    m=dispatcher_api();assert m is not None
    live=ReadOnlyLive(policy['account_id']);template=copy.deepcopy(snapshot);template.update(positions=[],open_orders=[])
    template['quotes']['NET']['risk_distance']='4'
    template['gates']['NET']['protection']=False  # overwritten only by verified protocol mapping
    protocol=json.loads((Path(__file__).parents[1]/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_text())
    protocol=copy.deepcopy(protocol);protocol['fractional_protocol']['requires_fresh_asset']['symbol']='NET'
    c=Clock(OPEN+1000)
    pub=m.PreloadedSourcePublisher(policy,template,protocol,'NET',live,
        lambda s:{'quote':{'t':'2026-10-07T13:30:00Z','ap':100},'received_ms':c.wall_ms()},c)
    result=pub.capture()
    assert result['liability_reserve_usd']=='0.01' and result['cash_usd']=='100'
    assert result['fee_rate']=='0' and result['quotes']['NET']['quote_ms']==OPEN
    assert result['source_sha256']!=snapshot['source_sha256'] and result['gates']['NET']['protection'] is True
    assert live.reads==['account','positions','orders','asset']
    assert result['source_evidence']==pub.last_source

@pytest.mark.parametrize('changes',[{'pending_reg_taf_fees':'0.02'},{'accrued_fees':None},{'status':'DISABLED'},{'cash':'NaN'}])
def test_unknown_or_unreconciled_fresh_account_blocks_publisher(policy,snapshot,changes):
    m=dispatcher_api();assert m is not None
    live=ReadOnlyLive(policy['account_id']);live.fail=changes
    protocol=json.loads((Path(__file__).parents[1]/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_text())
    with pytest.raises(ValueError):
        m.PreloadedSourcePublisher(policy,snapshot,protocol,'NET',live,lambda _:pytest.fail('must not request quote'),Clock(OPEN+1000)).capture()

def test_cli_has_no_live_write_route_or_profile_fallback():
    from scripts.run_alpaca_open_dispatch_v2 import LiveGetSource
    source=LiveGetSource('fixture','fixture')
    with pytest.raises(ValueError,match='LIVE_READ_ONLY_SOURCE_ROUTE'):source._request('POST','/v2/orders')
    with pytest.raises(ValueError):source._request('GET','https://evil.test/v2/assets/NET')


def test_fresh_ceiling_does_not_silently_admit_an_oversized_plan(setup,policy):
    _,d,c,_,book,snapshot=setup;c.advance(61000)
    snapshot['quotes']['NET']['fee_quantity_ceiling']='.5'
    r=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),
            execute=lambda _:pytest.fail('fee bound exceeded'))
    assert r['status']=='BLOCKED_DATA' and r['reason']=='SOURCE_FEE_QUANTITY_CEILING_EXCEEDED'

from test_alpaca_dynamic_v1 import causal_bundle

def test_precomputed_closed_ranking_matches_existing_opening_selector(policy,calendar,causal_bundle):
    m=dispatcher_api();assert m is not None
    from scripts.run_alpaca_dynamic_v1_orders_off import load_history
    from research_lab.alpaca_dynamic_v1 import build_ranking
    history=load_history(causal_bundle['history']);available=1791316800000+1000;prepared=OPEN-900000
    draft=m.precompute_ranking(policy,history,['AMD','CRWD','META'],'b'*64,available,prepared,OPEN)
    expected=build_ranking(policy,calendar,history,['AMD','CRWD','META'],'b'*64,available,OPEN+1000)
    assert draft['status']=='PRECOMPUTED_NOT_SEALED' and draft['ranking']==expected
    assert draft['prepared_ms']==prepared and draft['money_authority'] is False


def test_precompute_refuses_to_backdate_or_invent_weekly_refresh(policy,causal_bundle):
    m=dispatcher_api();assert m is not None
    from scripts.run_alpaca_dynamic_v1_orders_off import load_history
    history=load_history(causal_bundle['history'])
    with pytest.raises(ValueError):m.precompute_ranking(policy,history,[],'b'*64,OPEN-1,OPEN-900000,OPEN)
    with pytest.raises(ValueError):m.precompute_ranking(policy,history,[],'b'*64,OPEN-900001,OPEN-900000,1791466200000)

def test_static_preparation_must_finish_before_tminus15(setup,policy,tmp_path):
    m,_,_,static,book,_=setup;c=Clock(OPEN-900000)
    d=m.OpeningDispatcher(tmp_path/'slow-prep',policy,OPEN,{'static':static},setup[1].checks,c,plan_store=book.path)
    real=d._pins
    def slow():r=real();c.advance(1);return r
    d._pins=slow
    assert d.prepare()['status']=='BLOCKED_DATA'


def test_slow_fresh_persistence_blocks_before_reservation(setup):
    _,d,c,_,book,snapshot=setup;c.advance(61000);write=d._write
    def slow(name,value):
        r=write(name,value)
        if name=='fresh.json':c.advance(200000)
        return r
    d._write=slow
    r=d.run(fresh=lambda:snapshot,reserve=lambda _:pytest.fail('cannot consume vacancy'),execute=lambda _:None)
    assert r['status']=='BLOCKED_EXECUTION' and book.intent_count()==0
    assert r['timings'][0]['elapsed_ms']==200000


def test_missing_stop_day_mapping_cannot_claim_protection_eligibility(policy,snapshot):
    m=dispatcher_api();live=ReadOnlyLive(policy['account_id']);s=copy.deepcopy(snapshot);s['positions']=[]
    protocol=json.loads((Path(__file__).parents[1]/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_text())
    del protocol['fractional_protocol']['supported_execution']
    protocol['fractional_protocol']['requires_fresh_asset']['symbol']='NET'
    with pytest.raises(ValueError,match='PROTECTION_PROTOCOL_MAPPING'):
        m.PreloadedSourcePublisher(policy,s,protocol,'NET',live,lambda _:{},Clock(OPEN+1000)).capture()


def test_partial_protection_is_not_aborted_when_post_entry_work_extends_past_opening(setup,policy,tmp_path):
    m,d,c,_,book,snapshot=setup;c.advance(61000);broker=Broker();broker.fill_qty='.4'
    def existing(plan):
        r=m.existing_paper_path(plan,policy,broker,broker.account_id,tmp_path/'partial',c.wall_ms(),send=True)
        c.advance(600000);return r
    r=d.run(fresh=lambda:snapshot,reserve=lambda s:book.propose(s,policy['calendar_sessions'],c.wall_ms()),execute=existing)
    assert r['execution']['status']=='PAPER_PROTECTED' and r['execution']['filled_qty']=='0.4'
    assert broker.writes[-1]['qty']=='0.4'
    assert r['timings'][-1]['protection_not_aborted_by_dispatch_deadline'] is True
