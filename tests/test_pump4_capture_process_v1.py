"""Real credential-free child transport, same parent-only frozen intake."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from test_pump4_stream_publication_v1 import warm,context
from test_pump4_bybit_sources_v1 import NOW
import research_lab.pump4_supervisor_v1 as module


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
first=notice('ZROUSDT')
if mode=='hash':first['capture_sha256']='0'*64
print(json.dumps(first),flush=True)
if mode=='duplicate':print(json.dumps(first),flush=True);raise SystemExit(0)
if mode=='nonzero':raise SystemExit(7)
if mode=='noisy':sys.stderr.write('noise\n'*20000);sys.stderr.flush()
if mode=='delayed':
 deadline=time.monotonic()+5
 while not (archive/'allow-final-seal').exists():
  assert time.monotonic()<deadline,'parent never published early decision'
  time.sleep(.01)
for p in sorted((archive/'symbols').glob('*.json')):
 if p.stem!='ZROUSDT' and not (mode=='missing_notice' and p.stem=='HFTUSDT'):print(json.dumps(notice(p.stem)),flush=True)
if mode=='missing_seal':raise SystemExit(0)
seal['source_capture_files']={str(p.relative_to(archive)):hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.rglob('*.json')}
(archive/'receipt.json').write_text(json.dumps(seal))
if mode=='nonzero_after_seal':raise SystemExit(9)
'''


def child_fixture(tmp_path,monkeypatch,mode='normal'):
    root=tmp_path/'state';template=warm(root,tmp_path);context(template)
    stub=tmp_path/'child.py';stub.write_text(STUB);original=subprocess.Popen;children=[]
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
