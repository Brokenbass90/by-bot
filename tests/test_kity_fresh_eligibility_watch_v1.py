import json
from pathlib import Path
import pytest
from research_lab.kity_fresh_eligibility_watch_v1 import Watch,AlreadyRunning

POLICY='a'*64

def make(tmp_path, *, now=1000, expires=10000, capture=None, guard=None):
    at=[now];calls=[]
    def sample(store):
        calls.append(store)
        return capture(store) if capture else dict(compatible=False,reason='GROSS_CAP_EXCEEDED',gross='332')
    w=Watch(tmp_path,policy_id=POLICY,expires_ms=expires,clock=lambda:at[0],guard=guard or (lambda:None),capture=sample)
    return w,at,calls


def test_blocked_attempt_preserves_policy_and_ready_stops_without_another_capture(tmp_path):
    w,at,calls=make(tmp_path);r=w.step();assert r['status']=='PENDING' and r['reason']=='GROSS_CAP_EXCEEDED'
    assert not (tmp_path/'terminal.json').exists() and len(calls)==1
    w.capture=lambda store:dict(compatible=True,gross='174',source_sha256='b'*64,checks=10)
    at[0]+=1000;r=w.step();assert r['status']=='KITY_FRESH_COMPATIBLE_READY' and r['gross']=='174'
    original=(tmp_path/'terminal.json').read_bytes();w.capture=lambda _:pytest.fail('terminal must not recapture')
    assert w.step()==r and (tmp_path/'terminal.json').read_bytes()==original
    assert not any(p.name in ('selected-v2.json','owner-go.json','policy-claim.json','lifecycle.sqlite') for p in tmp_path.rglob('*'))
    w.close()


def test_expired_before_capture_or_during_capture_never_emits_ready(tmp_path):
    w,at,calls=make(tmp_path/'before',now=10000)
    assert w.step()['status']=='POLICY_EXPIRED_UNUSED' and not calls;w.close()
    w,at,calls=make(tmp_path/'during')
    def late(store):at[0]=10000;return dict(compatible=True,gross='174')
    w.capture=late
    assert w.step()['status']=='POLICY_EXPIRED_UNUSED' and len(calls)==0;w.close()


def test_owner_command_during_capture_stops_and_static_drift_never_passes(tmp_path):
    claimed=[False]
    def guard():return 'POLICY_OWNER_ACTION_PRESENT' if claimed[0] else None
    w,at,calls=make(tmp_path/'used',guard=guard)
    def raced(store):claimed[0]=True;return dict(compatible=True,gross='174')
    w.capture=raced
    assert w.step()['status']=='POLICY_OWNER_ACTION_PRESENT';w.close()
    w,at,calls=make(tmp_path/'drift',guard=lambda:(_ for _ in ()).throw(ValueError('SOURCE_PIN_DRIFT')))
    r=w.step();assert r['status']=='KITY_FRESH_WATCH_BLOCKED' and not calls and 'SOURCE_PIN_DRIFT' in r['reason'];w.close()


def test_single_instance_restart_and_terminal_identity_custody(tmp_path):
    w,at,calls=make(tmp_path)
    with pytest.raises(AlreadyRunning):make(tmp_path)
    w.capture=lambda _:dict(compatible=True,gross='174');r=w.step();w.close()
    again,at,calls=make(tmp_path);assert again.step()==r and not calls;again.close()
    p=tmp_path/'terminal.json';bad=json.loads(p.read_bytes());bad['policy_id']='c'*64;p.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='TERMINAL'):make(tmp_path)


def test_source_unknown_is_retained_without_false_zero_or_success(tmp_path):
    w,at,calls=make(tmp_path,capture=lambda _:(_ for _ in ()).throw(ValueError('CTS_UNKNOWN')))
    r=w.step();assert r['status']=='PENDING' and 'CTS_UNKNOWN' in r['reason'] and r.get('gross') is None
    assert len(list((tmp_path/'attempts').glob('*/result.json')))==1;w.close()


def test_real_observer_wire_cannot_post_even_with_bound_trade_credentials(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from research_lab.kity_fresh_eligibility_watch_v1 import ReadonlyCapture
    from research_lab import kity_micro_physical_owner_v1 as core
    monkeypatch.setattr(core,'load_bound_credentials',lambda _:('test-key','test-secret'))
    source=SimpleNamespace(c={},spec={'expires_ms':9999999999999},unclaimed=lambda:None)
    reader=ReadonlyCapture(source,tmp_path).reader.reader
    with pytest.raises(ValueError,match='GET_ONLY_PINNED_ORIGIN_SCOPE'):
        reader._wire('POST','https://api.bybit.com/v5/order/create',{},None,2)


def test_original_guard_source_drift_is_not_ignored_before_ready(tmp_path,monkeypatch):
    import hashlib
    import research_lab.kity_fresh_eligibility_watch_v1 as module
    actual_path=Path
    monkeypatch.setattr(module,'Path',lambda p:tmp_path if str(p)=='/etc/systemd/system' else actual_path(p))
    monkeypatch.setattr(module,'read_only_health',lambda _:dict(status='HEALTHY'))
    unit=tmp_path/'test.service';unit.write_text('original unit')
    guard=tmp_path/'guard.dat';guard.write_text('changed')
    lock=tmp_path/'account.lock';lock.touch()
    c=dict(unit='test.service',app_root=str(tmp_path),source_files={},
        guard_source_files={str(guard):hashlib.sha256(b'original').hexdigest()},
        prior_no_send_files={},predecessor_files={},account_lock_inode=lock.stat().st_ino,wire_baseline_files={})
    config=tmp_path/'config.json';config.write_text(json.dumps(c))
    policy=tmp_path/'policy.json';policy.write_text('{"policy_id":"a"}')
    s=module.PinnedSource.__new__(module.PinnedSource)
    s.core=config;s.pin=hashlib.sha256(config.read_bytes()).hexdigest();s.c=c;s.runtime=tmp_path;s.custody=tmp_path
    s.policy_path=policy;s.policy={'policy_id':'a'}
    s.spec={'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),
        'core_unit_sha256':hashlib.sha256(unit.read_bytes()).hexdigest(),'health_command':['health-readonly']}
    with pytest.raises(ValueError,match='WATCH_ORIGINAL_SOURCE_DRIFT'):s.guard()


def test_notification_happens_after_durable_terminal_and_unknown_send_never_repeats(tmp_path):
    from research_lab.kity_fresh_eligibility_watch_v1 import notify_once
    w,at,calls=make(tmp_path);w.capture=lambda _:dict(compatible=True,gross='174');r=w.step();w.close()
    sent=[]
    def uncertain(event):
        assert json.loads((tmp_path/'terminal.json').read_bytes())==r
        sent.append(event);raise TimeoutError('response lost')
    a=notify_once(tmp_path,r,uncertain);assert a['status']=='NOTIFICATION_UNKNOWN_DO_NOT_RETRY'
    assert notify_once(tmp_path,r,uncertain)==a and len(sent)==1


def test_health_uses_pinned_pure_observe_without_cli_lock_or_main(tmp_path):
    import hashlib
    from research_lab.kity_fresh_eligibility_watch_v1 import read_only_health
    script=tmp_path/'health.py';script.write_text("def observe(spec):\n return {'status':'HEALTHY','age_ms':spec['age']}\ndef main():\n raise AssertionError('CLI lock must never run')\n")
    spec=tmp_path/'health.json';spec.write_text('{"age":123}')
    x=read_only_health(dict(health_script=str(script),health_script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        health_spec=str(spec),health_spec_sha256=hashlib.sha256(spec.read_bytes()).hexdigest()))
    assert x=={'status':'HEALTHY','age_ms':123}
    assert {p.name for p in tmp_path.iterdir()}=={'health.py','health.json'}
