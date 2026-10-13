import copy
import importlib
import json
from pathlib import Path

import pytest

from research_lab.alpaca_dynamic_v1 import canonical,digest
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case,NOW


def api():
    return importlib.import_module('research_lab.alpaca_live_readiness_v1')


def test_package_has_no_keys_no_apply_and_disabled_timers(tmp_path):
    package=api().build_package(Path(__file__).resolve().parents[1])
    assert package['orders_allowed'] is False and package['enabled'] is False
    assert 'research_lab/alpaca_dynamic_live_runtime_v1.py' in package['files']
    assert not any(n.endswith('.env') or '.private' in n for n in package['files'])
    assert all('--apply' not in unit for unit in package['units'].values())
    assert all('[Install]' not in unit for unit in package['units'].values())
    assert package['manager_apply_arguments']==['--apply','--maintenance','--owner-go']


def test_package_drift_refuses_before_install(tmp_path):
    package=api().build_package(Path(__file__).resolve().parents[1])
    package['files']['research_lab/alpaca_dynamic_live_runtime_v1.py']['sha256']='0'*64
    with pytest.raises(ValueError,match='PACKAGE'):
        api().verify_package(package)


@pytest.fixture
def lifecycle(tmp_path):
    entry=dict(id='entry',client_order_id='entry-cid',symbol='NET',side='buy',type='limit',
        qty='.5',filled_qty='.5',filled_avg_price='100',status='filled',filled_at='2026-10-12T13:30:02Z')
    original=dict(id='initial-stop',symbol='NET',side='sell',type='stop',qty='.5',filled_qty='0',
        stop_price='95',time_in_force='day',status='expired')
    rearm=dict(id='rearm-stop',client_order_id='rearm-cid',symbol='NET',side='sell',type='stop',qty='.5',filled_qty='0',
        stop_price='95',time_in_force='day',status='new',submitted_at='2026-10-13T13:30:01Z')
    exit=dict(id='exit',symbol='NET',side='sell',type='market',qty='.5',filled_qty='.5',
        filled_avg_price='101',status='filled',filled_at='2026-10-13T13:35:01Z')
    arms=dict(packet_sha256='p',manifest_sha256='m',app_files=81,
        guard_unwind_not_before_ms=1791898500000,guard_hard_end_ms=1791900000000,
        paper_legacy_symbols=['ABNB'],production_services_unchanged={'bybot.service':['MainPID=1','NRestarts=0']})
    initial=dict(paper_account_id='paper',live_account_id='live',entry_order_id='entry',stop_order_id='initial-stop',
        qty='.5',fill_price='100',symbol='NET',parent_receipt_id='plan',stop_price='95',
        status='ENTRY_PROTECTED_LIFECYCLE_PENDING',
        offline_captured_state_recovery=[dict(same_receipt=True,dispatch_calls=0)])
    def response(now):
        return dict(observed_ms=now,packet_sha256='p',app_manifest=dict(sha256='m',files=81,mismatches=[]),
            broker_writes=0,remote_writes=0,packet=dict(paper_account='paper'),
            services={'bybot.service':dict(MainPID='1',NRestarts='0')},
            paper_broker=dict(account=dict(http_status=200,payload=dict(id='paper',cash='100.49')),
                positions=dict(http_status=200,payload=[dict(symbol='ABNB')]),
                open_orders=dict(http_status=200,payload=[]),
                net_orders=dict(http_status=200,payload=[entry,original,{**rearm,'status':'canceled'},exit]),
                fills=dict(http_status=200,payload=[dict(order_id='entry',symbol='NET',qty='.5',price='100'),dict(order_id='exit',symbol='NET',qty='.5',price='101')]),
                activities=dict(http_status=200,payload=[])),
            live_broker=dict(account=dict(http_status=200,payload=dict(id='live')),
                positions=dict(http_status=200,payload=[]),open_orders=dict(http_status=200,payload=[])),
            live_halt=dict(halted=True),runtime={},paper_runtime={},databases={})
    before=response(1791898320000)
    before['paper_broker']['positions']['payload'].append(dict(symbol='NET',qty='.5'))
    before['paper_broker']['open_orders']['payload']=[rearm]
    before['runtime']['runtime/guard/latest.json']=dict(payload=dict(observed_ms=1791898320000,
        deadline_ms=1791900000000,unwind_not_before_ms=1791898500000,
        receipt=dict(status='PAPER_PROTECTED',stop_order_id='rearm-stop')))
    record=dict(account_id='paper',entry_order_id='entry',entry_price=100,qty=.5,entry_fill_qty=.5,
        hwm=100,accepted_stop_floor=95,accepted_order_id='rearm-stop',
        lifecycle_first_seen_at_utc='2026-10-12T13:30:02Z',strategy_id='ALPACA-BASELINE-26f7ff663dc98e87')
    before['paper_runtime']['protective_exit_hwm.json']=dict(payload={'NET':record})
    after=response(1791900300000)
    item=dict(account='paper',receipt=initial,plan=dict(symbol='NET',receipt_id='plan'),
        rearms={'2026-10-13':dict(cid='rearm-cid',qty='.5',floor='95')},managed_stop_order_id='rearm-stop',
        terminal_preparation=dict(owned_record=record),
        terminal=dict(status='PAPER_EXIT_PENDING_FINALITY',exit_orders=[exit],gross_before_fees='.5'))
    after['databases']['paper']=dict(tables=dict(intents=dict(count=1,rows=[['intent','paper','slot',canonical(item).decode()]])))
    after['paper_runtime']['protective_exit_hwm.json']=dict(payload={})
    after['runtime']['runtime/guard/terminal.json']=dict(payload=dict(observed_ms=1791898502000,
        deadline_ms=1791900000000,unwind_not_before_ms=1791898500000,receipt=item['terminal']))
    # Custody is a real file pin, not a synthetic boolean/hash declaration.
    source=tmp_path/'captured.json';source.write_bytes(canonical(after))
    import hashlib
    files=[dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())]
    fees=dict(schema='ALPACA_PAPER_ACCOUNT_DAY_FINALITY_V1',account_id='paper',entry_order_id='entry',
        exit_order_ids=['exit'],cash_before='100',cash_after='100.49',other_cash_net_usd='0',
        gross_usd='.5',commission_usd='0',regulatory_fees_usd='.01',unresolved_liability_usd='0',
        closure_status='ACCOUNT_DAY_FEES_RECONCILED',observed_ms=1791900300000,
        capture_response_sha256=digest(after),activities_sha256=digest([]),
        source_manifest_sha256=digest(files),source_files=files)
    return arms,initial,before,after,fees


def verify(case):
    return api().verify_paper_lifecycle(*case,now_ms=1791900300000)


def test_complete_owned_lifecycle_and_costs_pass(lifecycle):
    r=verify(lifecycle)
    assert r['status']=='PAPER_EXECUTION_PASS' and r['net_usd']=='0.49'
    assert r['orders_allowed'] is False and r['ready_for_live_go'] is False


def test_actual_full_rearm_stop_fill_before_first_check_is_valid(lifecycle):
    arm,initial,before,after,fees=lifecycle
    stop=copy.deepcopy(before['paper_broker']['open_orders']['payload'][0])
    stop.update(status='filled',filled_qty='.5',filled_avg_price='101',filled_at='2026-10-13T13:31:01Z')
    item=json.loads(after['databases']['paper']['tables']['intents']['rows'][0][3])
    item['terminal'].update(status='PAPER_STOP_EXIT_PENDING_FINALITY',exit_orders=[stop])
    # Filled-on-submit recovery retains the pre-rearm owned record separately.
    record=item['terminal_preparation']['owned_record']
    record.update(accepted_order_id='initial-stop')
    item['terminal_preparation']['reconciled_record']={**record,'accepted_order_id':stop['id'],
        'accepted_order_tif':'day','accepted_stop_floor':95}
    item['managed_stop_order_id']='initial-stop'
    after['databases']['paper']['tables']['intents']['rows'][0][3]=canonical(item).decode()
    after['paper_broker']['net_orders']['payload']=after['paper_broker']['net_orders']['payload'][:2]+[stop]
    after['paper_broker']['fills']['payload'][-1]['order_id']=stop['id']
    after['runtime']['runtime/guard/terminal.json']['payload']['receipt']=item['terminal']
    before['runtime']['runtime/guard/latest.json']['payload']['receipt']=item['terminal']
    before['paper_runtime']['protective_exit_hwm.json']['payload']={}
    before['paper_broker']['open_orders']['payload']=[]
    before['paper_broker']['positions']['payload']=[dict(symbol='ABNB')]
    fees.update(exit_order_ids=[stop['id']],capture_response_sha256=digest(after))
    result=verify(lifecycle)
    assert result['status']=='PAPER_EXECUTION_PASS',result
    stop['client_order_id']='foreign'
    assert verify(lifecycle)['status']=='BLOCKED_DATA'


@pytest.mark.parametrize('bad',['time','source','partial_exit','foreign_order','no_rearm','ledger','fees','cash','cost_pin','services'])
def test_missing_or_conflicting_actual_evidence_is_a_blocker(lifecycle,bad):
    arm,initial,before,after,fees=copy.deepcopy(lifecycle)
    if bad=='time':after['observed_ms']=1791898000000
    if bad=='source':after['app_manifest']['mismatches']=['changed.py']
    if bad=='partial_exit':after['paper_broker']['net_orders']['payload'][-1]['filled_qty']='.2'
    if bad=='foreign_order':after['paper_broker']['open_orders']['payload']=[dict(symbol='NET',id='foreign')]
    if bad=='no_rearm':before['paper_broker']['open_orders']['payload']=[]
    if bad=='ledger':after['paper_runtime']['protective_exit_hwm.json']['payload']={'NET':{}}
    if bad=='fees':fees['unresolved_liability_usd']='.01'
    if bad=='cash':after['paper_broker']['account']['payload']['cash']='100.50'
    if bad=='cost_pin':fees['activities_sha256']='x'
    if bad=='services':after['services']['bybot.service']['NRestarts']='1'
    r=verify((arm,initial,before,after,fees))
    assert r['status'].startswith('BLOCKED') and r['ready_for_live_go'] is False


def test_missing_cost_closure_never_substitutes_zero(lifecycle):
    case=list(lifecycle);case[-1]=None
    r=verify(case)
    assert r['status']=='BLOCKED_DATA' and r['reason']=='PAPER_COST_FINALITY_SOURCE_REQUIRED'


def test_fee_file_mutation_does_not_pass(lifecycle):
    Path(lifecycle[-1]['source_files'][0]['path']).write_text('changed')
    r=verify(lifecycle)
    assert r['status']=='BLOCKED_DATA' and r['reason']=='PHYSICAL_SOURCE_HASH_CONFLICT'


def test_initial_offline_recovery_must_be_proven(lifecycle):
    lifecycle[1]['offline_captured_state_recovery']=[]
    assert verify(lifecycle)['reason']=='INITIAL_ENTRY_RECOVERY_NOT_PROVEN'


def test_exit_activity_quantity_must_match(lifecycle):
    lifecycle[3]['paper_broker']['fills']['payload'][-1]['qty']='.4'
    assert verify(lifecycle)['reason']=='FILL_ACTIVITY_RECONCILIATION'


def test_truncated_pages_do_not_pass(lifecycle):
    lifecycle[3]['paper_broker']['net_orders']['payload'] *= 25
    assert verify(lifecycle)['reason']=='BROKER_PAGE_INCOMPLETE:net_orders'


def test_dossier_cannot_promote_pending_paper():
    r=api().exact_dossier(paper=dict(status='PAPER_PENDING'),deployment={},binding={},intake={},policy={},now_ms=1791900300000)
    assert r['status']=='BLOCKED_DATA' and r['ready_for_live_go'] is False


def test_default_unit_templates_do_not_register_a_timer():
    p=api().build_package(Path(__file__).resolve().parents[1])
    assert all(n.endswith('.service') for n in p['units'])
    assert all('EnvironmentFile=' not in text and 'OnCalendar=' not in text for text in p['units'].values())
    draft=p['unapproved_activation_templates']['alpaca-dynamic-live-manager-20261013.service']
    assert '--apply --maintenance --owner-go' in draft
    assert '[Install]' not in draft


def paper_pass(case):
    return verify(case)


def test_disabled_installer_requires_due_time_and_actual_receipt(lifecycle,tmp_path):
    p=api().build_package(Path(__file__).resolve().parents[1])
    with pytest.raises(ValueError,match='ACTUAL_PAPER_PASS'):
        api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900200000,target=tmp_path/'app')
    with pytest.raises(ValueError,match='ACTUAL_PAPER_PASS'):
        api().install_disabled(p,dict(status='PAPER_PENDING'),now_ms=1791900300000,target=tmp_path/'app')
    assert not (tmp_path/'app').exists()


def test_disabled_install_repeated_verifies_without_overwriting(lifecycle,tmp_path):
    p=api().build_package(Path(__file__).resolve().parents[1]);target=tmp_path/'deployed'
    r=api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900300000,target=target)
    files={str(f.relative_to(target)):f.read_bytes() for f in target.rglob('*') if f.is_file()}
    restored=api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900400000,target=target)
    assert r==restored and r['service_activation_count']==r['installed_system_units']==0
    assert files=={str(f.relative_to(target)):f.read_bytes() for f in target.rglob('*') if f.is_file()}
    assert not (target/'session/binding.json').exists()
    changed=target/'app/research_lab/alpaca_dynamic_live_runtime_v1.py';changed.write_text('changed')
    with pytest.raises(ValueError,match='INSTALLED_FILE_DRIFT'):
        api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900400000,target=target)
    assert changed.read_text()=='changed'


def test_partial_install_is_not_repaired(lifecycle,tmp_path):
    p=api().build_package(Path(__file__).resolve().parents[1]);target=tmp_path/'deployed';target.mkdir()
    with pytest.raises(ValueError,match='PARTIAL_INSTALL_NO_REPAIR'):
        api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900300000,target=target)


def test_symlink_install_is_refused(lifecycle,tmp_path):
    p=api().build_package(Path(__file__).resolve().parents[1]);target=tmp_path/'deployed'
    target.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError,match='INSTALL_SYMLINK'):
        api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900300000,target=target)


def test_isolated_package_imports_and_frozen_dependencies_close(lifecycle,tmp_path):
    import os,subprocess,sys
    p=api().build_package(Path(__file__).resolve().parents[1]);target=tmp_path/'deployed'
    api().install_disabled(p,paper_pass(lifecycle),now_ms=1791900300000,target=target)
    code='''import json
from research_lab.alpaca_dynamic_v1 import source_check
from research_lab import alpaca_dynamic_live_runtime_v1
from research_lab import alpaca_live_readiness_v1
from scripts import run_alpaca_dynamic_live_v1
p=json.load(open("reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json"))
source_check(p,p["calendar_sessions"])
print("ISOLATED_IMPORT_AND_FROZEN_SOURCE_PASS")
'''
    r=subprocess.run([sys.executable,'-B','-c',code],cwd=target/'app',
        env={**os.environ,'PYTHONPATH':str(target/'app'),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert r.stdout.strip()=='ISOLATED_IMPORT_AND_FROZEN_SOURCE_PASS'


def dossier_case(lifecycle,setup,tmp_path):
    import hashlib
    paper=paper_pass(lifecycle)
    package=api().build_package(Path(__file__).resolve().parents[1])
    deployment=api().install_disabled(package,paper,now_ms=1791900300000,target=tmp_path/'installed')
    _,_,intake,policy,binding,_=setup
    Path(binding['sources']['paper']['path']).write_bytes(canonical(paper))
    h=hashlib.sha256(canonical(paper)).hexdigest()
    binding['sources']['paper']['sha256']=h;intake['scope']['paper_lifecycle_sha256']=h
    intake['intake_sha256']=digest({k:v for k,v in intake.items() if k!='intake_sha256'})
    binding['intake_sha256']=intake['intake_sha256']
    return dict(paper=paper,deployment=deployment,binding=binding,intake=intake,policy=policy,now_ms=NOW)


def test_exact_dossier_only_for_fresh_bound_plan(lifecycle,setup,tmp_path):
    inputs=dossier_case(lifecycle,setup,tmp_path)
    r=api().exact_dossier(**inputs)
    assert r['status']=='READY_FOR_LIVE_GO',r
    assert r['orders_allowed'] is False and r['ticker']=='NET' and r['qty']=='.5'
    assert r['stop_distance_risk_usd']=='2.0' and r['notional_usd']=='50.000'
    assert r['required_owner_go_text'].endswith(inputs['intake']['intake_sha256'])


def test_dossier_cannot_use_tomorrow_plan_today(lifecycle,setup,tmp_path):
    inputs=dossier_case(lifecycle,setup,tmp_path);inputs['now_ms']=1791900300000
    assert api().exact_dossier(**inputs)['reason']=='EXACT_OPENING_TIME_PLAN_REQUIRED'


@pytest.mark.parametrize('bad',['enabled','paper_pin','installed_source','authority'])
def test_dossier_rejects_deployment_or_authority_conflict(lifecycle,setup,tmp_path,bad):
    inputs=dossier_case(lifecycle,setup,tmp_path)
    if bad=='enabled':inputs['deployment']['enabled']=True
    if bad=='paper_pin':inputs['deployment']['paper_receipt_sha256']='wrong'
    if bad=='installed_source':Path(inputs['deployment']['source_files'][0]['path']).write_text('changed')
    if bad=='authority':Path(inputs['binding']['sources']['authority']['path']).write_text('{}')
    r=api().exact_dossier(**inputs)
    assert r['status']=='BLOCKED_DATA' and r['ready_for_live_go'] is False


def test_source_bound_paper_fee_semantics_close_cash_without_invented_fee(lifecycle,tmp_path,monkeypatch):
    import hashlib
    arm,initial,before,after,oldfees=copy.deepcopy(lifecycle)
    after['paper_broker']['account']['payload'].update(cash='100.50',accrued_fees='0',pending_reg_taf_fees='0')
    after['paper_broker']['activities']['payload']=[
        dict(id='fill1',activity_type='FILL',order_id='entry',symbol='NET',qty='.5',price='100',side='buy',transaction_time='2026-10-12T13:30:02Z'),
        dict(id='fill2',activity_type='FILL',order_id='exit',symbol='NET',qty='.5',price='101',side='sell',transaction_time='2026-10-13T13:35:01Z')]
    after['activity_request_after_ms']=1791676800000
    pre=dict(response=dict(observed_ms=1791700000000,paper_broker=dict(account=dict(http_status=200,payload=dict(id='paper',cash='100')))))
    pre_path=tmp_path/'pre.json';pre_path.write_bytes(canonical(pre))
    after_path=tmp_path/'after.json';after_path.write_bytes(canonical(dict(response=after)))
    doc=tmp_path/'official_fixture.md';doc.write_bytes(b'paper trading does not account for:\n- Regulatory fees\n')
    monkeypatch.setattr(api(),'PAPER_DOC_SHA',hashlib.sha256(doc.read_bytes()).hexdigest())
    root=Path(__file__).resolve().parents[1]
    fee=api().derive_paper_cost_closure(pre_path,after_path,
        doc,
        root/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json',now_ms=1791900300000)
    assert fee['regulatory_fees_usd']=='0' and fee['commission_usd']=='0'
    r=api().verify_paper_lifecycle(arm,initial,before,after,fee,now_ms=1791900300000)
    assert r['status']=='PAPER_EXECUTION_PASS' and r['net_usd']=='0.5',r


@pytest.fixture
def posted_case(lifecycle,tmp_path,monkeypatch):
    """Recorded NET arithmetic with simulated IDs; no private broker fixtures."""
    import hashlib
    from decimal import Decimal
    arm,initial,before,after,_=copy.deepcopy(lifecycle)
    qty='0.325167779';buy='363.2';sell='349.344'
    initial.update(qty=qty,fill_price=buy,stop_price='329.66')
    for o in after['paper_broker']['net_orders']['payload']:
        o['qty']=qty
        if o['side']=='buy':o.update(filled_qty=qty,filled_avg_price=buy)
        if o['type']=='market':o.update(filled_qty=qty,filled_avg_price=sell)
        if o['type']=='stop':o['stop_price']='329.66'
    stop=before['paper_broker']['open_orders']['payload'][0];stop.update(qty=qty,stop_price='329.66')
    before['paper_broker']['positions']['payload'][-1]['qty']=qty
    record=before['paper_runtime']['protective_exit_hwm.json']['payload']['NET']
    record.update(qty=float(qty),entry_fill_qty=float(qty),entry_price=float(buy),hwm=float(buy),accepted_stop_floor=329.66)
    item=json.loads(after['databases']['paper']['tables']['intents']['rows'][0][3])
    item['terminal_preparation']['owned_record']=copy.deepcopy(record)
    item['rearms']['2026-10-13'].update(qty=qty,floor='329.66')
    exit=after['paper_broker']['net_orders']['payload'][-1]
    item['terminal'].update(exit_orders=[exit],gross_before_fees=str(Decimal(qty)*(Decimal(sell)-Decimal(buy))))
    after['databases']['paper']['tables']['intents']['rows'][0][3]=canonical(item).decode()
    after['runtime']['runtime/guard/terminal.json']['payload']['receipt']=item['terminal']
    fills=[dict(id='buy-fill',activity_type='FILL',order_id='entry',symbol='NET',qty=qty,price=buy,side='buy',transaction_time='2026-10-12T13:30:02Z'),
           dict(id='sell-fill',activity_type='FILL',order_id='exit',symbol='NET',qty=qty,price=sell,side='sell',transaction_time='2026-10-13T13:35:01Z')]
    after['paper_broker']['fills']['payload']=copy.deepcopy(fills)
    fees=[dict(id='cat-buy',activity_type='FEE',date='2026-10-12',net_amount='-.01',description='CAT fee for proceed of 1 trades on 2026-10-12 by PAPER'),
          dict(id='cat-sell',activity_type='FEE',date='2026-10-13',net_amount='-.01',description='CAT fee for proceed of 1 trades on 2026-10-13 by PAPER'),
          dict(id='sec-sell',activity_type='FEE',date='2026-10-13',net_amount='-.01',description='SEC fee for proceed of 1 trades on 2026-10-13 by PAPER')]
    after['paper_broker']['activities']['payload']=fills+fees
    after['activity_request_after_ms']=1791676800000
    after['paper_broker']['account']['payload'].update(cash='99405.75',accrued_fees='0',pending_reg_taf_fees='0')
    before['paper_broker']['account']['payload'].update(cash='99292.17')
    pre=dict(observed_ms=1791700000000,paper_broker=dict(account=dict(http_status=200,payload=dict(id='paper',cash='99410.28'))))
    first=dict(observed_ms=1791812110000,paper_broker=dict(account=dict(http_status=200,payload=dict(id='paper',cash='99292.18'))))
    paths={}
    for name,data in [('cash_before',pre),('initial',first),('rearm',before),('terminal',after)]:
        p=tmp_path/(name+'.json');p.write_bytes(canonical(dict(response=data)));paths[name]=p
    protocol=json.loads((Path(__file__).resolve().parents[1]/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_bytes())
    protocol['account_id']='live';p=tmp_path/'protocol.json';p.write_bytes(canonical(protocol));paths['protocol']=p
    monkeypatch.setattr(api(),'COMMISSION_PROTOCOL_SHA',hashlib.sha256(p.read_bytes()).hexdigest())
    return arm,initial,before,after,paths


def posted_closure(case):
    paths=case[-1]
    return api().derive_paper_posted_cost_closure_v2(**{n+'_path':p for n,p in paths.items()},now_ms=1791900300000)


def test_actual_posted_fees_and_cent_checkpoint_chain_close_without_zero_assumption(posted_case):
    fee=posted_closure(posted_case)
    assert fee['regulatory_fees_usd']=='0.03'
    assert fee['cash_rounding_residual_usd']=='0.005524745824'
    r=api().verify_paper_lifecycle(*posted_case[:4],fee,now_ms=1791900300000)
    assert r['status']=='PAPER_EXECUTION_PASS' and r['net_usd']=='-4.535524745824',r


@pytest.mark.parametrize('fault',['missing_exit_fee','unknown_fee','foreign_fill','cash_drift','pending_liability','missing_checkpoint'])
def test_posted_fee_closure_never_hides_missing_or_conflicting_sources(posted_case,fault):
    paths=posted_case[-1];after=json.loads(paths['terminal'].read_bytes())['response']
    rows=after['paper_broker']['activities']['payload']
    if fault=='missing_exit_fee':rows.pop()
    elif fault=='unknown_fee':rows[-1]['description']='Unclassified fee'
    elif fault=='foreign_fill':rows.append({**rows[0],'id':'other','order_id':'unowned'})
    elif fault=='cash_drift':after['paper_broker']['account']['payload']['cash']='99405.76'
    elif fault=='pending_liability':after['paper_broker']['account']['payload']['pending_reg_taf_fees']='.01'
    else:paths['initial'].unlink()
    paths['terminal'].write_bytes(canonical(dict(response=after)))
    with pytest.raises((ValueError,FileNotFoundError)):
        posted_closure(posted_case)


def test_forged_cent_residual_cannot_promote_full_lifecycle(posted_case):
    fee=posted_closure(posted_case);fee['cash_rounding_residual_usd']='.02'
    r=api().verify_paper_lifecycle(*posted_case[:4],fee,now_ms=1791900300000)
    assert r['status']=='BLOCKED_DATA'


def pre_entry_case(lifecycle,setup,tmp_path):
    import hashlib,sqlite3
    from datetime import datetime,timezone
    from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
    inputs=dossier_case(lifecycle,setup,tmp_path)
    now=NOW-82800000
    snapshot=dict(endpoint=inputs['binding']['endpoint'],account=dict(id=inputs['policy']['account_id'],
        cash='100',non_marginable_buying_power='100',trading_blocked=False,account_blocked=False),
        quote=dict(ap='100',bp='99',t=datetime.fromtimestamp((now-1000)/1000,timezone.utc).isoformat()),
        asset=dict(symbol='NET',status='active',tradable=True,fractionable=True),
        positions=[],open_orders=[],observed_ms=now,
        gates=dict(earnings=True,reentry=True,concentration=True,protection=True))
    sp=tmp_path/'snapshot.json';sp.write_bytes(canonical(snapshot))
    rows=[dict(path=str(sp),sha256=hashlib.sha256(sp.read_bytes()).hexdigest())]
    ranking=dict(window_ms=1791811800000,picks=[dict(symbol='NET',signal_close='100',stop_price='96')])
    with sqlite3.connect(inputs['binding']['source_book']) as db:
        db.execute('DELETE FROM intents');db.execute('DELETE FROM intent_attempts')
        db.execute('CREATE TABLE rankings(window INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('INSERT INTO rankings VALUES(?,?)',(ranking['window_ms'],canonical(ranking).decode()))
    intent=prepare_first_intent(policy=inputs['policy'],binding=inputs['binding'],ticker='NET',session='2026-10-14',
        ranking_sha256=digest(ranking),slot_entry_order_id=inputs['intake']['plan']['slot_entry_order_id'],
        risk_distance='4',max_qty='.5',max_notional_usd='50',max_risk_usd='2',max_limit_price='100',
        price_source_sha256=rows[0]['sha256'],quote_cts_ms=now-1000,prepared_ms=now)
    del inputs['intake'];inputs.update(intent=intent,now_ms=now,
        preparation=dict(snapshot=snapshot,source_files=rows,source_manifest_sha256=digest(rows)))
    return inputs


def test_pre_entry_dossier_is_concrete_before_open_but_never_go(lifecycle,setup,tmp_path):
    r=api().pre_entry_dossier(**pre_entry_case(lifecycle,setup,tmp_path))
    assert r['status']=='READY_FOR_LIVE_GO' and r['orders_allowed'] is False,r
    assert r['max_qty']=='0.5' and r['attempts_allowed']==1
    assert r['required_owner_go_text'].startswith('GO ALPACA_DYNAMIC_FIRST_INTENT_V1 ')


@pytest.mark.parametrize('bad',['cash','raw_snapshot','authority','reserved','freshness','distance'])
def test_pre_entry_dossier_blocks_missing_actual_sources(lifecycle,setup,tmp_path,bad):
    import sqlite3
    inputs=pre_entry_case(lifecycle,setup,tmp_path)
    if bad=='cash':inputs['preparation']['snapshot']['account']['cash']='0'
    if bad=='raw_snapshot':inputs['preparation']['snapshot']['gates']['earnings']=False
    if bad=='authority':Path(inputs['binding']['sources']['authority']['path']).write_text('{}')
    if bad=='reserved':
        with sqlite3.connect(inputs['binding']['source_book']) as db:db.execute("INSERT INTO intents VALUES('x','2026-10-14','{}')")
    if bad=='freshness':inputs['now_ms']+=300001
    if bad=='distance':inputs['intent']['reference_risk_distance']='5'
    r=api().pre_entry_dossier(**inputs)
    assert r['status']=='BLOCKED_DATA' and r['ready_for_live_go'] is False,r
