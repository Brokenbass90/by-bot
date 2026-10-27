import importlib.util
from pathlib import Path
import pytest,json,fcntl,os

spec=importlib.util.spec_from_file_location('ops',Path(__file__).with_name('ops.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_clone_preserves_history_and_rejects_existing_target(tmp_path):
    old=tmp_path/'old';old.mkdir();(old/'intake').mkdir()
    (old/'intake/A.jsonl').write_bytes(b'{"cursor":42}\n')
    (old/'data-binding.json').write_bytes(b'old binding')
    before=m.tree(old);new=tmp_path/'new'
    m.clone_data(old,new,b'new binding')
    assert m.tree(old)==before
    assert (new/'intake/A.jsonl').read_bytes()==(old/'intake/A.jsonl').read_bytes()
    assert (new/'intake/A.jsonl').stat().st_ino!=(old/'intake/A.jsonl').stat().st_ino
    assert (new/'data-binding.json').read_bytes()==b'new binding'
    with pytest.raises((AssertionError,FileExistsError)):m.clone_data(old,new,b'new binding')

def test_clone_refuses_symlink(tmp_path):
    old=tmp_path/'old';old.mkdir();(old/'leak').symlink_to(tmp_path/'other')
    with pytest.raises(AssertionError):m.clone_data(old,tmp_path/'new',b'binding')

@pytest.mark.parametrize('name',['owner-go.json','admitted-lifecycle.json','entry-revoked.json','risk.jsonl',
    'flows/p/execution-config.json','send-barriers/once.json','supervisor/attempts/a.json'])
def test_rebind_rejects_any_financial_history(tmp_path,name):
    p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'{}')
    with pytest.raises(AssertionError):m.empty_off(tmp_path)

def test_rebind_accepts_only_empty_financial_state(tmp_path):
    for n in ('flows','send-barriers','supervisor/attempts'):(tmp_path/n).mkdir(parents=True,exist_ok=True)
    m.empty_off(tmp_path)

def test_rollback_copies_forward_new_journal_bytes_and_receipts(tmp_path):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    (old/'a.jsonl').write_bytes(b'prefix\n');(new/'a.jsonl').write_bytes(b'prefix\nnext\n')
    (old/'data-binding.json').write_bytes(b'old');(new/'data-binding.json').write_bytes(b'new')
    (new/'receipt.json').write_bytes(b'{}')
    m.copy_forward(new,old)
    assert (old/'a.jsonl').read_bytes()==b'prefix\nnext\n'
    assert (old/'receipt.json').read_bytes()==b'{}'
    assert (old/'data-binding.json').read_bytes()==b'old'
    assert (new/'a.jsonl').read_bytes()==b'prefix\nnext\n'

@pytest.mark.parametrize('name', ['a.jsonl','epoch.json'])
def test_rollback_refuses_conflicting_history_before_any_write(tmp_path,name):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    (old/name).write_bytes(b'old\n');(new/name).write_bytes(b'foreign\n');(new/'fresh').write_bytes(b'new')
    with pytest.raises(AssertionError):m.copy_forward(new,old)
    assert not (old/'fresh').exists() and (old/name).read_bytes()==b'old\n'

def test_candidate_rejects_forged_material_and_changed_driver(tmp_path):
    (tmp_path/'app').mkdir();(tmp_path/'app/source.py').write_bytes(b'pass\n');(tmp_path/'accept.py').write_bytes(b'driver')
    body=dict(files={'source.py':m.sha(b'pass\n')},driver_sha256=m.sha(b'driver'))
    material=m.digest(body)
    manifest=dict(files=body['files'],acceptance_driver_sha256=body['driver_sha256'],material_sha256=material)
    raw=m.encode(manifest);(tmp_path/'manifest.json').write_bytes(raw)
    m.verify_candidate(tmp_path,material,m.sha(raw))
    with pytest.raises(AssertionError):m.verify_candidate(tmp_path,'f'*64,m.sha(raw))
    (tmp_path/'accept.py').write_bytes(b'changed')
    with pytest.raises(AssertionError):m.verify_candidate(tmp_path,material,m.sha(raw))

def test_worker_overrides_fail_closed():
    clean=dict(MainPID='0',ActiveState='inactive',DropInPaths='',ExecStop='',ExecStopPost='',Job='')
    m.quiet_state(clean)
    for field in ('DropInPaths','ExecStop','ExecStopPost','Job'):
        with pytest.raises(AssertionError):m.quiet_state(dict(clean,**{field:'unreviewed'}))

def test_systemd_writable_runtime_exists_before_start(tmp_path):
    root=tmp_path/'runtime/off'
    m.prepare_runtime(root)
    assert root.is_dir() and root.stat().st_mode & 0o777==0o700
    with pytest.raises((AssertionError,FileExistsError)):m.prepare_runtime(root)

def test_timer_catchup_can_acquire_both_data_locks(tmp_path,monkeypatch):
    paths=[tmp_path/'old.lock',tmp_path/'new.lock'];fds=[]
    for p in paths:
        fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);fds.append(fd)
    calls=[]
    def start(*args):
        calls.append(args)
        for p in paths:
            fd=os.open(p,os.O_RDWR)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(fd)
    monkeypatch.setattr(m,'ctl',start)
    m.resume_timer('timer',fds)
    assert calls==[('start','timer')] and fds==[]

def test_rollback_restores_wrapper_after_crash_before_unit_replace(tmp_path):
    unit=tmp_path/'unit';wrapper=tmp_path/'wrapper';unit.write_bytes(b'old unit');wrapper.write_bytes(b'new wrapper')
    m.restore_owner_files(unit,wrapper,b'old unit',b'new unit',b'old wrapper',b'new wrapper')
    assert unit.read_bytes()==b'old unit' and wrapper.read_bytes()==b'old wrapper'

def test_rollback_rejects_unknown_wrapper_before_unit_write(tmp_path):
    unit=tmp_path/'unit';wrapper=tmp_path/'wrapper';unit.write_bytes(b'new unit');wrapper.write_bytes(b'unknown')
    with pytest.raises(AssertionError):m.restore_owner_files(unit,wrapper,b'old unit',b'new unit',b'old wrapper',b'new wrapper')
    assert unit.read_bytes()==b'new unit'


def test_rollback_blocks_current_incomplete_process_hour(tmp_path):
    (tmp_path/'capture-attempts').mkdir();(tmp_path/'capture-complete').mkdir()
    (tmp_path/'capture-attempts/7200000.json').write_text('{}')
    with pytest.raises(AssertionError):m.rollback_capture_safe(tmp_path,7200001)
    m.rollback_capture_safe(tmp_path,10800001)
    (tmp_path/'capture-complete/7200000.json').write_text('{}')
    m.rollback_capture_safe(tmp_path,7200001)
