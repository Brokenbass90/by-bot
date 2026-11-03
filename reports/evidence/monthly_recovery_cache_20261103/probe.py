"""Pinned production final-dispatch AST, actual GETs, orders-disabled transport."""
import ast,hashlib,json,sqlite3,time,os
from pathlib import Path

def load_final_guard(n,ticket,window,anchor_dir,at,started):
 import inspect
 from research_lab import alpaca_monthly_native_binding_v1 as mod
 from research_lab.kity_oct15_deadline_v1 import publish_once
 source=Path(inspect.getsourcefile(mod.MonthlyNativeBinding));tree=ast.parse(source.read_bytes())
 cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='MonthlyNativeBinding')
 enter=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='enter')
 validator=next(x for x in ast.walk(enter) if isinstance(x,ast.FunctionDef) and x.name=='final_dispatch')
 module=ast.fix_missing_locations(ast.Module(body=[validator],type_ignores=[]))
 ns={**vars(mod),'self':n,'ticket':ticket,'window':window,'now':at,'started':started,'anchor_dir':anchor_dir,'cid':ticket['client_order_id'],'args':{'state_dir':n.runtime/'halt'},'publish_once':publish_once}
 exec(compile(module,str(source),'exec'),ns)
 return ns['final_dispatch']

def run_probe(spec,folder):
 from scripts.run_alpaca_monthly_cycle_v1 import monthly_environment,pinned_input
 from scripts.run_alpaca_dynamic_live_v1 import load_client
 from research_lab.alpaca_monthly_binding_v1 import CONTRACT
 from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
 from research_lab.alpaca_monthly_cost_source_v1 import capture_and_produce_cost_sources
 from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
 from research_lab import alpaca_dynamic_live_runtime_v1 as lifecycle
 from scripts import equities_alpaca_paper_bridge as native
 from research_lab.kity_oct15_deadline_v1 import publish_once
 root=Path(spec['manager']['root']);bookpath=root/'book/monthly-orders-off.sqlite'
 class ReadOnlyBook:
  path=bookpath;contract=CONTRACT
  def rows(self,table):
   assert table in {'positions','exits','selections','dispatches','rotations','closes','stops'}
   with sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True) as db:
    return [json.loads(v[0]) for v in db.execute('SELECT payload FROM '+table+' ORDER BY key')]
 book=ReadOnlyBook();tickets=sorted((root/'tickets').glob('*.json'));assert len(tickets)==1,'EXACT_PREPARED_TICKET_REQUIRED'
 ticket=json.loads(tickets[0].read_bytes());start=time.monotonic();now=lambda:time.time_ns()//1000000
 out={'schema':'MONTHLY_ACTUAL_GET_PREPOST_PROBE_V7','observed_start_ms':now(),'broker_writes':0,'orders_disabled_at_transport':True,'financial_journal_constructors':False,'observational_wrapper_only':True,'refreshes':0,'proof_checks':[]}
 original_files={p:str(p.stat().st_mtime_ns)+':'+hashlib.sha256(p.read_bytes()).hexdigest() for p in [bookpath,tickets[0]]}
 with monthly_environment(spec):
  client=load_client(pinned_input(spec['profile']),dict(broker_root=spec['broker_root'],lock_path=spec['manager']['account_lock_path']),apply=False,order_contract=CONTRACT['schema'])
  assert client.writes_enabled is False and client.write_permit is None
  http=client._http;methods=[]
  def get_http(url,method,payload=None):
   assert method=='GET' and payload is None,'NON_GET_TRANSPORT_REFUSED';methods.append(method);return http(url,method,payload)
  client._http=get_http
  n=MonthlyNativeBinding(book,client=client,base_url=lifecycle.LIVE,account_id=spec['manager']['account_id'],capital=spec['manager']['capital'],runtime=root/'native',lock_path=spec['manager']['account_lock_path'],entry_halt_path=spec['manager']['entry_halt_path'],live_scope_path=spec['authority']['scope_path'],live_scope_sha256=spec['authority']['scope_sha256'],owner_go_path=spec['authority']['owner_go_path'],**spec['native'])
  assert n._live_custody()['runner_config_sha256'];n._loss_latch_guard()
  def capture():
   return capture_and_produce_cost_sources(n,after=spec['costs']['after'],allow_pending=True,legacy_transition=spec['costs']['legacy_transition'],**{k+'_path':pinned_input(spec['costs'][k]) for k in ['protocol','calendar','assets']})
  def refresh():out['refreshes']+=1;capture()
  original_check=n._pending_dispatch_fresh
  def check(proof,observed):
   original_check(proof,observed)
   n._last_probe_pending_proof=proof
   out['proof_checks'].append(dict(observed_ms=observed,source_age_ms=observed-proof['source_observed_ms'],coverage_age_ms=observed-proof['source_coverage_end_ms']))
  n._pending_dispatch_fresh=check
  original_authority=n._entry_authority
  def record_authority(*args,**kwargs):
   scope=original_authority(*args,**kwargs)
   n._last_actual_probe_scope=scope
   return scope
  n._entry_authority=record_authority
  selected=n._selection(ticket['selection_id']);window=next(r for r in selected['calendar'] if r['session']==selected['entry_session']);cid=ticket['client_order_id'];anchor_dir=folder/('probe-evidence-'+str(now()));anchor_dir.mkdir(mode=0o700)
  source=Path(__import__('inspect').getsourcefile(MonthlyNativeBinding));raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==spec['files']['research_lab/alpaca_monthly_native_binding_v1.py']
  with account_lock(dict(lock_path=str(n.lock_path))) as fd,n._cost_capture_lock(fd):
   out['account_lock_inode']=os.fstat(fd).st_ino
   account=client.get_account();positions=client.list_positions();orders=client.list_orders(status='open',limit=500)
   assert account['id']==n.account and positions==[] and orders==[],'ACTUAL_ACCOUNT_NOT_FLAT'
   assert not n.reentry.exists() and not n.ledger.exists(),'FINANCIAL_HISTORY_PRESENT'
   capture();time.sleep(5.2)  # actual ageing, never retime evidence or broker clock
   started=time.monotonic();at=now()
   final_guard=load_final_guard(n,ticket,window,anchor_dir,at,started)
   with n.admission_cost_refresh(refresh):
    try:final_guard();out['final_gate']='PASS'
    except ValueError as error:
     if str(error)!='MONTHLY_FINAL_DISPATCH_WINDOW_OR_CLOCK':raise
     out['final_gate']=str(error)
   out['clock']=client.get_clock();out['source_identity_verified']=True
   scope=n._last_actual_probe_scope;n._standing_entry_state(scope,now());n._loss_latch_guard()
   out['post_guard_scope_comes_from_actual_authority']=True
   from research_lab.alpaca_monthly_handoff_v1 import require_fresh
   require_fresh(n._entry_handoff_proof,scope['legacy_handoff'],cid,now_ms=now())
   from research_lab.alpaca_dynamic_v1 import dec
   out['final_flat_started_ms']=now()
   fresh=client.get_account();positions=client.list_positions();orders=client.list_orders(status='open',limit=500)
   assert fresh['id']==n.account and fresh.get('trading_blocked') is False and fresh.get('account_blocked') is False
   assert positions==[] and orders==[],'FINAL_ACCOUNT_NOT_FLAT'
   need_cash=dec(ticket['notional'])+n.liability
   assert min(dec(fresh['cash']),dec(fresh['non_marginable_buying_power']))>=need_cash,'ACTUAL_CASH_RESERVE'
   assert dec(ticket['notional'])<=min(dec(fresh['equity']),dec(n.capital))*dec('.70')*dec(ticket['entry_gate']['weight']),'ACTUAL_EQUITY_GROSS_CAP'
   n._pending_dispatch_fresh(n._last_probe_pending_proof,now())
   require_fresh(n._entry_handoff_proof,scope['legacy_handoff'],cid,now_ms=now())
   assert now()-out['final_flat_started_ms']<=5000,'FINAL_FLAT_SOURCE_STALE'
   out['fresh_cash_and_gross_caps_pass']=True;out['legacy_handoff_fresh_after_fee_refresh']=True
   assert out['refreshes']>=1 and out['proof_checks'],'FRESHNESS_PATH_NOT_EXERCISED'
   assert all(0<=r['source_age_ms']<=5000 and 0<=r['coverage_age_ms']<=5000 for r in out['proof_checks'])
   assert client.write_permit is None and not client.writes_enabled
   assert not n.reentry.exists() and not n.ledger.exists(),'UNEXPECTED_FINANCIAL_WRITE'
   out['actual_positions']=len(positions);out['actual_open_orders']=len(orders);out['non_get_methods']=[]
 for p,v in original_files.items():assert str(p.stat().st_mtime_ns)+':'+hashlib.sha256(p.read_bytes()).hexdigest()==v,'ORIGINAL_BOOK_OR_TICKET_CHANGED'
 out.update(observed_end_ms=now(),elapsed_ms=int((time.monotonic()-start)*1000),original_book_and_ticket_unchanged=True,status='GET_PREPOST_FEES_PASS_WINDOW_BLOCKED' if out['final_gate']!='PASS' else 'GET_PREPOST_PASS_NO_POST')
 return out
