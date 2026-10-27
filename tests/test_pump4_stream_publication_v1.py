"""Existing frozen journals, delayed census and immutable per-symbol publication."""
import copy
import hashlib
import json
from pathlib import Path
import threading

import pytest
from test_pump4_supervisor_v1 import archive, fixture_candidate, row
from test_pump4_bybit_sources_v1 import capture, H, NOW
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.pump4_bybit_sources_v1 import universe, UNIVERSE_SHA
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_supervisor_v1 import Supervisor


def context(path):
    clock=capture('/v5/market/time',{}, {},at=NOW)
    metadata={'clock.json':clock,'instrument-pages.json':dict(complete=True,pages=[capture('/v5/market/instruments-info',dict(category='linear',limit=1000),dict(list=[],nextPageCursor=''),at=NOW)]),
              'tickers.json':capture('/v5/market/tickers',dict(category='linear'),dict(list=[]),at=NOW)}
    for name,value in metadata.items():publish(path/name,value)
    header=dict(schema='PUMP4_PUBLIC_CAPTURE_CONTEXT_V1',universe_sha256=UNIVERSE_SHA,
        census=137,source_hour_open_ms=NOW,started_ms=NOW,
        source_capture_files={n:hashlib.sha256((path/n).read_bytes()).hexdigest() for n in metadata},
        orders_allowed=False,money_authority=False)
    publish(path/'capture-context.json',header)


def warm(root,tmp_path):
    candidate=fixture_candidate(tmp_path)
    (root/'intake').mkdir(parents=True)
    intake=Pump4Intake(root/'intake/ZROUSDT.jsonl','ZROUSDT')
    seed=candidate['intake'].journal.read()[0]
    state=intake.seed(seed['bars'],available_ms=NOW-H,observed_ms=NOW-H)
    publish(root/'epochs/ZROUSDT.json',dict(schema='PUMP4_DATA_EPOCH_V1',symbol='ZROUSDT',
        epoch_started_ms=NOW-1,seed_sha256=state['seed_bars_sha256'],financial_authority=False))
    return tmp_path/'source'


def streaming_collector(template,t,check=None):
    def collect(path,*,on_symbol=None):
        assert callable(on_symbol), 'FULL_CENSUS_MUST_NOT_PRECEDE_PUBLICATION'
        import shutil
        shutil.copytree(template,path)
        old=json.loads((path/'receipt.json').read_bytes());(path/'receipt.json').unlink()
        context(path)
        on_symbol(path,'ZROUSDT')
        assert not (path/'receipt.json').exists()
        if check:check(path)
        t[0]=NOW+120000  # Slow other instruments must not delay this decision.
        old.update(completed_ms=t[0],source_capture_files={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*.json')})
        publish(path/'receipt.json',old)
    return collect


def test_current_decision_is_durable_before_full_census_and_finalization_is_idempotent(tmp_path):
    root=tmp_path/'state';template=warm(root,tmp_path);t=[NOW+3];s=Supervisor(root,clock=lambda:t[0]);early=[]
    def check(path):
        observations=list((root/'observations').glob('*.json'));assert len(observations)==1
        observation=json.loads(observations[0].read_bytes());assert observation['status']=='CAUSAL_PLAN_DATA_ONLY'
        early.append(observation)
    out=s.public_cycle(collector=streaming_collector(template,t,check))
    assert row(out)['decisions']==early and row(out)['mode']=='CURRENT_CLOSED_BAR'
    receipts=list((root/'streamed').rglob('ZROUSDT.json'));assert len(receipts)==1
    receipt=json.loads(receipts[0].read_bytes())
    assert receipt['publication_completed_ms']==NOW+3 and out['prospective_decisions_credited']==0
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}
    assert Supervisor(root,clock=lambda:NOW+H).process_archive(root/'archives'/str(NOW))==out
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}


def test_partial_stream_is_preserved_and_never_blindly_recollected(tmp_path):
    root=tmp_path/'state';template=warm(root,tmp_path);t=[NOW+3];s=Supervisor(root,clock=lambda:t[0])
    def interrupted(path):raise RuntimeError('fixture collector interrupted after durable decision')
    with pytest.raises(RuntimeError,match='interrupted'):
        s.public_cycle(collector=streaming_collector(template,t,interrupted))
    before=(root/'intake/ZROUSDT.jsonl').read_bytes()
    with pytest.raises(ValueError,match='PARTIAL_ARCHIVE'):
        s.public_cycle(collector=lambda *a,**kw:pytest.fail('No recollection after partial publication'))
    assert (root/'intake/ZROUSDT.jsonl').read_bytes()==before
    assert len(list((root/'observations').glob('*.json')))==1


def test_changed_capture_after_early_publication_blocks_finalization(tmp_path):
    root=tmp_path/'state';template=warm(root,tmp_path);t=[NOW+3];s=Supervisor(root,clock=lambda:t[0])
    def changed(path):
        p=path/'symbols/ZROUSDT.json';x=json.loads(p.read_bytes());x['extra']='tampered after publication';p.write_text(json.dumps(x))
    with pytest.raises(ValueError,match='STREAM_CAPTURE_CHANGED'):
        s.public_cycle(collector=streaming_collector(template,t,changed))
    assert len(list((root/'observations').glob('*.json')))==1


def test_streaming_cannot_promote_bootstrap_or_extend_entry_window(tmp_path):
    for mode in ['bootstrap','late']:
        home=tmp_path/mode;home.mkdir();root=home/'state';t=[NOW+60001 if mode=='late' else NOW+3]
        if mode=='late':template=warm(root,home)
        else:
            fixture_candidate(home);template=home/'source'
        out=Supervisor(root,clock=lambda:t[0]).public_cycle(collector=streaming_collector(template,t))
        observation=row(out)['decisions'][0]
        assert observation['status']==('BLOCKED_ENTRY_DIAGNOSTIC' if mode=='late' else 'REPLAY_NOT_PROSPECTIVE')
        assert observation['orders_allowed'] is False and observation['money_authority'] is False


def test_public_collector_calls_back_on_completion_not_input_order(tmp_path,monkeypatch):
    from scripts import capture_pump4_sources_v1 as collector
    monkeypatch.setattr(collector,'ROOT',tmp_path)
    monkeypatch.setattr(collector.time,'time_ns',lambda:(NOW+3)*1000000)
    released=threading.Event();seen=[]
    def get(path,params,**_):
        if path=='/v5/market/time':return capture(path,params,{},at=NOW+2)
        if path=='/v5/market/instruments-info':
            return capture(path,params,dict(list=[dict(symbol=n,status='Trading',quoteCoin='USDT',contractType='LinearPerpetual') for n in ['BLESSUSDT','ZROUSDT']],nextPageCursor=''),at=NOW+2)
        if path=='/v5/market/tickers':return capture(path,params,dict(list=[]),at=NOW+2)
        assert path=='/v5/market/kline'
        if params['symbol']=='BLESSUSDT':assert released.wait(4),'CALLBACK_WAITED_FOR_SLOWER_EARLIER_SYMBOL'
        return capture(path,params,dict(category='linear',symbol=params['symbol'],list=[]),at=NOW+2)
    monkeypatch.setattr(collector,'public_get',get)
    def ready(path,symbol):
        assert (path/'symbols'/(symbol+'.json')).is_file() and (path/'capture-context.json').is_file()
        assert not (path/'receipt.json').exists();seen.append(symbol)
        if symbol=='ZROUSDT':released.set()
    out=collector.capture(tmp_path/'.private/source',on_symbol=ready)
    assert seen.index('ZROUSDT')<seen.index('BLESSUSDT')
    assert out['census']==137 and len(seen)==137 and out['broker_writes']==0
    assert out['strategy_calls'] is None and out['data_intake_callback_used'] is True
    assert {p['symbol'] for p in out['blocked']}==set(universe())


def test_changed_context_after_early_publication_cannot_fork_the_archive(tmp_path):
    root=tmp_path/'state';template=warm(root,tmp_path);t=[NOW+3];s=Supervisor(root,clock=lambda:t[0])
    def changed(path):
        p=path/'capture-context.json';x=json.loads(p.read_bytes());x['started_ms']+=1;p.write_text(json.dumps(x))
    with pytest.raises(ValueError,match='STREAM_CONTEXT_CHANGED'):
        s.public_cycle(collector=streaming_collector(template,t,changed))
    assert len(list((root/'observations').glob('*.json')))==1


def test_finalization_rechecks_actual_capture_bytes_against_full_seal(tmp_path,monkeypatch):
    root=tmp_path/'state';template=warm(root,tmp_path);t=[NOW+3];s=Supervisor(root,clock=lambda:t[0]);verified=s._archive
    def race(path):
        archive_path,identity,seal,data=verified(path)
        p=archive_path/'symbols/BLESSUSDT.json';x=json.loads(p.read_bytes());x['extra']='changed after full verification';p.write_text(json.dumps(x))
        return archive_path,identity,seal,data
    monkeypatch.setattr(s,'_archive',race)
    with pytest.raises(ValueError,match='STREAM_FULL_SEAL_CAPTURE_CHANGED'):
        s.public_cycle(collector=streaming_collector(template,t))
