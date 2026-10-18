import importlib
import json
import pytest
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case


def test_entry_cannot_start_without_personal_arm_or_pinned_spec(tmp_path,capsys):
    p=tmp_path/'spec.json';p.write_text('{}')
    try:module=importlib.import_module('scripts.alpaca_next_entry_control_v1')
    except ImportError:module=None
    assert module is not None,'next-entry control missing'
    assert module.main(['--spec',str(p),'--spec-sha256','0'*64,'--entry'])==2
    out=json.loads(capsys.readouterr().out)
    assert out['status']=='BLOCKED_DATA' and out['broker_writes']==0


def test_complete_controller_uses_existing_live_book_and_never_rebuys_after_restart(setup,tmp_path,monkeypatch,capsys):
    """Only broker and wall clock are external substitutes; all controls are real."""
    import hashlib,copy,sqlite3
    from pathlib import Path
    from research_lab.alpaca_dynamic_v1 import canonical,digest,DynamicBook
    from research_lab.alpaca_dynamic_live_lineage_v1 import reconcile_live_lineage
    from tests.test_alpaca_next_entry_scope_v1 import fixture
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json
    from research_lab.alpaca_open_dispatch_v2 import STATIC_CHECKS
    scope,preview,policy,broker,now=fixture(setup,tmp_path)
    binding=preview['binding'];book=DynamicBook(binding['source_book'],policy)
    with book.db() as db:
        db.execute('DELETE FROM intents WHERE session=?',('2026-10-19',))
    old_binding=read_json(binding['portfolio_bindings'][0]['path'])
    original=copy.deepcopy(broker.positions)
    reconcile_live_lineage(old_binding,policy,broker,now_ms=now,apply=True)
    with book.db() as db:old_plan=json.loads(db.execute('SELECT payload FROM intents').fetchone()[0])
    ranking=dict(policy_sha256=digest(policy),window_ms=1792416600000,signal_session='2026-10-16',
        input_sha256='a'*64,source_available_ms=1792282200000,gate_ok=True,
        picks=[dict(symbol='SHOP',signal_close=100,stop_price=96,atr20=2,rawscore=.5)],
        blocked_symbols=['AMD','CRWD','META','NET'],selector_source_hashes=policy['selector_source_hashes'])
    slot=next(s for s in policy['inherited_slots'] if s['symbol']=='META')
    scope.update(ranking_sha256=digest(ranking),max_notional_usd=slot['notional_cap'],max_risk_usd=slot['risk_cap'])
    scope['scope_sha256']=digest({k:v for k,v in scope.items() if k!='scope_sha256'})
    template=dict(account_id=policy['account_id'],observed_ms=now,source_sha256='a'*64,
        single_owner_verified=True,cash_finality_verified=True,cash_usd='100',liability_reserve_usd='.01',fee_rate='0',
        positions=original,open_orders=[],blocked_symbols=['AMD','CRWD','META','NET'],
        exits=[dict(entry_order_id=slot['entry_order_id'],orders=[dict(id='meta-exit',symbol='META',side='sell',status='filled',filled_qty=slot['qty'],filled_avg_price='700',filled_ms=1792180000000)])],
        gates={'SHOP':dict(earnings=True,concentration=True,symbol=True,protection=True)},quotes={'SHOP':dict(risk_distance='4')})
    protocol=json.loads((Path(__file__).parents[1]/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_bytes())
    protocol['fractional_protocol']['requires_fresh_asset']['symbol']='SHOP'
    # External authenticated broker boundary; no strategy or controller is mocked.
    raw_request=broker._request
    def external_request(method,path,payload=None):
        if method=='GET' and path=='/v2/assets/SHOP':return broker.get_asset('SHOP')
        if method=='POST' and payload['side']=='buy':broker.fill=payload['qty']
        result=raw_request(method,path,payload)
        if method=='POST' and payload['side']=='buy':
            from datetime import datetime,timezone
            result['filled_at']=datetime.fromtimestamp(wall[0]/1000,timezone.utc).isoformat()
            broker.orders[result['id']]['filled_at']=result['filled_at']
        return result
    broker._request=external_request;broker.account.update(status='ACTIVE',pending_reg_taf_fees='0',accrued_fees='0')
    import scripts.run_alpaca_dynamic_live_v1 as transport
    monkeypatch.setattr(transport,'load_client',lambda *a,**kw:broker)
    module=importlib.import_module('scripts.alpaca_next_entry_control_v1')
    wall=[1792416600000-1000000]
    monkeypatch.setattr(module.time,'time_ns',lambda:wall[0]*1000000)
    spec=dict(schema='ALPACA_NEXT_SESSION_CONTROL_V1',static_files=[],live_profile='/unused-test-profile',
        dispatch_state=str(tmp_path/'next-dispatch'),session_dir=str(tmp_path/'session'),personal_arm=str(tmp_path/'arm.json'),
        resolved_source_plans=[dict(plan_sha256=digest(old_plan),child_entry_order_id=old_plan and 'order-1',live_intake_sha256=old_binding['intake_sha256'])],
        checks={k:dict(status='VERIFIED',source_sha256='a'*64) for k in STATIC_CHECKS})
    spec['checks']['reservation_handoff']['status']='CLEAR_OR_REVIEWED'
    for key,value in [('policy',policy),('binding',binding),('scope',scope),('ranking',ranking),('template',template),('protocol',protocol),('calendar',dict(earnings_dates=['2026-11-03']))]:
        p=tmp_path/('next-'+key+'.json');p.write_bytes(canonical(value));spec[key]=str(p);spec['static_files'].append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    selected=tmp_path/'selected-unit';selected.write_text('one existing manager')
    spec['selected_unit_pins']=[dict(path=str(selected),sha256=hashlib.sha256(selected.read_bytes()).hexdigest())]
    path=tmp_path/'next-spec.json';path.write_bytes(canonical(spec));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    def call(mode):
        result=module.main(['--spec',str(path),'--spec-sha256',pin,mode]);return result,json.loads(capsys.readouterr().out)
    assert call('--prepare')[1]['status']=='STATIC_PREPARED'
    assert call('--ready')[1]['status']=='READY_TO_DISPATCH'
    before=len(broker.writes);wall[0]=now
    absent=call('--entry')[1]
    assert absent['status']=='BLOCKED_DATA' and len(broker.writes)==before
    # Simulated human arming fixture, not an actual owner permission.
    from research_lab.alpaca_next_entry_scope_v1 import APPROVAL_SHA256
    Path(spec['personal_arm']).write_bytes(canonical(dict(schema='ALPACA_DYNAMIC_PERSONAL_SESSION_ARM_V1',scope_sha256=scope['scope_sha256'],
        owner_approval_text_sha256=APPROVAL_SHA256,personal_owner_start=True,session=scope['session'],attempts_allowed=1,auto_repeat=False)))
    selected.write_text('foreign manager')
    assert call('--entry')[1]['reason']=='NEXT_SELECTED_UNIT_DRIFT'
    assert len(broker.writes)==before
    selected.write_text('one existing manager')
    result,out=call('--entry')
    assert result==0 and out['status']=='OPENING_PATH_COMPLETED',out
    assert out['execution']['status']=='LIVE_PROTECTED',out
    assert len(broker.writes)==before+2
    result,out=call('--entry')
    assert len(broker.writes)==before+2
    # Original NET and new SHOP are both owned after a fresh maintenance pass.
    result,out=call('--maintenance')
    assert result==0 and out['status']=='LIVE_PROTECTED',out
    assert len(broker.writes)==before+2

    old_module,_,old_intake,_,_,old_permit=setup
    old_out=old_module.run_once(intake=old_intake,policy=policy,binding=old_binding,client=broker,now_ms=now,apply=True,owner_go_path=old_permit,maintenance=True)
    assert old_out['status']=='LIVE_PROTECTED',old_out
    assert len(broker.writes)==before+2
