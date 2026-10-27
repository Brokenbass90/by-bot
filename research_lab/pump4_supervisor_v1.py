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
import json
import resource
import selectors
import stat
import subprocess
import sys
import time

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_oct15_deadline_v1 import decode, stable_bytes
from research_lab.pump4_account_owner_v1 import safe, source_sizing
from research_lab.pump4_bybit_sources_v1 import closed_h1, checked, universe, UNIVERSE_SHA, H
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake, _closed
from research_lab.att1_lifecycle_journal import SCHEMA
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
from research_lab.pump4_selected_runner_v1 import causal_plan, source_pins
from research_lab.pump4_server_cycle_v1 import owner_cycle

ROOT=Path(__file__).resolve().parents[1]
CAPTURE_PROCESS_TIMEOUT_SECONDS=600


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

    @staticmethod
    def _warm_accept(intake,bar,*,available_ms,observed_ms):
        # Same frozen event and validator as accept(). The normal single-bar
        # caller already verified its prefix; validate again under append lock,
        # never substitute a cached result for the locked producer replay.
        _closed(bar,available_ms,observed_ms)
        event=dict(schema_id=SCHEMA,event_id='pump4:'+intake.symbol+':'+str(bar[0]),
            **intake._context(),kind='CLOSED_BAR',bar=bar,
            available_ms=available_ms,observed_ms=observed_ms)
        new,state=intake.journal.append_checked(event,intake._replay)
        decision=next(d for d in state['decisions'] if d['bar_open_ms']==bar[0])
        return dict(new=new,decision=decision),state['cursor_ms']

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
        batch_path=safe(self.root/'batches'/archive_id/(symbol+'.json'))
        if events:
            # For one contiguous current bar, the locked append below replays
            # and validates the ENTIRE producer prefix before any journal write.
            # Only scheduling/overlap/epoch inputs are derived here; no cached
            # strategy result, decision or source clock can authorize admission.
            tail=events[-1]
            cursor=tail['bar'][0] if tail.get('kind')=='CLOSED_BAR' else None
            one_current=(type(cursor) is int and not batch_path.exists()
                and source['signal_bar'][0]==cursor+H
                and sum(b[0]>cursor for b in bars)==1)
            if one_current:
                snapshot=dict(cursor_ms=cursor,seed_bars_sha256=digest(events[0]['bars']))
            else:
                snapshot=intake._replay(events);cursor=snapshot['cursor_ms']
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
            snapshot=intake.seed(source['seed'],available_ms=source['available_ms'],observed_ms=source['observed_ms'])
            pending=[source['signal_bar']]
        epoch=read(epoch_path)
        need(epoch['schema']=='PUMP4_DATA_EPOCH_V1' and epoch['symbol']==symbol
            and epoch['financial_authority'] is False
            and epoch['seed_sha256']==snapshot['seed_bars_sha256']
            and type(epoch['epoch_started_ms']) is int
            and (events[0]['observed_ms'] if events else source['observed_ms'])<epoch['epoch_started_ms'], 'EPOCH_IDENTITY')
        mode='BOOTSTRAP_REPLAY' if bootstrap else ('CATCHUP_REPLAY' if len(pending)>1 else 'CURRENT_CLOSED_BAR')
        recovered=batch_path.exists()
        if recovered:
            batch=read(batch_path)
            need(batch['symbol']==symbol and batch['archive_id']==archive_id, 'BATCH_IDENTITY')
            mode=batch['mode'];pending=batch['bars']
        else:
            batch=dict(symbol=symbol,archive_id=archive_id,mode=mode,bars=pending)
            publish(batch_path,batch)
        decisions=[];warm_cursor=None
        warm_current=bool(events) and not recovered and mode=='CURRENT_CLOSED_BAR' and len(pending)==1
        for bar in pending:
            if warm_current:
                result,warm_cursor=self._warm_accept(intake,bar,available_ms=source['available_ms'],observed_ms=source['observed_ms'])
            else:
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
            cursor_ms=warm_cursor if warm_cursor is not None else intake.snapshot()['cursor_ms'],decisions=decisions)

    def _stream_context(self, archive):
        """Verify a collector-sealed prefix, never claim complete coverage early."""
        archive=safe(archive);raw=stable_bytes(safe(archive/'capture-context.json'));header=decode(raw)
        need(header['schema']=='PUMP4_PUBLIC_CAPTURE_CONTEXT_V1'
            and header['universe_sha256']==UNIVERSE_SHA and header['census']==137
            and header['orders_allowed'] is False and header['money_authority'] is False,
            'STREAM_CONTEXT_IDENTITY')
        pins=header['source_capture_files']
        need(set(pins)=={'clock.json','instrument-pages.json','tickers.json'},'STREAM_CONTEXT_FILES')
        documents={}
        for name,pin in pins.items():
            value=stable_bytes(safe(archive/name))
            need(hashlib.sha256(value).hexdigest()==pin,'STREAM_CONTEXT_HASH')
            documents[name]=decode(value)
        clock=documents['clock.json'];checked(clock,'/v5/market/time',now_ms=clock['receive_ms'],private=False)
        need(type(header['source_hour_open_ms']) is int
            and header['source_hour_open_ms']==clock['body']['time']//H*H,'STREAM_CONTEXT_HOUR')
        pages=documents['instrument-pages.json'];need(pages.get('complete') is True
            and 0<len(pages['pages'])<=8,'STREAM_METADATA_INCOMPLETE')
        for cap in pages['pages']:checked(cap,'/v5/market/instruments-info',now_ms=cap['receive_ms'],private=False)
        need(pages['pages'][-1]['body']['result'].get('nextPageCursor','')=='','STREAM_METADATA_CURSOR')
        ticker=documents['tickers.json'];checked(ticker,'/v5/market/tickers',now_ms=ticker['receive_ms'],private=False)
        return hashlib.sha256(raw).hexdigest(),header

    def _stream_symbol(self, archive, symbol, context, *, expected_sha256=None):
        """Same intake/batch/recovery rules, sealed individually before census."""
        need(symbol in universe(),'STREAM_SYMBOL')
        context_id,header=context
        binding_path=safe(self.root/'stream-archives'/(digest(str(archive))+'.json'))
        binding=dict(archive=str(archive),context_sha256=context_id)
        try:publish(binding_path,binding)
        except FileExistsError:need(read(binding_path)==binding,'STREAM_CONTEXT_CHANGED')
        raw=stable_bytes(safe(archive/'symbols'/(symbol+'.json')))
        pin=hashlib.sha256(raw).hexdigest()
        need(expected_sha256 is None or pin==expected_sha256,'STREAM_FULL_SEAL_CAPTURE_CHANGED')
        receipt_path=safe(self.root/'streamed'/context_id/(symbol+'.json'))
        if receipt_path.exists():
            previous=read(receipt_path)
            need(previous['context_sha256']==context_id and previous['symbol']==symbol
                and previous['capture_sha256']==pin,'STREAM_CAPTURE_CHANGED')
            return previous['result']
        identity=digest(dict(context_sha256=context_id,symbol=symbol,capture_sha256=pin))
        try:result=self._symbol(symbol,decode(raw),header,identity)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            result=dict(symbol=symbol,status='BLOCKED_SOURCE',reason=str(exc))
        # Conservative completion time follows the observation's fsync; no
        # first-observed/source clock is changed to make a delayed row fresh.
        publish(receipt_path,dict(schema='PUMP4_STREAMED_SYMBOL_RECEIPT_V1',
            context_sha256=context_id,symbol=symbol,capture_sha256=pin,
            publication_completed_ms=self.clock(),result=result,
            coverage_complete=False,broker_writes=0,orders_allowed=False,money_authority=False))
        return result

    def process_archive(self, archive):
        archive,archive_id,seal,data=self._archive(archive)
        context=None
        if 'capture-context.json' in data:
            context=self._stream_context(archive);context_id,header=context
            need(context_id==seal['source_capture_files']['capture-context.json']
                and header['source_hour_open_ms']==seal['source_hour_open_ms']
                and all(seal['source_capture_files'].get(n)==h for n,h in header['source_capture_files'].items()),
                'STREAM_FINAL_CONTEXT_CONFLICT')
        with self._writer():
            receipt_path=safe(self.root/'cycles'/(archive_id+'.json'))
            if receipt_path.exists():
                receipt=read(receipt_path)
                self._notify(receipt)
                return receipt
            rows=[]
            for symbol in universe():
                try:
                    if context is None:
                        result=self._symbol(symbol,data['symbols/'+symbol+'.json'],seal,archive_id)
                    else:
                        # _archive already checked all bytes against full seal.
                        # A changed streamed row is fatal, never silently replayed.
                        result=self._stream_symbol(archive,symbol,context,
                            expected_sha256=seal['source_capture_files']['symbols/'+symbol+'.json'])
                except (ValueError,KeyError,TypeError,OSError) as exc:
                    if context is not None:raise
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

    def _catchup_reference(self,archive,symbol,context,pin):
        """Advisory scheduling only; unchanged _symbol still validates producer."""
        try:
            # An UNVERIFIED bounded tail can only choose the immediate path.
            # Actual _stream_symbol/_symbol still performs every hash, source,
            # journal and producer check. No hint can authorize a publication.
            path=safe(self.root/'intake'/(symbol+'.jsonl'))
            if path.is_file():
                with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as f:
                    st=os.fstat(f.fileno());need(stat.S_ISREG(st.st_mode),'PRIORITY_HINT_FILE')
                    f.seek(max(0,st.st_size-8192));tail=f.read(8192)
                if tail.endswith(b'\n'):
                    try:
                        last=decode(tail.splitlines()[-1])['event'];cursor=last['bar'][0]
                        if (last['kind']=='CLOSED_BAR' and type(cursor) is int and cursor%H==0
                            and cursor>=context[1]['source_hour_open_ms']-2*H):return None
                    except (ValueError,KeyError,TypeError,IndexError):pass
            raw=stable_bytes(safe(archive/'symbols'/(symbol+'.json')))
            need(hashlib.sha256(raw).hexdigest()==pin,'PRIORITY_CAPTURE_HASH')
            row=decode(raw)
            if row['status']!='READY_H1_BOOTSTRAP_NOT_ENTRY':return None
            path=safe(self.root/'intake'/(symbol+'.jsonl'))
            if not path.is_file():return None
            original=stable_bytes(path);intake=Pump4Intake(path,symbol);events=intake.journal.read()
            if len(events)<2 or events[-1].get('kind')!='CLOSED_BAR':return None
            cursor=events[-1]['bar'][0]
            if row['source']['signal_bar'][0]<=cursor+H:return None
            need(stable_bytes(path)==original,'PRIORITY_JOURNAL_RACE')
            expected=intake._context();need(all(all(e.get(k)==v for k,v in expected.items()) for e in events),'PRIORITY_CONTEXT')
            source=closed_h1(row['captures'],symbol,next_open_ms=context[1]['source_hour_open_ms'],observed_ms=row['source']['observed_ms'])
            need(source==row['source'],'PRIORITY_SOURCE')
            known={b[0]:b for b in events[0]['bars']};known.update({e['bar'][0]:e['bar'] for e in events[1:]})
            bars=[*source['seed'],source['signal_bar']];pending=[b for b in bars if b[0]>cursor]
            need(len(pending)>1 and pending[0][0]==cursor+H and all(b[0] not in known or known[b[0]]==b for b in bars),'PRIORITY_OVERLAP')
            ep=safe(self.root/'epochs'/(symbol+'.json'));epoch_raw=stable_bytes(ep);epoch=decode(epoch_raw)
            need(epoch['schema']=='PUMP4_DATA_EPOCH_V1' and epoch['symbol']==symbol and epoch['financial_authority'] is False
                and epoch['seed_sha256']==digest(events[0]['bars']) and type(epoch['epoch_started_ms']) is int
                and events[0]['observed_ms']<epoch['epoch_started_ms'],'PRIORITY_EPOCH')
            identity=digest(dict(context_sha256=context[0],symbol=symbol,capture_sha256=pin))
            if (self.root/'batches'/identity/(symbol+'.json')).exists():return None
            return dict(journal_sha256=hashlib.sha256(original).hexdigest(),epoch_sha256=hashlib.sha256(epoch_raw).hexdigest(),archive_id=identity)
        except (ValueError,KeyError,TypeError,OSError):return None

    def _capture_process(self,archive,on_symbol,hour):
        """Public archive child only; this parent remains the sole journal writer."""
        command=[sys.executable,'-B',str(ROOT/'scripts/capture_pump4_sources_v1.py'),
            '--capture','--root',str(archive),'--stream-symbols']
        env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',
            OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        start=self.clock();usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        before_cpu=usage.ru_utime+usage.ru_stime;deadline=time.monotonic()+CAPTURE_PROCESS_TIMEOUT_SECONDS
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,env=env,close_fds=True,bufsize=0,cwd=str(ROOT))
        selector=selectors.DefaultSelector();buffer=b'';seen=set();stderr=b'';stderr_bytes=0;notice_times=[];deferred=[];context=None;classification_starts={}
        def run_notice(symbol,pin,received,classified,index,scheduling):
            begun=self.clock();on_symbol(archive,symbol,expected_sha256=pin)
            notice_times.append(dict(symbol=symbol,notice_index=index,parent_received_ms=received,
                classification_completed_ms=classified,parent_processing_started_ms=begun,
                classification_started_ms=classification_starts[symbol],
                parent_publication_finished_ms=self.clock(),scheduling=scheduling))
        try:
            for kind,pipe in (('out',process.stdout),('err',process.stderr)):
                os.set_blocking(pipe.fileno(),False);selector.register(pipe,selectors.EVENT_READ,kind)
            while selector.get_map():
                need(time.monotonic()<deadline,'CAPTURE_PROCESS_TIMEOUT')
                for key,_ in selector.select(min(.25,max(0,deadline-time.monotonic()))):
                    chunk=os.read(key.fd,4096)
                    if not chunk:selector.unregister(key.fileobj);continue
                    received=self.clock()
                    if key.data=='err':
                        stderr_bytes+=len(chunk);need(stderr_bytes<=1048576,'CAPTURE_STDERR_LIMIT')
                        stderr=(stderr+chunk)[-65536:];continue
                    buffer+=chunk
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1);need(0<len(line)<=1024,'CAPTURE_NOTICE_SIZE')
                        notice=decode(line)
                        need(isinstance(notice,dict) and set(notice)=={'schema','symbol','capture_sha256'}
                            and notice['schema']=='PUMP4_PUBLIC_SYMBOL_NOTICE_V1','CAPTURE_NOTICE_SCHEMA')
                        symbol=notice['symbol'];pin=notice['capture_sha256']
                        need(type(symbol) is str and symbol in universe() and symbol not in seen and len(seen)<137,'CAPTURE_NOTICE_SYMBOL')
                        need(type(pin) is str and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'CAPTURE_NOTICE_HASH')
                        seen.add(symbol)
                        if context is None:context=self._stream_context(archive)
                        need(context[1]['source_hour_open_ms']==hour,'STREAM_PARENT_HOUR')
                        classification_starts[symbol]=self.clock()
                        reference=self._catchup_reference(archive,symbol,context,pin);classified=self.clock();index=len(seen)
                        if reference is not None:deferred.append((symbol,pin,received,classified,index,reference))
                        else:run_notice(symbol,pin,received,classified,index,'IMMEDIATE')
                    need(len(buffer)<=1024,'CAPTURE_NOTICE_SIZE')
            need(not buffer,'CAPTURE_NOTICE_TRUNCATED')
            remaining=max(.01,deadline-time.monotonic())
            try:code=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:raise ValueError('PUMP4_SUPERVISOR_CAPTURE_PROCESS_TIMEOUT')
            need(code==0 and len(seen)==137 and (archive/'receipt.json').is_file(),'CAPTURE_PROCESS_INCOMPLETE')
            if deferred:
                _,_,seal,_=self._archive(archive)
                need(seal['source_hour_open_ms']==hour and seal['source_capture_files'].get('capture-context.json')==context[0]
                    and all(seal['source_capture_files'].get(n)==h for n,h in context[1]['source_capture_files'].items()),'PRIORITY_FINAL_CONTEXT')
            for symbol,pin,received,classified,index,reference in deferred:
                need(time.monotonic()<deadline,'CAPTURE_PROCESS_TIMEOUT')
                need(hashlib.sha256(stable_bytes(safe(self.root/'intake'/(symbol+'.jsonl')))).hexdigest()==reference['journal_sha256']
                    and hashlib.sha256(stable_bytes(safe(self.root/'epochs'/(symbol+'.json')))).hexdigest()==reference['epoch_sha256']
                    and not (self.root/'batches'/reference['archive_id']/(symbol+'.json')).exists(),'PRIORITY_DEFERRED_STATE_CHANGED')
                run_notice(symbol,pin,received,classified,index,'DEFERRED_CATCHUP_NON_ENTRY')
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            publish(self.root/'capture-process'/(str(hour)+'.json'),
                dict(schema='PUMP4_PUBLIC_CAPTURE_PROCESS_RECEIPT_V1',source_hour_open_ms=hour,
                    child_pid=process.pid,child_returncode=code,child_cpu_seconds=usage.ru_utime+usage.ru_stime-before_cpu,
                    parent_pid=os.getpid(),parent_started_ms=start,parent_completed_ms=self.clock(),
                    symbols=137,notices=sorted(notice_times,key=lambda n:n['notice_index']),deferred_catchup_count=len(deferred),stderr_bytes=stderr_bytes,
                    stderr_tail=stderr.decode('utf-8',errors='replace').encode('utf-8')[-65536:].decode('utf-8',errors='ignore'),
                    financial_owner_constructed=False,broker_writes=0))
        except BaseException as exc:
            try:
                publish(self.root/'capture-process-failures'/(str(hour)+'.json'),
                    dict(schema='PUMP4_PUBLIC_CAPTURE_PROCESS_FAILURE_V1',source_hour_open_ms=hour,
                        child_pid=process.pid,child_returncode=process.poll(),observed_ms=self.clock(),
                        error_type=type(exc).__name__,notice_count=len(seen),stderr_bytes=stderr_bytes,
                        stderr_tail=stderr.decode('utf-8',errors='replace').encode('utf-8')[-65536:].decode('utf-8',errors='ignore'),
                        incomplete_preserved=True,broker_writes=0))
            except (ValueError,OSError):pass # attempt marker still prohibits a same-hour retry
            raise
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()

    def public_cycle(self, *, collector=None):
        """At most one full existing capture per UTC hour, including restarts.

        A partial capture is preserved and blocked for that hour. Next hour can
        recover bars from the source window; no in-place archive repair/reset.
        """
        hour=self.clock()//H*H
        archive=safe(self.root/'archives'/str(hour))
        attempt=safe(self.root/'capture-attempts'/(str(hour)+'.json'))
        complete=safe(self.root/'capture-complete'/(str(hour)+'.json'))
        with self._writer():
            need(not attempt.exists() or complete.exists(),'PARTIAL_ARCHIVE_PRESERVED_UNTIL_NEXT_HOUR')
            if not archive.exists():
                publish(attempt,dict(source_hour_open_ms=hour,started_ms=self.clock(),money_authority=False))
                context=None
                def completed(path,symbol,*,expected_sha256=None):
                    nonlocal context
                    need(safe(path)==archive,'STREAM_ARCHIVE_PATH')
                    if context is None:context=self._stream_context(archive)
                    need(context[1]['source_hour_open_ms']==hour,'STREAM_PARENT_HOUR')
                    self._stream_symbol(archive,symbol,context,expected_sha256=expected_sha256)
                if collector is None:self._capture_process(archive,completed,hour)
                else:collector(archive,on_symbol=completed)
                publish(complete,dict(source_hour_open_ms=hour,completed_ms=self.clock(),money_authority=False))
            need((archive/'receipt.json').is_file(), 'PARTIAL_ARCHIVE_PRESERVED_UNTIL_NEXT_HOUR')
        return self.process_archive(archive)
