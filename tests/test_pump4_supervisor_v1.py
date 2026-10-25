"""Persistent DATA daemon and selected-owner bridge, fictional sources only."""
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest
from test_pump4_bybit_sources_v1 import capture, H, NOW
from research_lab.pump4_bybit_sources_v1 import closed_h1, universe, UNIVERSE_SHA
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake


def module():
    try:
        return importlib.import_module('research_lab.pump4_supervisor_v1')
    except ImportError:
        pytest.fail('Persistent PUMP4 supervisor and selected lifecycle bridge are missing')


def archive(root, *, hour=2000, changed=False):
    root.mkdir(parents=True)
    bars = [[i*H, 10., 12., 8., 11., 100.] for i in range(hour-1001, hour+1)]
    if changed:
        bars[500][-1] = 999.
    return archive_bars(root, bars)


def archive_bars(root, bars, *, symbol='ZROUSDT'):
    root.mkdir(parents=True, exist_ok=True)
    entry = bars[-1][0]
    rows = [[str(b[0]), *map(str, b[1:]), '0'] for b in reversed(bars)]
    params = dict(category='linear',symbol=symbol,interval='60',start=bars[0][0],end=entry+H-1,limit=1000)
    caps = [capture('/v5/market/kline',params,dict(category='linear',symbol=symbol,list=rows[:1000]),at=entry),
        capture('/v5/market/kline',dict(params,end=int(rows[1000][0])+H-1),dict(category='linear',symbol=symbol,list=rows[1000:]),at=entry)]
    source = closed_h1(caps,symbol,next_open_ms=entry,observed_ms=entry+2)
    (root/'symbols').mkdir()
    for name in universe():
        row = dict(symbol=name,status='UNAVAILABLE_INSTRUMENT',captures=[])
        if name == symbol:
            row = dict(symbol=name,status='READY_H1_BOOTSTRAP_NOT_ENTRY',source=source,captures=caps)
        (root/'symbols'/(name+'.json')).write_text(json.dumps(row))
    seal = dict(schema='PUMP4_FROZEN137_PUBLIC_BOOTSTRAP_RECEIPT_V1',universe_sha256=UNIVERSE_SHA,census=137,
        source_hour_open_ms=entry,completed_ms=entry+2,source_capture_files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json')})
    (root/'receipt.json').write_text(json.dumps(seal))
    return root


def row(receipt):
    return next(r for r in receipt['rows'] if r['symbol']=='ZROUSDT')


def test_bootstrap_restart_and_identical_archive_have_immutable_observations(tmp_path):
    m=module();src=archive(tmp_path/'src');root=tmp_path/'state'
    s=m.Supervisor(root,clock=lambda:NOW+3)
    a=s.process_archive(src)
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}
    b=m.Supervisor(root,clock=lambda:NOW+500).process_archive(src)
    assert a==b and a['census']==137 and a['broker_writes']==0
    assert row(a)['mode']=='BOOTSTRAP_REPLAY' and a['prospective_decisions_credited']==0
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json*')}


def test_downtime_catches_every_missed_bar_in_order_without_reseed(tmp_path):
    m=module();root=tmp_path/'state';s=m.Supervisor(root,clock=lambda:NOW+3)
    s.process_archive(archive(tmp_path/'first'))
    out=m.Supervisor(root,clock=lambda:NOW+3*H+3).process_archive(archive(tmp_path/'later',hour=2003))
    intake=Pump4Intake(root/'intake/ZROUSDT.jsonl','ZROUSDT')
    events=intake.journal.read()
    assert [e['bar'][0] for e in events[1:]]==[1999*H,2000*H,2001*H,2002*H]
    assert len(events[0]['bars'])==1000 and row(out)['mode']=='CATCHUP_REPLAY'
    assert row(out)['accepted_bars']==3 and out['prospective_decisions_credited']==0


@pytest.mark.parametrize('fault',['changed','gap','hash','coverage'])
def test_invalid_archive_never_advances_existing_cursor(tmp_path,fault):
    m=module();root=tmp_path/'state';s=m.Supervisor(root,clock=lambda:NOW+3)
    s.process_archive(archive(tmp_path/'first'))
    src=archive(tmp_path/'later',hour=3002 if fault=='gap' else 2001,changed=fault=='changed')
    if fault=='hash':
        with (src/'symbols/ZROUSDT.json').open('a') as f:f.write(' ')
    if fault=='coverage':
        seal=json.loads((src/'receipt.json').read_text());seal['source_capture_files'].pop('symbols/ZROUSDT.json')
        (src/'receipt.json').write_text(json.dumps(seal))
    path=root/'intake/ZROUSDT.jsonl';before=path.read_bytes()
    if fault in {'hash','coverage'}:
        with pytest.raises(ValueError):s.process_archive(src)
    else:
        out=s.process_archive(src)
        assert row(out)['status']=='BLOCKED_SOURCE'
    assert path.read_bytes()==before


def test_default_cli_and_dispatch_fail_without_touching_state_or_sources(tmp_path,capsys):
    module()
    from scripts import run_pump4_supervisor_v1 as cli
    assert cli.main(['--root',str(tmp_path/'unused'),'--once'])==0
    assert json.loads(capsys.readouterr().out)['status']=='ORDERS_OFF_NO_REQUESTS'
    assert not (tmp_path/'unused').exists()
    assert cli.main(['--dispatch','--root',str(tmp_path/'unused'),'--once'])==2
    assert 'SELECTED_DISPATCH_NOT_WIRED' in capsys.readouterr().out
    assert not (tmp_path/'unused').exists()


def test_existing_admission_custody_preempts_missing_candidate_and_restarts(tmp_path):
    m=module()
    from test_pump4_account_owner_v1 import create,inputs,KEY,SECRET
    from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
    from decimal import Decimal as D
    o,e,t,_,f,lease=create(tmp_path,wire_kind='entry_reply_loss')
    try:
        x,p=inputs(e,now=t[0]);assert o.cycle(f,x,p,apply=True)['status']=='WIRE_UNKNOWN_RECONCILE_ONLY'
        def missing():raise AssertionError('Owned custody must not request fresh signal/H1')
        def read(plan,*,custody):
            assert custody and plan==f.config['plan']
            return inputs(e,now=t[0],price=price[0])
        price=['100']
        o=Pump4AccountOwner(o.scope,lease=lease,key=KEY,secret=SECRET,wire=e.wire,platform_check=o.platform_check,clock=lambda:t[0])
        assert m.selected_tick(o,read,missing,epoch_started_ms=1,max_delay_ms=1,apply=True)['status']=='PROTECTED_WAIT'
        assert e.state['calls']==1
        t[0]+=1000;price[0]='97.8';assert m.selected_tick(o,read,missing,epoch_started_ms=1,max_delay_ms=1,apply=True)['role']=='TP1'
        t[0]+=1000;price[0]='95.7';assert m.selected_tick(o,read,missing,epoch_started_ms=1,max_delay_ms=1,apply=True)['role']=='TP2'
        t[0]+=1000;assert m.selected_tick(o,read,missing,epoch_started_ms=1,max_delay_ms=1,apply=True)['status']=='FLAT_COSTS_PENDING'
        reqs=f.requests();assert D(reqs[1]['qty'])==D(reqs[0]['qty'])*D('.4') and D(reqs[2]['qty'])==D(reqs[0]['qty'])*D('.6')
        assert e.state['calls']==3
    finally:lease.close()


def test_new_entry_cannot_supply_a_plan_in_place_of_causal_candidate(tmp_path):
    m=module()
    from test_pump4_account_owner_v1 import create
    o,e,t,_,f,lease=create(tmp_path)
    try:
        def forbidden(*a,**kw):raise AssertionError('Account reader must follow causal gate')
        out=m.selected_tick(o,forbidden,lambda:dict(plan=f.config['plan']),epoch_started_ms=NOW-1,max_delay_ms=60000,apply=True)
        assert out['status']=='BLOCKED_NEW_INPUTS' and e.state['calls']==0
        assert not (o.root/'admitted-lifecycle.json').exists()
    finally:lease.close()


def fixture_candidate(root):
    x=json.loads((Path(__file__).parent/'fixtures/pump4_cycle_20261022.json').read_bytes())
    offset=NOW-(x['signal_bar'][0]+H);scale=100/x['next_open']
    def shifted(bar):return [bar[0]+offset,*[v*scale for v in bar[1:5]],bar[5]]
    bars=[*[shifted(b) for b in x['seed']],shifted(x['signal_bar']),[NOW,100.,100.,100.,100.,0.]]
    src=archive_bars(root/'source',bars)
    data=json.loads((src/'symbols/ZROUSDT.json').read_bytes())
    intake=Pump4Intake(root/'candidate.jsonl','ZROUSDT')
    intake.seed(bars[:-2],available_ms=NOW-H,observed_ms=NOW-H)
    decision=intake.accept(bars[-2],available_ms=NOW+1,observed_ms=NOW+1)['decision']
    assert decision['signal'] is not None
    return dict(intake=intake,decision_id=decision['decision_id'],captures=data['captures'])


def test_actual_causal_candidate_reaches_existing_cost_sizing_and_memory_entry(tmp_path):
    m=module()
    from test_pump4_account_owner_v1 import create,inputs,reseal
    o,e,t,_,_,lease=create(tmp_path);candidate=fixture_candidate(tmp_path)
    try:
        def read(plan,*,custody):
            assert not custody and plan['entry']==100.
            x,p=inputs(e,now=t[0]);cap=p['instruments']['pages'][0]
            cap['body']['result']['list'][0]['priceFilter']['tickSize']='.000000000000000001';reseal(cap)
            return x,p
        out=m.selected_tick(o,read,lambda:candidate,epoch_started_ms=NOW-1,max_delay_ms=60000,apply=True)
        assert out['status']=='ACK_RECONCILE_REQUIRED' and out['role']=='ENTRY'
        assert e.state['calls']==1
        identity=json.loads((o.root/'admitted-lifecycle.json').read_bytes())
        flow=json.loads((Path(identity['flow_root'])/'execution-config.json').read_bytes())
        assert flow['plan']['stop']>118 and flow['plan']['fractions']==[.4,.6]
    finally:lease.close()


@pytest.mark.parametrize('when',['before','after'])
def test_entry_clock_checked_before_and_after_account_reads(tmp_path,when):
    m=module()
    from test_pump4_account_owner_v1 import create,inputs
    o,e,t,_,_,lease=create(tmp_path);candidate=fixture_candidate(tmp_path)
    try:
        if when=='before':t[0]=NOW+60001
        def read(plan,*,custody):
            if when=='before':pytest.fail('Late H1 must block before account GET')
            x,p=inputs(e,now=t[0]);t[0]=NOW+60001
            return x,p
        out=m.selected_tick(o,read,lambda:candidate,epoch_started_ms=NOW-1,max_delay_ms=60000,apply=True)
        assert out['status']=='BLOCKED_NEW_INPUTS' and 'ENTRY_WINDOW' in out['reason']
        assert e.state['calls']==0 and not (o.root/'admitted-lifecycle.json').exists()
    finally:lease.close()


def test_current_signal_flows_through_causal_plan_and_stale_replay_stays_blocked(tmp_path):
    m=module();candidate=fixture_candidate(tmp_path)
    root=tmp_path/'state';root.mkdir();(root/'intake').mkdir()
    target=root/'intake/ZROUSDT.jsonl'
    # Existing continuous prefix is the previous capture's durable seed only.
    original=candidate['intake'].journal.read()[0]
    intake=Pump4Intake(target,'ZROUSDT');intake.seed(original['bars'],available_ms=NOW-H,observed_ms=NOW-H)
    from research_lab.kity_micro_physical_owner_v1 import publish
    publish(root/'epochs/ZROUSDT.json',dict(schema='PUMP4_DATA_EPOCH_V1',symbol='ZROUSDT',epoch_started_ms=NOW-1,
        seed_sha256=intake.snapshot()['seed_bars_sha256'],financial_authority=False))
    out=m.Supervisor(root,clock=lambda:NOW+3).process_archive(tmp_path/'source')
    observation=row(out)['decisions'][0]
    assert observation['status']=='CAUSAL_PLAN_DATA_ONLY' and observation['plan']['entry']==100.
    assert m.Supervisor(root,clock=lambda:NOW+60001).process_archive(tmp_path/'source')==out


def test_public_capture_cadence_survives_restart_without_repeated_collector(tmp_path):
    m=module();root=tmp_path/'state';t=[NOW+3];calls=[]
    def collect(path,*,on_symbol=None):calls.append(path);archive(path,hour=t[0]//H)
    one=m.Supervisor(root,clock=lambda:t[0]).public_cycle(collector=collect)
    two=m.Supervisor(root,clock=lambda:t[0]+30000).public_cycle(collector=collect)
    assert one==two and len(calls)==1
    t[0]+=H;m.Supervisor(root,clock=lambda:t[0]).public_cycle(collector=collect)
    assert len(calls)==2


def test_partial_public_capture_is_preserved_without_blind_retry(tmp_path):
    m=module();root=tmp_path/'state';s=m.Supervisor(root,clock=lambda:NOW+3)
    path=root/'archives'/str(NOW);path.mkdir(parents=True);(path/'partial').write_text('preserved')
    with pytest.raises(ValueError,match='PARTIAL_ARCHIVE'):
        s.public_cycle(collector=lambda _:pytest.fail('Must not overwrite partial archive'))
    assert (path/'partial').read_text()=='preserved'


def test_data_alert_callback_has_durable_once_delivery_and_replay_is_quiet(tmp_path):
    m=module();fixture_candidate(tmp_path);events=[]
    def alert(event):events.append(event);return dict(delivered=True)
    s=m.Supervisor(tmp_path/'state',clock=lambda:NOW+3,alert=alert)
    a=s.process_archive(tmp_path/'source');s.process_archive(tmp_path/'source')
    assert len(events)==1 and events[0]['status']=='REPLAY_NOT_PROSPECTIVE'
    assert events[0]['broker_writes']==0 and events[0]['money_authority'] is False
    assert len(list((tmp_path/'state/alerts').rglob('notification-receipt.json')))==1


def test_cli_sigterm_cleanly_stops_data_loop(tmp_path,monkeypatch,capsys):
    module()
    import os,signal
    from scripts import run_pump4_supervisor_v1 as cli
    src=archive(tmp_path/'source');original=cli.Supervisor.process_archive
    def stop_after(self,path):
        result=original(self,path);os.kill(os.getpid(),signal.SIGTERM);return result
    monkeypatch.setattr(cli.Supervisor,'process_archive',stop_after)
    assert cli.main(['--source-mode','archive','--archive',str(src),'--root',str(tmp_path/'state')])==0
    assert json.loads(capsys.readouterr().out)['broker_writes']==0


def test_missing_epoch_after_bootstrap_cannot_silently_reset_prospective_boundary(tmp_path):
    m=module();root=tmp_path/'state';s=m.Supervisor(root,clock=lambda:NOW+3)
    s.process_archive(archive(tmp_path/'first'));(root/'epochs/ZROUSDT.json').unlink()
    path=root/'intake/ZROUSDT.jsonl';before=path.read_bytes()
    out=s.process_archive(archive(tmp_path/'later',hour=2001))
    assert row(out)['status']=='BLOCKED_SOURCE' and 'EPOCH_MISSING_NO_RESET' in row(out)['reason']
    assert path.read_bytes()==before and not (root/'epochs/ZROUSDT.json').exists()


def test_data_writer_is_exclusive_without_claiming_any_account_lease(tmp_path):
    m=module();s=m.Supervisor(tmp_path/'state',clock=lambda:NOW+3)
    src=archive(tmp_path/'source')
    with s._writer():
        with pytest.raises(BlockingIOError):m.Supervisor(tmp_path/'state').process_archive(src)
    assert not list((tmp_path/'state').rglob('account.lock'))


def test_committed_cycle_recovers_alert_delivery_before_claim_without_duplicate(tmp_path,monkeypatch):
    m=module();fixture_candidate(tmp_path);events=[]
    from research_lab import kity_fresh_eligibility_watch_v1 as channel
    def before_claim(*a,**kw):raise OSError('crash after cycle receipt before notification claim')
    with monkeypatch.context() as patch:
        patch.setattr(channel,'notify_once',before_claim)
        with pytest.raises(OSError):
            m.Supervisor(tmp_path/'state',clock=lambda:NOW+3,alert=lambda e:None).process_archive(tmp_path/'source')
    def alert(event):events.append(event);return dict(delivered=True)
    s=m.Supervisor(tmp_path/'state',clock=lambda:NOW+300,alert=alert)
    s.process_archive(tmp_path/'source');s.process_archive(tmp_path/'source')
    assert len(events)==1
