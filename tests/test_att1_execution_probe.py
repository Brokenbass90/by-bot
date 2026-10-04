import json
from pathlib import Path
import pytest
from scripts import run_att1_execution_probe as probe


def test_restart_keeps_original_deadline_and_does_not_extend_study(tmp_path):
    first=probe.Study(tmp_path,'transport','a'*64,now_ms=1000,duration_ms=10000,min_free=0)
    first.close()
    second=probe.Study(tmp_path,'transport','a'*64,now_ms=9000,duration_ms=10000,min_free=0)
    assert second.spec['started_ms']==1000 and second.spec['deadline_ms']==11000
    with pytest.raises(probe.StudyStopped,match='COMPLETE_DEADLINE'):second.check(11000)
    second.close()


def test_replacement_context_and_concurrent_writer_are_rejected(tmp_path):
    first=probe.Study(tmp_path,'funding','a'*64,now_ms=1000,min_free=0)
    with pytest.raises(probe.StudyStopped,match='ALREADY_RUNNING'):
        probe.Study(tmp_path,'funding','a'*64,now_ms=1000,min_free=0)
    first.close()
    with pytest.raises(probe.StudyStopped,match='CONTEXT_CHANGED'):
        probe.Study(tmp_path,'funding','b'*64,now_ms=1000,min_free=0)


def test_capture_caps_stop_without_removing_evidence(tmp_path):
    s=probe.Study(tmp_path,'transport','a'*64,now_ms=1000,min_free=0,max_bytes=200)
    s.append({'raw':'preserve'},now_ms=1001)
    with pytest.raises(probe.StudyStopped,match='STOP_STORAGE_CAP'):
        s.append({'raw':'x'*1000,'random':list(range(100))},now_ms=1002)
    s.close()
    assert list(tmp_path.glob('capture-*.jsonl.gz'))


def header(submit):
    from research_lab.att1_lifecycle_journal import _canonical,_hash,GENESIS
    event={'schema_id':'att1_lifecycle_event_v1','event_id':f'start:{submit}','kind':'START','intent':{'submit_ms':submit}}
    core={'seq':1,'prev_hash':GENESIS,'event':event,'event_sha256':_hash(event)}
    return _canonical({**core,'hash':_hash(core)})+b'\n'


def test_only_future_start_and_replaced_prefix_is_explicit(tmp_path):
    source=tmp_path/'source';source.mkdir()
    old=source/'old.jsonl';old.write_bytes(header(500))
    state=probe.initial_frontier(source)
    (source/'late-old.jsonl').write_bytes(header(999))
    fresh=source/'fresh.jsonl';fresh.write_bytes(header(1001))
    rows=probe.new_starts(source,state,started_ms=1000)
    assert [r['status'] for r in rows]==['FUTURE_START','PRELAUNCH_START_EXCLUDED']
    assert probe.new_starts(source,state,started_ms=1000)==[]
    fresh.write_bytes(header(1002))
    with pytest.raises(probe.StudyStopped,match='SOURCE_PREFIX_CHANGED'):
        probe.new_starts(source,state,started_ms=1000)


def test_torn_new_start_is_retried_but_source_symlink_fails(tmp_path):
    p=tmp_path/'new.jsonl';p.write_bytes(header(1001)[:-1])
    state={};assert probe.new_starts(tmp_path,state,started_ms=1000)==[]
    assert state=={}
    p.write_bytes(header(1001));assert probe.new_starts(tmp_path,state,started_ms=1000)[0]['status']=='FUTURE_START'
    p.unlink();p.symlink_to(tmp_path/'missing')
    with pytest.raises(probe.StudyStopped,match='SOURCE_SYMLINK'):
        probe.new_starts(tmp_path,state,started_ms=1000)


def test_established_study_missing_frontier_fails_closed(tmp_path):
    import asyncio
    s=probe.Study(tmp_path/'runtime','funding','a'*64,now_ms=1000,min_free=0)
    source=tmp_path/'source';source.mkdir();(source/'new.jsonl').write_bytes(header(2000))
    with pytest.raises(probe.StudyStopped,match='BLOCKED_FRONTIER_MISSING'):
        asyncio.run(probe.funding(s,{},source))
    assert not (s.root/'frontier.json').exists()
    s.close()


def test_funding_capture_is_complete_and_fsynced_before_cursor_commit(tmp_path,monkeypatch):
    import gzip
    import stat
    s=probe.Study(tmp_path,'funding','a'*64,now_ms=1000,min_free=0)
    s.append({'kind':'first'},now_ms=1001)
    original=s.file;writes=[];syncs=[];real_sync=probe.os.fsync
    class ShortWriter:
        def write(self,value):
            n=max(1,len(value)//2);writes.append(n);return original.write(value[:n])
        def fileno(self):return original.fileno()
        def close(self):original.close()
    def synced(fd):
        syncs.append('directory' if stat.S_ISDIR(probe.os.fstat(fd).st_mode) else 'file');real_sync(fd)
    s.file=ShortWriter();monkeypatch.setattr(probe.os,'fsync',synced)
    s.append({'kind':'second','exact':'durable'},now_ms=1002)
    assert len(writes)>1 and syncs==['file','directory']
    s.close()
    rows=[]
    for p in tmp_path.glob('capture-*.jsonl.gz'):
        with gzip.open(p,'rt') as f:rows.extend(json.loads(line) for line in f)
    assert rows==[{'kind':'first'},{'kind':'second','exact':'durable'}]


def funding_fixture():
    from research_lab.att1_lifecycle_profile import build_profile
    base=build_profile(probe.ROOT);s=base['strategy'];t=1800000000000//3600000*3600000
    signal={'schema_id':'att1_lifecycle_signal_v1','symbol':'BTCUSDT','stream':'EXECUTION_FORWARD',
        'side':'short','entry':'100','sl':'110','tps':['88','75'],'bar_close_ms':t,
        'source_available_ms':t+100,'signal_ready_ms':t+200,
        'profile_sha256':base['profile_sha256'],'source_sha256':'a'*64,'data_sha256':'b'*64,
        **{k:s[k] for k in ('tp_fracs','be_trigger_rr','be_lock_rr','trailing_atr_mult',
                            'trailing_atr_period','trail_activate_rr','time_stop_bars_5m')}}
    instrument={'symbol':'BTCUSDT','tick_size':'0.01','qty_step':'0.01','min_order_qty':'0.01',
        'min_notional':'1','max_market_qty':'10000','observed_ms':t+300,'source_sha256':'c'*64}
    row={'start':{'event':{'intent':{'signal':signal,'instrument':instrument,
         'submit_ms':t+500,'book_state':{'active_decision_id':None,'last_admitted_bar_ms':None,'last_terminal_ms':None}}}}}
    context={'study_id':'test-hypothetical','public_profile':base,'symbols':{'BTCUSDT':{
        'taker_fee':'0.00055','historical43_adverse':'0.00357573','fee_asof_ms':t-100000}}}
    return row,context


def test_frozen_sizing_integration_keeps_synthetic_provenance_and_dated_fees(monkeypatch):
    row,context=funding_fixture()
    monkeypatch.setattr(probe,'public_instrument',lambda s:({'result':{'list':[
        {'lowerFundingRate':'-0.00333','fundingInterval':480}]}},1800000001000))
    out=probe.funding_row(row,context)
    assert out['sizing']['plan']['requested_qty']=='0.03'
    assert out['sizing']['plan']['submit_ms']==row['start']['event']['intent']['submit_ms']
    assert out['synthetic_binding_is_account_evidence'] is False
    assert out['fee_status']=='DATED_CAPTURED_FEE_ASSUMPTION_NOT_REFRESHED'
    assert out['comparison']['candidate_money_ready'] is False and out['orders_allowed'] is False


def test_frozen_zero_quantity_never_fetches_costs_or_rounds_up(monkeypatch):
    row,context=funding_fixture();row['start']['event']['intent']['instrument']['qty_step']='0.1'
    monkeypatch.setattr(probe,'public_instrument',lambda s:pytest.fail('zero size must not reach cost fetch'))
    out=probe.funding_row(row,context)
    assert out['status']=='FROZEN_QUANTITY_REJECTED' and out['sizing']['code']=='BELOW_MIN_QTY'
    assert out['candidate_money_ready'] is False
