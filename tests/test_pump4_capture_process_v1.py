"""Real credential-free child transport, same parent-only frozen intake."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from test_pump4_stream_publication_v1 import warm,context
from test_pump4_bybit_sources_v1 import NOW
import research_lab.pump4_supervisor_v1 as module

REAL_POPEN=subprocess.Popen


STUB=r'''
import os,sys,json,shutil,hashlib,time,socket
def denied(*a,**k):raise AssertionError('OFFLINE_CHILD_NETWORK_DENIED')
class OffSocket(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=OffSocket
socket.create_connection=denied
assert 'BYBIT_API_KEY' not in os.environ and 'BYBIT_ACCOUNTS_JSON' not in os.environ
from pathlib import Path
template=Path(sys.argv[1]);archive=Path(sys.argv[2]);mode=sys.argv[3]
if mode=='silent':time.sleep(20);raise SystemExit(2)
shutil.copytree(template,archive);seal=json.loads((archive/'receipt.json').read_bytes());(archive/'receipt.json').unlink()
if mode=='wrong_hour':
 p=archive/'clock.json';c=json.loads(p.read_bytes())
 c['body']['time']+=3600000;c['request_ms']+=3600000;c['receive_ms']+=3600000
 c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest();p.write_text(json.dumps(c))
 p=archive/'capture-context.json';v=json.loads(p.read_bytes());v['source_hour_open_ms']+=3600000
 v['source_capture_files']['clock.json']=hashlib.sha256((archive/'clock.json').read_bytes()).hexdigest();p.write_text(json.dumps(v))
def notice(symbol):
 raw=(archive/'symbols'/(symbol+'.json')).read_bytes()
 return dict(schema='PUMP4_PUBLIC_SYMBOL_NOTICE_V1',symbol=symbol,capture_sha256=hashlib.sha256(raw).hexdigest())
if mode=='oversized':print('x'*2048,flush=True);raise SystemExit(0)
if mode=='malformed':print('not json',flush=True);raise SystemExit(0)
if mode=='unknown':print(json.dumps(dict(notice('ZROUSDT'),symbol='UNKNOWNUSDT')),flush=True);raise SystemExit(0)
first=notice('BLESSUSDT' if mode.startswith('catchup') else 'ZROUSDT')
if mode=='hash':first['capture_sha256']='0'*64
print(json.dumps(first),flush=True)
if mode=='duplicate':print(json.dumps(first),flush=True);raise SystemExit(0)
if mode=='nonzero':raise SystemExit(7)
if mode=='catchup_fail':print(json.dumps(notice('ZROUSDT')),flush=True);raise SystemExit(7)
if mode=='noisy':sys.stderr.write('noise\n'*20000);sys.stderr.flush()
if mode=='delayed':
 deadline=time.monotonic()+5
 while not (archive/'allow-final-seal').exists():
  assert time.monotonic()<deadline,'parent never published early decision'
  time.sleep(.01)
for p in sorted((archive/'symbols').glob('*.json')):
 if p.stem!=first['symbol'] and not (mode=='missing_notice' and p.stem=='HFTUSDT'):print(json.dumps(notice(p.stem)),flush=True)
if mode=='missing_seal':raise SystemExit(0)
seal['source_capture_files']={str(p.relative_to(archive)):hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.rglob('*.json')}
(archive/'receipt.json').write_text(json.dumps(seal))
if mode=='nonzero_after_seal':raise SystemExit(9)
'''


def child_fixture(tmp_path,monkeypatch,mode='normal'):
    root=tmp_path/'state';template=warm(root,tmp_path);context(template)
    if mode.startswith('catchup'):
        from test_pump4_supervisor_v1 import archive_bars
        from test_pump4_bybit_sources_v1 import H
        from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
        from research_lab.kity_micro_physical_owner_v1 import publish
        from research_lab.alpaca_dynamic_v1 import digest
        source=archive_bars(tmp_path/'catchup-source',[[i*H,10.,12.,8.,11.,100.] for i in range(999,2001)],symbol='BLESSUSDT')
        (template/'symbols/BLESSUSDT.json').write_bytes((source/'symbols/BLESSUSDT.json').read_bytes())
        intake=Pump4Intake(root/'intake/BLESSUSDT.jsonl','BLESSUSDT');bars=[[i*H,10.,12.,8.,11.,100.] for i in range(997,1997)]
        state=intake.seed(bars,available_ms=1997*H,observed_ms=1997*H)
        publish(root/'epochs/BLESSUSDT.json',dict(schema='PUMP4_DATA_EPOCH_V1',symbol='BLESSUSDT',epoch_started_ms=1997*H+1,seed_sha256=state['seed_bars_sha256'],financial_authority=False))
        intake.accept([1997*H,10.,12.,8.,11.,100.],available_ms=1998*H,observed_ms=1998*H)
    stub=tmp_path/'child.py';stub.write_text(STUB);original=REAL_POPEN;children=[]
    monkeypatch.setenv('BYBIT_API_KEY','FICTIONAL_TEST_VALUE')
    monkeypatch.setenv('BYBIT_ACCOUNTS_JSON','FICTIONAL_TEST_VALUE')
    def launch(command,**kwargs):
        assert command[0]==sys.executable and '--stream-symbols' in command
        assert kwargs['close_fds'] is True and 'pass_fds' not in kwargs
        destination=command[command.index('--root')+1]
        child=original([sys.executable,'-B',str(stub),str(template),destination,mode],**kwargs)
        children.append(child);return child
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    return root,module.Supervisor(root,clock=lambda:NOW+3),children


def test_real_child_publishes_early_in_parent_without_credentials_or_fd(tmp_path,monkeypatch):
    root,s,children=child_fixture(tmp_path,monkeypatch,'delayed');original=s._stream_symbol;calls=[]
    def observed(archive,symbol,*a,**kw):
        out=original(archive,symbol,*a,**kw);calls.append(os.getpid())
        if symbol=='ZROUSDT' and not (archive/'allow-final-seal').exists():
            assert not (archive/'receipt.json').exists()
            assert len(list((root/'observations').glob('*.json')))==1
            (archive/'allow-final-seal').touch()
        return out
    monkeypatch.setattr(s,'_stream_symbol',observed)
    out=s.public_cycle()
    assert len(calls)==274 and set(calls)=={os.getpid()}
    assert out['source_intake_pass']==1 and out['broker_writes']==0
    assert children[0].poll()==0
    raw={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}
    assert s.public_cycle()==out
    assert len(children)==1 and raw=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}


@pytest.mark.parametrize('mode',['oversized','malformed','unknown','hash','duplicate','nonzero','missing_notice','missing_seal','nonzero_after_seal','wrong_hour','silent'])
def test_child_failure_is_reaped_and_never_retried_same_hour(tmp_path,monkeypatch,mode):
    root,s,children=child_fixture(tmp_path,monkeypatch,mode)
    monkeypatch.setattr(module,'CAPTURE_PROCESS_TIMEOUT_SECONDS',.2 if mode=='silent' else 5,raising=False)
    with pytest.raises((ValueError,OSError)) as error:s.public_cycle()
    if mode=='wrong_hour':assert 'PARENT_HOUR' in str(error.value)
    assert len(children)==1 and children[0].poll() is not None
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}
    with pytest.raises(ValueError):s.public_cycle()
    assert len(children)==1 and before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}


def test_noisy_stderr_is_drained_with_bounded_retention(tmp_path,monkeypatch):
    root,s,children=child_fixture(tmp_path,monkeypatch,'noisy')
    assert s.public_cycle()['source_intake_pass']==1 and children[0].poll()==0
    proof=json.loads(next((root/'capture-process').glob('*.json')).read_bytes())
    assert proof['stderr_bytes']>65536 and len(proof['stderr_tail'].encode())<=65536


def test_parent_loss_after_fsync_preserves_decision_without_replay(tmp_path,monkeypatch):
    root,s,children=child_fixture(tmp_path,monkeypatch);original=s._stream_symbol
    def lost(archive,symbol,*a,**kw):
        result=original(archive,symbol,*a,**kw)
        if symbol=='ZROUSDT':raise OSError('parent response lost after journal fsync')
        return result
    monkeypatch.setattr(s,'_stream_symbol',lost)
    with pytest.raises(OSError):s.public_cycle()
    journal=(root/'intake/ZROUSDT.jsonl').read_bytes();assert children[0].poll() is not None
    with pytest.raises(ValueError):s.public_cycle()
    assert journal==(root/'intake/ZROUSDT.jsonl').read_bytes() and len(children)==1


def test_process_and_inprocess_collectors_have_identical_journals(tmp_path,monkeypatch):
    import hashlib,shutil
    from research_lab.pump4_bybit_sources_v1 import universe
    results=[]
    for name in ('process','direct'):
        home=tmp_path/name;home.mkdir();root=home/'state'
        if name=='process':
            root,s,children=child_fixture(home,monkeypatch)
            out=s.public_cycle()
        else:
            template=warm(root,home);context(template);s=module.Supervisor(root,clock=lambda:NOW+3)
            def collect(path,*,on_symbol):
                shutil.copytree(template,path);seal=json.loads((path/'receipt.json').read_bytes());(path/'receipt.json').unlink()
                for symbol in ['ZROUSDT',*[s for s in universe() if s!='ZROUSDT']]:on_symbol(path,symbol)
                seal['source_capture_files']={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*.json')}
                (path/'receipt.json').write_text(json.dumps(seal))
            out=s.public_cycle(collector=collect)
        results.append((out['rows'],(root/'intake/ZROUSDT.jsonl').read_bytes(),
            {p.name:p.read_bytes() for p in (root/'observations').glob('*.json')},
            {p.name:p.read_bytes() for p in (root/'epochs').glob('*.json')}))
    assert results[0]==results[1]


def test_cli_progress_protocol_contains_only_published_symbol_and_hash(tmp_path,monkeypatch,capsys):
    import hashlib
    from scripts import capture_pump4_sources_v1 as cli
    def collect(root,*,on_symbol):
        p=root/'symbols/ZROUSDT.json';p.parent.mkdir(parents=True);p.write_bytes(b'{"public":true}\n')
        on_symbol(root,'ZROUSDT');return dict(public_get_requests=0)
    monkeypatch.setattr(cli,'capture',collect)
    assert cli.main(['--capture','--root',str(tmp_path/'archive'),'--stream-symbols'])==0
    notice=json.loads(capsys.readouterr().out)
    assert notice==dict(schema='PUMP4_PUBLIC_SYMBOL_NOTICE_V1',symbol='ZROUSDT',
        capture_sha256=hashlib.sha256(b'{"public":true}\n').hexdigest())


def test_current_signal_precedes_earlier_nonentry_catchup(tmp_path,monkeypatch):
    root,s,children=child_fixture(tmp_path,monkeypatch,'catchup_first');original=s._stream_symbol;first=[]
    before=(root/'intake/BLESSUSDT.jsonl').read_bytes()
    def observed(archive,symbol,*a,**kw):
        if symbol in ('BLESSUSDT','ZROUSDT') and symbol not in first:
            first.append(symbol)
            if symbol=='ZROUSDT':assert (root/'intake/BLESSUSDT.jsonl').read_bytes()==before
        return original(archive,symbol,*a,**kw)
    monkeypatch.setattr(s,'_stream_symbol',observed)
    out=s.public_cycle()
    assert first==['ZROUSDT','BLESSUSDT']
    catchup=next(r for r in out['rows'] if r['symbol']=='BLESSUSDT')
    assert catchup['mode']=='CATCHUP_REPLAY' and catchup['accepted_bars']==2
    assert all(r['mode']=='CATCHUP_REPLAY' and r['status']=='NO_SIGNAL' for r in catchup['decisions'])
    proof=json.loads(next((root/'capture-process').glob('*.json')).read_bytes())
    notice=next(r for r in proof['notices'] if r['symbol']=='BLESSUSDT')
    assert notice['scheduling']=='DEFERRED_CATCHUP_NON_ENTRY'


def test_failed_child_never_processes_deferred_catchup(tmp_path,monkeypatch):
    root,s,children=child_fixture(tmp_path,monkeypatch,'catchup_fail')
    before=(root/'intake/BLESSUSDT.jsonl').read_bytes()
    with pytest.raises(ValueError):s.public_cycle()
    assert (root/'intake/BLESSUSDT.jsonl').read_bytes()==before and children[0].poll() is not None


def test_classifier_never_defers_seed_only_or_recovery(tmp_path,monkeypatch):
    from research_lab.pump4_bybit_sources_v1 import H
    from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
    from research_lab.alpaca_dynamic_v1 import digest
    root,s,children=child_fixture(tmp_path,monkeypatch,'catchup_first');source=tmp_path/'source';raw=(source/'symbols/BLESSUSDT.json').read_bytes();pin=__import__('hashlib').sha256(raw).hexdigest();context_info=s._stream_context(source)
    descriptor=s._catchup_reference(source,'BLESSUSDT',context_info,pin)
    assert descriptor is not None
    identity=digest(dict(context_sha256=context_info[0],symbol='BLESSUSDT',capture_sha256=pin));p=root/'batches'/identity/'BLESSUSDT.json';p.parent.mkdir(parents=True);p.write_text('{}')
    assert s._catchup_reference(source,'BLESSUSDT',context_info,pin) is None
    p.unlink();journal=root/'intake/BLESSUSDT.jsonl';rows=journal.read_bytes().splitlines(keepends=True);journal.write_bytes(rows[0])
    assert s._catchup_reference(source,'BLESSUSDT',context_info,pin) is None


def test_deferred_schedule_preserves_exact_existing_state(tmp_path,monkeypatch):
    results=[]
    for label in ('fifo','priority'):
        home=tmp_path/label;home.mkdir();root,s,children=child_fixture(home,monkeypatch,'catchup_first')
        if label=='fifo':monkeypatch.setattr(s,'_catchup_reference',lambda *a:None)
        out=s.public_cycle();results.append((out['rows'],
            {p.name:p.read_bytes() for p in (root/'intake').glob('*.jsonl')},
            {p.name:p.read_bytes() for p in (root/'observations').glob('*.json')},
            {p.name:p.read_bytes() for p in (root/'epochs').glob('*.json')}))
    assert results[0]==results[1]


@pytest.mark.parametrize('fault',['journal','epoch','source','batch'])
def test_changed_queued_input_is_never_silently_reinterpreted(tmp_path,monkeypatch,fault):
    import hashlib
    from research_lab.alpaca_dynamic_v1 import digest
    root,s,children=child_fixture(tmp_path,monkeypatch,'catchup_first');original=s._stream_symbol;changed=[]
    def mutate(archive,symbol,context_info,*a,**kw):
        if symbol=='ZROUSDT' and not changed:
            changed.append(True)
            if fault=='journal':
                p=root/'intake/BLESSUSDT.jsonl';p.write_bytes(p.read_bytes()+b'\n')
            elif fault=='epoch':
                p=root/'epochs/BLESSUSDT.json';v=json.loads(p.read_bytes());v['epoch_started_ms']+=1;p.write_text(json.dumps(v))
            elif fault=='source':
                p=archive/'symbols/BLESSUSDT.json';p.write_bytes(p.read_bytes()+b' ')
            else:
                pin=hashlib.sha256((archive/'symbols/BLESSUSDT.json').read_bytes()).hexdigest()
                identity=digest(dict(context_sha256=context_info[0],symbol='BLESSUSDT',capture_sha256=pin))
                p=root/'batches'/identity/'BLESSUSDT.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
        return original(archive,symbol,context_info,*a,**kw)
    monkeypatch.setattr(s,'_stream_symbol',mutate)
    with pytest.raises(ValueError):s.public_cycle()
    assert children[0].poll() is not None
    with pytest.raises(ValueError):s.public_cycle()
