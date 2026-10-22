"""Separate early-exit scope, never a broker or original packet mutation."""
import hashlib,json
from pathlib import Path
import pytest
from scripts import alpaca_legacy_net_early_exit_v1 as early
from scripts import alpaca_legacy_net_exit_once_v1 as original

START=1792764000000 #23Oct14:00UTC /17:00Cyprus
def plan():
    return dict(session='2026-10-23',open_ms=START,end_ms=START+300000,
        session_open_ms=START-1800000,symbol='NET')

def test_default_never_loads_manifest_or_broker(monkeypatch,capsys):
    monkeypatch.setattr(early,'load',lambda *a:pytest.fail('must not load'))
    assert early.main([])==0 and 'OFFLINE_NO_AUTHORITY' in capsys.readouterr().out

@pytest.mark.parametrize('delta',[-1,0,299999,300000])
def test_separate_exact_early_window(delta):
    p=plan()
    if 0<=delta<300000:early.window(p,START+delta)
    else:
        with pytest.raises(ValueError):early.window(p,START+delta)
    with pytest.raises(ValueError):original.window(p,START+max(0,delta))

def test_actual_session_calendar_does_not_convert_early_window_into_open():
    assert early.calendar_open([dict(date='2026-10-23',open='09:30',close='16:00')])==START-1800000
    with pytest.raises(ValueError):early.calendar_open([dict(date='2026-11-02',open='09:30',close='16:00')])

@pytest.mark.parametrize('fault',['absent','legacy_go','changed_hash','extra','symlink'])
def test_early_go_is_separate_and_strict(tmp_path,fault):
    p=tmp_path/'go.json';pin='a'*64
    value=dict(schema='NET_EARLY_EXIT_EXACT_OWNER_GO_V1',manifest_sha256=pin,owner_go_text='GO NET EARLY EXIT '+pin)
    if fault=='legacy_go':value=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1')
    elif fault=='changed_hash':value['manifest_sha256']='b'*64
    elif fault=='extra':value['allow_buy']=True
    if fault!='absent':p.write_text(json.dumps(value));p.chmod(0o600)
    if fault=='symlink':q=tmp_path/'link';q.symlink_to(p);p=q
    with pytest.raises((ValueError,OSError)):
        early.check_early_owner_go(dict(new_owner_go_path=str(p),_manifest_sha256=pin))

def test_exact_early_go_acceptance_is_not_execution(tmp_path):
    p=tmp_path/'go.json';pin='a'*64
    p.write_text(json.dumps(dict(schema='NET_EARLY_EXIT_EXACT_OWNER_GO_V1',manifest_sha256=pin,owner_go_text='GO NET EARLY EXIT '+pin)));p.chmod(0o600)
    early.check_early_owner_go(dict(new_owner_go_path=str(p),_manifest_sha256=pin))

def test_unapproved_owner_execute_rejects_before_loading_control(tmp_path,monkeypatch):
    monkeypatch.setattr(early.importlib.util,'spec_from_file_location',lambda *a:pytest.fail('control loaded'))
    with pytest.raises((ValueError,OSError)):
        early.owner_execute(dict(new_owner_go_path=str(tmp_path/'missing'),_manifest_sha256='a'*64))


def test_claim_consumes_initiation_go_without_post_reservation_rejection(tmp_path,monkeypatch):
    """Real helper flow; simulated native permission boundary, no HTTP/orders."""
    import sqlite3
    from datetime import datetime,timezone
    from types import SimpleNamespace
    from research_lab import alpaca_dynamic_live_runtime_v1 as runtime
    from scripts import run_alpaca_dynamic_live_v1 as loader
    p=plan();p.update(entry_order_id='ORIGINAL_NET',intake_sha256='b'*64,initial_quantity='.5')
    pin='a'*64;go=tmp_path/'early-go.json'
    go.write_text(json.dumps(dict(schema='NET_EARLY_EXIT_EXACT_OWNER_GO_V1',manifest_sha256=pin,owner_go_text='GO NET EARLY EXIT '+pin)));go.chmod(0o600)
    ledger=tmp_path/'ledger.json';ledger.write_text(json.dumps(dict(NET=dict(accepted_stop_floor=277.69))))
    item=dict(entry=dict(id='ORIGINAL_NET'),intake=dict(intake_sha256='b'*64,plan=dict(symbol='NET',qty='.5')))
    with sqlite3.connect(tmp_path/'live.sqlite') as db:
        db.execute('create table intents(payload text)');db.execute('insert into intents values(?)',(json.dumps(item),))
    binding=dict(account_id='FIXTURE_ONLY',runtime=str(tmp_path),ledger_path=str(ledger))
    (tmp_path/'binding.json').write_text(json.dumps(binding));(tmp_path/'intake.json').write_text('{}');(tmp_path/'policy.json').write_text('{}')
    spec=dict(session_dir=str(tmp_path),live_profile='UNUSED_FIXTURE_PROFILE',policy=str(tmp_path/'policy.json'),intent=str(tmp_path/'intent'))
    (tmp_path/'spec.json').write_text(json.dumps(spec))
    control=tmp_path/'control.py';control.write_text('import json\ndef load_spec(path):\n return json.load(open(path))\n')
    clock=[START];monkeypatch.setattr(early.time,'time_ns',lambda:clock[0]*1000000)
    reader=SimpleNamespace(get_account=lambda:dict(id='FIXTURE_ONLY'),
        _http=lambda *a:[dict(date='2026-10-23',open='09:30',close='16:00')],
        get_clock=lambda:dict(is_open=True,timestamp=datetime.fromtimestamp(START/1000,timezone.utc).isoformat()),
        list_positions=lambda:[dict(symbol='NET',qty='.5',side='long')])
    permits=[];writer=SimpleNamespace(permit_write=lambda *a:permits.append(a))
    outroot=tmp_path/'receipts'
    def client(profile,binding,apply):
        if apply:
            assert (outroot/'personal-exit-claim.json').exists()
            go.unlink();clock[0]=START+400000 # Already consumed claim, not a new initiation.
            return writer
        return reader
    monkeypatch.setattr(loader,'load_client',client)
    monkeypatch.setattr(runtime,'owned_snapshot',lambda *a,**kw:None)
    def owned_run(**kw):
        assert kw['maintenance'] is True and kw['kill'] is True
        kw['client'].permit_write('DELETE','/v2/orders/OWNED_STOP')
        return dict(status='FIXTURE_OWNED_RECOVERY_ALLOWED')
    monkeypatch.setattr(runtime,'run_once',owned_run)
    m=dict(plan=p,new_owner_go_path=str(go),_manifest_sha256=pin,
        authority_semantics='CLAIM_INITIATION_WINDOW_THEN_OWNED_RECOVERY',
        control_path=str(control),spec_path=str(tmp_path/'spec.json'),output_root=str(outroot),existing_owner_go='FIXTURE_EXISTING_CUSTODY')
    assert early.owner_execute(m)['status']=='FIXTURE_OWNED_RECOVERY_ALLOWED'
    assert permits==[('DELETE','/v2/orders/OWNED_STOP')]
