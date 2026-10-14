"""Source-only deadline observer; synthetic payloads/tmp paths, no live reads."""
import copy,hashlib,importlib,json,os
from pathlib import Path
import pytest


def api():
    try:m=importlib.import_module('research_lab.kity_oct15_deadline_v1')
    except ImportError:m=None
    assert m is not None,'independent source deadline observer missing'
    return m


@pytest.fixture
def cfg(tmp_path):
    source=tmp_path/'producer.py';source.write_text('# approved source fixture')
    return dict(schema='KITY_OCT15_DEADLINE_OBSERVER_V1',day='2026-10-15',
        producer_path=str(source),producer_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        snapshot_path=str(tmp_path/'snimok_2355.json'),publisher_receipt_path=str(tmp_path/'publisher-receipt.json'),
        output_path=str(tmp_path/'observer.json'),approval_scope='SOURCE_ONLY_NO_STRATEGY_CHANGE')


def complete(cfg,m):
    snapshot=dict(vremya='2026-10-14T23:55:00+00:00',oi_usd={'BTCUSDT':1},instrumenty={'BTCUSDT':{}},oi_otsutstvuet=[])
    p=Path(cfg['snapshot_path']);p.write_text(json.dumps(snapshot))
    r=dict(status='CAPTURE_PASS',day='2026-10-15',producer_sha256=cfg['producer_sha256'],
        snapshot_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),completed_ms=m.END-1000)
    Path(cfg['publisher_receipt_path']).write_text(json.dumps(r))
    return p,r


def test_publish_once_cannot_overwrite_completed_file(tmp_path):
    m=api();p=tmp_path/'source.json';m.publish_once(p,b'first')
    with pytest.raises(FileExistsError):m.publish_once(p,b'second')
    assert p.read_bytes()==b'first'
    assert list(tmp_path.iterdir())==[p]


def test_crash_before_publication_leaves_no_final_snapshot(tmp_path,monkeypatch):
    m=api();p=tmp_path/'source.json'
    def failed(fd):raise OSError('file fsync failure')
    monkeypatch.setattr(m.os,'fsync',failed)
    with pytest.raises(OSError):m.publish_once(p,b'full')
    assert not p.exists();assert list(tmp_path.iterdir())==[]


def test_partial_os_write_is_completed_before_atomic_publish(tmp_path,monkeypatch):
    m=api();real=m.os.write
    monkeypatch.setattr(m.os,'write',lambda fd,b:real(fd,b[:2]))
    p=tmp_path/'source.json';m.publish_once(p,b'complete-body')
    assert p.read_bytes()==b'complete-body'
    assert p.stat().st_nlink==1


def test_pending_deadline_never_creates_future_result(cfg):
    m=api();r=m.run_once(cfg,now_ms=m.END-1)
    assert r['status']=='WATCH_PENDING';assert not Path(cfg['output_path']).exists()


def test_dead_producer_missing_capture_becomes_immutable_blocked(cfg):
    m=api();r=m.run_once(cfg,now_ms=m.END)
    assert r['status']=='CAPTURE_BLOCKED' and r['reason']=='SNAPSHOT_MISSING'
    before=Path(cfg['output_path']).read_bytes();complete(cfg,m)
    assert m.run_once(cfg,now_ms=m.END+1000)==r
    assert Path(cfg['output_path']).read_bytes()==before


def test_success_requires_publisher_window_and_exact_source_identity(cfg):
    m=api();complete(cfg,m);r=m.run_once(cfg,now_ms=m.END)
    assert r['status']=='CAPTURE_OBSERVATION_PASS'
    assert not r['money_ready'] and not r['c1_pass'] and not r['c2_pass']


@pytest.mark.parametrize('fault,reason',[
    ('receipt_missing','PUBLISHER_RECEIPT_MISSING'),('late','PUBLICATION_OUTSIDE_WINDOW'),
    ('wrong_day','CAPTURE_DAY_CONFLICT'),('wrong_hash','SNAPSHOT_PIN_CONFLICT'),
    ('producer_changed','PRODUCER_SOURCE_DRIFT'),('snapshot_old','SNAPSHOT_OUTSIDE_WINDOW'),
    ('malformed','MALFORMED_SOURCE'),('oi_missing','SNAPSHOT_OI_UNKNOWN'),('oi_inf','SNAPSHOT_OI_UNKNOWN'),
    ('excluded_name','SNAPSHOT_OI_UNKNOWN')])
def test_unknown_sources_are_never_zero_or_pass(cfg,fault,reason):
    m=api();p,r=complete(cfg,m)
    if fault=='receipt_missing':Path(cfg['publisher_receipt_path']).unlink()
    elif fault=='late':r['completed_ms']=m.END
    elif fault=='wrong_day':r['day']='2026-10-22'
    elif fault=='wrong_hash':r['snapshot_sha256']='0'*64
    elif fault=='producer_changed':Path(cfg['producer_path']).write_text('# other version')
    elif fault=='snapshot_old':
        s=json.loads(p.read_bytes());s['vremya']='2026-10-07T23:55:00+00:00';p.write_text(json.dumps(s));r['snapshot_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    elif fault=='malformed':p.write_text('{')
    elif fault.startswith('oi_') or fault=='excluded_name':
        s=json.loads(p.read_bytes())
        if fault=='oi_missing':s['oi_usd']['BTCUSDT']=None
        if fault=='oi_inf':s['oi_usd']['BTCUSDT']=float('inf')
        if fault=='excluded_name':s['oi_otsutstvuet']=['BTCUSDT']
        p.write_text(json.dumps(s));r['snapshot_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    if fault!='receipt_missing':Path(cfg['publisher_receipt_path']).write_text(json.dumps(r))
    assert m.run_once(cfg,now_ms=m.END)['reason']==reason


def test_reboot_check_after_deadline_cannot_transfer_capture_to_new_date(cfg):
    m=api();r=m.run_once(cfg,now_ms=m.END+4*86400000)
    assert r['status']=='CAPTURE_BLOCKED' and r['day']=='2026-10-15'
    assert r['observed_ms']==m.END+4*86400000


def test_unapproved_source_cannot_become_pass(cfg):
    m=api();complete(cfg,m);cfg['approval_scope']='PENDING'
    r=m.run_once(cfg,now_ms=m.END)
    assert r['status']=='CAPTURE_BLOCKED' and r['reason']=='PRODUCER_APPROVAL_PENDING'


def test_observer_cli_before_deadline_creates_no_actual_receipt(tmp_path,monkeypatch,capsys):
    m=api()
    from scripts import kity_oct15_deadline_v1 as cli
    monkeypatch.setattr(cli.time,'time_ns',lambda:(m.END-1)*1000000)
    assert cli.main([])==0
    assert json.loads(capsys.readouterr().out)['status']=='WATCH_PENDING'


def test_observer_cli_missing_deployment_after_deadline_is_explicit_blocked(tmp_path,monkeypatch,capsys):
    m=api()
    from scripts import kity_oct15_deadline_v1 as cli
    monkeypatch.setattr(cli,'OWN',tmp_path);monkeypatch.setattr(cli,'CONFIG',tmp_path/'config.json');monkeypatch.setattr(cli,'OUTPUT',tmp_path/'source-deadline.json')
    monkeypatch.setattr(cli.time,'time_ns',lambda:m.END*1000000)
    assert cli.main([])==2
    r=json.loads(capsys.readouterr().out)
    assert r['status']=='CAPTURE_BLOCKED' and r['reason']=='PRODUCER_APPROVAL_PENDING'
    assert (tmp_path/'source-deadline.json').exists()


def test_existing_tampered_terminal_is_not_accepted_or_repaired(cfg):
    m=api();complete(cfg,m);r=m.run_once(cfg,now_ms=m.END)
    p=Path(cfg['output_path']);r['c1_pass']=True;p.write_text(json.dumps(r));before=p.read_bytes()
    with pytest.raises(ValueError,match='EXISTING_RECEIPT_CONFLICT'):m.run_once(cfg,now_ms=m.END+1000)
    assert p.read_bytes()==before


def test_source_replacement_during_read_is_explicit_unknown(cfg,monkeypatch):
    m=api();p,_=complete(cfg,m);original=Path.read_bytes;called=[]
    def replaced(self):
        raw=original(self)
        if self==p and not called:
            called.append(True);self.write_text('{"another":"source"}')
        return raw
    monkeypatch.setattr(Path,'read_bytes',replaced)
    assert m.run_once(cfg,now_ms=m.END)['reason']=='SOURCE_CHANGED_DURING_READ'
