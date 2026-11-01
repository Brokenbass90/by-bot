"""Financial transitions tested with fictional keys, real temp files and flock."""
import copy,json
from pathlib import Path
from contextlib import contextmanager
import pytest

from scripts import pump4_source_handoff_v1 as M

@pytest.fixture
def case(tmp_path):
    folder=tmp_path/'packet';folder.mkdir();old=tmp_path/'old';old.mkdir()
    new=tmp_path/'new';lock=tmp_path/'account.lock';lock.touch()
    scope=dict(root=str(old),policy=dict(M.POLICY),valid_from_ms=1,valid_until_ms=100,
        account_lock_path=str(lock),account_lock_inode=lock.stat().st_ino,account_fingerprint='a'*64)
    nextscope=dict(scope,root=str(new),valid_from_ms=200,valid_until_ms=10000)
    e=dict(old_scope=scope,new_scope=nextscope,new_config_sha256='c'*64,
        old_scope_sha256=M.digest(scope),new_scope_sha256=M.digest(nextscope),
        old_account_identity_sha256='uid',required_key_until_ms=50000,acceptance_ready=True,
        new_account_fingerprint='a'*64)
    class Ops:
        def __init__(self):self.events=[];self.failure=None;self.uid='uid';self.expiry=60000;self.old_active=True;self.installed=False;self.new_attempted=False;self.race=None
        def verify(self,e,*,stopped=False):self.events.append('verify-stopped' if stopped else 'verify')
        def snapshot(self,e):
            self.events.append('GET');return dict(observed_ms=1000,flat=True,history_empty=True,available_usdt='50',account_identity_sha256=self.uid,account_fingerprint='a'*64,key_valid_until_ms=self.expiry,key_no_fixed_expiry=False)
        @contextmanager
        def observer_lock(self,e):self.events.append('observer-lock');yield
        @contextmanager
        def account_lock(self,e):
            self.events.append('account-lock')
            if self.failure=='lock':raise M.HandoffError('LOCK_BUSY')
            yield
        def stop(self,e):
            self.events.append('stop');self.old_active=False
            if self.race:
                p=old/self.race;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
        def install(self,e):
            self.events.append('install');self.installed=True
            if self.failure=='install':raise OSError('partial CAS')
        def start(self,e):
            self.events.append('start-new');self.new_attempted=True
            if self.failure=='start':raise TimeoutError('response lost')
        def readback(self,e):
            self.events.append('readback')
            if self.failure=='readback':raise TimeoutError('unknown source')
            return dict(status='OWNER_ARMED_FUTURE',broker_writes=None)
        def restore_revoked_old(self,e):
            self.events.append('restore-old');self.installed=False;self.old_active=True
        def clock(self):return 1000
    return folder,e,Ops()

def apply(case):
    f,e,o=case;return M.apply_once(f,'packetpin',e,o,owner_go_text='GO PUMP4_SOURCE_REPAIR_PACKET packetpin')

def test_default_cli_no_packet_read_credentials_or_operations(monkeypatch,capsys):
    monkeypatch.setattr(M,'SystemOps',lambda *a:pytest.fail('no default operations'))
    assert M.main([])==0
    assert json.loads(capsys.readouterr().out)['status']=='NO_REQUESTS_NO_AUTHORITY'

def test_missing_exact_go_has_no_operations(case):
    f,e,o=case
    with pytest.raises(M.HandoffError):M.apply_once(f,'pin',e,o,owner_go_text='GO')
    assert o.events==[] and not (f/'handoff-claim.json').exists()

@pytest.mark.parametrize('fault',['expiry','uid','funds','notflat','history'])
def test_bad_access_or_account_stops_before_claim_and_unit_stop(case,fault):
    f,e,o=case
    if fault=='expiry':o.expiry=49999
    elif fault=='uid':o.uid='another-account'
    else:
        original=o.snapshot
        def bad(e):
            s=original(e);s.update({'funds':{'available_usdt':'49'},'notflat':{'flat':False},'history':{'history_empty':False}}[fault]);return s
        o.snapshot=bad
    with pytest.raises(M.HandoffError):apply(case)
    assert 'stop' not in o.events and not (f/'handoff-claim.json').exists()

@pytest.mark.parametrize('name',['admitted-lifecycle.json','risk.jsonl','entry-loss-stop.json','flows/p/x.json','tickets/x','send-barriers/x','supervisor/attempts/x'])
def test_any_old_spent_or_unknown_history_is_preserved_and_blocks(case,name):
    f,e,o=case;p=Path(e['old_scope']['root'])/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    with pytest.raises(M.HandoffError):apply(case)
    assert p.read_text()=='{}' and 'stop' not in o.events

def test_success_one_writer_no_epoch_or_policy_reset_and_no_replay(case):
    f,e,o=case;before=copy.deepcopy(e);r=apply(case)
    assert r['status']=='OWNER_ARMED_FUTURE' and e==before
    assert o.events.count('stop')==o.events.count('start-new')==1
    assert o.events.index('stop')<o.events.index('account-lock')<o.events.index('install')<o.events.index('start-new')
    assert (Path(e['old_scope']['root'])/'entry-revoked.json').exists()
    assert json.loads((Path(e['new_scope']['root'])/'owner-go.json').read_bytes())['scope_sha256']==e['new_scope_sha256']
    events=list(o.events)
    with pytest.raises(M.HandoffError):apply(case)
    assert o.events==events

@pytest.mark.parametrize('failure',['lock','install'])
def test_prestart_failure_restores_old_custody_with_entries_revoked(case,failure):
    f,e,o=case;o.failure=failure
    with pytest.raises((M.HandoffError,OSError)):apply(case)
    assert o.events.count('restore-old')==1 and 'start-new' not in o.events
    assert (Path(e['old_scope']['root'])/'entry-revoked.json').exists()
    assert (f/'handoff-claim.json').exists()

def test_raced_admission_after_stop_never_grants_new_authority(case):
    f,e,o=case;o.race='admitted-lifecycle.json'
    with pytest.raises(M.HandoffError):apply(case)
    assert (Path(e['old_scope']['root'])/'admitted-lifecycle.json').exists()
    assert not Path(e['new_scope']['root']).exists() and o.events.count('restore-old')==1

@pytest.mark.parametrize('failure',['start','readback'])
def test_unknown_after_start_never_repeats_or_switches_custody(case,failure):
    f,e,o=case;o.failure=failure
    with pytest.raises(TimeoutError):apply(case)
    assert o.events.count('start-new')==1 and 'restore-old' not in o.events
    assert (f/'handoff-claim.json').exists() and (Path(e['new_scope']['root'])/'owner-go.json').exists()

def test_revoke_entry_keeps_custody_history_and_no_unit_operations(case):
    f,e,o=case;apply(case);root=Path(e['new_scope']['root']);p=root/'admitted-lifecycle.json';p.write_text('{"live":true}')
    before=list(o.events)
    result=M.revoke_entry(f,'packetpin',e,o,owner_go_text='REVOKE PUMP4_SOURCE_REPAIR_PACKET packetpin')
    assert result['status']=='ENTRY_REVOKED_CUSTODY_PRESERVED'
    assert o.events==before and p.read_text()=='{"live":true}' and (root/'owner-go.json').exists()

def test_original_real_flock_cannot_be_acquired_twice(tmp_path):
    p=tmp_path/'account.lock';p.touch()
    with M.file_lock(p,p.stat().st_ino):
        with pytest.raises((BlockingIOError,M.HandoffError)):
            with M.file_lock(p,p.stat().st_ino):pytest.fail('two writers')


def test_future_window_sends_no_command_and_claims_no_attempt(case):
    f,e,o=case;e['new_scope']['valid_from_ms']=1001
    result=apply(case)
    assert result['status']=='NOT_DUE_NO_COMMAND_SENT' and o.events==[]
    assert not (f/'handoff-claim.json').exists()


def test_key_lifetime_never_guesses_from_an_empty_or_unbound_sentinel():
    value=dict(expiredAt='1970-01-01T00:00:00Z',deadlineDay=-2)
    assert M.key_lifetime(value,True)==(0,True)
    assert M.key_lifetime(value,False)==(0,False)
    assert M.key_lifetime(dict(expiredAt='',deadlineDay=-2),True)==(None,False)
    with pytest.raises(M.HandoffError):M.key_lifetime(dict(expiredAt='2026-11-06T08:43:37'),True)

def test_nonfinite_available_balance_cannot_pass_the_handoff(case):
    f,e,o=case;original=o.snapshot
    def bad(e):
        v=original(e);v['available_usdt']='Infinity';return v
    o.snapshot=bad
    with pytest.raises(M.HandoffError):apply(case)
    assert 'stop' not in o.events


def test_no_financial_apply_before_offline_and_independent_acceptance(case):
    f,e,o=case;e['acceptance_ready']=False
    with pytest.raises(M.HandoffError,match='ACCEPTANCE_REQUIRED'):apply(case)
    assert o.events==[] and not (f/'handoff-claim.json').exists()


def test_unhealthy_observer_cannot_turn_unknown_execution_into_false():
    scope=dict(valid_from_ms=100,valid_until_ms=200)
    assert M.readback_status(dict(status='UNHEALTHY',financial_trading_proven=False),150,scope)==('OWNER_ACTION_REQUIRED','UNKNOWN')
    assert M.readback_status(dict(status='PENDING_SOURCE',financial_trading_proven=False),150,scope)==('OWNER_ARMED_SOURCE_PENDING',False)
    assert M.readback_status(dict(status='HEALTHY',financial_trading_proven=True),201,scope)==('ENTRY_PERIOD_EXPIRED_CUSTODY_RETAINED',True)

def test_expiry_during_second_get_restores_revoked_old_without_install(case):
    f,e,o=case;calls=[0];tick=[1000];original=o.snapshot;o.clock=lambda:tick[0]
    def advancing(e):
        calls[0]+=1;s=original(e)
        if calls[0]==2:tick[0]=e['new_scope']['valid_until_ms'];s['observed_ms']=tick[0]
        return s
    o.snapshot=advancing
    with pytest.raises(M.HandoffError,match='WINDOW_ENDED'):apply(case)
    assert 'install' not in o.events and 'start-new' not in o.events and o.events.count('restore-old')==1


@pytest.mark.parametrize("script",["pump4_source_handoff_v1.py","pump4_source_repair_health_v1.py"])
@pytest.mark.parametrize("mode",["flag","environment"])
def test_optimized_interpreter_rejected_before_any_operation(script,mode):
    import subprocess,sys,os
    args=[sys.executable,"-B"]+(["-O"] if mode=="flag" else [])+[str(Path(M.__file__).with_name(script))]
    env=dict(os.environ)
    if mode=="environment":env["PYTHONOPTIMIZE"]="1"
    run=subprocess.run(args,env=env,capture_output=True,text=True)
    assert run.returncode!=0 and "OPTIMIZED_PYTHON_FORBIDDEN" in run.stderr+run.stdout


def test_changed_owner_while_waiting_for_observer_lock_is_not_stopped(case):
    f,e,o=case;changed=[False];original=o.verify
    @contextmanager
    def contested(e):
        o.events.append('observer-lock');changed[0]=True;yield
    def verify(e,*,stopped=False):
        if changed[0]:raise M.HandoffError('OLD_UNIT_WRAPPER_DRIFT')
        original(e,stopped=stopped)
    o.observer_lock=contested;o.verify=verify
    with pytest.raises(M.HandoffError,match='DRIFT'):apply(case)
    assert 'stop' not in o.events and 'restore-old' not in o.events
    assert not (f/'handoff-claim.json').exists()
    assert not (Path(e['old_scope']['root'])/'entry-revoked.json').exists()
