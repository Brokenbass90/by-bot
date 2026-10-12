"""Durable dispatch/manager counterexamples; all broker writes are simulated."""
import copy
import importlib
import json
from pathlib import Path
import sqlite3

import pytest

from tests.test_alpaca_dynamic_live_intake_v1 import case, compiled, NOW
from research_lab.alpaca_dynamic_v1 import canonical, digest
from scripts.equities_alpaca_paper_bridge import AlpacaAPIError


def api():
    try:
        return importlib.import_module('research_lab.alpaca_dynamic_live_runtime_v1')
    except ImportError:
        return None


class Broker:
    base_url = 'https://api.alpaca.markets'
    def __init__(self, account):
        self.account = dict(id=account, cash='100', non_marginable_buying_power='100',
                            trading_blocked=False, account_blocked=False)
        self.orders = {}; self.positions = []; self.writes = []
        self.fail = None; self.fill = '.5'; self.clock_ms = NOW

    def get_account(self): return copy.deepcopy(self.account)
    def get_asset(self,symbol): return dict(symbol=symbol,status='active',tradable=True,fractionable=True)
    def latest_quote(self,symbol):
        from datetime import datetime,timezone
        return dict(ap=100,bp=99,t=datetime.fromtimestamp((self.clock_ms-1000)/1000,timezone.utc).isoformat())
    def get_clock(self):
        from datetime import datetime, timezone
        return dict(is_open=True, timestamp=datetime.fromtimestamp(self.clock_ms/1000,timezone.utc).isoformat())
    def list_positions(self): return copy.deepcopy(self.positions)
    def list_orders(self, status='open', limit=100, symbols=None):
        rows=list(self.orders.values())
        if status=='open': rows=[r for r in rows if r['status'] in {'new','accepted','partially_filled'}]
        if symbols: rows=[r for r in rows if r['symbol'] in symbols]
        return copy.deepcopy(rows[:limit])
    def get_order(self, oid): return copy.deepcopy(self.orders[oid])
    def get_order_by_client_id(self, cid):
        return next((copy.deepcopy(r) for r in self.orders.values() if r['client_order_id']==cid),None)
    def _request(self, method, path, payload=None):
        assert method=='POST' and path=='/v2/orders'
        self.writes.append(copy.deepcopy(payload))
        if self.fail=='lost_entry' and payload['side']=='buy': raise TimeoutError('lost entry')
        if self.fail=='reject_stop' and payload['type']=='stop': raise AlpacaAPIError(422,'race')
        if self.fail=='lost_stop' and payload['type']=='stop': raise TimeoutError('lost stop')
        oid='order-'+str(len(self.writes)); row={**payload,'id':oid,'filled_qty':'0','status':'new'}
        if payload['side']=='buy':
            row.update(status='filled' if self.fill==payload['qty'] else 'partially_filled',
                       filled_qty=self.fill,filled_avg_price='99',filled_at='2026-10-14T13:30:02Z')
            self.positions=[dict(symbol='NET',side='long',qty=self.fill,avg_entry_price='99',current_price='100')]
        elif payload['type']=='market':
            row.update(status='filled',filled_qty=payload['qty'],filled_avg_price='98',filled_at='2026-10-14T13:31:00Z')
            self.positions=[]
        self.orders[oid]=row
        return copy.deepcopy(row)
    def cancel_order(self, oid):
        self.writes.append({'cancel':oid}); self.orders[oid]['status']='canceled'; return self.get_order(oid)
    def replace_order(self, oid, payload):
        self.writes.append({'replace':oid,**payload})
        old=self.orders[oid];old['status']='replaced';new={**old,**payload,'id':'replace-'+str(len(self.writes)),
             'status':'new','replaces':oid}
        self.orders[new['id']]=new
        return copy.deepcopy(new)


@pytest.fixture
def setup(case,tmp_path):
    r=compiled(case); assert r['status']=='LIVE_INTAKE_PREPARED_ORDERS_OFF'
    module=api(); assert module is not None, 'isolated Dynamic LIVE runtime missing'
    broker=Broker(case[0]['account_id'])
    # The original source book format is reused, but this is a distinct LIVE book.
    book=tmp_path/'live-source.sqlite'
    db=sqlite3.connect(book)
    db.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE intents(entry TEXT, session TEXT,payload TEXT); CREATE TABLE intent_attempts(receipt TEXT,entry TEXT,session TEXT,payload TEXT); CREATE TABLE intent_retirements(receipt TEXT,payload TEXT);')
    db.execute('INSERT INTO meta VALUES (?,?)',('policy',digest(case[0])))
    db.execute('INSERT INTO meta VALUES (?,?)',('runtime_kind','LIVE_DYNAMIC_SEPARATE'))
    db.execute('INSERT INTO intents VALUES (?,?,?)',(r['plan']['slot_entry_order_id'],r['plan']['session'],canonical(r['plan']).decode()))
    db.commit();db.close()
    root=tmp_path/'broker';(root/'runtime').mkdir(parents=True)
    authority=dict(account_id=case[0]['account_id'],endpoint=broker.base_url,
        single_entry_owner_verified=True,old_monthly_entries_off=True,single_manager_verified=True,
        lock_path=str(root/'runtime/shared.lock'),ledger_path=str(root/'runtime/dynamic/protective_exit_hwm.json'))
    paper=dict(status='PAPER_EXECUTION_PASS',live_orders_allowed=False)
    old=dict(account_id=case[0]['account_id'],evidence_kind='BROKER_LIVE',
             entry_order_id=r['scope']['old_terminal_entry_order_id'],qty=r['scope']['old_terminal_qty'],status='TERMINAL_FINAL')
    cost=dict(account_id=case[0]['account_id'],endpoint=broker.base_url,commission_rate='0',
              buy_regulatory_reserve_usd='.01',unresolved_liability_usd='0',source_status='SOURCE_BOUND')
    sources={}
    for name,data in [('authority',authority),('paper',paper),('old_terminal',old),('cost',cost)]:
        p=tmp_path/(name+'.json');p.write_bytes(canonical(data));sources[name]=dict(path=str(p),sha256=__import__('hashlib').sha256(p.read_bytes()).hexdigest())
    # Bind fixture custody to the previously inert compiler inputs.
    r['scope'].update(original_shared_lock_sha256=sources['authority']['sha256'],
                      paper_lifecycle_sha256=sources['paper']['sha256'],old_terminal_sha256=sources['old_terminal']['sha256'],
                      cost_source_sha256=sources['cost']['sha256'])
    from scripts import alpaca_protective_exit_manager as native_manager
    from scripts import equities_alpaca_paper_bridge as native_bridge
    r['scope']['native_manager_source_sha256']=__import__('hashlib').sha256(Path(native_manager.__file__).read_bytes()).hexdigest()
    r['intake_sha256']=digest({k:v for k,v in r.items() if k!='intake_sha256'})
    binding=dict(schema='ALPACA_DYNAMIC_LIVE_RUNTIME_V1',endpoint=broker.base_url,account_id=case[0]['account_id'],
        policy_sha256=digest(case[0]),intake_sha256=r['intake_sha256'],source_book=str(book),
        broker_root=str(root),runtime=str(root/'runtime/dynamic'),lock_path=authority['lock_path'],
        ledger_path=authority['ledger_path'],halt_path=str(root/'runtime/HALT.json'),sources=sources)
    binding['native_bridge_sha256']=__import__('hashlib').sha256(Path(native_bridge.__file__).read_bytes()).hexdigest()
    permit=dict(schema='ALPACA_DYNAMIC_EXACT_OWNER_GO_V1',account_id=broker.account['id'],endpoint=broker.base_url,
        intake_sha256=r['intake_sha256'],binding_sha256=digest(binding),
        owner_go_text='GO ALPACA_DYNAMIC_V1 '+r['intake_sha256'],session=r['plan']['session'])
    p=tmp_path/'owner-go.json';p.write_bytes(canonical(permit))
    return module,broker,r,case[0],binding,p


def run(s,now=NOW+3000,apply=False,**kw):
    m,b,r,p,binding,permit=s
    b.clock_ms=now
    return m.run_once(intake=r,policy=p,binding=binding,client=b,now_ms=now,
                      apply=apply,owner_go_path=permit if apply else None,**kw)


def test_default_orders_off_performs_no_reservation_or_write(setup):
    r=run(setup); assert r['status']=='LIVE_READ_ONLY_READY'
    assert setup[1].writes==[] and not Path(setup[4]['runtime']).exists()


def test_exact_bound_entry_protection_manager_and_duplicate_recovery(setup):
    out=run(setup,apply=True)
    assert out['status']=='LIVE_PROTECTED'
    assert len(setup[1].writes)==2
    state=json.loads(Path(setup[4]['ledger_path']).read_text())['NET']
    assert state['entry_selection_policy']=='ALPACA_DYNAMIC_V1' and state['accepted_stop_floor']==95
    assert run(setup,apply=True)['status']=='LIVE_PROTECTED'
    assert len(setup[1].writes)==2


@pytest.mark.parametrize('which',['account','endpoint','source_book','paper','permit','halt','lock','ledger'])
def test_conflicting_authority_cannot_dispatch(setup,which,tmp_path):
    m,b,r,p,binding,permit=setup
    if which=='account': b.account['id']='foreign'
    if which=='endpoint': b.base_url='https://paper-api.alpaca.markets'
    if which=='source_book': binding['source_book']=str(tmp_path/'absent.sqlite')
    if which=='paper': Path(binding['sources']['paper']['path']).write_text('{}')
    if which=='permit': permit.write_text('{}')
    if which=='halt': Path(binding['halt_path']).write_text('{"halted":true}')
    if which=='lock': binding['lock_path']=str(tmp_path/'different.lock')
    if which=='ledger': binding['ledger_path']=str(tmp_path/'paper/protective_exit_hwm.json')
    out=run(setup,apply=True)
    assert out['status'].startswith('BLOCKED') and b.writes==[]


@pytest.mark.parametrize('failure',['lost_entry','lost_stop'])
def test_uncertain_dispatch_is_never_resent_after_restart(setup,failure):
    setup[1].fail=failure
    first=run(setup,apply=True); count=len(setup[1].writes)
    assert first['status']=='BLOCKED_EXECUTION'
    setup[1].fail=None
    second=run(setup,apply=True)
    assert second['status']=='BLOCKED_EXECUTION' and len(setup[1].writes)==count


def test_partial_entry_cancels_remainder_and_protects_exact_fill(setup):
    setup[1].fill='.2'
    out=run(setup,apply=True)
    assert out['status']=='LIVE_PROTECTED'
    assert float(setup[1].writes[-1]['qty'])==.2
    assert json.loads(Path(setup[4]['ledger_path']).read_text())['NET']['qty']==.2


def test_definitive_stop_422_runs_one_scoped_emergency_exit(setup):
    setup[1].fail='reject_stop'
    out=run(setup,now=NOW+61000,apply=True)
    assert out['status']=='LIVE_EXIT_PENDING_FINALITY'
    assert [w.get('type') for w in setup[1].writes]==['limit','stop','market']
    assert float(setup[1].writes[-1]['qty'])==.5
    run(setup,now=NOW+62000,apply=True)
    assert len(setup[1].writes)==3
    assert Path(setup[4]['halt_path']).exists()


def test_native_ratchet_preserves_dynamic_identity_and_hwm_across_restart(setup):
    assert run(setup,apply=True)['status']=='LIVE_PROTECTED'
    setup[1].positions[0]['current_price']='110'
    out=run(setup,apply=True,maintenance=True)
    assert out['status']=='LIVE_PROTECTED'
    row=json.loads(Path(setup[4]['ledger_path']).read_text())['NET']
    assert row['hwm']==110 and row['accepted_stop_floor']>100
    assert row['entry_selection_policy']=='ALPACA_DYNAMIC_V1'
    count=len(setup[1].writes)
    assert run(setup,apply=True,maintenance=True)['status']=='LIVE_PROTECTED'
    assert len(setup[1].writes)==count


def test_day_expiry_rearms_once_using_frozen_accepted_floor(setup):
    run(setup,apply=True)
    stop=next(o for o in setup[1].orders.values() if o['type']=='stop');stop['status']='expired'
    setup[1].clock_ms=NOW+86400000
    out=run(setup,now=NOW+86400000,apply=True,maintenance=True)
    assert out['status']=='LIVE_PROTECTED'
    assert setup[1].writes[-1]['stop_price']=='95.00'
    count=len(setup[1].writes)
    run(setup,now=NOW+86400000,apply=True,maintenance=True)
    assert len(setup[1].writes)==count


def test_terminal_cash_and_fees_never_inferred_from_flatness(setup):
    run(setup,apply=True)
    stop=next(o for o in setup[1].orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.5',filled_avg_price='95',filled_at='2026-10-14T13:31:00Z')
    setup[1].positions=[]
    out=run(setup,now=NOW+61000,apply=True,maintenance=True)
    assert out['status']=='LIVE_EXIT_PENDING_FINALITY' and out['net_pnl_status']=='NOT_PROVEN'
    assert out['exit_kind']=='NATIVE_STOP' and out['gross_before_fees']=='-2.0'


def test_foreign_symbol_order_blocks_owned_unwind(setup):
    run(setup,apply=True)
    setup[1].orders['foreign']=dict(id='foreign',symbol='NET',side='buy',type='limit',status='new',client_order_id='foreign',qty='.1',filled_qty='0')
    count=len(setup[1].writes)
    out=run(setup,apply=True,maintenance=True,kill=True)
    assert out['status']=='BLOCKED_EXECUTION' and len(setup[1].writes)==count


@pytest.mark.parametrize('fault',['stale_quote','missing_cts','not_tradable','not_fractionable','window_crossed','cash_reserve'])
def test_final_fresh_source_checks_prevent_entry(setup,fault):
    b=setup[1]
    if fault=='stale_quote': b.latest_quote=lambda s:dict(ap=100,bp=99,t='2026-10-14T13:20:00Z')
    if fault=='missing_cts': b.latest_quote=lambda s:dict(ap=100,bp=99)
    if fault=='not_tradable': b.get_asset=lambda s:dict(symbol=s,status='active',tradable=False,fractionable=True)
    if fault=='not_fractionable': b.get_asset=lambda s:dict(symbol=s,status='active',tradable=True,fractionable=False)
    if fault=='window_crossed':
        b.get_clock=lambda:dict(is_open=True,timestamp='2026-10-14T13:35:00Z')
    if fault=='cash_reserve': b.account.update(cash='50',non_marginable_buying_power='50')
    out=run(setup,apply=True)
    assert out['status'].startswith('BLOCKED') and b.writes==[]


def test_stop_cancel_race_recomputes_exact_owned_remainder_before_emergency(setup):
    run(setup,apply=True)
    b=setup[1]; cancel=b.cancel_order
    def race(oid):
        out=cancel(oid);b.orders[oid].update(filled_qty='.2',filled_avg_price='95',filled_at='2026-10-14T13:30:20Z')
        b.positions[0]['qty']='.3'
        return b.get_order(oid)
    b.cancel_order=race
    out=run(setup,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert out['status']=='LIVE_EXIT_PENDING_FINALITY' and out['exit_kind']=='MIXED_NATIVE_STOP_EMERGENCY'
    assert float(b.writes[-1]['qty'])==.3


def test_replace_response_loss_recovers_chain_without_second_patch(setup):
    run(setup,apply=True);b=setup[1];b.positions[0]['current_price']='110'
    replace=b.replace_order
    def lost(oid,payload): replace(oid,payload);raise TimeoutError('response lost')
    b.replace_order=lost
    assert run(setup,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'
    count=len(b.writes);b.replace_order=replace
    assert run(setup,apply=True,maintenance=True)['status']=='LIVE_PROTECTED'
    row=json.loads(Path(setup[4]['ledger_path']).read_text())['NET']
    assert row['accepted_order_id'].startswith('replace-') and row['accepted_stop_floor']>100
    assert len(b.writes)==count


def test_lost_patch_without_broker_evidence_never_repeats_it(setup):
    run(setup,apply=True);b=setup[1];b.positions[0]['current_price']='110'
    def lost(oid,payload):b.writes.append({'replace':oid,**payload});raise TimeoutError('no evidence')
    b.replace_order=lost
    assert run(setup,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'
    count=len(b.writes)
    assert run(setup,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'
    assert len(b.writes)==count


def test_wrong_fresh_asset_symbol_is_not_an_authority_for_target(setup):
    setup[1].get_asset=lambda s:dict(symbol='OTHER',status='active',tradable=True,fractionable=True)
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='FRESH_ASSET_INELIGIBLE'
    assert setup[1].writes==[]


def test_transport_is_off_by_default_and_refuses_account_flatten_or_redirect(setup):
    m,b,r,p,binding,permit=setup
    client=m.DynamicLiveClient('test-key','test-secret')
    with pytest.raises(ValueError):client._request('POST','/v2/orders',r['entry_payload'])
    with pytest.raises(ValueError):client._request('DELETE','/v2/positions/NET')
    with pytest.raises(ValueError):client._request('GET','https://example.com/v2/account')
    with pytest.raises(ValueError):client._request('GET','/v2/account?unapproved=true')
    assert client.base_url==b.base_url


def test_physical_cost_source_must_cover_reserve_before_dispatch(setup):
    m,b,r,p,binding,permit=setup
    src=binding['sources']['cost'];cost=json.loads(Path(src['path']).read_text())
    cost['buy_regulatory_reserve_usd']='1'
    Path(src['path']).write_bytes(canonical(cost))
    src['sha256']=__import__('hashlib').sha256(Path(src['path']).read_bytes()).hexdigest()
    r['scope']['cost_source_sha256']=src['sha256']
    r['intake_sha256']=digest({k:v for k,v in r.items() if k!='intake_sha256'})
    binding['intake_sha256']=r['intake_sha256']
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='COST_RESERVE_SOURCE_CONFLICT'
    assert b.writes==[]


def test_native_source_drift_blocks_before_any_entry(setup):
    setup[4]['native_bridge_sha256']='0'*64
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='NATIVE_MANAGER_SOURCE_CONFLICT'
    assert setup[1].writes==[]


def test_shared_original_lock_busy_never_reaches_adapter(setup):
    import fcntl
    path=Path(setup[4]['lock_path'])
    with path.open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=run(setup,apply=True)
    assert out['status']=='BLOCKED_EXECUTION' and setup[1].writes==[]


def test_future_exit_fill_is_not_terminal_truth(setup):
    run(setup,apply=True)
    stop=next(o for o in setup[1].orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.5',filled_avg_price='95',filled_at='2026-10-15T13:31:00Z')
    setup[1].positions=[]
    assert run(setup,now=NOW+61000,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'


def test_dispatch_past_reserved_window_cannot_reappear_on_next_session(setup):
    assert run(setup,now=NOW+300001,apply=True)['status']=='BLOCKED_DATA'
    assert run(setup,now=NOW+86400000,apply=True)['status']=='BLOCKED_DATA'
    assert setup[1].writes==[]


def test_definitive_rearm_rejection_unwinds_without_lowering_floor(setup):
    run(setup,apply=True)
    stop=next(o for o in setup[1].orders.values() if o['type']=='stop');stop['status']='expired'
    setup[1].fail='reject_stop'
    out=run(setup,now=NOW+86400000,apply=True,maintenance=True)
    assert out['status']=='LIVE_EXIT_PENDING_FINALITY'
    assert setup[1].writes[-2]['stop_price']=='95.00' and setup[1].writes[-1]['type']=='market'


def test_uncertain_rearm_never_resends_or_sells_while_stop_unknown(setup):
    run(setup,apply=True)
    stop=next(o for o in setup[1].orders.values() if o['type']=='stop');stop['status']='expired'
    setup[1].fail='lost_stop'
    assert run(setup,now=NOW+86400000,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'
    count=len(setup[1].writes);setup[1].fail=None
    assert run(setup,now=NOW+86400000,apply=True,maintenance=True)['status']=='BLOCKED_EXECUTION'
    assert len(setup[1].writes)==count


def test_kill_does_not_submit_sell_while_protection_dispatch_is_unknown(setup):
    setup[1].fail='lost_stop';run(setup,apply=True)
    count=len(setup[1].writes)
    assert run(setup,apply=True,maintenance=True,kill=True)['status']=='BLOCKED_EXECUTION'
    assert len(setup[1].writes)==count


def test_read_only_recovery_reports_existing_intent_instead_of_entry_ready(setup):
    run(setup,apply=True)
    out=run(setup)
    assert out['status']=='LIVE_READ_ONLY_RECOVERY_REQUIRED'
    assert len(setup[1].writes)==2


def test_cli_profile_uses_original_live_lock_and_no_environment_fallback(setup,tmp_path,monkeypatch):
    try:m=importlib.import_module('scripts.run_alpaca_dynamic_live_v1')
    except ImportError:m=None
    assert m is not None,'LIVE runtime CLI missing'
    profile=Path(setup[4]['broker_root'])/'configs/live.env';profile.parent.mkdir()
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=test\nALPACA_API_SECRET_KEY=test-secret\nALPACA_BRIDGE_LOCK_PATH='+setup[4]['lock_path']+'\n')
    monkeypatch.setenv('ALPACA_BASE_URL','https://paper-api.alpaca.markets')
    client=m.load_client(profile,setup[4],apply=False)
    assert client.base_url=='https://api.alpaca.markets' and client.writes_enabled is False
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\n')
    with pytest.raises(ValueError):m.load_client(profile,setup[4],apply=True)


def test_cli_rejects_profile_lock_alias_even_when_owner_boolean_is_true(setup,tmp_path):
    try:m=importlib.import_module('scripts.run_alpaca_dynamic_live_v1')
    except ImportError:m=None
    assert m is not None,'LIVE runtime CLI missing'
    profile=Path(setup[4]['broker_root'])/'configs/live.env';profile.parent.mkdir()
    profile.write_text('ALPACA_BASE_URL=https://api.alpaca.markets\nALPACA_API_KEY_ID=test\nALPACA_API_SECRET_KEY=secret\nALPACA_BRIDGE_LOCK_PATH='+str(tmp_path/'else.lock')+'\n')
    with pytest.raises(ValueError):m.load_client(profile,setup[4],apply=True)


def test_partial_native_stop_keeps_exact_remaining_protection(setup):
    run(setup,apply=True)
    b=setup[1];stop=next(o for o in b.orders.values() if o['type']=='stop')
    stop.update(status='partially_filled',filled_qty='.2',filled_avg_price='95',filled_at='2026-10-14T13:30:20Z')
    b.positions[0]['qty']='.3'
    out=run(setup,now=NOW+61000,apply=True,maintenance=True)
    assert out['status']=='LIVE_PARTIAL_STOP_PROTECTED' and out['remaining_qty']=='0.3'
    assert len(b.writes)==2


def test_rejected_initial_stop_crash_recovery_retains_one_exit(setup,monkeypatch):
    setup[1].fail='reject_stop'
    # Stop rejection was committed but the first emergency helper never ran.
    unwind=setup[0].unwind
    monkeypatch.setattr(setup[0],'unwind',lambda *args:(_ for _ in ()).throw(OSError('process crash')))
    assert run(setup,now=NOW+61000,apply=True)['status']=='BLOCKED_EXECUTION'
    monkeypatch.setattr(setup[0],'unwind',unwind)
    assert run(setup,now=NOW+62000,apply=True,maintenance=True)['status']=='LIVE_EXIT_PENDING_FINALITY'
    assert [w.get('type') for w in setup[1].writes]==['limit','stop','market']


def test_symlinked_source_book_cannot_adopt_paper_or_foreign_plan(setup,tmp_path):
    original=setup[4]['source_book'];alias=tmp_path/'alias.sqlite';alias.symlink_to(original)
    setup[4]['source_book']=str(alias)
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='PATH_IDENTITY'
    assert setup[1].writes==[]


def test_crash_after_reservation_cannot_start_buy_later_outside_window(setup,monkeypatch):
    initial=setup[0].initial
    def crash(*args,**kwargs):raise OSError('crash before dispatch boundary')
    monkeypatch.setattr(setup[0],'initial',crash)
    assert run(setup,apply=True)['status']=='BLOCKED_EXECUTION'
    monkeypatch.setattr(setup[0],'initial',initial)
    assert run(setup,now=NOW+86400000,apply=True)['status']=='BLOCKED_EXECUTION'
    assert setup[1].writes==[]


def test_accepted_stop_response_loss_can_recover_pending_native_ledger(setup):
    b=setup[1];post=b._request
    def lost(method,path,payload=None):
        row=post(method,path,payload)
        if payload['type']=='stop':raise TimeoutError('accepted then lost')
        return row
    b._request=lost
    assert run(setup,apply=True)['status']=='BLOCKED_EXECUTION'
    b._request=post
    assert run(setup,apply=True,maintenance=True)['status']=='LIVE_PROTECTED'
    assert len(b.writes)==2


def test_no_fill_terminal_cancellation_cannot_create_protection_or_second_buy(setup):
    b=setup[1];b.fill='0'
    # A limit can remain new, be canceled, then have no fill at all.
    out=run(setup,apply=True)
    assert out['status']=='LIVE_NO_FILL_TERMINAL'
    assert run(setup,apply=True)['status']=='LIVE_NO_FILL_TERMINAL'
    assert [w.get('type') for w in b.writes]==['limit',None]


def test_path_with_parent_traversal_cannot_escape_original_runtime(setup):
    root=setup[4]['broker_root'];setup[4]['runtime']=root+'/runtime/../outside'
    setup[4]['ledger_path']=root+'/runtime/../outside/protective_exit_hwm.json'
    assert run(setup,apply=True)['status']=='BLOCKED_DATA'
    assert setup[1].writes==[]


def test_native_stop_filled_before_initial_readback_reconciles_without_fake_protection(setup):
    b=setup[1];post=b._request
    def fast(method,path,payload=None):
        row=post(method,path,payload)
        if payload['type']=='stop':
            b.orders[row['id']].update(status='filled',filled_qty='.5',filled_avg_price='95',filled_at='2026-10-14T13:30:03Z')
            b.positions=[]
        return row
    b._request=fast
    out=run(setup,apply=True)
    assert out['status']=='LIVE_EXIT_PENDING_FINALITY' and out['initial_full_protection_proven'] is False
    assert out['exit_kind']=='NATIVE_STOP' and len(b.writes)==2
    assert run(setup,apply=True,maintenance=True)['status']=='LIVE_EXIT_PENDING_FINALITY'
    assert len(b.writes)==2


def test_delayed_stop_ack_with_partial_exit_retains_exact_native_remaining_floor(setup):
    b=setup[1];post=b._request
    def partial(method,path,payload=None):
        row=post(method,path,payload)
        if payload['type']=='stop':
            b.orders[row['id']].update(status='partially_filled',filled_qty='.2',filled_avg_price='95',filled_at='2026-10-14T13:30:03Z')
            b.positions[0]['qty']='.3'
        return row
    b._request=partial
    out=run(setup,apply=True)
    assert out['status']=='LIVE_PARTIAL_STOP_PROTECTED' and out['initial_full_protection_proven'] is False
    assert out['remaining_qty']=='0.3' and len(b.writes)==2
    row=json.loads(Path(setup[4]['ledger_path']).read_text())['NET']
    assert row['qty']==.3 and row['accepted_stop_floor']==95
    assert run(setup,apply=True,maintenance=True)['status']=='LIVE_PARTIAL_STOP_PROTECTED'


@pytest.mark.parametrize('field',['qty','limit_price','stop_cid'])
def test_self_consistent_changed_intake_cannot_override_exact_planner_payload(setup,field):
    m,b,r,p,binding,go=setup
    if field=='stop_cid':r['stop_client_order_id']='dyf-'+'9'*32
    else:r['entry_payload'][field]='5' if field=='qty' else '150'
    r['intake_sha256']=digest({k:v for k,v in r.items() if k!='intake_sha256'})
    binding['intake_sha256']=r['intake_sha256']
    approval=m.read_json(str(go));approval.update(intake_sha256=r['intake_sha256'],binding_sha256=digest(binding),
        owner_go_text='GO ALPACA_DYNAMIC_V1 '+r['intake_sha256']);go.write_bytes(canonical(approval))
    b.fill='5'
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='DERIVED_LIVE_PAYLOAD_CONFLICT'
    assert b.writes==[]


def test_unknown_patch_blocks_kill_until_replacement_outcome_is_proven(setup):
    run(setup,apply=True);b=setup[1];b.positions[0]['current_price']='110'
    def lost(oid,payload):b.writes.append({'replace':oid,**payload});raise TimeoutError('unknown patch')
    b.replace_order=lost
    run(setup,apply=True,maintenance=True)
    count=len(b.writes)
    out=run(setup,apply=True,maintenance=True,kill=True)
    assert out['status']=='BLOCKED_EXECUTION' and out['reason']=='UNKNOWN_REPLACEMENT_OWNER_ACTION_REQUIRED'
    assert len(b.writes)==count


def test_cost_finality_requires_exact_exit_sources_and_cash_reconciliation(setup,tmp_path):
    run(setup,apply=True);b=setup[1]
    stop=next(o for o in b.orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.5',filled_avg_price='95',filled_at='2026-10-14T13:31:00Z');b.positions=[]
    out=run(setup,now=NOW+61000,apply=True,maintenance=True)
    source=dict(schema='ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1',account_id=b.account['id'],
        intake_sha256=setup[2]['intake_sha256'],exit_orders_sha256=digest(out['exit_orders']),
        gross_before_fees='-2.0',commission_usd='0',regulatory_fees_usd='.01',
        unresolved_liability_usd='0',closure_status='ACCOUNT_DAY_FEES_RECONCILED',
        cash_before_entry='100',cash_after_exit='97.99',other_cash_net_usd='0',
        observed_ms=NOW+62000,coverage_end_ms=NOW+61000)
    raw=tmp_path/'activities.json';raw.write_bytes(canonical({'fixture':'sourced account-day fee reconciliation'}))
    source['source_files']=[dict(path=str(raw),sha256=__import__('hashlib').sha256(raw.read_bytes()).hexdigest())]
    source['source_manifest_sha256']=digest(source['source_files'])
    cost=tmp_path/'cost-finality.json';cost.write_bytes(canonical(source))
    b.account['cash']='97.99'
    finalized=run(setup,now=NOW+62000,apply=True,maintenance=True,cost_finality_path=str(cost))
    assert finalized['status']=='LIVE_TERMINAL_COST_FINALITY' and finalized['net_usd_exact']=='-2.01'
    assert len(b.writes)==2
    restored=run(setup,now=NOW+63000,apply=True,maintenance=True)
    assert restored['status']=='LIVE_TERMINAL_COST_FINALITY' and restored['net_usd_exact']=='-2.01'
    source['regulatory_fees_usd']='0';cost.write_bytes(canonical(source))
    assert run(setup,now=NOW+63000,apply=True,maintenance=True,cost_finality_path=str(cost))['status']=='BLOCKED_EXECUTION'


def test_pending_fee_or_wrong_exit_pin_cannot_finalize_flat_account(setup,tmp_path):
    run(setup,apply=True);b=setup[1]
    stop=next(o for o in b.orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.5',filled_avg_price='95',filled_at='2026-10-14T13:31:00Z');b.positions=[]
    cost=tmp_path/'cost-finality.json';cost.write_text('{"closure_status":"PENDING_FEES"}')
    assert run(setup,now=NOW+61000,apply=True,maintenance=True,cost_finality_path=str(cost))['status']=='BLOCKED_EXECUTION'
    assert len(b.writes)==2


def test_stale_native_owner_blocks_before_buy_not_after_fill(setup):
    ledger=Path(setup[4]['ledger_path']);ledger.parent.mkdir(parents=True)
    ledger.write_bytes(canonical({'NET':{'entry_order_id':'old-owner'}}))
    before=ledger.read_bytes()
    out=run(setup,apply=True)
    assert out['status']=='BLOCKED_DATA' and out['reason']=='PRE_ENTRY_NATIVE_OWNER_CONFLICT'
    assert setup[1].writes==[] and ledger.read_bytes()==before
