import copy
import json
from pathlib import Path

import pytest

from test_alpaca_day_protection_v1 import source
from research_lab import alpaca_day_monitor_v1 as monitor


def missing():
    s=source();s['open_orders']=[];s['stop_readbacks'][0]['status']='expired'
    return s


def test_critical_is_durable_before_notification_and_not_repeated(tmp_path):
    s=missing();sent=[]
    def sender(event):
        assert list((tmp_path/'journal').glob('*.json'))
        assert json.loads((tmp_path/'state.json').read_bytes())['incident_id']==event['incident_id']
        sent.append(event)
        return dict(delivered=True,http_status=200,message_id=1)
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:
        a=m.once(lambda:copy.deepcopy(s),sender)
        b=m.once(lambda:copy.deepcopy(s),sender)
    assert a['observation']['status']=='DAY_PROTECTION_MISSING'
    assert len(sent)==1 and b['notification']['status']=='ALREADY_RECORDED'


def test_restart_does_not_repeat_critical_and_recovery_notifies_once(tmp_path):
    s=missing();sent=[]
    sender=lambda e:sent.append(e) or dict(delivered=True)
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:m.once(lambda:s,sender)
    good=source()
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:
        m.once(lambda:s,sender)
        m.once(lambda:good,sender)
        m.once(lambda:good,sender)
        m.once(lambda:s,sender)
    assert [r['kind'] for r in sent]==['CRITICAL','RECOVERED','CRITICAL']


def test_notification_response_lost_is_not_resent(tmp_path):
    s=missing();calls=[]
    def sender(e):calls.append(e);raise OSError('response lost')
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:
        a=m.once(lambda:s,sender);m.once(lambda:s,sender)
    assert len(calls)==1 and a['notification']['status']=='DELIVERY_UNKNOWN_NO_RETRY'


def test_crash_after_claim_never_becomes_an_automatic_resend(tmp_path):
    s=missing();sent=[]
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:
        incident=monitor.digest(dict(first='test'))
        event=dict(kind='CRITICAL',incident_id=incident)
        key=monitor.digest(event)
        monitor.publish(tmp_path/'notifications'/(key+'.claim.json'),event)
        out=m.notify(event,lambda e:sent.append(e))
    assert not sent and out['status']=='DELIVERY_UNKNOWN_NO_RETRY'


def test_weekend_capture_is_quiet_and_does_not_claim_protection(tmp_path):
    s=source();s['clock']['is_open']=False;s['calendar']=[]
    s['completed_ms']=1792218519245;s['started_ms']=s['completed_ms']-1000
    s['clock']['timestamp']='2026-10-17T02:28:39.245-04:00';s['open_orders']=[]
    sent=[]
    with monitor.Monitor(tmp_path,clock=lambda:s['completed_ms']) as m:
        out=m.once(lambda:s,lambda e:sent.append(e))
    assert out['observation']['status']=='DAY_CLOSED_SESSION' and not sent


def test_source_failure_is_unknown_not_zero_and_does_not_leak_error_text(tmp_path):
    sent=[]
    def fail():raise RuntimeError('secret-value-that-must-not-be-printed')
    with monitor.Monitor(tmp_path,clock=lambda:1792416660000) as m:
        r=m.once(fail,lambda e:sent.append(e) or dict(delivered=True))
    assert r['observation']['status']=='DAY_PROTECTION_UNKNOWN' and len(sent)==1
    assert 'secret-value' not in json.dumps(r)
    assert 'secret-value' not in ''.join(p.read_text() for p in tmp_path.rglob('*.json'))


def test_only_one_observer_lock_and_no_foreign_runtime_writes(tmp_path):
    foreign=tmp_path/'foreign';foreign.mkdir();(foreign/'HALT').write_text('keep')
    own=tmp_path/'observer'
    with monitor.Monitor(own,clock=lambda:1):
        with pytest.raises(monitor.AlreadyRunning):monitor.Monitor(own,clock=lambda:1)
    assert (foreign/'HALT').read_text()=='keep' and list(foreign.iterdir())==[foreign/'HALT']


def test_test_notification_is_not_a_fake_protection_event(tmp_path):
    sent=[]
    with monitor.Monitor(tmp_path,clock=lambda:1792218519245) as m:
        m.delivery_test(lambda e:sent.append(e) or dict(delivered=True))
        m.delivery_test(lambda e:sent.append(e) or dict(delivered=True))
    assert len(sent)==1 and sent[0]['kind']=='DELIVERY_TEST'
    assert not list((tmp_path/'journal').glob('*.json'))


def test_get_reader_refuses_every_trade_and_external_route():
    calls=[]
    r=monitor.GetReader('key','secret',open_request=lambda req:calls.append(req))
    for route in ('https://evil.invalid','/v2/orders/../../positions','/v2/orders?status=all',
                  '/v2/orders?status=open&limit=500&symbols=NET','/v2/orders?status=open&limit=501',
                  '/v2/calendar?start=bad&end=bad'):
        with pytest.raises(ValueError):r.get(route)
    assert not calls


def test_get_reader_wire_is_get_and_never_accepts_a_method_or_payload():
    calls=[]
    def send(req):
        calls.append(req)
        assert req.get_method()=='GET' and req.data is None
        return b'{"is_open":false}'
    r=monitor.GetReader('key','secret',open_request=send)
    assert r.get('/v2/clock')['is_open'] is False
    with pytest.raises(TypeError):r.get('/v2/orders',method='POST',payload={})
    assert len(calls)==1


def test_failure_hook_does_not_depend_on_a_valid_observation_state(tmp_path):
    sent=[]
    with monitor.Monitor(tmp_path,clock=lambda:1792416660000) as m:
        (tmp_path/'state.json').write_text('broken')
        sender=lambda e:sent.append(e) or dict(delivered=True)
        m.service_failure(sender);m.service_failure(sender)
    assert len(sent)==1 and sent[0]['issues'][0]['code']=='DAY_MONITOR_SERVICE_FAILED'
    assert (tmp_path/'state.json').read_text()=='broken'


@pytest.mark.parametrize('flag',['--apply','--owner-go','--maintenance','--kill'])
def test_observer_cli_has_no_money_or_manager_interface(flag):
    from scripts.run_alpaca_day_monitor_v1 import main
    with pytest.raises(SystemExit):main([flag])


def test_real_collector_only_uses_whitelisted_gets_and_never_opens_account_lock(tmp_path,monkeypatch):
    import hashlib
    s=source();profile=tmp_path/'profile.env';binding=tmp_path/'binding.json'
    ledger=tmp_path/'ledger.json';lock=tmp_path/'account.lock'
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=fixture-key\nALPACA_API_SECRET_KEY=fixture-secret\n')
    ledger.write_text(json.dumps(s['expected']));lock.write_text('foreign-lock-unchanged')
    binding.write_text(json.dumps(dict(account_id='fixture-account',ledger_path=str(ledger),lock_path=str(lock))))
    config=dict(binding_path=str(binding),live_profile=str(profile),initial_expected=s['expected'],symbols=['NET'],
        account_lock_inode=lock.stat().st_ino,
        read_only_pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (profile,binding)})
    calls=[]
    class FakeGetReader:
        def __init__(self,*args):pass
        def get(self,path):
            calls.append(path)
            if path=='/v2/clock':return s['clock']
            if path.startswith('/v2/calendar?'):return s['calendar']
            return {'/v2/account':dict(id='fixture-account'),'/v2/positions':s['positions'],
                '/v2/orders?status=open&limit=500':s['open_orders'],'/v2/orders/owned-stop':s['stop_readbacks'][0]}[path]
    monkeypatch.setattr(monitor,'GetReader',FakeGetReader)
    monkeypatch.setattr(monitor.time,'time_ns',lambda:s['completed_ms']*1000000)
    before={p:p.read_bytes() for p in (profile,binding,ledger,lock)}
    out=monitor.collect(config)
    assert monitor.evaluate(out,now_ms=s['completed_ms'])['status']=='DAY_PROTECTION_CONFIRMED'
    assert len(calls)==7 and all(p.startswith('/v2/') for p in calls)
    assert before=={p:p.read_bytes() for p in before}


def _halt_pin_fixture(tmp_path, monkeypatch):
    """An entry HALT may move while owned NET maintenance remains legitimate."""
    import hashlib
    s=source();profile=tmp_path/'profile.env';binding=tmp_path/'binding.json'
    ledger=tmp_path/'ledger.json';lock=tmp_path/'account.lock';halt=tmp_path/'entry-halt.json'
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=fixture-key\nALPACA_API_SECRET_KEY=fixture-secret\n')
    ledger.write_text(json.dumps(s['expected']));lock.write_text('account-custody')
    binding.write_text(json.dumps(dict(account_id='fixture-account',ledger_path=str(ledger),lock_path=str(lock),halt_path=str(halt))))
    config=dict(binding_path=str(binding),live_profile=str(profile),initial_expected=s['expected'],symbols=['NET'],
        account_lock_inode=lock.stat().st_ino,
        read_only_pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (profile,binding)})
    calls=[]
    class FakeGetReader:
        def __init__(self,*args):pass
        def get(self,path):
            calls.append(path)
            if path=='/v2/clock':return s['clock']
            if path.startswith('/v2/calendar?'):return s['calendar']
            return {'/v2/account':dict(id='fixture-account'),'/v2/positions':s['positions'],
                '/v2/orders?status=open&limit=500':s['open_orders'],'/v2/orders/owned-stop':s['stop_readbacks'][0]}[path]
    monkeypatch.setattr(monitor,'GetReader',FakeGetReader)
    monkeypatch.setattr(monitor.time,'time_ns',lambda:s['completed_ms']*1000000)
    return config,calls,halt,binding,ledger,lock,s


def test_archived_entry_halt_in_source_pins_reproduces_capture_failure_before_get(tmp_path,monkeypatch):
    import hashlib
    config,calls,halt,*_= _halt_pin_fixture(tmp_path,monkeypatch)
    config['read_only_pins'][str(halt)]=hashlib.sha256(b'old archived HALT').hexdigest()
    with pytest.raises(FileNotFoundError):monitor.collect(config)
    assert not calls and not halt.exists()


@pytest.mark.parametrize('new_halt_present',[False,True])
def test_owned_stop_capture_ignores_entry_halt_state_without_mutating_it(tmp_path,monkeypatch,new_halt_present):
    config,calls,halt,binding,ledger,lock,s=_halt_pin_fixture(tmp_path,monkeypatch)
    if new_halt_present:halt.write_bytes(b'new entry remains HALTED')
    paths=[binding,ledger,lock,*([halt] if halt.exists() else [])]
    before={p:(p.read_bytes(),p.stat().st_ino,p.stat().st_mtime_ns) for p in paths}
    out=monitor.collect(config)
    observation=monitor.evaluate(out,now_ms=s['completed_ms'])
    assert observation['status']=='DAY_PROTECTION_CONFIRMED'
    assert observation['orders_allowed'] is False and observation['money_authority'] is False
    assert len(calls)==7 and halt.exists() is new_halt_present
    assert before=={p:(p.read_bytes(),p.stat().st_ino,p.stat().st_mtime_ns) for p in paths}


def test_removing_mutable_halt_pin_does_not_weaken_binding_pin(tmp_path,monkeypatch):
    config,calls,halt,binding,*_=_halt_pin_fixture(tmp_path,monkeypatch)
    binding.write_bytes(binding.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='READ_ONLY_SOURCE_PIN_DRIFT'):monitor.collect(config)
    assert not calls and not halt.exists()
