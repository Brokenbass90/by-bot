"""Entry-only legacy handoff; fixtures never contact systemd or a broker."""
import pytest
import hashlib
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign


def test_even_direct_live_entry_requires_signed_legacy_handoff(setup,monkeypatch):
    _,_,adapter,_,now=setup
    _,writes,_=connect_wire(setup,monkeypatch)
    scope=standing(adapter,now);scope.pop('legacy_handoff',None);resign(adapter,scope)
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_HANDOFF_REQUIRED'):
        adapter.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]


@pytest.fixture
def retired(tmp_path,monkeypatch):
    import importlib
    from scripts.rehearse_alpaca_monthly_cycle_v1 import LegacyMemoryUnits
    module=importlib.import_module('research_lab.alpaca_monthly_handoff_v1')
    units=LegacyMemoryUnits(tmp_path/'legacy')
    monkeypatch.setattr(module,'_systemctl_show',units.show)
    monkeypatch.setattr(module,'_legacy_crontab',lambda:units.cron)
    monkeypatch.setattr(module,'_legacy_processes',lambda:units.processes)
    return module,units


def test_retired_units_produce_fresh_bound_check(retired):
    m,u=retired;proof=m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)
    assert proof['status']=='LEGACY_RETIREMENT_CONFIRMED'
    assert set(proof['units'])==set(m.UNITS)
    assert m.require_fresh(proof,u.policy,'fixture-cid',now_ms=proof['completed_ms']) is proof


def test_pinned_static_timer_is_retired_only_while_inactive_and_jobless(retired):
    m,u=retired;timer='alpaca-oct15-owned-manager.timer'
    u.rows[timer]['UnitFileState']='static'
    proof=m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)
    assert proof['units'][timer]['UnitFileState']=='static'
    u.rows[timer]['Job']='42'
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_NOT_RETIRED'):
        m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)


@pytest.mark.parametrize('fault',['active_timer','enabled_timer','active_service','pid','control_pid','job',
    'dropin','daemon_reload','transient','load_unknown','extra_trigger','missing_unit','fragment_drift','cron_writer','cron_drift'])
def test_unsafe_legacy_state_never_passes(retired,fault):
    m,u=retired;t='alpaca-oct15-owned-manager.timer';s='alpaca-oct15-owned-manager.service'
    if fault=='active_timer':u.rows[t]['ActiveState']='active'
    elif fault=='enabled_timer':u.rows[t]['UnitFileState']='enabled'
    elif fault=='active_service':u.rows[s]['ActiveState']='activating'
    elif fault=='pid':u.rows[s]['MainPID']='123'
    elif fault=='control_pid':u.rows[s]['ControlPID']='123'
    elif fault=='job':u.rows[t]['Job']='123'
    elif fault=='dropin':u.rows[s]['DropInPaths']='/tmp/override.conf'
    elif fault=='daemon_reload':u.rows[s]['NeedDaemonReload']='yes'
    elif fault=='transient':u.rows[s]['Transient']='yes'
    elif fault=='load_unknown':u.rows[s]['LoadState']='not-found'
    elif fault=='extra_trigger':u.rows[s]['TriggeredBy']+=' another.timer'
    elif fault=='missing_unit':u.rows.pop(s)
    elif fault=='fragment_drift':__import__('pathlib').Path(u.policy['units'][s]['fragment_path']).write_text('changed')
    elif fault=='cron_writer':
        u.cron='* * * * * /root/by-bot/runtime/alpaca_intended_live/run.sh --send-orders\n'
        u.policy['cron_projection_sha256']=m.cron_projection(u.cron)[0]
    else:u.cron='# changed alpaca_intended_live\n'
    with pytest.raises((ValueError,OSError)):m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)


@pytest.mark.parametrize('fault',['stale','future','cid','policy','content'])
def test_retirement_evidence_cannot_be_reused_or_aged(retired,fault):
    m,u=retired;proof=m.capture_retirement(u.policy,'fixture-cid',now_ms=10000);now=proof['completed_ms'];cid='fixture-cid'
    if fault=='stale':now+=5001
    elif fault=='future':now-=1
    elif fault=='cid':cid='other-cid'
    elif fault=='policy':u.policy['cron_projection_sha256']='0'*64
    else:proof['status']='tampered'
    with pytest.raises(ValueError):m.require_fresh(proof,u.policy,cid,now_ms=now)


def test_handoff_source_failure_blocks_entry(retired,monkeypatch):
    m,u=retired
    def unknown():raise OSError('fixture systemd unavailable')
    monkeypatch.setattr(m,'_systemctl_show',unknown)
    with pytest.raises(OSError):m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)


def test_handoff_helper_itself_must_be_owner_source_pinned(setup,monkeypatch):
    from pathlib import Path
    from research_lab.alpaca_dynamic_v1 import canonical
    import hashlib,json
    _,_,a,_,now=setup;_,writes,_=connect_wire(setup,monkeypatch)
    s=json.loads(Path(a.live_scope_path).read_bytes())
    s['source_files']=[x for x in s['source_files'] if not x['path'].endswith('/alpaca_monthly_handoff_v1.py')]
    Path(a.live_scope_path).write_bytes(canonical(s));a.live_scope_sha256=hashlib.sha256(Path(a.live_scope_path).read_bytes()).hexdigest()
    Path(a.owner_go_path).write_bytes(canonical(dict(schema='ALPACA_MONTHLY_EXACT_OWNER_GO_V1',
        scope_sha256=a.live_scope_sha256,owner_go_text='GO ALPACA_MONTHLY '+a.live_scope_sha256)))
    with pytest.raises(ValueError,match='MONTHLY_LIVE_IMPLEMENTATION_UNBOUND'):
        a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]


def test_final_dispatch_rechecks_legacy_state_after_reservation(setup,monkeypatch):
    _,_,a,_,now=setup;_,writes,_=connect_wire(setup,monkeypatch);saved=ticket(setup)
    from research_lab import alpaca_monthly_handoff_v1 as h
    real=h._systemctl_show;calls=[]
    def changed():
        calls.append(1)
        if len(calls)==2:a.fixture_legacy.rows['alpaca-oct15-owned-manager.timer']['UnitFileState']='enabled'
        return real()
    monkeypatch.setattr(h,'_systemctl_show',changed)
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_TIMER_NOT_DISABLED'):
        a.enter(saved,now_ms=now,apply=True)
    assert len(calls)==2 and writes==[]


def test_missing_handoff_source_never_blocks_owned_stop_rearm_and_recovery(setup,monkeypatch):
    b,_,a,io,now=setup;_,writes,_=connect_wire(setup,monkeypatch);standing(a,now);saved=ticket(setup)
    a.enter(saved,now_ms=now,apply=True);before=len(writes)
    io.orders['stop']['status']='expired'
    from research_lab import alpaca_monthly_handoff_v1 as h
    def unknown():raise AssertionError('maintenance/recovery must not query legacy entry gate')
    monkeypatch.setattr(h,'_systemctl_show',unknown)
    a.maintain(now_ms=now+1000,apply=True)
    assert len(writes)==before+1 and writes[-1][1]['type']=='stop'
    assert a.enter(saved,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    assert len([w for w in writes if w[1] and w[1].get('side')=='buy'])==1


def test_legacy_process_and_unknown_cron_modes_block(retired):
    m,u=retired;u.processes='/bin/bash /root/by-bot/run_alpaca_live_v38_once.sh\n'
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_PROCESS_ACTIVE'):
        m.capture_retirement(u.policy,'cid',now_ms=10000)
    u.processes='';u.cron='* * * * * /root/by-bot/runtime/alpaca_intended_live/run.sh\n'
    u.policy['cron_projection_sha256']=m.cron_projection(u.cron)[0]
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_CRON_NOT_RETIRED'):
        m.capture_retirement(u.policy,'cid',now_ms=10000)


def test_readonly_cron_cannot_be_allowed_with_unrelated_source_pin(retired):
    m,u=retired;u.cron='* * * * * /root/by-bot/runtime/alpaca_intended_live/run.sh\n'
    u.policy['cron_projection_sha256']=m.cron_projection(u.cron)[0]
    import hashlib
    row=next(iter(u.policy['units'].values()))
    u.policy['readonly_cron'][hashlib.sha256(u.cron.strip().encode()).hexdigest()]={row['fragment_path']:row['sha256']}
    with pytest.raises(ValueError,match='MONTHLY_HANDOFF_READONLY_CRON_UNBOUND'):
        m.capture_retirement(u.policy,'cid',now_ms=10000)


@pytest.mark.parametrize('command',[
    '/root/by-bot/runtime/alpaca_intended_live/run.sh',
    '/bin/bash /root/by-bot/runtime/alpaca_intended_live/run.sh --read-only',
    '/usr/bin/flock -n /root/by-bot/runtime/alpaca_intended_live/data.lock /bin/bash '
    '/root/by-bot/runtime/alpaca_intended_live/run.sh --prepare >> '
    '/root/by-bot/runtime/alpaca_intended_live/logs/prepare.log 2>&1 # alpaca_intended_live_data',
])
def test_known_readonly_cron_is_allowed_only_with_pinned_chain(retired,tmp_path,monkeypatch,command):
    import hashlib
    m,u=retired;paths=[];pins={}
    for name in ('run.sh','intended.sh','driver.sh','driver.py','fixture-profile'):
        p=tmp_path/name;p.write_text('FIXTURE ONLY '+name);paths.append(str(p));pins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(m,'READONLY_CRON_SOURCES',tuple(paths))
    line='* * * * * '+command
    u.cron=line+'\n';u.policy['cron_projection_sha256']=m.cron_projection(u.cron)[0]
    u.policy['readonly_cron']={hashlib.sha256(line.encode()).hexdigest():pins}
    assert m.capture_retirement(u.policy,'cid',now_ms=10000)['status']=='LEGACY_RETIREMENT_CONFIRMED'
    (tmp_path/'driver.sh').write_text('changed')
    with pytest.raises(ValueError,match='MONTHLY_HANDOFF_FILE_DRIFT'):
        m.capture_retirement(u.policy,'cid',now_ms=10000)


@pytest.mark.parametrize('command', [
    '/root/by-bot/runtime/alpaca_intended_live/run.sh --send-orders;',
    '/root/by-bot/runtime/alpaca_intended_live/run.sh --send-orders>/tmp/fixture.log',
    '/bin/bash -c "/root/by-bot/runtime/alpaca_intended_live/run.sh --send-orders"',
    '/root/by-bot/runtime/alpaca_intended_live/run.sh --read-only; /bin/true',
    '/root/by-bot/runtime/alpaca_intended_live/run.sh $(echo --send-orders)',
    '/root/by-bot/runtime/alpaca_intended_live/run.sh --prepare >> /tmp/other.log',
])
def test_pinned_cron_still_rejects_shell_write_flags(retired, tmp_path, monkeypatch, command):
    m, u = retired
    pins = {}
    for name in ('run.sh', 'intended.sh', 'driver.sh', 'driver.py', 'fixture-profile'):
        p = tmp_path/name
        p.write_text('FIXTURE ONLY '+name)
        pins[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(m, 'READONLY_CRON_SOURCES', tuple(pins))
    line = '* * * * * '+command
    u.cron = line+'\n'
    u.policy['cron_projection_sha256'] = m.cron_projection(u.cron)[0]
    u.policy['readonly_cron'] = {hashlib.sha256(line.encode()).hexdigest(): pins}
    with pytest.raises(ValueError, match='MONTHLY_LEGACY_CRON_NOT_RETIRED'):
        m.capture_retirement(u.policy, 'fixture-cid', now_ms=10000)

@pytest.mark.parametrize('command', [
    '/usr/bin/python3 /fixture/app/scripts/run_alpaca_dynamic_live_v1.py --maintenance --apply',
    '/usr/bin/python3 /fixture/app/scripts/alpaca_next_entry_control_v1.py --entry',
    '/usr/bin/python3 /fixture/app/scripts/alpaca_next_entry_control_v1.py --maintenance',
])
def test_running_legacy_dynamic_writer_rejected(retired, command):
    m, u = retired
    u.processes = command+'\n'
    with pytest.raises(ValueError, match='MONTHLY_LEGACY_PROCESS_ACTIVE'):
        m.capture_retirement(u.policy, 'fixture-cid', now_ms=10000)


def test_current_next_entry_cron_cannot_escape_projection(retired):
    m, u = retired
    u.cron = ('* * * * * /root/by-bot/.venv/bin/python -B '
              '/opt/bybot-research/alpaca-next-entry-20261019-v1/app/scripts/alpaca_next_entry_control_v1.py '
              '--spec /fixture/spec.json --spec-sha256 '+('a'*64)+' --maintenance\n')
    # Original approved empty projection remains untouched; no cron row allowlisted.
    with pytest.raises(ValueError):
        m.capture_retirement(u.policy, 'fixture-cid', now_ms=10000)


@pytest.mark.parametrize('path', [
    '/opt/bybot-research/alpaca-next-entry-20261019-v1/manager-wrapper.py',
    '/opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/control-v1.py',
    '/opt/bybot-research/alpaca-dynamic-live-20261013/repairs/oct16-entry-identity-v2/control-v1.py',
])
def test_pinned_legacy_wrapper_running_or_scheduled_is_not_retired(retired,path):
    m,u=retired;u.processes='/usr/bin/python3 '+path+' --maintenance\n'
    with pytest.raises(ValueError,match='MONTHLY_LEGACY_PROCESS_ACTIVE'):
        m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)
    u.processes='';u.cron='* * * * * /usr/bin/python3 '+path+' --maintenance\n'
    with pytest.raises(ValueError,match='MONTHLY_HANDOFF_CRON_DRIFT'):
        m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)


def test_unrelated_generic_control_process_does_not_block_entry(retired):
    m,u=retired;u.processes='/usr/bin/python3 /fixture/unrelated/control-v1.py --maintenance\n'
    assert m.capture_retirement(u.policy,'fixture-cid',now_ms=10000)['legacy_process_count']==0


def test_handoff_receipt_disk_failure_cannot_send_new_buy(setup,monkeypatch):
    _,_,a,_,now=setup;_,writes,_=connect_wire(setup,monkeypatch);standing(a,now)
    from research_lab import kity_oct15_deadline_v1 as store
    real=store.publish_once
    def failed(path,raw):
        if str(path).endswith('.legacy-handoff.json'):raise OSError('fixture handoff disk failure')
        return real(path,raw)
    monkeypatch.setattr(store,'publish_once',failed)
    with pytest.raises(OSError,match='fixture handoff disk failure'):
        a.enter(ticket(setup),now_ms=now,apply=True)
    assert writes==[]
