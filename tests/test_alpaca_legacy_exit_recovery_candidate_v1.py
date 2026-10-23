"""Isolated candidate only; never the deployed actor or approved owner packet."""
import copy,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
import pytest
from decimal import Decimal
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,run
from tests.test_alpaca_dynamic_live_intake_v1 import case,NOW
from scripts.equities_alpaca_paper_bridge import AlpacaAPIError

@pytest.fixture(params=['local_wrapper','exact_deployed_overlay'])
def candidate(setup,monkeypatch,tmp_path,request):
    from research_lab.alpaca_legacy_exit_recovery_v1 import guarded_unwind
    if request.param=='exact_deployed_overlay':
        from research_lab.alpaca_legacy_exit_recovery_v1 import build_overlay_candidate
        source=(Path(__file__).parent/'fixtures/net_runtime_overlay_20261016.txt').read_bytes()
        path=tmp_path/'candidate.py';path.write_bytes(build_overlay_candidate(source))
        spec=importlib.util.spec_from_file_location('net_recovery_candidate',path)
        rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
        setup=(rt,*setup[1:])
    else:
        rt=setup[0];original=rt.unwind
        monkeypatch.setattr(rt,'unwind',lambda db,item,client,record,binding,**kw:
            guarded_unwind(rt,original,db,item,client,record,binding,**kw))
    assert run(setup,apply=True)['status']=='LIVE_PROTECTED'
    return setup

def faulted(s,kind):
    b=s[1];send=b._request;markets=[]
    def wire(method,path,payload=None):
        if payload and payload['type']=='market':
            markets.append(copy.deepcopy(payload))
            if kind in ('unknown','ambiguous422'):
                if kind=='unknown':raise TimeoutError('no visible acceptance')
                raise AlpacaAPIError(422,'ambiguous duplicate-client-id or rejection')
            row=send(method,path,payload)
            if kind=='lost_filled':raise TimeoutError('filled, lost reply')
            q='0' if kind=='terminal_rejected' else '.2'
            b.orders[row['id']].update(status='rejected' if kind=='terminal_rejected' else 'partially_filled' if kind=='active_partial' else 'canceled',filled_qty=q)
            b.positions=[dict(symbol='NET',side='long',qty='.5' if q=='0' else '.3',avg_entry_price='99',current_price='100')]
            return b.get_order(row['id'])
        return send(method,path,payload)
    b._request=wire;return markets

@pytest.mark.parametrize('kind',['terminal_rejected','terminal_partial'])
def test_terminal_owned_exit_restores_stop_and_future_kill_never_cancels_it(candidate,kind):
    s=candidate;markets=faulted(s,kind)
    first=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert first['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    b=s[1];qty='.5' if kind=='terminal_rejected' else '.3'
    stop=[o for o in b.list_orders() if o['type']=='stop'];assert len(stop)==1 and Decimal(stop[0]['qty'])==Decimal(qty)
    ledger=json.loads(Path(s[4]['ledger_path']).read_bytes())['NET'];assert ledger['accepted_order_id']==stop[0]['id'] and ledger['accepted_stop_floor']>=95
    before=copy.deepcopy(b.writes)
    for kill in (False,True,False):
        assert run(s,now=NOW+62000,apply=True,maintenance=True,kill=kill)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    assert b.writes==before and len(markets)==1

@pytest.mark.parametrize('kind',['unknown','ambiguous422','active_partial'])
def test_active_unknown_or_ambiguous_422_never_restores_competing_stop_or_resends(candidate,kind):
    s=candidate;markets=faulted(s,kind)
    r=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert r['status']=='BLOCKED_EXECUTION' and r['owner_action_required'] is True
    assert r['protection_present'] is False
    for kill in (False,True):
        r=run(s,now=NOW+62000,apply=True,maintenance=True,kill=kill)
        assert r['status']=='BLOCKED_EXECUTION' and r['owner_action_required'] is True
    assert len(markets)==1
    if kind!='active_partial':assert not s[1].list_orders(status='open')
    assert len([w for w in s[1].writes if w.get('type')=='stop'])==1 # original stop only

def test_filled_exit_reply_loss_reconciles_flat_without_restoration(candidate):
    s=candidate;markets=faulted(s,'lost_filled')
    r=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert r['status']=='LIVE_EXIT_PENDING_FINALITY' and not s[1].positions
    assert len(markets)==1 and len([w for w in s[1].writes if w.get('type')=='stop'])==1

@pytest.mark.parametrize('accepted',['yes','unknown'])
def test_recovery_stop_response_loss_never_causes_second_stop(candidate,accepted):
    s=candidate;faulted(s,'terminal_partial');b=s[1];send=b._request
    def loss(method,path,payload=None):
        if payload and payload['type']=='stop':
            if accepted=='yes':send(method,path,payload)
            raise TimeoutError('recovery stop response lost')
        return send(method,path,payload)
    b._request=loss
    r=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    before=copy.deepcopy(b.writes)
    r2=run(s,now=NOW+62000,apply=True,maintenance=True,kill=True)
    assert b.writes==before
    assert r2['status']==('LIVE_EXIT_RECOVERY_PROTECTED' if accepted=='yes' else 'BLOCKED_EXECUTION')
    if accepted=='unknown':
        next_day=run(s,now=NOW+86400000+61000,apply=True,maintenance=True,kill=True)
        assert next_day['status']=='BLOCKED_EXECUTION' and b.writes==before

def test_candidate_builder_refuses_any_unreviewed_source():
    from research_lab.alpaca_legacy_exit_recovery_v1 import build_overlay_candidate
    with pytest.raises(ValueError,match='BASE_SOURCE'):build_overlay_candidate(b'def unwind(): pass\n')

def test_recovery_stop_filled_before_ack_is_terminal_not_another_rearm(candidate):
    s=candidate;faulted(s,'terminal_partial');b=s[1];send=b._request
    def instant(method,path,payload=None):
        row=send(method,path,payload)
        if payload and payload['type']=='stop':
            b.orders[row['id']].update(status='filled',filled_qty=payload['qty'],filled_avg_price=payload['stop_price'],filled_at='2026-10-14T13:31:00Z')
            b.positions=[]
        return b.get_order(row['id'])
    b._request=instant
    r=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert r['status']=='LIVE_EXIT_PENDING_FINALITY' and not b.positions
    assert len([w for w in b.writes if w.get('type')=='stop'])==2

def test_restoration_does_not_lower_a_more_recent_ledger_floor(candidate):
    s=candidate;faulted(s,'terminal_partial');b=s[1];send=b._request;p=Path(s[4]['ledger_path'])
    def updated(method,path,payload=None):
        row=send(method,path,payload)
        if payload and payload['type']=='market':
            state=json.loads(p.read_bytes());state['NET']['accepted_stop_floor']=100;p.write_text(json.dumps(state))
        return row
    b._request=updated
    r=run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)
    assert r['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    assert Decimal(b.list_orders()[0]['stop_price'])>=100
    assert json.loads(p.read_bytes())['NET']['accepted_stop_floor']>=100

@pytest.mark.parametrize('partial',['0','.2'])
def test_recovery_day_expiry_rearms_proven_remainder_once_next_session(candidate,partial):
    s=candidate;markets=faulted(s,'terminal_rejected');b=s[1]
    assert run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    stop=b.list_orders()[0]
    b.orders[stop['id']].update(status='expired',filled_qty=partial)
    if partial!='0':
        b.orders[stop['id']].update(filled_avg_price=stop['stop_price'],filled_at='2026-10-14T13:31:00Z')
        b.positions[0]['qty']='.3'
    r=run(s,now=NOW+86400000+61000,apply=True,maintenance=True)
    assert r['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    fresh=b.list_orders();assert len(fresh)==1 and fresh[0]['id']!=stop['id']
    assert Decimal(fresh[0]['qty'])==Decimal('.5')-Decimal(partial)
    writes=copy.deepcopy(b.writes)
    assert run(s,now=NOW+86400000+62000,apply=True,maintenance=True,kill=True)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    assert b.writes==writes and len(markets)==1

def test_new_interpreter_keeps_hold_and_never_cancels_recovered_stop(candidate,tmp_path):
    s=candidate;faulted(s,'terminal_partial');b=s[1]
    assert run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    context=tmp_path/'restart.json';context.write_text(json.dumps(dict(
        intake=s[2],policy=s[3],binding=s[4],go=str(s[5]),module=s[0].__file__,
        broker=dict(account=b.account,orders=b.orders,positions=b.positions),now_ms=NOW+62000)))
    code='''import json,sys,importlib.util
from tests.test_alpaca_dynamic_live_runtime_v1 import Broker
from research_lab.alpaca_legacy_exit_recovery_v1 import guarded_unwind
x=json.load(open(sys.argv[1]));spec=importlib.util.spec_from_file_location('restarted_net',x['module'])
rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
if not hasattr(rt,'_unwind_before_exit_recovery_v1'):
 original=rt.unwind
 rt.unwind=lambda db,item,client,record,binding,**kw:guarded_unwind(rt,original,db,item,client,record,binding,**kw)
b=Broker(x['broker']['account']['id'])
for key,value in x['broker'].items():setattr(b,key,value)
b.clock_ms=x['now_ms']
out=rt.run_once(intake=x['intake'],policy=x['policy'],binding=x['binding'],client=b,
 now_ms=x['now_ms'],apply=True,owner_go_path=x['go'],maintenance=True,kill=True)
print(json.dumps(dict(result=out,writes=b.writes)))
'''
    out=json.loads(subprocess.check_output([sys.executable,'-B','-c',code,str(context)],text=True))
    assert out['result']['status']=='LIVE_EXIT_RECOVERY_PROTECTED' and out['writes']==[]

def test_slow_prior_stop_readback_cannot_dispatch_from_expired_snapshot(candidate,monkeypatch):
    s=candidate;faulted(s,'terminal_rejected');b=s[1]
    assert run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    stop=b.list_orders()[0];b.orders[stop['id']]['status']='expired'
    tick=[1000.0];monkeypatch.setattr(s[0].time,'monotonic',lambda:tick[0])
    get=b.get_order
    def slow(oid):
        if oid==stop['id']:tick[0]+=6
        return get(oid)
    b.get_order=slow;writes=copy.deepcopy(b.writes)
    r=run(s,now=NOW+86400000+61000,apply=True,maintenance=True)
    assert r['status']=='BLOCKED_EXECUTION' and b.writes==writes

def test_slow_final_cid_lookup_cannot_reach_stop_post(candidate,monkeypatch):
    s=candidate;faulted(s,'terminal_rejected');b=s[1]
    assert run(s,now=NOW+61000,apply=True,maintenance=True,kill=True)['status']=='LIVE_EXIT_RECOVERY_PROTECTED'
    stop=b.list_orders()[0];b.orders[stop['id']]['status']='expired'
    tick=[1000.0];monkeypatch.setattr(s[0].time,'monotonic',lambda:tick[0])
    lookup=b.get_order_by_client_id
    def slow(cid):
        if cid.startswith('dyr-') and cid!=stop['client_order_id']:tick[0]+=6
        return lookup(cid)
    b.get_order_by_client_id=slow;writes=copy.deepcopy(b.writes)
    r=run(s,now=NOW+86400000+61000,apply=True,maintenance=True)
    assert r['status']=='BLOCKED_EXECUTION' and b.writes==writes

def test_personal_helper_candidate_bootstraps_without_missing_kity_module(tmp_path):
    from research_lab.alpaca_legacy_exit_recovery_v1 import build_helper_candidate
    source=Path('scripts/alpaca_legacy_net_early_exit_v1.py').read_bytes()
    generated=build_helper_candidate(source)
    assert b'from research_lab.kity_oct15_deadline_v1 import' not in generated
    script=tmp_path/'personal-exit.py';script.write_bytes(generated)
    out=json.loads(subprocess.check_output([sys.executable,'-I','-B',str(script)],text=True,cwd=tmp_path))
    assert out==dict(status='OFFLINE_NO_AUTHORITY',broker_writes=0)
    spec=importlib.util.spec_from_file_location('personal_candidate',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    target=tmp_path/'immutable.json';module.publish_once(target,b'first\n')
    with pytest.raises(FileExistsError):module.publish_once(target,b'replacement\n')
    assert target.read_bytes()==b'first\n'
    assert target.stat().st_nlink==1 and target.stat().st_mode&0o777==0o600

def test_personal_helper_candidate_preserves_financial_code_and_requires_exact_base():
    import ast
    from research_lab.alpaca_legacy_exit_recovery_v1 import build_helper_candidate
    source=Path('scripts/alpaca_legacy_net_early_exit_v1.py').read_bytes()
    before=ast.parse(source);after=ast.parse(build_helper_candidate(source))
    for tree in (before,after):
        for node in ast.walk(tree):
            if isinstance(node,ast.FunctionDef):
                node.body=[n for n in node.body if not(isinstance(n,ast.ImportFrom) and n.module=='research_lab.kity_oct15_deadline_v1')]
    funcs=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    assert funcs(before).items()<=funcs(after).items()
    with pytest.raises(ValueError,match='HELPER_BASE_SOURCE_PIN'):build_helper_candidate(source+b'\n')
