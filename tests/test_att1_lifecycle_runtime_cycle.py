from copy import deepcopy
from pathlib import Path
import json
import pytest
from scripts import run_att1_lifecycle_zero_risk as runner
from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_session import LifecycleSession
from research_lab.att1_lifecycle_journal import JournalViolation

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=json.loads((ROOT/'tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json').read_bytes())

class PublicTape:
    def __init__(self,t):
        self.now=t;self.bid='100';self.ask='100.01';self.calls=[];self.funding=[]
    def clock(self):return self.now
    def sleep(self,seconds):self.now+=int(seconds*1000)
    def __call__(self,url,params,**kwargs):
        self.now+=100;self.calls.append((url,params))
        if url.endswith('/orderbook'):
            result={'s':'BTCUSDT','b':[[self.bid,'10']],'a':[[self.ask,'10']],
                    'ts':self.now,'cts':self.now,'u':self.now,'seq':self.now}
        elif url.endswith('/funding/history'):
            result={'category':'linear','list':self.funding}
        elif url.endswith('/mark-price-kline'):
            result={'category':'linear','symbol':'BTCUSDT','list':[[str(params['start']),'100','100','100','100']]}
        else:raise AssertionError(url)
        return json.dumps({'retCode':0,'result':result,'time':self.now}).encode()


def make_runtime(tmp_path,tape):
    config=json.loads((ROOT/'configs/research/att1_lifecycle_public_v1.json').read_bytes())
    (tmp_path/'cache').mkdir(exist_ok=True)
    config.update(enabled=True,runtime_dir=str(tmp_path/'runtime'),l1_cache_dir=str(tmp_path/'cache'))
    return runner.PublicLifecycleRuntime(config,clock_ms=tape.clock,transport=tape,sleep_fn=tape.sleep)


def test_public_tape_entry_two_targets_fees_and_full_restart_oracle(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape)
    session=rt.admit_candidate(intent['signal'],intent['instrument'])
    assert session.receipt['held_qty']=='1/10'
    assert session.receipt['protected_qty']=='1/10'
    assert session.receipt['entry_status']=='FILLED'
    original=deepcopy(session.receipt)
    restarted=make_runtime(tmp_path,tape)
    assert next(iter(restarted.sessions.values())).receipt==original
    assert rt.state()==restarted.state()
    tape.bid='87.99';tape.ask='88'
    rt.manage(session)
    assert session.receipt['held_qty']=='1/20'
    tape.bid='74.99';tape.ask='75'
    rt.manage(session)
    assert session.receipt['held_qty']=='0'
    assert session.receipt['final_net_r'] is None
    tape.now+=65000
    rt.reconcile_funding(session)
    assert session.receipt['final_net_r']=='36637/20000'
    final_state=rt.state();assert make_runtime(tmp_path,tape).state()==final_state
    assert session.receipt['accounting']['known_fee_total']=='363/20000'
    assert all('/v5/market/' in endpoint for endpoint,_ in tape.calls)


def test_restart_gap_preserves_open_position_before_simulated_emergency_exit(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    before=deepcopy(session.receipt);tape.now+=10000
    restart=make_runtime(tmp_path,tape);restored=next(iter(restart.sessions.values()))
    assert restored.receipt==before
    restart.mark_restart_gaps()
    assert restored.receipt['held_qty']=='1/10'
    assert restored.receipt['incidents']==['RECOVERY_GAP']
    restart.manage(restored)
    assert restored.receipt['held_qty']=='0'
    assert restored.receipt['final_net_r'] is None


def test_runtime_refuses_torn_journal_and_changed_execution_epoch(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    path=session.journal.path;raw=path.read_bytes()[:-1];path.write_bytes(raw)
    with pytest.raises(JournalViolation):make_runtime(tmp_path,tape)
    assert path.read_bytes()==raw


def test_ioc_nonfill_retains_zero_exposure_without_trade_or_net_r(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    original=tape.__call__
    def stale(url,params,**kwargs):
        data=json.loads(original(url,params,**kwargs))
        if url.endswith('/orderbook'):data['result']['cts']=intent['submit_ms']-1
        return json.dumps(data).encode()
    rt=make_runtime(tmp_path,tape);rt.transport=stale
    session=rt.admit_candidate(intent['signal'],intent['instrument'])
    assert session.receipt['terminal_nonfill'] is True
    assert session.receipt['held_qty']=='0'
    assert session.receipt['final_net_r'] is None


def test_public_funding_uses_historical_exposure_after_exit(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    settlement=intent['signal']['bar_close_ms']+60000
    tape.now=settlement+20000;tape.bid='111.99';tape.ask='112'
    rt.manage(session)  # the observation gap is explicitly dirty, while cash stays measurable
    assert session.receipt['held_qty']=='0'
    tape.funding=[{'symbol':'BTCUSDT','fundingRate':'0.001','fundingRateTimestamp':str(settlement)}]
    tape.now+=65000;rt.reconcile_funding(session)
    assert session.receipt['accounting']['settled_funding']=='1/100'
    assert session.receipt['accounting']['net_realized']=='-757/625'
    assert session.receipt['final_net_r'] is None
    assert make_runtime(tmp_path,tape).state()==rt.state()


def test_slow_observation_book_marks_open_session_dirty_after_response(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    original=tape.__call__
    def slow_book(url,params,**kwargs):
        if url.endswith('/orderbook'):tape.now+=2100
        return original(url,params,**kwargs)
    rt.transport=slow_book
    rt.manage(session)
    assert session.receipt['incidents']==['RECOVERY_GAP']
    assert session.receipt['final_net_r'] is None


def test_open_session_defers_slow_optional_scan_before_next_observation(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    tape.now=(tape.now//runner.H1_MS)*runner.H1_MS+20000
    rt.last_observed[session.receipt['plan']['decision_id']]=tape.now
    scan_calls=[]
    def slow_scan(symbol):
        scan_calls.append(symbol);tape.now+=2100
        return {'result':'NO_SIGNAL'}
    rt.scan_symbol=slow_scan
    rt.tick()
    rt.manage(session)
    assert scan_calls==[]
    assert session.receipt['incidents']==[]
    assert session.receipt['held_qty']=='1/10'


def test_dirty_flat_completed_funding_coverage_does_not_repeat_public_get(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    settlement=intent['signal']['bar_close_ms']+60000
    tape.now=settlement+20000;tape.bid='111.99';tape.ask='112'
    rt.manage(session)
    assert session.receipt['incidents']==['RECOVERY_GAP']
    tape.funding=[{'symbol':'BTCUSDT','fundingRate':'0.001','fundingRateTimestamp':str(settlement)}]
    tape.now+=65000;rt.reconcile_funding(session)
    before_calls=len(tape.calls)
    before_coverage=len([e for e in rt._records(session) if e['kind']=='FUNDING_COVERAGE'])
    tape.now+=65000;rt.reconcile_funding(session)
    assert len(tape.calls)==before_calls
    assert len([e for e in rt._records(session) if e['kind']=='FUNDING_COVERAGE'])==before_coverage
    assert session.receipt['incidents']==['RECOVERY_GAP']
    assert session.receipt['final_net_r'] is None
