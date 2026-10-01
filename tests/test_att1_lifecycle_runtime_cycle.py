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

def _runtime_with_session(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent'])
    rt=make_runtime(tmp_path,PublicTape(intent['submit_ms']))
    return rt,rt.admit_candidate(intent['signal'],intent['instrument'])

def test_state_cache_reuses_unchanged_journals_and_isolation(tmp_path, monkeypatch):
    rt,session=_runtime_with_session(tmp_path); calls=[]; original=runner.verify_state
    monkeypatch.setattr(runner,'verify_state',lambda *args:(calls.append(1) or original(*args)))
    first=rt.state(); assert rt.state()==first; assert len(calls)==1
    first['sessions'].append({'poison':True}); assert all('poison' not in x for x in rt.state()['sessions']); assert len(calls)==1

def test_state_cache_invalidates_append_and_replacement(tmp_path, monkeypatch):
    rt,session=_runtime_with_session(tmp_path); calls=[]; original=runner.verify_state
    monkeypatch.setattr(runner,'verify_state',lambda *args:(calls.append(1) or original(*args)))
    rt.state(); path=session.journal.path
    rt._emit(session,'CLOCK')
    rt.state(); assert len(calls)==2
    replacement=path.with_suffix('.replacement'); replacement.write_bytes(path.read_bytes()); replacement.chmod(0o600); replacement.replace(path)
    assert rt.state()==runner.verify_state([path],rt.profile)
    assert len(calls)==4  # Cache invalidation plus the explicit independent replay.

def test_state_cache_rejects_corruption_symlink_and_concurrent_change(tmp_path, monkeypatch):
    rt,session=_runtime_with_session(tmp_path); path=session.journal.path
    path.write_bytes(path.read_bytes()+b'not-json\n')
    from research_lab.att1_lifecycle_journal import JournalViolation
    with pytest.raises(JournalViolation):
        rt.state()
    path.unlink(); path.symlink_to(tmp_path/'missing')
    with pytest.raises(runner.RunnerViolation,match='journal'):
        runner._journal_signature([path])

def test_state_cache_detects_change_during_replay(tmp_path, monkeypatch):
    rt,session=_runtime_with_session(tmp_path); path=session.journal.path; original=runner.verify_state
    def changing(*args):
        result=original(*args); path.touch(); return result
    monkeypatch.setattr(runner,'verify_state',changing)
    with pytest.raises(runner.RunnerViolation,match='changed during'):
        rt.state()


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


def test_scan_concurrency_does_not_hide_a_real_global_clock_gap(tmp_path):
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
    rt.scan_future[2].result(timeout=2)
    rt.manage(session)
    assert len(scan_calls)==1
    assert session.receipt['incidents']==['RECOVERY_GAP']
    assert session.receipt['final_net_r'] is None
    rt.scan_executor.shutdown(wait=True)


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

@pytest.mark.parametrize('offset', [-2001, 1])
def test_bad_book_time_keeps_process_and_durable_gap_until_fresh_exit(tmp_path, offset):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    def bad_book(url,params,**kwargs):
        data=json.loads(tape(url,params,**kwargs))
        if url.endswith('/orderbook'):data['result']['cts']=tape.now+offset
        return json.dumps(data).encode()
    rt.transport=bad_book
    rt.tick()  # The old driver raises RunnerViolation and exits its process here.
    assert session.receipt['held_qty']=='1/10'
    assert session.receipt['incidents']==['RECOVERY_GAP']
    assert session.receipt['final_net_r'] is None
    assert session.receipt==LifecycleSession(session.journal.path,rt.profile).receipt
    assert not any(e['kind']=='EXIT_FILL' for e in rt._records(session))
    assert rt.poll_errors
    rt.tick()
    assert sum(e['kind']=='RECOVERY_GAP' for e in rt._records(session))==1
    rt.transport=tape;rt.tick()
    assert session.receipt['held_qty']=='0'
    assert session.receipt['final_net_r'] is None
    assert not rt.poll_errors

@pytest.mark.parametrize('offset', [-2001, 1])
def test_invalid_entry_book_cancels_only_simulated_ioc_without_dangling_intent(tmp_path, offset):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape)
    def bad_book(url,params,**kwargs):
        data=json.loads(tape(url,params,**kwargs));data['result']['cts']=tape.now+offset
        return json.dumps(data).encode()
    rt.transport=bad_book
    session=rt.admit_candidate(intent['signal'],intent['instrument'])
    assert session.receipt['terminal_nonfill'] is True
    assert session.receipt['pending_entry_qty']=='0'
    assert session.receipt['held_qty']=='0'
    assert session.receipt['final_net_r'] is None
    assert list((rt.root/'sources').glob('*.json'))


def test_malformed_book_remains_fatal_not_caught_as_time_error(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);rt.admit_candidate(intent['signal'],intent['instrument'])
    tape.bid='102'
    with pytest.raises(runner.RunnerViolation,match='crossed'):rt.tick()


def test_hour_scan_covers_universe_while_open_book_observation_continues(tmp_path):
    from threading import Event
    import time
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    tape.now=(tape.now//runner.H1_MS)*runner.H1_MS+20000
    rt.last_observed[session.receipt['plan']['decision_id']]=tape.now
    entered=Event();release=Event();called=[]
    def scan(symbol):
        called.append(symbol);entered.set()
        assert release.wait(2)
        return {'result':'NO_SIGNAL'}
    rt.scan_symbol=scan
    try:
        rt.tick()
        assert entered.wait(.5), 'open exposure must not starve the fixed-universe scan'
        before=len(tape.calls);rt.tick()
        assert len(tape.calls)>before and session.receipt['incidents']==[]
        release.set()
        for _ in range(400):
            rt.tick();time.sleep(.001)
            if len(rt.scanned)==len(runner.FIXED51_UNIVERSE):break
        assert set(rt.scanned)==set(runner.FIXED51_UNIVERSE)
        assert len(called)==len(set(called))==51
        assert session.receipt['held_qty']=='1/10'
        assert session.receipt['incidents']==[]
    finally:
        release.set()
        if getattr(rt,'scan_executor',None):rt.scan_executor.shutdown(wait=True)


def test_simulated_entry_transport_failure_does_not_leave_pending_order(tmp_path):
    from urllib.error import URLError
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape)
    def unavailable(*args,**kwargs):raise URLError('public timeout')
    rt.transport=unavailable
    session=rt.admit_candidate(intent['signal'],intent['instrument'])
    assert session.receipt['terminal_nonfill'] is True
    assert session.receipt['pending_entry_qty']=='0'
    assert session.receipt['final_net_r'] is None


def test_public_get_has_bounded_concurrency_and_start_rate(tmp_path):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);lock=Lock();active=0;peak=0;starts=[]
    def slow(url,params,**kwargs):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active);starts.append(time.monotonic())
        time.sleep(.20)
        with lock:
            raw=tape(url,params,**kwargs);active-=1
        return raw
    rt.transport=slow
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(rt._get,'/v5/market/orderbook','BTCUSDT',limit=50) for _ in range(8)]
        for f in futures:f.result(timeout=4)
    assert peak<=2
    assert max(starts)-min(starts)>=.80  # Eight starts at no more than 8/s.


def test_scan_result_cannot_admit_a_different_h1_cutoff(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);close=intent['signal']['bar_close_ms']-runner.H1_MS
    rt.scan_close=close
    rt.finish_scan(close,'BTCUSDT',{'result':'CANDIDATE','signal':intent['signal'],'instrument':intent['instrument']})
    assert rt.sessions=={}
    assert rt.scan_results['BTCUSDT']=='SCAN_REJECTED'


def test_scan_journal_identity_and_restart_dedupe_are_deterministic(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);close=intent['signal']['bar_close_ms'];rt.scan_close=close
    rt.finish_scan(close,'BTCUSDT',{'result':'NO_SIGNAL'})
    row=rt.scan_journal.read()[0]
    assert row['event_id']=='scan:'+rt.config['epoch_id']+':BTCUSDT:'+str(close)
    before=rt.scan_journal.path.read_bytes()
    rt.finish_scan(close,'BTCUSDT',{'result':'NO_SIGNAL'})
    assert rt.scan_journal.path.read_bytes()==before
    restart=make_runtime(tmp_path,tape);restart.tick()
    assert 'BTCUSDT' in restart.scanned
    assert restart.scan_journal.path.read_bytes()==before
    if restart.scan_executor:restart.scan_executor.shutdown(wait=True)


def test_current_scan_append_never_replays_previous_hours(tmp_path, monkeypatch):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);close=intent['signal']['bar_close_ms'];rt.scan_close=close
    rt.finish_scan(close,'BTCUSDT',{'result':'NO_SIGNAL'})
    old=rt.scan_journal.path;before=old.read_bytes()
    tape.now+=runner.H1_MS;rt.scan_close=close+runner.H1_MS
    original=runner.LifecycleJournal._load
    def no_old_replay(self,fd):
        assert self.path!=old, 'previous H1 scan journal replayed on hot path'
        return original(self,fd)
    monkeypatch.setattr(runner.LifecycleJournal,'_load',no_old_replay)
    rt.finish_scan(close+runner.H1_MS,'BTCUSDT',{'result':'NO_SIGNAL'})
    assert rt.scan_journal.path!=old
    assert old.read_bytes()==before
    assert len(rt.scan_journal.read())==1


def test_state_update_replays_only_changed_session_with_identical_oracle(tmp_path, monkeypatch):
    rt,session=_runtime_with_session(tmp_path)
    intent=deepcopy(FIXTURE['cases'][0]['intent']);intent['book']='second-independent-book'
    other=LifecycleSession(tmp_path/'other.jsonl',rt.profile,intent=intent)
    rt.sessions['other']=other
    rt.state();calls=[];original=runner.verify_state
    def counted(paths,profile):
        calls.append(tuple(paths));return original(paths,profile)
    monkeypatch.setattr(runner,'verify_state',counted)
    rt._emit(session,'CLOCK')
    updated=rt.state()
    assert calls==[(session.journal.path,)]
    assert updated==original([s.journal.path for s in rt.sessions.values()],rt.profile)


def test_late_previous_hour_scan_does_not_contaminate_current_coverage(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);old_close=intent['signal']['bar_close_ms']
    tape.now+=runner.H1_MS;rt.scan_close=old_close+runner.H1_MS
    rt.finish_scan(rt.scan_close,'ETHUSDT',{'result':'NO_SIGNAL'})
    current=rt.scan_journal.path;current_bytes=current.read_bytes()
    rt.finish_scan(old_close,'BTCUSDT',{'result':'NO_SIGNAL'})
    assert rt.scanned=={'ETHUSDT'}
    assert rt.scan_journal.path==current and current.read_bytes()==current_bytes
    assert rt._scan_journal_for(old_close).read()[0]['bar_close_ms']==old_close


def test_changed_cached_archive_is_revalidated_and_rejected(tmp_path):
    rt,session=_runtime_with_session(tmp_path);rt.state()
    # Same length / original mtime cannot hide corruption: ctime participates.
    import os
    p=session.journal.path;before=p.stat();raw=p.read_bytes()
    p.write_bytes(raw.replace(b'"START"',b'"STORT"',1))
    os.utime(p,ns=(before.st_atime_ns,before.st_mtime_ns))
    with pytest.raises(JournalViolation):rt.state()


def test_real_hour_rollover_rejects_old_candidate_by_existing_age_contract(tmp_path):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);old_close=intent['signal']['bar_close_ms']
    tape.now+=runner.H1_MS;rt.scan_close=old_close+runner.H1_MS
    rt.finish_scan(old_close,'BTCUSDT',{'result':'CANDIDATE','signal':intent['signal'],'instrument':intent['instrument']})
    assert not rt.sessions
    assert rt._scan_journal_for(old_close).read()[0]['result']!='ADMITTED'
    assert not rt.scanned


def test_gap_preserves_bounded_operation_timing_source_without_cleaning_evidence(tmp_path, monkeypatch):
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape);session=rt.admit_candidate(intent['signal'],intent['instrument'])
    perf=[0];monkeypatch.setattr(runner.time,'perf_counter_ns',lambda:perf[0])
    original=rt.transport
    def delayed(*args,**kwargs):
        perf[0]+=2_100_000_000;tape.now+=2100
        return original(*args,**kwargs)
    rt.transport=delayed
    rt.manage(session)
    gap=next(e for e in session.journal.read() if e['kind']=='RECOVERY_GAP')
    source=json.loads((rt.root/'sources'/(gap['source_sha256']+'.json')).read_text())
    assert source['observation_gap_ms']>2000
    assert any(t['operation']=='public_get' and t['path']=='/v5/market/orderbook'
               and t['elapsed_ms']==2100 for t in source['operation_timings'])
    assert session.receipt['incidents']==['RECOVERY_GAP']
    assert session.receipt['final_net_r'] is None
    for i in range(100):
        with rt._timed('probe'):perf[0]+=1_000_000
    timings=rt._operation_timings()
    assert len(timings)==64
    timings[0]['operation']='poison'
    assert rt._operation_timings()[0]['operation']=='probe'


def test_failed_public_get_retains_timing_and_exception_type(tmp_path, monkeypatch):
    tape=PublicTape(FIXTURE['cases'][0]['intent']['submit_ms']);rt=make_runtime(tmp_path,tape)
    perf=[0];monkeypatch.setattr(runner.time,'perf_counter_ns',lambda:perf[0])
    def timeout(*args,**kwargs):
        perf[0]+=3_000_000_000;raise TimeoutError('test')
    rt.transport=timeout
    with pytest.raises(TimeoutError):rt._get('/v5/market/orderbook','BTCUSDT',limit=50)
    timings=rt._operation_timings()
    assert timings[-1]['operation']=='public_get'
    assert timings[-1]['elapsed_ms']==3000
    assert timings[-1]['error']=='TimeoutError'


def _two_book_runtime(tmp_path,symbols=('BTCUSDT','ETHUSDT')):
    """Real journals for two symbols; replace only external public transport."""
    intent=deepcopy(FIXTURE['cases'][0]['intent']);tape=PublicTape(intent['submit_ms'])
    rt=make_runtime(tmp_path,tape)
    def multi_symbol(url,params,**kwargs):
        data=json.loads(tape(url,params,**kwargs))
        if url.endswith('/orderbook'):data['result']['s']=params['symbol']
        return json.dumps(data).encode()
    rt.transport=multi_symbol;sessions=[]
    for symbol in symbols:
        signal=deepcopy(intent['signal']);signal['symbol']=symbol
        instrument=deepcopy(intent['instrument']);instrument['symbol']=symbol
        sessions.append(rt.admit_candidate(signal,instrument))
    assert all(s.receipt['held_qty']=='1/10' for s in sessions)
    return rt,tape,sessions


def _stop_observation_workers(rt):
    # Resource cleanup stays in test utilities; run() owns it in production.
    executor=getattr(rt,'observation_executor',None)
    if executor is not None:executor.shutdown(wait=True,cancel_futures=True)


def test_two_fresh_books_do_not_sum_individual_request_latency_into_recovery_gap(tmp_path):
    """Serial1100ms+1100ms polling wrongly dirties otherwise fresh observations."""
    import time
    rt,tape,sessions=_two_book_runtime(tmp_path)
    origin=time.monotonic();base=tape.now
    rt.clock=lambda:base+int((time.monotonic()-origin)*1000)
    rt.last_observed={s.receipt['plan']['decision_id']:base for s in sessions}
    def delayed_book(url,params,**kwargs):
        assert url.endswith('/orderbook')
        time.sleep(1.1);now=rt.clock()
        result={'s':params['symbol'],'b':[['100','10']],'a':[['100.01','10']],
                'ts':now,'cts':now,'u':now,'seq':now}
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    rt.transport=delayed_book
    try:
        rt.tick()
        assert [s.receipt['incidents'] for s in sessions]==[[],[]]
        assert [s.receipt['held_qty'] for s in sessions]==['1/10','1/10']
        assert all(s.receipt['final_net_r'] is None for s in sessions)
    finally:_stop_observation_workers(rt)


@pytest.mark.parametrize('cts_offset',[-2643,5000])
def test_parallel_books_keep_stale_and_future_observations_dirty(tmp_path,cts_offset):
    rt,tape,sessions=_two_book_runtime(tmp_path)
    now=tape.now+100;rt.clock=lambda:now
    def invalid_book(url,params,**kwargs):
        result={'s':params['symbol'],'b':[['100','10']],'a':[['100.01','10']],
                'ts':now,'cts':now+cts_offset,'u':now,'seq':now}
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    rt.transport=invalid_book
    try:
        rt.tick()
        assert [s.receipt['incidents'] for s in sessions]==[['RECOVERY_GAP'],['RECOVERY_GAP']]
        assert [s.receipt['held_qty'] for s in sessions]==['1/10','1/10']
        assert all(s.receipt['final_net_r'] is None for s in sessions)
        assert rt.state()==runner.verify_state([s.journal.path for s in sessions],rt.profile)
    finally:_stop_observation_workers(rt)


@pytest.mark.parametrize('age,accepted',[(2000,True),(2001,False)])
def test_prefetched_book_is_rechecked_at_consumption_without_retiming(tmp_path,age,accepted):
    rt,tape,sessions=_two_book_runtime(tmp_path);rx=tape.now+100
    raw={'retCode':0,'result':{'s':'BTCUSDT','b':[['100','10']],'a':[['100.01','10']],
                             'ts':rx,'cts':rx,'u':rx,'seq':rx},'time':rx}
    rt.clock=lambda:rx+age
    if accepted:
        snapshot,received,observed=rt._book('BTCUSDT',observation=(raw,rx))
        assert received==rx and snapshot['cts']==rx and observed==raw
    else:
        with pytest.raises(runner.PublicBookTimeViolation) as failure:
            rt._book('BTCUSDT',observation=(raw,rx))
        source=json.loads((rt.root/'sources'/(failure.value.source_sha256+'.json')).read_text())
        assert source['received_ms']==rx and source['consumed_ms']==rx+age
        assert source['public_response']==raw


def test_parallel_books_preserve_serial_receipts_and_one_journal_writer(tmp_path,monkeypatch):
    import threading
    serial_dir=tmp_path/'serial';parallel_dir=tmp_path/'parallel'
    serial_dir.mkdir();parallel_dir.mkdir()
    serial,serial_tape,serial_sessions=_two_book_runtime(serial_dir)
    parallel,parallel_tape,parallel_sessions=_two_book_runtime(parallel_dir)
    now=max(serial_tape.now,parallel_tape.now)+100
    def target_book(url,params,**kwargs):
        result={'s':params['symbol'],'b':[['87.99','10']],'a':[['88','10']],
                'ts':now,'cts':now,'u':now,'seq':now}
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    for rt in (serial,parallel):rt.clock=lambda:now;rt.transport=target_book
    for session in serial_sessions:serial.manage(session)
    main=threading.get_ident();writers=[];sources=[]
    original_apply=LifecycleSession.apply;original_save=parallel._save_source
    def checked_apply(self,event):
        writers.append(threading.get_ident());return original_apply(self,event)
    def checked_save(value):
        sources.append(threading.get_ident());return original_save(value)
    monkeypatch.setattr(LifecycleSession,'apply',checked_apply)
    monkeypatch.setattr(parallel,'_save_source',checked_save)
    try:
        parallel.tick()
        assert writers and sources and set(writers+sources)=={main}
        for expected,actual in zip(serial_sessions,parallel_sessions):
            assert actual.receipt['held_qty']=='1/20'
            assert actual.receipt==expected.receipt
            assert actual.journal.path.read_bytes()==expected.journal.path.read_bytes()
        assert parallel.state()==serial.state()
        assert parallel.state()==runner.verify_state([s.journal.path for s in parallel_sessions],parallel.profile)
    finally:_stop_observation_workers(parallel)


@pytest.mark.parametrize('pending_index',[0,1])
def test_prefetch_cannot_cross_or_delay_an_earlier_pending_exit(tmp_path,pending_index):
    from threading import Event,Lock
    symbols=('BTCUSDT','ETHUSDT','XRPUSDT','ADAUSDT')[:3+pending_index]
    rt,tape,sessions=_two_book_runtime(tmp_path,symbols)
    now=tape.now+100;rt.clock=lambda:now
    pending=sessions[pending_index];pending_symbol=symbols[pending_index]
    rt._emit(pending,'PRICE',bid='87.99',ask='88',exchange_ms=now,received_ms=now)
    assert pending.receipt['pending_exit'] is not None
    later_started=Event();starts=[];lock=Lock();original_manage=rt.manage
    def guarded_manage(session,**kwargs):
        if session is pending:later_started.wait(.3)
        return original_manage(session,**kwargs)
    def book(url,params,**kwargs):
        symbol=params['symbol']
        with lock:starts.append(symbol)
        if symbols.index(symbol)>pending_index:later_started.set()
        bid,ask=('87.99','88') if symbol==pending_symbol else ('100','100.01')
        result={'s':symbol,'b':[[bid,'10']],'a':[[ask,'10']],
                'ts':now,'cts':now,'u':now,'seq':now}
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    rt.manage=guarded_manage;rt.transport=book
    try:
        rt.tick()
        assert pending.receipt['held_qty']=='1/20'
        assert starts.index(pending_symbol)<min(starts.index(s) for s in symbols[pending_index+1:])
        assert rt.state()==runner.verify_state([s.journal.path for s in sessions],rt.profile)
    finally:_stop_observation_workers(rt)


def test_failed_prefetch_keeps_other_observations_and_journals_replayable(tmp_path):
    rt,tape,sessions=_two_book_runtime(tmp_path,('BTCUSDT','ETHUSDT','XRPUSDT'))
    now=tape.now+100;rt.clock=lambda:now
    def book(url,params,**kwargs):
        if params['symbol']=='BTCUSDT':raise TimeoutError('synthetic observation timeout')
        result={'s':params['symbol'],'b':[['87.99','10']],'a':[['88','10']],
                'ts':now,'cts':now,'u':now,'seq':now}
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    rt.transport=book
    try:
        rt.tick()
        assert rt.poll_errors[sessions[0].receipt['plan']['decision_id']]=='TimeoutError'
        assert [s.receipt['held_qty'] for s in sessions]==['1/10','1/20','1/20']
        assert rt.state()==runner.verify_state([s.journal.path for s in sessions],rt.profile)
    finally:_stop_observation_workers(rt)


def test_new_exit_fresh_ioc_cannot_compete_with_observation_workers(tmp_path):
    import time
    from threading import Event,Lock,get_ident
    rt,tape,sessions=_two_book_runtime(tmp_path)
    now=tape.now+100;rt.clock=lambda:now
    main=get_ident();eth_started=Event();lock=Lock();active=[0]
    def book(url,params,**kwargs):
        worker=get_ident()!=main
        if worker:
            with lock:active[0]+=1
            if params['symbol']=='ETHUSDT':eth_started.set();time.sleep(.2)
            else:assert eth_started.wait(2)
        else:
            with lock:assert active[0]==0, 'fresh exit IOC competed with prefetched observations'
        result={'s':params['symbol'],'b':[['87.99','10']],'a':[['88','10']],
                'ts':now,'cts':now,'u':now,'seq':now}
        if worker:
            with lock:active[0]-=1
        return json.dumps({'retCode':0,'result':result,'time':now}).encode()
    rt.transport=book
    try:
        rt.tick()
        assert [s.receipt['held_qty'] for s in sessions]==['1/20','1/20']
        assert all(not s.receipt['incidents'] for s in sessions)
        assert rt.state()==runner.verify_state([s.journal.path for s in sessions],rt.profile)
    finally:_stop_observation_workers(rt)
