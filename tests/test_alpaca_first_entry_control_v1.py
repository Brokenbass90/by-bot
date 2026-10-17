import importlib,json,hashlib,subprocess,sys,os,sqlite3,copy
from pathlib import Path
import pytest
from tests.test_alpaca_dynamic_first_intent_v1 import approved,setup,case
from research_lab.alpaca_dynamic_v1 import canonical,digest

@pytest.fixture
def control_spec(approved,tmp_path):
    s,ip,gp,intent=approved;_,broker,intake,policy,binding,_=s;root=Path(__file__).resolve().parents[1]
    paths={}
    for name,value in [('policy',policy),('binding',binding)]:
        p=tmp_path/(name+'.json');p.write_bytes(canonical(value));paths[name]=str(p)
    spec={**paths,'app_root':str(root),'intent':str(ip),'intent_sha256':intent['intent_sha256'],
        'runtime_overlay':str(root/'research_lab/alpaca_dynamic_live_runtime_v1.py'),
        'publisher_module':str(root/'research_lab/alpaca_open_dispatch_v2.py'),
        'assembly_module':str(root/'research_lab/alpaca_first_entry_assembly_v1.py'),
        'static_files':[{'path':str(ip),'sha256':hashlib.sha256(ip.read_bytes()).hexdigest()}],
        'dispatch_state':str(tmp_path/'dispatch'),'session_dir':str(tmp_path/'session'),
        'checks':{},'live_profile':str(tmp_path/'not-opened.env')}
    p=tmp_path/'spec.json';p.write_bytes(canonical(spec));return p,s,gp

# Break caught: even a correct external GO must not skip the original HALT gate.
def test_exact_first_go_reaches_halt_gate_without_source_or_broker_write(control_spec,capsys):
    try:m=importlib.import_module('scripts.alpaca_first_entry_control_v1')
    except ImportError:m=None
    assert m is not None,'one-session control wiring missing'
    sp,s,gp=control_spec;Path(s[4]['halt_path']).write_text('{}')
    assert m.main(['--spec',str(sp),'--entry','--owner-go',str(gp)])==2
    r=json.loads(capsys.readouterr().out);assert r['reason']=='ENTRY_HALTED',r
    assert s[1].writes==[];assert not Path(s[4]['runtime']).exists()


def test_no_go_cannot_create_dispatch_state_or_source_reservation(control_spec,capsys):
    m=importlib.import_module('scripts.alpaca_first_entry_control_v1');sp,s,_=control_spec
    before=Path(s[4]['source_book']).read_bytes()
    assert m.main(['--spec',str(sp),'--entry'])==2
    r=json.loads(capsys.readouterr().out);assert r['reason']=='SEPARATE_EXACT_OWNER_GO_REQUIRED'
    assert Path(s[4]['source_book']).read_bytes()==before
    assert not Path(json.loads(sp.read_bytes())['dispatch_state']).exists()


def test_isolated_deployed_control_bootstraps_app_before_no_go_boundary(control_spec,tmp_path):
    sp,s,_=control_spec
    original=Path(__file__).resolve().parents[1]/'scripts/alpaca_first_entry_control_v1.py'
    isolated=tmp_path/'control-kit'/'control.py';isolated.parent.mkdir();isolated.write_bytes(original.read_bytes())
    before=Path(s[4]['source_book']).read_bytes()
    process=subprocess.run([sys.executable,'-I','-B',str(isolated),'--spec',str(sp),'--entry'],
        cwd=tmp_path,env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'},capture_output=True,text=True,timeout=10)
    assert process.returncode==2,process.stderr
    assert json.loads(process.stdout)['reason']=='SEPARATE_EXACT_OWNER_GO_REQUIRED',process.stdout
    assert Path(s[4]['source_book']).read_bytes()==before
    assert not Path(s[4]['runtime']).exists()


def test_exact_go_cannot_make_old_weekly_ranking_valid_off_cycle(control_spec,tmp_path,monkeypatch,capsys):
    """Old successful fixture was the stale weekly execution now prohibited."""
    from tests.test_alpaca_dynamic_live_runtime_v1 import NOW
    from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
    from scripts import run_alpaca_dynamic_live_v1 as loader
    sp,s,gp=control_spec;_,broker,old_intake,policy,binding,_=s
    ranking=dict(window_ms=NOW-2*86400000,signal_session='2026-10-09',gate_ok=True,
        picks=[dict(symbol='NET',signal_close=100,stop_price=96,atr20=2)])
    amd=next(x for x in policy['inherited_slots'] if x['symbol']=='AMD')
    with sqlite3.connect(binding['source_book']) as db:
        db.execute('DELETE FROM intents')
        db.executescript('CREATE TABLE rankings(window INTEGER PRIMARY KEY,payload TEXT); CREATE TABLE slots(entry TEXT PRIMARY KEY,payload TEXT); CREATE TABLE exits(entry TEXT PRIMARY KEY,payload TEXT);')
        db.execute('INSERT INTO rankings VALUES (?,?)',(ranking['window_ms'],canonical(ranking).decode()))
        for slot in policy['inherited_slots']:db.execute('INSERT INTO slots VALUES (?,?)',(slot['entry_order_id'],canonical(slot).decode()))
    snapshot=dict(account_id=policy['account_id'],observed_ms=NOW+3000,source_sha256='a'*64,
        single_owner_verified=True,cash_finality_verified=True,cash_usd='50.01',fee_rate='0',liability_reserve_usd='.01',
        positions=[],open_orders=[],blocked_symbols=['AMD'],
        exits=[dict(entry_order_id=amd['entry_order_id'],orders=[dict(id='old-amd-exit',symbol='AMD',side='sell',status='filled',
            filled_qty=amd['qty'],filled_avg_price='622',filled_ms=amd['entry_ms']+1000)])],
        gates={'NET':dict(earnings=True,concentration=True,symbol=True,protection=True)},
        quotes={'NET':dict(ask='100',quote_ms=NOW+2000,received_ms=NOW+3000,qty_step='.000000001',min_qty='.000000001',min_notional='1',tradable=True,fractionable=True,fee_quantity_ceiling='.5')},
        source_evidence={'account':dict(cash='50.01',non_marginable_buying_power='50.01')})
    spec=json.loads(sp.read_bytes())
    intent=prepare_first_intent(policy=policy,binding=binding,ticker='NET',session='2026-10-14',ranking_sha256=digest(ranking),
        slot_entry_order_id=amd['entry_order_id'],risk_distance='4',max_qty='.5',max_notional_usd='50',max_risk_usd='2',max_limit_price='100',
        price_source_sha256='a'*64,quote_cts_ms=NOW-86400000,prepared_ms=NOW-86400000)
    Path(spec['intent']).write_bytes(canonical(intent));spec['intent_sha256']=intent['intent_sha256']
    spec['static_files'][0]['sha256']=hashlib.sha256(Path(spec['intent']).read_bytes()).hexdigest()
    go=dict(schema='ALPACA_DYNAMIC_FIRST_INTENT_OWNER_GO_V1',account_id=intent['account_id'],endpoint=intent['endpoint'],session=intent['session'],
        intent_sha256=intent['intent_sha256'],static_binding_sha256=intent['static_binding_sha256'],owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
    gp.write_bytes(canonical(go))
    for name,value in [('template',{'gates':{'NET':{}}}),('protocol',{}),('calendar',{'next_net_earnings':'2026-11-05'})]:
        path=tmp_path/(name+'.json');path.write_bytes(canonical(value));spec[name]=str(path)
    from research_lab.alpaca_open_dispatch_v2 import STATIC_CHECKS
    spec['checks']={k:dict(status='CLEAR_OR_REVIEWED' if k=='reservation_handoff' else 'VERIFIED',source_sha256='a'*64) for k in STATIC_CHECKS}
    sp.write_bytes(canonical(spec));clock=[intent['open_ms']-901000]
    control=importlib.import_module('scripts.alpaca_first_entry_control_v1');original=control.load_spec
    def loaded(path):
        result=original(path)
        dispatch=sys.modules['research_lab.alpaca_open_dispatch_v2']
        monkeypatch.setattr(dispatch.PreloadedSourcePublisher,'capture',lambda self:copy.deepcopy(snapshot))
        class FixedClock:
            def wall_ms(self):return clock[0]
            def monotonic_ms(self):return 0
        monkeypatch.setattr(dispatch,'WallClock',FixedClock)
        return result
    monkeypatch.setattr(control,'load_spec',loaded)
    monkeypatch.setattr(control.time,'time_ns',lambda:clock[0]*1000000)
    monkeypatch.setattr(loader,'load_client',lambda *args,**kwargs:broker)
    assert control.main(['--spec',str(sp),'--prepare'])==0;capsys.readouterr()
    clock[0]=intent['open_ms']-61000
    assert control.main(['--spec',str(sp),'--ready'])==0;capsys.readouterr()
    clock[0]=NOW+3000;broker.clock_ms=clock[0]
    request=broker._request
    def filled_at_dispatch(method,path,payload=None):
        from datetime import datetime,timezone
        row=request(method,path,payload)
        if payload and payload['side']=='buy':
            row.update(status='filled',filled_qty=payload['qty'],filled_at=datetime.fromtimestamp(clock[0]/1000,timezone.utc).isoformat())
            broker.orders[row['id']].update(row)
        return row
    monkeypatch.setattr(broker,'_request',filled_at_dispatch)
    assert control.main(['--spec',str(sp),'--entry','--owner-go',str(gp)])==2
    result=json.loads(capsys.readouterr().out)
    assert result['reason']=='STALE_SIGNAL_RESELECT_FAIL',result
    assert broker.writes==[] and not Path(binding['runtime']).exists()
    with sqlite3.connect(binding['source_book']) as db:assert db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]==0
    assert control.main(['--spec',str(sp),'--entry','--owner-go',str(gp)])==2
    assert json.loads(capsys.readouterr().out)==result
    assert broker.writes==[]
