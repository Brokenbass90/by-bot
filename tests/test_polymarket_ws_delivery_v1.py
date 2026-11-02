import copy,hashlib,importlib,json,gzip
from pathlib import Path
import pytest
from test_polymarket_ws_data_v1 import store,NOW


def mod():
    try:return importlib.import_module('scripts.pull_polymarket_ws_data_v1')
    except ImportError:pytest.fail('Missing immutable Polymarket DATA delivery')

def sample(root):
    s=store(root);s.append('RECV','hello');seal=s.seal();s.close();return seal,(root/seal['file']).read_bytes()


def test_immutable_import_is_idempotent_and_keeps_first_mtime_and_actual_times(tmp_path):
    seal,raw=sample(tmp_path/'source');out=tmp_path/'local';m=mod()
    first=m.import_segment(out,seal,raw,observed_ms=NOW+5000)
    p=out/seal['file'];before=p.stat();again=m.import_segment(out,seal,raw,observed_ms=NOW+9000)
    after=p.stat()
    assert first['actual_import_ms']==NOW+5000 and again==first
    assert first['source_closed_ms']==seal['closed_ms']
    assert (before.st_ino,before.st_mtime_ns)==(after.st_ino,after.st_mtime_ns)
    assert first['first_local_mtime_ns']==before.st_mtime_ns


@pytest.mark.parametrize('fault',['hash','path','gzip','rows','existing_conflict','future_import'])
def test_bad_data_never_overwrites_existing_evidence(tmp_path,fault):
    seal,raw=sample(tmp_path/'source');out=tmp_path/'local';m=mod();existing=None
    if fault=='hash':raw+=b'x'
    if fault=='path':seal['file']='../../elsewhere'
    if fault=='gzip':raw=b'broken';seal.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    if fault=='rows':seal['rows']+=1
    if fault=='existing_conflict':
        existing=out/seal['file'];existing.parent.mkdir(parents=True);existing.write_bytes(b'foreign')
    with pytest.raises((ValueError,OSError,EOFError)):m.import_segment(out,seal,raw,observed_ms=NOW-1 if fault=='future_import' else NOW+5000)
    if existing:assert existing.read_bytes()==b'foreign'
    assert not list(out.glob('receipts/*.json'))


def test_unfinished_local_receipt_recovers_first_arrival_time_without_rewriting(tmp_path):
    seal,raw=sample(tmp_path/'source');m=mod();out=tmp_path/'local';p=out/seal['file'];p.parent.mkdir(parents=True);p.write_bytes(raw);before=p.stat()
    receipt=m.import_segment(out,seal,raw,observed_ms=NOW+5000)
    assert p.stat().st_ino==before.st_ino and receipt['first_local_mtime_ns']==before.st_mtime_ns


def test_export_does_not_list_or_deliver_crash_partial(tmp_path):
    seal,raw=sample(tmp_path/'source');m=mod()
    (tmp_path/'source/sports/unsealed.partial').write_text('{')
    listed=m.export_listing(tmp_path/'source')
    assert listed==[seal]
    assert m.export_file(tmp_path/'source',seal['file'],seal['sha256'])==raw
    for bad in ('sports/unsealed.partial','../../private.env','/root/.env'):
        with pytest.raises(ValueError):m.export_file(tmp_path/'source',bad,'0'*64)


def test_cli_without_pull_does_not_read_or_connect(tmp_path,capsys):
    m=mod();assert m.main(['--destination',str(tmp_path/'absent')])==0
    assert json.loads(capsys.readouterr().out)['status']=='DATA_ONLY_NO_REQUESTS'
    assert not list(tmp_path.iterdir())


def test_mac_selector_claims_only_two_data_locks_and_refuses_second_launcher(tmp_path):
    m=mod();assert callable(getattr(m,'claim_selector_locks',None)), 'Missing non-producing Mac selector'
    import fcntl,os
    locks=tmp_path/'research_lab/data/locks';locks.mkdir(parents=True)
    for role in ('sportsws','clobws'):(locks/(role+'.lock')).write_text('original\n')
    before={p.name:p.stat().st_ino for p in locks.iterdir()}
    fds=m.claim_selector_locks(tmp_path)
    try:
        for p in locks.iterdir():
            fd=os.open(p,os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(fd)
        with pytest.raises(BlockingIOError):m.claim_selector_locks(tmp_path)
        assert all(p.stat().st_ino==before[p.name] and p.read_text()=='original\n' for p in locks.iterdir())
    finally:
        for fd in fds:os.close(fd)


def test_archive_evicts_only_after_verified_durable_mac_copy_and_keeps_tombstone(tmp_path):
    m=mod();assert callable(getattr(m,'make_archive_ack',None)), 'Missing verified archive acknowledgement'
    assert callable(getattr(m,'archive_ack',None)), 'Missing bounded DATA cache eviction'
    seal,raw=sample(tmp_path/'source');dest=tmp_path/'local';m.import_segment(dest,seal,raw,observed_ms=NOW+5000)
    ack=m.make_archive_ack(dest,seal)
    result=m.archive_ack(tmp_path/'source',[ack],now_ms=NOW+6000)
    assert result['evicted_files']==1 and result['freed_bytes']>=len(raw)
    assert not (tmp_path/'source'/seal['file']).exists()
    assert (dest/seal['file']).read_bytes()==raw
    assert list((tmp_path/'source/sports/archived').glob('*.json'))
    assert m.archive_ack(tmp_path/'source',[ack],now_ms=NOW+7000)['evicted_files']==0


@pytest.mark.parametrize('fault',['missing_local','corrupt_local','bad_receipt','bad_source','partial_path'])
def test_archive_never_deletes_unverified_or_changed_bytes(tmp_path,fault):
    m=mod();assert callable(getattr(m,'make_archive_ack',None)), 'Missing verified archive acknowledgement'
    seal,raw=sample(tmp_path/'source');dest=tmp_path/'local';m.import_segment(dest,seal,raw,observed_ms=NOW+5000)
    file=dest/seal['file']
    if fault=='missing_local':file.unlink()
    if fault=='corrupt_local':file.write_bytes(b'broken')
    if fault in ('missing_local','corrupt_local'):
        with pytest.raises((ValueError,OSError)):m.make_archive_ack(dest,seal)
    else:
        ack=m.make_archive_ack(dest,seal)
        if fault=='bad_receipt':ack['local_receipt']['file_sha256']='0'*64
        if fault=='bad_source':(tmp_path/'source'/seal['file']).write_bytes(b'changed')
        if fault=='partial_path':ack['seal']['file']='sports/incomplete.partial'
        with pytest.raises(ValueError):m.archive_ack(tmp_path/'source',[ack],now_ms=NOW+6000)
    assert (tmp_path/'source'/seal['file']).exists()


def test_archive_updates_live_budget_after_external_eviction(tmp_path):
    m=mod();assert callable(getattr(m,'archive_ack',None)), 'Missing bounded DATA cache eviction'
    from research_lab import polymarket_ws_data_v1 as core
    source=tmp_path/'source';s=store(source);s.append('RECV','a'*10000);seal=s.seal();raw=(source/seal['file']).read_bytes()
    dest=tmp_path/'local';m.import_segment(dest,seal,raw,observed_ms=NOW+5000)
    m.archive_ack(source,[m.make_archive_ack(dest,seal)],now_ms=NOW+6000)
    used_before=s.used;s._budget(0)
    assert s.used<used_before+3000
    s.append('RECV','next');s.close()


def test_ack_history_compaction_recovers_after_interruption(tmp_path,monkeypatch):
    m=mod();source=tmp_path/'source';dest=tmp_path/'local'
    for _ in range(2):
        seal,raw=sample(source);m.import_segment(dest,seal,raw,observed_ms=NOW+5000)
        m.archive_ack(source,[m.make_archive_ack(dest,seal)],now_ms=NOW+6000)
    original=Path.unlink;counter=[0]
    def interrupted(path,*a,**k):
        if str(path).endswith('.ack.json'):
            counter[0]+=1
            if counter[0]==2:raise OSError('fixture interrupted')
        return original(path,*a,**k)
    with monkeypatch.context() as mm:
        mm.setattr(Path,'unlink',interrupted)
        with pytest.raises(OSError):m._prune_ack_history(source,NOW+9*86400000)
    m._prune_ack_history(source,NOW+9*86400000)
    assert not list((source/'sports/archived').glob('*.ack.json'))
    assert list((source/'sports/archived').glob('history-*.json'))
    assert len(list(dest.glob('sports/sealed/*.gz')))==2


def test_import_and_ack_fsync_new_directory_chain_before_source_eviction(tmp_path,monkeypatch):
    import os,stat
    m=mod();seal,raw=sample(tmp_path/'source');dest=tmp_path/'fresh/dataset';seen=[];original=os.fsync
    def sync(fd):
        st=os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):seen.append(st.st_ino)
        return original(fd)
    monkeypatch.setattr(os,'fsync',sync)
    m.import_segment(dest,seal,raw,observed_ms=NOW+5000);ack=m.make_archive_ack(dest,seal)
    for p in [tmp_path,dest.parent,dest,dest/'sports',dest/'sports/sealed',dest/'receipts']:
        assert p.stat().st_ino in seen,str(p)
    assert m.archive_ack(tmp_path/'source',[ack],now_ms=NOW+6000)['evicted_files']==1


def test_failed_mac_pull_cannot_reuse_previous_success(tmp_path,monkeypatch):
    import os,subprocess
    m=mod();locks=tmp_path/'fake/research_lab/data/locks';locks.mkdir(parents=True)
    for role in ('sportsws','clobws'):(locks/(role+'.lock')).touch()
    claim=m.claim_selector_locks;monkeypatch.setattr(m,'claim_selector_locks',lambda _:claim(tmp_path/'fake'))
    config=dict(schema='POLY_WS_MAC_CONSUMER_V1',mac_root='/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28',source_files={},status_path=str(tmp_path/'status.json'),identity='fixture',destination='fixture',package_root='fixture',package_sha256='fixture')
    p=tmp_path/'config.json';p.write_text(json.dumps(config));calls=[0];sleeps=[0]
    def run(*a,**k):
        calls[0]+=1
        if calls[0]==1:return subprocess.CompletedProcess([],0,json.dumps(dict(data_health=dict(warnings=[]))), '')
        raise subprocess.TimeoutExpired('fixture',1)
    def sleep(_):
        sleeps[0]+=1
        if sleeps[0]>=2:raise KeyboardInterrupt()
    monkeypatch.setattr(m.subprocess,'run',run);monkeypatch.setattr(m.time,'sleep',sleep);monkeypatch.setattr(m,'notify_storage',lambda *a:None)
    with pytest.raises(KeyboardInterrupt):m.run_mac_consumer(p,hashlib.sha256(p.read_bytes()).hexdigest())
    status=json.loads((tmp_path/'status.json').read_bytes())
    assert status['last_pull_exit']==-1 and status['last_pull'] is None
    assert 'DATA_DELIVERY_FAILED' in status['warnings']


def test_remote_export_verification_and_work_use_data_resource_slice(monkeypatch):
    import subprocess
    m=mod();calls=[]
    def run(cmd,**kwargs):calls.append(cmd);return subprocess.CompletedProcess(cmd,0,b'[]',b'')
    monkeypatch.setattr(m.subprocess,'run',run)
    assert m.remote(Path('fictional-key'),'/opt/bybot-research/polymarket-ws-data-20261102/candidate-'+'a'*16,'b'*64,['--export-list'])==b'[]'
    command=calls[0][-1]
    for x in ('systemd-run','Slice=poly-ws-data.slice','MemoryMax=96M','CPUQuota=10%','DynamicUser=yes','ProtectHome=yes'):assert x in command
