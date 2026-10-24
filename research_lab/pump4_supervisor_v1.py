"""Persistent frozen137 DATA intake and a separately selected owner's tick bridge.

The daemon never constructs a financial owner, claims the account lease, loads
credentials or dispatches. Epochs here are DATA observations, not owner authority.
The bridge accepts an already selected owner (selected_runner.selected_owner);
its caller must bind epoch/delay to that selected configuration. No new-entry
plan bypass: causal_plan runs before account reads and again immediately after.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import time

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import decode, stable_bytes
from research_lab.pump4_account_owner_v1 import safe, source_sizing
from research_lab.pump4_bybit_sources_v1 import closed_h1, universe, UNIVERSE_SHA, H
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
from research_lab.pump4_selected_runner_v1 import causal_plan, source_pins
from research_lab.pump4_server_cycle_v1 import owner_cycle


def need(ok, reason):
    if not ok:
        raise ValueError('PUMP4_SUPERVISOR_'+reason)


def read(path):
    return decode(stable_bytes(safe(path)))


def selected_tick(owner, read_account_provider, fresh_candidate_provider, *,
                  epoch_started_ms, max_delay_ms, apply=False):
    """Custody first; providers return (bundle, public) and causal inputs only.

    read_account_provider(plan, custody=bool) must fetch fresh GET evidence for
    the already selected account. A reservation without a lifecycle request is
    an ambiguous crash boundary, never permission to restart entry. No send
    retry, orphan adoption, authority minting or replacement physical lease.
    """
    owner._exclusive()
    admission = safe(owner.root/'admitted-lifecycle.json')
    if os.path.lexists(admission):
        identity = read(admission)
        flow_root=safe(identity['flow_root'])
        need(flow_root==owner.flows/identity['plan_sha256'], 'ADMISSION_PATH')
        flow = Pump4Lifecycle.resume(flow_root)
        need(identity == dict(scope_sha256=owner.scope_sha256,
            plan_sha256=flow.config['plan']['plan_sha256'],flow_root=str(flow.root),
            execution_config_sha256=digest(flow.config)), 'ADMISSION_IDENTITY')
        owner._flow(flow)
        need(bool(flow.requests()), 'ADMITTED_WITHOUT_REQUEST_RECONCILE_ONLY')
        bundle, public = read_account_provider(flow.config['plan'], custody=True)
        return owner_cycle(owner, flow.config['plan'], bundle, public, apply=apply)
    try:
        candidate = fresh_candidate_provider()
        if candidate is None:
            return dict(status='NO_NEW_SIGNAL', broker_writes=0)
        need(set(candidate) == {'intake','decision_id','captures'}, 'CAUSAL_CANDIDATE_REQUIRED')
        def plan_now():
            return causal_plan(candidate['intake'],candidate['decision_id'],candidate['captures'],
                epoch_started_ms=epoch_started_ms,max_delay_ms=max_delay_ms,now_ms=owner.clock())
        plan = plan_now()
        bundle, public = read_account_provider(plan, custody=False)
        need(plan_now() == plan, 'CAUSAL_PLAN_CHANGED')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return dict(status='BLOCKED_NEW_INPUTS',reason=str(exc),broker_writes=0)
    return owner_cycle(owner, plan, bundle, public, apply=apply)


class Supervisor:
    """Single DATA writer, persistent per-symbol cursor and immutable receipts.

    A historical archive is verified at its capture cutoff. Execution diagnostics
    use the current clock; replay never makes a source fresh. Catch-up is bounded
    by the existing source window and refuses gaps and any changed overlap.
    """
    def __init__(self, root, *, clock=None, max_delay_ms=60000, account_provider=None,
                 policy=None, fingerprint=None, alert=None):
        need(type(max_delay_ms) is int and 0<max_delay_ms<=60000, 'DELAY_POLICY')
        self.root=safe(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.clock=clock or (lambda:time.time_ns()//1000000)
        self.max_delay_ms=max_delay_ms
        self.account_provider,self.policy,self.fingerprint=account_provider,policy,fingerprint
        self.alert=alert
        binding=dict(schema='PUMP4_DATA_SUPERVISOR_V1',universe_sha256=UNIVERSE_SHA,
            source_files=source_pins(),max_delay_ms=max_delay_ms,orders_allowed=False,money_authority=False)
        path=self.root/'data-binding.json'
        try:
            publish(path,binding)
        except FileExistsError:
            need(read(path)==binding, 'DATA_BINDING_DRIFT_NO_RESET')

    @contextmanager
    def _writer(self):
        # Separate DATA lock only. Never use AccountLease or original account.lock.
        path=safe(self.root/'data-writer.lock')
        fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            need(os.fstat(fd).st_ino==path.stat().st_ino, 'DATA_LOCK_CHANGED')
            yield
        finally:
            os.close(fd)

    def _archive(self, archive):
        archive=safe(archive);raw=stable_bytes(archive/'receipt.json');seal=decode(raw)
        need(seal['schema']=='PUMP4_FROZEN137_PUBLIC_BOOTSTRAP_RECEIPT_V1'
             and seal['universe_sha256']==UNIVERSE_SHA and seal['census']==137, 'ARCHIVE_IDENTITY')
        files=seal['source_capture_files'];data={}
        for name,pin in files.items():
            path=safe(archive/name)
            need(path.is_relative_to(archive), 'ARCHIVE_PATH')
            content=stable_bytes(path)
            need(hashlib.sha256(content).hexdigest()==pin, 'ARCHIVE_HASH')
            data[name]=decode(content)
        need(all('symbols/'+s+'.json' in data for s in universe()), 'ARCHIVE_COVERAGE')
        return archive,hashlib.sha256(raw).hexdigest(),seal,data

    def _symbol(self, symbol, row, seal, archive_id):
        need(row['symbol']==symbol, 'SYMBOL_IDENTITY')
        if row['status']!='READY_H1_BOOTSTRAP_NOT_ENTRY':
            return dict(symbol=symbol,status=row['status'])
        source=closed_h1(row['captures'],symbol,next_open_ms=seal['source_hour_open_ms'],
                         observed_ms=row['source']['observed_ms'])
        need(source==row['source'], 'SOURCE_REPLAY')
        safe(self.root/'intake').mkdir(mode=0o700,exist_ok=True)
        intake=Pump4Intake(safe(self.root/'intake'/(symbol+'.jsonl')),symbol)
        events=intake.journal.read();bars=[*source['seed'],source['signal_bar']]
        epoch_path=safe(self.root/'epochs'/(symbol+'.json'))
        need(not events or epoch_path.exists(), 'EPOCH_MISSING_NO_RESET')
        bootstrap=not events
        if events:
            snapshot=intake.snapshot();cursor=snapshot['cursor_ms']
            known={b[0]:b for b in events[0]['bars']}
            known.update({e['bar'][0]:e['bar'] for e in events[1:]})
            need(all(b[0] not in known or known[b[0]]==b for b in bars), 'SOURCE_HISTORY_CONFLICT')
            pending=[b for b in bars if b[0]>cursor]
            need(not pending or pending[0][0]==cursor+H, 'SOURCE_WINDOW_GAP_NO_RESET')
        else:
            epoch=dict(schema='PUMP4_DATA_EPOCH_V1',symbol=symbol,
                epoch_started_ms=max(self.clock(),source['observed_ms'])+1,
                seed_sha256=digest(source['seed']),financial_authority=False)
            if not epoch_path.exists():publish(epoch_path,epoch)
            need(read(epoch_path)['seed_sha256']==digest(source['seed']), 'BOOTSTRAP_PREFIX_CHANGED')
            intake.seed(source['seed'],available_ms=source['available_ms'],observed_ms=source['observed_ms'])
            pending=[source['signal_bar']]
        epoch=read(epoch_path)
        need(epoch['schema']=='PUMP4_DATA_EPOCH_V1' and epoch['symbol']==symbol
            and epoch['financial_authority'] is False
            and epoch['seed_sha256']==intake.snapshot()['seed_bars_sha256']
            and type(epoch['epoch_started_ms']) is int
            and intake.journal.read()[0]['observed_ms']<epoch['epoch_started_ms'], 'EPOCH_IDENTITY')
        mode='BOOTSTRAP_REPLAY' if bootstrap else ('CATCHUP_REPLAY' if len(pending)>1 else 'CURRENT_CLOSED_BAR')
        batch_path=safe(self.root/'batches'/archive_id/(symbol+'.json'))
        recovered=batch_path.exists()
        if recovered:
            batch=read(batch_path)
            need(batch['symbol']==symbol and batch['archive_id']==archive_id, 'BATCH_IDENTITY')
            mode=batch['mode'];pending=batch['bars']
        else:
            batch=dict(symbol=symbol,archive_id=archive_id,mode=mode,bars=pending)
            publish(batch_path,batch)
        decisions=[]
        for bar in pending:
            result=intake.accept(bar,available_ms=source['available_ms'],observed_ms=source['observed_ms'])
            decision=result['decision'];path=safe(self.root/'observations'/(decision['decision_id']+'.json'))
            if path.exists():
                observation=read(path)
                need(observation['decision']==decision,'OBSERVATION_IDENTITY')
            else:
                observation=dict(schema='PUMP4_DATA_DECISION_OBSERVATION_V1',decision=decision,
                    archive_id=archive_id,mode='RECOVERY_REPLAY' if recovered else mode,
                    status='NO_SIGNAL' if decision['signal'] is None else 'REPLAY_NOT_PROSPECTIVE',
                    orders_allowed=False,money_authority=False)
                if decision['signal'] and mode=='CURRENT_CLOSED_BAR' and not recovered and result['new']:
                    epoch=read(epoch_path)
                    try:
                        plan=causal_plan(intake,decision['decision_id'],row['captures'],
                            epoch_started_ms=epoch['epoch_started_ms'],max_delay_ms=self.max_delay_ms,now_ms=self.clock())
                        observation.update(status='CAUSAL_PLAN_DATA_ONLY',plan=plan)
                        if self.account_provider is not None:
                            bundle,public=self.account_provider(plan,custody=False)
                            # Reader latency cannot extend the entry window.
                            causal_plan(intake,decision['decision_id'],row['captures'],
                                epoch_started_ms=epoch['epoch_started_ms'],max_delay_ms=self.max_delay_ms,now_ms=self.clock())
                            observation['sizing']=source_sizing(plan,bundle,public,self.policy,
                                fingerprint=self.fingerprint,now_ms=self.clock())
                    except (ValueError,KeyError,TypeError,OSError) as exc:
                        observation.update(status='BLOCKED_ENTRY_DIAGNOSTIC',reason=str(exc))
                publish(path,observation)
            decisions.append(observation)
        return dict(symbol=symbol,status='CLOSED_H1_INTAKE_PASS',mode=mode,accepted_bars=len(pending),
            cursor_ms=intake.snapshot()['cursor_ms'],decisions=decisions)

    def process_archive(self, archive):
        archive,archive_id,seal,data=self._archive(archive)
        with self._writer():
            receipt_path=safe(self.root/'cycles'/(archive_id+'.json'))
            if receipt_path.exists():
                receipt=read(receipt_path)
                self._notify(receipt)
                return receipt
            rows=[]
            for symbol in universe():
                try:
                    result=self._symbol(symbol,data['symbols/'+symbol+'.json'],seal,archive_id)
                except (ValueError,KeyError,TypeError,OSError) as exc:
                    result=dict(symbol=symbol,status='BLOCKED_SOURCE',reason=str(exc))
                rows.append(result)
            receipt=dict(schema='PUMP4_PERSISTENT_DATA_CYCLE_V1',status='ORDERS_OFF_DATA_ONLY',
                archive_id=archive_id,source_archive=str(archive),source_hour_open_ms=seal['source_hour_open_ms'],
                census=len(rows),rows=rows,source_intake_pass=sum(r['status']=='CLOSED_H1_INTAKE_PASS' for r in rows),
                financial_owner_constructed=False,original_account_lease_acquired=False,
                prospective_decisions_credited=0,broker_writes=0,orders_allowed=False,money_authority=False,tiny_ready=False)
            publish(receipt_path,receipt)
            self._notify(receipt)
            return receipt

    def _notify(self,receipt):
        if self.alert is not None:
            from research_lab.kity_fresh_eligibility_watch_v1 import notify_once
            for result in receipt['rows']:
                for observation in result.get('decisions',[]):
                    if observation['decision']['signal'] is None:
                        continue
                    event=dict(terminal_id=observation['decision']['decision_id'],
                        observed_ms=observation['decision']['first_observed_ms'],
                        status=observation['status'],symbol=result['symbol'],broker_writes=0,money_authority=False)
                    target=safe(self.root/'alerts'/event['terminal_id'])
                    try:publish(target/'terminal.json',event)
                    except FileExistsError:need(read(target/'terminal.json')==event,'ALERT_IDENTITY')
                    notify_once(target,event,self.alert)

    def public_cycle(self, *, collector=None):
        """At most one full existing capture per UTC hour, including restarts.

        A partial capture is preserved and blocked for that hour. Next hour can
        recover bars from the source window; no in-place archive repair/reset.
        """
        if collector is None:
            from scripts.capture_pump4_sources_v1 import capture
            collector=capture
        hour=self.clock()//H*H
        archive=safe(self.root/'archives'/str(hour))
        with self._writer():
            if not archive.exists():
                collector(archive)
            need((archive/'receipt.json').is_file(), 'PARTIAL_ARCHIVE_PRESERVED_UNTIL_NEXT_HOUR')
        return self.process_archive(archive)
