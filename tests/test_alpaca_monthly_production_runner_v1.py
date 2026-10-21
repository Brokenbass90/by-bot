"""Production entrypoint acceptance. Explicit fake grants/transport, no network."""
import copy
import hashlib
import json
import os
import sqlite3
from test_alpaca_monthly_native_binding_v1 import ticket
from pathlib import Path

import pytest
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab import alpaca_monthly_native_binding_v1 as native
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager
from scripts import run_alpaca_monthly_cycle_v1 as cli
from test_alpaca_monthly_native_binding_v1 import setup
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign


def write(path,value):
    path.write_bytes(canonical(value));return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def runner(setup,tmp_path,monkeypatch):
    book,selection,a,io,now=setup
    client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(a,now)
    manager=dict(root=str(tmp_path/'cycle'),account_id='fixture',capital='487.42',
        account_lock_path=str(a.lock_path),entry_halt_path=str(a.halt))
    m=MonthlyManager(**manager);dest=m.root/'book/monthly-orders-off.sqlite';dest.parent.mkdir()
    with sqlite3.connect(book.path) as before,sqlite3.connect(dest) as after:before.backup(after)
    binding=Path(os.environ['ALPACA_INTENDED_LIVE_BINDING_PATH'])
    costs=dict(after='2026-10-30T00:00:00Z',protocol=dict(path=str(tmp_path/'absent-protocol'),sha256='a'*64),
        calendar=dict(path=str(tmp_path/'absent-calendar'),sha256='b'*64),assets=dict(path=str(tmp_path/'absent-assets'),sha256='c'*64))
    spec=dict(schema='ALPACA_MONTHLY_OWNED_RUNNER_V1',enabled=True,orders_allowed=True,money_authority=True,
        files=native.standing_source_pins(),manager=manager,source_captures=str(tmp_path/'captures'),
        broker_root=str(tmp_path),profile=dict(path=str(tmp_path/'unused-profile'),sha256='d'*64),
        native_binding=dict(path=str(binding),sha256=hashlib.sha256(binding.read_bytes()).hexdigest()),legacy_handoff=scope['legacy_handoff'],
        native=dict(liability_reserve_usd='0',pending_fee_admission=False),costs=costs,notifications=None)
    scope.update(book=str(dest),runtime=str(m.root/'native'),runner_config_sha256=cli.runner_config_sha256(spec))
    resign(a,scope)
    spec['authority']=dict(scope_path=str(a.live_scope_path),scope_sha256=a.live_scope_sha256,owner_go_path=str(a.owner_go_path))
    return spec,m,client,writes,now,a,scope


def test_runner_config_pin_covers_operational_inputs_without_hash_cycle():
    spec={k:{} for k in cli.RUNNER_CONFIG_FIELDS}
    before=cli.runner_config_sha256(spec)
    spec['authority']=dict(scope_sha256='x'*64)
    assert cli.runner_config_sha256(spec)==before
    spec['costs']={'after':'changed'}
    assert cli.runner_config_sha256(spec)!=before


def test_disabled_dispatch_never_constructs_transport(tmp_path):
    path=tmp_path/'disabled.json'
    write(path,dict(schema='ALPACA_MONTHLY_CYCLE_DISABLED_V1',enabled=False,
        orders_allowed=False,money_authority=False,files={}))
    calls=[]
    assert cli.main(['--spec',str(path),'--spec-sha256',hashlib.sha256(path.read_bytes()).hexdigest(),'--dispatch'],
        client_factory=lambda s:calls.append(s))==2
    assert calls==[]


@pytest.mark.parametrize('fault',['old_grant','changed_config','wrong_go','source_drift'])
def test_unapproved_dispatch_stops_before_transport_or_owned_state(runner,fault):
    spec,m,client,writes,now,a,scope=runner;calls=[]
    if fault=='old_grant':scope.pop('runner_config_sha256');resign(a,scope);spec['authority']['scope_sha256']=a.live_scope_sha256
    elif fault=='changed_config':spec['costs']['after']='changed'
    elif fault=='wrong_go':Path(a.owner_go_path).write_text('{}')
    else:spec['files'][next(iter(spec['files']))]='f'*64
    before=m.book.rows('positions')
    with pytest.raises(ValueError):cli.dispatch_cycle(spec,client_factory=lambda s:calls.append(s),now_ms=now)
    assert calls==writes==[] and m.book.rows('positions')==before


def test_source_failure_reaches_existing_owned_maintenance(runner,monkeypatch):
    spec,m,client,writes,now,a,scope=runner;events=[]
    maintain=MonthlyManager.maintain
    def observed(self,*args,**kwargs):events.append('maintenance');return maintain(self,*args,**kwargs)
    monkeypatch.setattr(MonthlyManager,'maintain',observed)
    def missing(*args):events.append('source');raise ValueError('fixture source unavailable')
    out=cli.dispatch_cycle(spec,client_factory=lambda s:client,now_ms=now,bundle_loader=missing)
    assert events==['maintenance','source']
    assert any(i['phase']=='SOURCE' for i in out['issues']) and out['entry_status']=='BLOCKED'
    assert writes==[]


def test_full_frozen_rotation_runs_through_production_cli(tmp_path):
    from scripts.rehearse_alpaca_monthly_cycle_v1 import run_pending_rotation
    out=run_pending_rotation(tmp_path/'production',production_entrypoint=True)
    assert out['status']=='MONTHLY_PRODUCTION_ENTRYPOINT_ORDERS_OFF_E2E_PASS'
    assert out['production_entrypoint'] and out['production_cli_calls']>=6
    assert out['source_loader_injected'] is False and out['selector_monkeypatched'] is False
    assert out['first_entry_buy_and_stop_response_loss_recovered']
    assert out['rotation_exits']==1 and out['simulated_entries']==2 and out['duplicate_entries']==0
    assert out['legacy_retirement_checks']==2 and out['legacy_handoff_fixture_only'] is True
    assert out['old_exit_pending_during_new_entries'] and out['old_exit_finalized_after_posting']
    assert out['real_broker_requests']==out['real_broker_writes']==0


def test_disabled_templates_keep_source_separate_from_one_dispatch_manager():
    from research_lab.alpaca_monthly_release_v1 import unit_templates
    files=unit_templates('/opt/monthly/app','/opt/python','/opt/monthly/source.json','a'*64,
        dispatch_spec='/opt/monthly/owned.json',dispatch_sha256='b'*64)
    assert '--source' in files['alpaca-monthly-owned-source.service']
    assert '--dispatch' not in files['alpaca-monthly-owned-source.service']
    assert '--dispatch' in files['alpaca-monthly-owned-manager.service']
    assert '/opt/monthly/owned.json' in files['alpaca-monthly-owned-manager.service']
    assert 'enable --now' not in ''.join(files.values())
    assert len([n for n in files if n.endswith('.timer')])==2


def test_dispatch_record_failure_after_write_never_claims_zero(runner,setup,monkeypatch,capsys,tmp_path):
    spec,m,client,writes,now,a,scope=runner
    _,_,_,io,_=setup
    a.book=m.book;a.runtime=m.root/'native';a.ledger=a.runtime/'native-floor.json';a.reentry=a.runtime/'native-intents.json'
    prepared=ticket(setup)
    a.enter(prepared,now_ms=now,apply=True)
    assert len(writes)==2
    io.orders['stop']['status']='expired'
    original=MonthlyManager._record
    def failing_record(self,kind,out,stamp):
        if kind=='DISPATCH_TICK':raise OSError('fixture: final receipt disk failure')
        return original(self,kind,out,stamp)
    monkeypatch.setattr(MonthlyManager,'_record',failing_record)
    path=tmp_path/'runner.json';pin=write(path,spec)['sha256']
    def missing(*args):raise ValueError('fixture source unavailable')
    before=len(writes)
    rc=cli.main(['--spec',str(path),'--spec-sha256',pin,'--dispatch'],client_factory=lambda s:client,
        now_ms=now,bundle_loader=missing)
    out=json.loads(capsys.readouterr().out)
    assert len(writes)>before,(writes,out)
    print(json.dumps(dict(cli=out,actual_memory_writes_during_tick=len(writes)-before,exit_code=rc),sort_keys=True))
    assert out['broker_writes'] is None
    assert out['broker_write_count_source']=='EXISTING_OWNED_DISPATCH_JOURNAL'
    assert rc==2


def test_unapproved_dispatch_cannot_use_notification_configuration(runner,tmp_path,monkeypatch):
    from research_lab import alpaca_monthly_notifications_v1 as notifications
    spec,m,client,writes,now,a,scope=runner;sent=[]
    spec['notifications']={'output_root':str(tmp_path/'alerts')}
    scope['runner_config_sha256']=cli.runner_config_sha256(spec);resign(a,scope)
    spec['authority']['scope_sha256']=a.live_scope_sha256
    Path(a.owner_go_path).write_text('{}')
    monkeypatch.setattr(notifications,'event_delivery',lambda *a,**kw:sent.append(kw) or {})
    path=tmp_path/'unapproved.json';pin=write(path,spec)['sha256']
    assert cli.main(['--spec',str(path),'--spec-sha256',pin,'--dispatch'],client_factory=lambda s:client,now_ms=now)==2
    assert sent==writes==[]


def test_production_profile_loader_selects_monthly_contract_without_write_permit(runner,tmp_path):
    spec,m,client,writes,now,a,scope=runner
    folder=tmp_path/'configs';folder.mkdir();profile=folder/'fixture.env'
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=FIXTURE\nALPACA_API_SECRET_KEY=FIXTURE\nALPACA_BRIDGE_LOCK_PATH='+str(a.lock_path)+'\n')
    spec['profile']=dict(path=str(profile),sha256=hashlib.sha256(profile.read_bytes()).hexdigest())
    actual=cli.production_client(spec)
    assert actual.order_contract==native.CONTRACT['schema'] and actual.writes_enabled
    actual._http=lambda *a:pytest.fail('No HTTP without existing exact permit')
    with pytest.raises(ValueError,match='PERMIT_REQUIRED'):
        actual.submit_market_buy('NET',10,client_order_id='abm-'+'a'*32,notional_precision=9)


@pytest.mark.parametrize('fault',['host','lock','pin'])
def test_profile_drift_cannot_construct_an_alternate_monthly_transport(runner,tmp_path,fault):
    spec,m,client,writes,now,a,scope=runner
    folder=tmp_path/'configs';folder.mkdir();profile=folder/'fixture.env'
    profile.write_text('ALPACA_BASE_URL='+('https://paper-api.alpaca.markets' if fault=='host' else 'https://api.alpaca.markets')+'\nALPACA_API_KEY_ID=FIXTURE\nALPACA_API_SECRET_KEY=FIXTURE\nALPACA_BRIDGE_LOCK_PATH='+str(tmp_path/'other.lock' if fault=='lock' else a.lock_path)+'\n')
    spec['profile']=dict(path=str(profile),sha256='f'*64 if fault=='pin' else hashlib.sha256(profile.read_bytes()).hexdigest())
    with pytest.raises(ValueError):cli.production_client(spec)


def test_disabled_source_failure_keeps_authorized_existing_alert_route(runner,tmp_path,monkeypatch):
    from research_lab import alpaca_monthly_notifications_v1 as notifications
    spec,m,client,writes,now,a,scope=runner;sent=[]
    spec.update(schema='ALPACA_MONTHLY_CYCLE_DISABLED_V1',enabled=False,orders_allowed=False,money_authority=False,
        notifications={'output_root':str(tmp_path/'alerts')})
    monkeypatch.setattr(notifications,'event_delivery',lambda *a,**kw:sent.append(kw) or {'status':'FIXTURE'})
    path=tmp_path/'disabled-source.json';pin=write(path,spec)['sha256']
    assert cli.main(['--spec',str(path),'--spec-sha256',pin,'--source'],now_ms=now)==2
    assert sent and sent[0]['component']=='source' and writes==[]
