"""Actual public prices/selector, simulated account/clock/HTTP. No network."""
import argparse,hashlib,json,os,shutil,sys,time
from pathlib import Path
A=argparse.ArgumentParser();A.add_argument('--app',required=True);A.add_argument('--directory',required=True);a=A.parse_args();sys.path.insert(0,a.app)
import socket
class NoNetwork(socket.socket):
 def connect(self,*a,**k):raise AssertionError('REHEARSAL_NETWORK_FORBIDDEN')
socket.socket=NoNetwork;socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError('REHEARSAL_NETWORK_FORBIDDEN'))
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager,publish
from research_lab.alpaca_monthly_native_binding_v1 import RECOVERY_SELECTION_POLICY,standing_source_pins
from scripts import run_alpaca_monthly_cycle_v1 as cli
from scripts.rehearse_alpaca_monthly_cycle_v1 import MemoryBroker,standing_mode
from research_lab.alpaca_monthly_binding_v1 import validate_initial_recovery
root=Path(a.directory);root.mkdir(mode=0o700)
raw=json.loads(Path('/private/tmp/monthly-recovery-intake-20261103.json').read_bytes());original=raw['selections'][0];ticket=raw['tickets'][0]['ticket']
source=Path('/private/tmp/monthly-recovery-original-history-20261103.json');frozen=root/'frozen-history.json';shutil.copyfile(source,frozen)
actual=next(r for r in original['calendar'] if r['session']=='2026-11-03');opening=actual['open_ms'];clock=opening+1000
policy=dict(schema='ALPACA_MONTHLY_INITIAL_ENTRY_RECOVERY_V1',original_selection_id=original['selection_id'],original_selection_sha256=digest(original),original_ticket_sha256=ticket['ticket_sha256'],entry_session='2026-11-03',open_ms=opening,close_ms=opening+300000,symbol=ticket['symbol'],max_notional_usd=str(ticket['notional']),max_entries=1,created_ms=opening-3600000,frozen_history=dict(path=str(frozen),sha256=hashlib.sha256(frozen.read_bytes()).hexdigest()))
validate_initial_recovery(policy,original,ticket)
args=dict(account_id='MONTHLY_REHEARSAL_ONLY',capital='487.42',account_lock_path=root/'fixture-account.lock',entry_halt_path=root/'fixture-HALT.json')
m=MonthlyManager(root/'cycle',**args);captures='/private/tmp/monthly-recovery-source-20261103';bundle=cli.latest_bundle(captures,clock);m.source(bundle,now_ms=clock)
book=m.book
with book.db() as db:book._save(db,'selections',original['selection_id'],original);book._event(db,'FIXTURE_COPY_OF_ACTUAL_SELECTION',original)
publish(m.root/'tickets'/(ticket['client_order_id']+'.json'),ticket)
recovery=m.book.seal_initial_recovery(policy,ticket,now_ms=clock-2000)
broker=MemoryBroker(root/'broker.json',original['calendar'],standing=True);broker.mark({p['symbol']:p['signal_close'] for p in original['picks']});broker.set_clock(clock)
with standing_mode(root,m,clock) as authority:
 scope=json.loads(Path(authority['live_scope_path']).read_bytes());scope.update(selection_policy=RECOVERY_SELECTION_POLICY,initial_recovery=policy,max_new_entries_per_session=1)
 live=Path(os.environ['ALPACA_INTENDED_LIVE_BINDING_PATH'])
 spec=dict(schema=cli.RUNNER_SCHEMA,enabled=True,orders_allowed=True,money_authority=True,files=standing_source_pins(),manager={k:str(v) for k,v in dict(root=m.root,**args).items()},source_captures=captures,broker_root=str(root),profile=dict(path=str(root/'UNUSED-NO-CREDENTIALS-profile'),sha256='0'*64),native_binding=dict(path=str(live),sha256=ops.sha(live)),legacy_handoff=scope['legacy_handoff'],native=dict(liability_reserve_usd='0',pending_fee_admission=False),costs=dict(after='2026-10-30T00:00:00Z'),notifications=None)
 scope['runner_config_sha256']=cli.runner_config_sha256(spec);sp=root/'FIXTURE-NOT-AUTHORITY-recovery-scope.json';publish(sp,scope);go=root/'FIXTURE-NOT-AUTHORITY-recovery-go.json';publish(go,dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=ops.sha(sp),owner_go_text='GO ALPACA_MONTHLY_STANDING '+ops.sha(sp)))
 spec['authority']=dict(scope_path=str(sp),scope_sha256=ops.sha(sp),owner_go_path=str(go))
 out=cli.dispatch_cycle(spec,client_factory=lambda spec:broker,now_ms=clock)
 assert not out['issues'],out['issues']
 assert len(broker.state['writes'])==2,broker.state['writes']
 p=m.book.rows('positions')[0];assert p['symbol']=='LLY' and p['daily_state']['entry_session']=='2026-11-03'
 assert p['native_stop_id'] and p['native_floor']>0
 assert next(s for s in m.book.rows('selections') if s['selection_id']==original['selection_id'])==original
 before=digest(p);broker.set_clock(clock+1000)
 again=cli.dispatch_cycle(spec,client_factory=lambda spec:broker,now_ms=clock+1000)
 assert not again['issues'],again['issues']
 assert len(broker.state['writes'])==2 and digest(m.book.rows('positions')[0])==before
 receipt=dict(schema='MONTHLY_INITIAL_RECOVERY_ACTUAL_SOURCE_OFF_V1',status='ACTUAL_SOURCE_FAKE_ACCOUNT_DISPATCH_PASS',actual_observed_ms=time.time_ns()//1000000,simulated_execution_ms=clock,prospective=False,real_broker_requests=0,real_broker_writes=0,selector_monkeypatched=False,source_loader_injected=False,production_entrypoint=True,simulated_native_buy=1,simulated_native_stop=1,restart_duplicate_buy=False,original_selection_preserved=True,actual_date_in_daily_state='2026-11-03',original_selection_id=original['selection_id'],frozen_history_sha256=ops.sha(frozen),current_history_window_has_different_sha=True,recovery_selection_id=recovery['selection_id'],symbol='LLY',notional_cap_usd=policy['max_notional_usd'])
 publish(root/'receipt.json',receipt);print(json.dumps(receipt,sort_keys=True))
