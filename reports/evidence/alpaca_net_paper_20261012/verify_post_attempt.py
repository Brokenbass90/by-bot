"""Validate private captured NET broker/state; offline existing-intent recovery.

No server/client access, no new PAPER entry, no invented DAY/finality PASS.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from decimal import Decimal as D

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_paper import execute_paper, PAPER, _plan_check
from research_lab.alpaca_dynamic_v1 import digest
from scripts.equities_alpaca_paper_bridge import _validated_existing_intended_lifecycle


def main(capture_path, output):
    capture_raw=capture_path.read_bytes();r=json.loads(capture_raw)['response']
    arm=json.loads((ROOT/'reports/evidence/alpaca_net_arm_20261011/arming_receipt.json').read_bytes())
    assert r['packet_sha256']==arm['packet_sha256']
    assert r['app_manifest']['sha256']==arm['manifest_sha256']
    assert r['app_manifest']['files']==81 and not r['app_manifest']['mismatches']
    def opening(name):
        wrapped=r['runtime']['runtime/opening/'+name+'.json']['payload']
        assert digest(wrapped['value'])==wrapped['sha256']
        return wrapped['value']
    prep=opening('prepared');ready=opening('ready');fresh=opening('fresh')
    reserved=opening('reserve');invoking=opening('invoking_adapter');terminal=opening('terminal')
    assert prep['prepared_ms']==arm['prepared_ms'] and ready['ready_ms']==arm['ready_ms']
    assert fresh['value_sha256']==digest(fresh['value'])
    plan=reserved['value'];assert reserved['value_sha256']==digest(plan)
    assert invoking['plan_sha256']==digest(plan) and invoking['parent_receipt_id']==plan['receipt_id']
    policy=json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_bytes())
    _plan_check(plan,policy)
    assert fresh['value']['liability_reserve_usd']=='0.01'
    assert plan['snapshot_sha256']==digest(fresh['value'])
    assert terminal['status']=='OPENING_PATH_COMPLETED'
    execution=terminal['execution'];assert execution['status']=='PAPER_PROTECTED'
    assert r['databases']['book']['tables']['intent_attempts']['count']==1
    attempts=r['databases']['book']['tables']['intent_attempts']['rows']
    assert len(attempts)==1 and json.loads(attempts[0][-1])==plan
    rows=r['databases']['paper']['tables']['intents']['rows']
    assert r['databases']['paper']['tables']['intents']['count']==len(rows)==1
    item=json.loads(rows[0][3]);assert item['phase']=='PROTECTED'
    assert item['plan']==plan and item['receipt']==execution
    account=r['paper_broker']['account']['payload']
    identity=digest({'parent':plan['receipt_id'],'paper_account':account['id']})
    assert item['id']==rows[0][0]==identity and item['account']==account['id']==rows[0][1]
    orders=r['paper_broker']['net_orders']['payload'];assert len(orders)==2
    entry=next(x for x in orders if x['side']=='buy')
    stop=next(x for x in orders if x['side']=='sell')
    assert entry['client_order_id']==item['entry_cid']=='dyp-'+identity[:32]
    assert stop['client_order_id']==item['stop_cid']=='dys-'+identity[:32]
    assert entry['id']==execution['entry_order_id'] and stop['id']==execution['stop_order_id']
    assert entry['status']=='filled' and entry['symbol']==stop['symbol']==plan['symbol']=='NET'
    assert entry['qty']==entry['filled_qty']==stop['qty']==plan['qty']==execution['filled_qty']
    assert entry['filled_avg_price']==execution['filled_price'] and stop['filled_qty']=='0'
    assert stop['type']=='stop' and stop['status']=='new' and stop['time_in_force']=='day'
    assert stop['stop_price']==execution['stop_price']
    assert D(entry['filled_avg_price'])-D(stop['stop_price'])==D(plan['risk_distance'])
    net_position=r['paper_broker']['net_position']['payload']
    assert net_position['qty']==entry['filled_qty'] and net_position['avg_entry_price']==entry['filled_avg_price']
    assert [x for x in r['paper_broker']['open_orders']['payload'] if x['symbol']=='NET']==[stop]
    fills=[f for f in r['paper_broker']['fills']['payload'] if f['symbol']=='NET']
    assert len(fills)==1 and fills[0]['order_id']==entry['id'] and fills[0]['qty']==entry['filled_qty']
    ledger=r['paper_runtime']['protective_exit_hwm.json']['payload']
    assert set(ledger)=={'NET'}
    validated=_validated_existing_intended_lifecycle(ledger['NET'],account['id'])
    assert validated['entry_order_id']==entry['id'] and validated['accepted_order_id']==stop['id']
    assert D(str(validated['accepted_stop_floor']))==D(stop['stop_price'])
    assert D(str(validated['qty']))==D(entry['filled_qty'])
    assert digest(validated)==execution['native_ledger_sha256']
    guard=r['runtime']['runtime/guard/latest.json']['payload']
    assert guard['receipt']['status']=='PAPER_PROTECTED' and guard['receipt']['stop_order_id']==stop['id']
    assert guard['deadline_ms']==arm['guard_hard_end_ms'] and guard['unwind_not_before_ms']==arm['guard_unwind_not_before_ms']
    assert r['services']['alpaca-net-paper-guard-20261012.service']['MainPID']==arm['units']['alpaca-net-paper-guard-20261012.service']['MainPID']
    assert r['services']['alpaca-net-paper-guard-20261012.service']['NRestarts']=='0'
    assert r['services']['alpaca-net-paper-open-20261012.service']['ExecMainStatus']=='0'
    for name,expected in arm['production_services_unchanged'].items():
        for line in expected:
            key,value=line.split('=',1);assert r['services'][name][key]==value
    assert r['live_halt']['halted'] is True and not r['live_broker']['positions']['payload'] and not r['live_broker']['open_orders']['payload']
    assert r['legacy_exclusions']['sha256']==arm['legacy_NET_exclusion_sha256']
    assert sorted(x['symbol'] for x in r['paper_broker']['positions']['payload'] if x['symbol']!='NET')==arm['paper_legacy_symbols']

    class CapturedClient:
        base_url=PAPER
        calls=[]
        def get_account(self):self.calls.append('GET account');return account
        def list_positions(self):self.calls.append('GET positions');return r['paper_broker']['positions']['payload']
        def get_order(self,oid):self.calls.append('GET order '+oid);return next(x for x in orders if x['id']==oid)
        def _request(self,*args,**kwargs):raise AssertionError('NO_NETWORK_OR_DISPATCH_PERMITTED')
    recovered=[]
    with tempfile.TemporaryDirectory(prefix='net-state-recovery-',dir=ROOT/'.private/alpaca_net_paper_20261012') as temp:
        for i in range(2):
            runtime=Path(temp)/str(i);runtime.mkdir()
            with sqlite3.connect(runtime/'paper.sqlite') as db:
                db.execute('CREATE TABLE intents(id TEXT PRIMARY KEY, account TEXT, slot TEXT, payload TEXT)')
                db.execute('INSERT INTO intents VALUES(?,?,?,?)',rows[0])
            client=CapturedClient();client.calls=[]
            replay=execute_paper(plan,policy,client,account['id'],runtime,r['observed_ms'],send=False)
            assert replay==execution
            with sqlite3.connect((runtime/'paper.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                assert db.execute('SELECT * FROM intents').fetchall()==[tuple(rows[0])]
            recovered.append({'same_receipt':True,'read_calls':client.calls,'dispatch_calls':0})
    notional=D(entry['filled_qty'])*D(entry['filled_avg_price'])
    risk=D(entry['filled_qty'])*(D(entry['filled_avg_price'])-D(stop['stop_price']))
    result={'schema':'ALPACA_NET_PAPER_POST_ATTEMPT_V1','status':'ENTRY_PROTECTED_LIFECYCLE_PENDING',
      'observed_ms':r['observed_ms'],'capture_sha256':hashlib.sha256(capture_raw).hexdigest(),
      'packet_sha256':r['packet_sha256'],'app_manifest_sha256':r['app_manifest']['sha256'],
      'symbol':'NET','entry_order_id':entry['id'],'stop_order_id':stop['id'],
      'filled_at':entry['filled_at'],'stop_submitted_at':stop['submitted_at'],
      'qty':entry['filled_qty'],'fill_price':entry['filled_avg_price'],'actual_notional_usd':str(notional),
      'stop_price':stop['stop_price'],'stop_risk_usd_before_gap_and_costs':str(risk),'protection_tif':'day',
      'full_current_native_protection':True,'one_entry_one_stop':True,'persistent_state_phase':'PROTECTED',
      'source_attempt_count':1,'paper_intent_count':1,'offline_captured_state_recovery':recovered,
      'actual_process_restart_performed':False,'guard_status':'PAPER_PROTECTED','guard_pid':'1979385',
      'opening_timings':terminal['timings'],'legacy_holdings_outside_authority':arm['paper_legacy_symbols'],
      'live_flat':True,'live_halt':True,'live_cash_usd':r['live_broker']['account']['payload']['cash'],
      'live_pending_fees_usd':r['live_broker']['account']['payload']['pending_reg_taf_fees'],
      'transient_guard_blocker':{'reason':'PAPER_FOREIGN_ACTIVE_ORDER','at_ms':1791811811205,
         'recovered_protected_at_ms':1791811814940,'cause':'NOT_PROVEN; raw failing GET response not captured'},
      'remaining_gates':['actual Oct13 DAY rearm if overnight','owned terminal exit and costs/finality','exact fresh LIVE GO dossier and separate owner GO'],
      'guard_unwind_not_before_ms':arm['guard_unwind_not_before_ms'],'guard_hard_end_ms':arm['guard_hard_end_ms'],
      'paper_execution_pass':False,'ready_for_live_go':False,'broker_writes':0,'remote_writes':0,
      'additional_paper_entries':0,'live_orders_allowed':False}
    with output.open('x') as handle:json.dump(result,handle,indent=2);handle.write('\n')
    print(json.dumps({'status':result['status'],'native_protection':'PASS','offline_state_recovery':'PASS',
                     'qty':result['qty'],'stop':result['stop_price'],'risk_usd':str(risk),'live_halt':True}))


if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))
