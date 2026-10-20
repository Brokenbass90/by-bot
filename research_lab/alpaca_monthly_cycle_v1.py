"""One Monthly source/book/manager binding. No scheduler or money activation.

The installed CLI invokes only source and preview. Applying methods require an
explicit native client and its existing native/Monthly owner checks; tests pass
a broker whose HTTP implementation never leaves memory.
"""
from contextlib import contextmanager
import fcntl
import json
import os
import time
from pathlib import Path
import uuid

from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_monthly_binding_v1 import MonthlyBook,CONTRACT
from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding,STANDING_SCHEMA
from research_lab.alpaca_dynamic_v1 import digest,positive
from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
from research_lab.kity_oct15_deadline_v1 import publish_once

SCHEMA='ALPACA_MONTHLY_OWNED_CYCLE_V1'


def publish(path,value):
    publish_once(Path(path),(json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode())


class MonthlyManager:
    def __init__(self,root,*,account_id,capital,account_lock_path,entry_halt_path):
        self.root=ops.safe_path(root);self.account=account_id;self.capital=str(positive(capital))
        if positive(capital)>positive(CONTRACT['capital_ceiling_usd']):raise ValueError('CYCLE_CAPITAL_CAP')
        self.lock=ops.safe_path(account_lock_path);self.halt=ops.safe_path(entry_halt_path)
        if not isinstance(account_id,str) or not account_id:raise ValueError('CYCLE_ACCOUNT_REQUIRED')
        self.identity=dict(schema=SCHEMA,account_id=account_id,capital=self.capital,
            account_lock_path=str(self.lock),entry_halt_path=str(self.halt),contract_sha256=digest(CONTRACT))
        marker=self.root/'cycle-identity.json'
        if self.root.exists() and any(self.root.iterdir()) and not marker.is_file():
            raise ValueError('CYCLE_IDENTITY_FOREIGN_ROOT')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not marker.exists():publish(marker,self.identity)
        if json.loads(marker.read_bytes())!=self.identity:raise ValueError('CYCLE_IDENTITY_CHANGED')
        (self.root/'observations').mkdir(exist_ok=True,mode=0o700)
        (self.root/'tickets').mkdir(exist_ok=True,mode=0o700)

    @contextmanager
    def guard(self,name='cycle.lock'):
        if name not in {'cycle.lock','dispatch.lock'}:raise ValueError('CYCLE_LOCK_NAME')
        fd=os.open(self.root/name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    @property
    def book(self):
        p=self.root/'book/monthly-orders-off.sqlite'
        if not p.is_file():raise ValueError('CYCLE_SOURCE_REQUIRED')
        return MonthlyBook(p,CONTRACT)

    def native(self,client,*,base_url,**scope):
        return MonthlyNativeBinding(self.book,client=client,base_url=base_url,account_id=self.account,
            capital=self.capital,runtime=self.root/'native',lock_path=self.lock,entry_halt_path=self.halt,**scope)

    def _record(self,kind,out,now_ms):
        publish(self.root/'observations'/(str(now_ms)+'-'+uuid.uuid4().hex+'.json'),
            dict(schema=SCHEMA,operation=kind,observed_ms=now_ms,result=out,identity_sha256=digest(self.identity)))
        return out

    def _custody(self,native):
        runtime=self.root/'native'
        if (native.book.path!=self.book.path or native.lock_path!=self.lock or native.halt!=self.halt
            or native.account!=self.account or positive(native.capital)!=positive(self.capital)
            or native.runtime!=runtime or native.ledger!=runtime/'native-floor.json'
            or native.reentry!=runtime/'native-intents.json'):
            raise ValueError('CYCLE_NATIVE_CUSTODY_CONFLICT')

    def source(self,bundle,*,now_ms):
        with self.guard():
            out=ops.bind_source(self.root/'book',bundle,now_ms=now_ms)
            return self._record('SOURCE',out,now_ms)

    def preview(self,*,now_ms):
        with self.guard():
            if not (self.root/'book/monthly-orders-off.sqlite').is_file():
                return self._record('PREVIEW',dict(status='WAITING_COMPLETED_SOURCE',broker_writes=0,
                    orders_allowed=False,money_authority=False),now_ms)
            book=self.book;selections=book.rows('selections');plans=[]
            for s in selections:
                row=next(r for r in s['calendar'] if r['session']==s['entry_session'])
                if row['open_ms']<=now_ms<row['open_ms']+300000:
                    plans.append(book.monthly_actions(s['selection_id'],now_ms=now_ms))
            out=dict(status='MONTHLY_MANAGER_PREVIEW_ORDERS_OFF',plans=plans,
                stops=book.stop_actions(now_ms=now_ms),positions=len(book.rows('positions')),
                broker_writes=0,orders_allowed=False,money_authority=False,
                source_and_financial_book=str(book.path),entry_halt_present=self.halt.exists())
            return self._record('PREVIEW',out,now_ms)

    def opening(self,native,history,selection_id,*,quotes,now_ms,apply=False,symbols=None,before_entry=None):
        if type(apply) is not bool:raise ValueError('CYCLE_EXPLICIT_BOOLEAN_REQUIRED')
        self._custody(native)
        started=time.monotonic();clock=lambda:now_ms+int((time.monotonic()-started)*1000)
        with self.guard():
            selected=next(s for s in self.book.rows('selections') if s['selection_id']==selection_id)
            allowed={p['symbol'] for p in selected['picks']}
            if symbols is not None:
                if not isinstance(symbols,list) or len(set(symbols))!=len(symbols) or not set(symbols)<=allowed:
                    raise ValueError('CYCLE_SELECTED_SCOPE_REQUIRED')
                allowed=set(symbols)
            entry_block=None;scope=None
            if apply and native.base_url=='https://api.alpaca.markets':
                scope=native._live_custody()
                if scope['schema']==STANDING_SCHEMA:
                    try:native._standing_entry_state(scope,clock())
                    except ValueError as exc:allowed.clear();entry_block=str(exc)
                else:allowed&={scope['symbol']}
            entries=json.loads(native.reentry.read_bytes()).get('entry_intents',{}) if native.reentry.exists() else {}
            recovered=[];handled=set()
            # Reconcile the exact pre-dispatch ticket BEFORE rotation validates
            # fully protected state. A lost stop response may leave a durable
            # pending native record which rotation must never treat as owned
            # protected inventory or delete.
            for path in sorted((self.root/'tickets').glob('*.json')):
                saved=json.loads(ops.safe_path(path).read_bytes())
                if (saved['selection_id']==selection_id
                    and (saved['symbol'] in allowed or saved['client_order_id'] in entries)):
                    recovered.append(native.enter(saved,now_ms=clock(),apply=apply))
                    handled.add(saved['symbol'])
            plan=native.rotate(selection_id,now_ms=clock(),apply=apply)
            actions=self.book.monthly_actions(selection_id,now_ms=clock())
            tickets=[];results=list(recovered)
            for symbol in actions.get('new_symbols',[]):
                if symbol not in allowed or symbol in handled:continue
                if scope:
                    entries=json.loads(native.reentry.read_bytes()).get('entry_intents',{}) if native.reentry.exists() else {}
                    used=sum(1 for i in entries.values() if i.get('entry_session')==selected['entry_session'])
                    if used>=scope['max_new_entries_per_session']:
                        entry_block='MONTHLY_SESSION_ENTRY_ALREADY_CONSUMED';break
                if apply and before_entry:before_entry()
                account=native.client.get_account()
                ticket=native.prepare_entry(history,selection_id,symbol,quote=quotes[symbol],now_ms=clock(),
                    cash=account['cash'],open_equity=account['equity'])
                tickets.append(ticket)
                if ticket['status']=='MONTHLY_NATIVE_ENTRY_PREPARED_ORDERS_OFF':
                    path=self.root/'tickets'/(ticket['client_order_id']+'.json')
                    if path.exists():
                        if json.loads(path.read_bytes())!=ticket:raise ValueError('CYCLE_TICKET_REVISION')
                    elif apply:publish(path,ticket)
                    results.append(native.enter(ticket,now_ms=clock(),apply=apply))
                else:results.append(ticket)
            return self._record('OPENING',dict(status='MONTHLY_OPENING_CYCLE',rotation=plan,
                tickets=tickets,results=results,entry_block=entry_block,
                orders_allowed=False,money_authority=False),clock())

    def maintain(self,native,*,now_ms,apply=False):
        self._custody(native)
        with self.guard():return self._record('MAINTAIN',native.maintain(now_ms=now_ms,apply=apply),now_ms)

    def finalize(self,native,entry_id,cost_source,*,now_ms):
        self._custody(native)
        with self.guard():return self._record('ACCOUNTING',native.finalize_exit(entry_id,cost_source,now_ms=now_ms),now_ms)

    def recover(self,native,*,now_ms,apply=False):
        """Only durable dispatched CIDs, across ALL selections; never resend a buy."""
        self._custody(native)
        if type(apply) is not bool:raise ValueError('CYCLE_EXPLICIT_BOOLEAN_REQUIRED')
        if not apply:return []
        started=time.monotonic();clock=lambda:now_ms+int((time.monotonic()-started)*1000)
        with self.guard():
            # Reconcile a native rotation committed before the Monthly journal.
            # Never hold the account lock around enter(), which takes it itself.
            with account_lock(dict(lock_path=str(native.lock_path))):
                native._native_authority()
                native._recover_rotation_receipts(now_ms=clock(),known_only=True)
            entries=json.loads(ops.safe_path(native.reentry).read_bytes()).get('entry_intents',{}) if native.reentry.exists() else {}
            ledger=json.loads(ops.safe_path(native.ledger).read_bytes()) if native.ledger.exists() else {}
            owned={r['entry_id'] for r in self.book.rows('positions')};out=[]
            for cid,item in entries.items():
                missing=any(r.get('entry_order_id')==item.get('entry_order_id') for r in ledger.values()) and item.get('entry_order_id') not in owned
                if item.get('status')=='complete' and not missing:continue
                path=ops.safe_path(self.root/'tickets'/(cid+'.json'))
                if not path.is_file():raise ValueError('CYCLE_PENDING_TICKET_MISSING')
                saved=json.loads(path.read_bytes())
                if saved['client_order_id']!=cid:raise ValueError('CYCLE_RECOVERY_TICKET_IDENTITY')
                out.append(native.enter(saved,now_ms=clock(),apply=True))
            return out

    def tick(self,native,*,now_ms,source_loader=None,quotes=None,cost_sources=None,
             apply=False,notifications=None,sender=None):
        """One existing owner: recover, protect, reconcile, source, monthly entry.

        Cost sources are accepted external immutable reconciliation files, never
        inferred from empty activities or flatness. Default does no broker I/O.
        """
        if type(apply) is not bool:raise ValueError('CYCLE_EXPLICIT_BOOLEAN_REQUIRED')
        self._custody(native)
        if not apply:return self.preview(now_ms=now_ms)
        started=time.monotonic();clock=lambda:now_ms+int((time.monotonic()-started)*1000)
        out=dict(status='MONTHLY_STANDING_DISPATCH_TICK',recovered=[],maintenance=None,
            source=None,accounting=[],opening=None,issues=[],entry_status='NO_SOURCE',
            orders_allowed=False,money_authority=False)
        def attempt(phase,fn):
            try:return fn()
            except Exception as exc:
                out['issues'].append(dict(phase=phase,code=type(exc).__name__,reason=str(exc)))
                return None
        with self.guard('dispatch.lock'):
            out['recovered']=attempt('RECOVERY',lambda:self.recover(native,now_ms=clock(),apply=True)) or []
            out['maintenance']=attempt('MAINTENANCE',lambda:self.maintain(native,now_ms=clock(),apply=True))
            def finality(*,guarded=False):
                import sqlite3
                sources=cost_sources(self.book.rows('exits')) if callable(cost_sources) else cost_sources or {}
                native.pending_fee_sources={}
                for exited in self.book.rows('exits'):
                    eid=exited['entry_id'];identity=digest(dict(schema=CONTRACT['schema'],entry_id=eid))
                    p=native.runtime/'safety'/identity/'live.sqlite';done=False
                    if p.is_file():
                        with sqlite3.connect(ops.safe_path(p).as_uri()+'?mode=ro',uri=True) as db:
                            row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
                        done=bool(row and json.loads(row[0]).get('cost_finality'))
                    if not done and eid in sources:
                        document=json.loads(ops.safe_path(sources[eid]).read_bytes())
                        if document.get('schema')=='ALPACA_MONTHLY_PENDING_FEE_ESTIMATE_V1':
                            native.pending_fee_sources[eid]=sources[eid]
                        else:
                            # opening() already holds cycle.lock. The native
                            # finalizer still takes the original account lock.
                            out['accounting'].append(native.finalize_exit(eid,sources[eid],now_ms=clock())
                                if guarded else self.finalize(native,eid,sources[eid],now_ms=clock()))
                native._require_admission_accounting(now_ms=clock())
            attempt('ACCOUNTING',finality)
            bundle=attempt('SOURCE',source_loader) if source_loader else None
            if bundle is not None:
                out['source']=attempt('SOURCE_BIND',lambda:self.source(bundle,now_ms=clock()))
            if not out['issues'] and bundle is not None and out['source'] is not None:
                selections=[s for s in self.book.rows('selections') if any(
                    r['session']==s['entry_session'] and r['open_ms']<=clock()<r['open_ms']+300000 for r in s['calendar'])]
                if len(selections)>1:out['issues'].append(dict(phase='OPENING',code='AMBIGUOUS_SELECTION'))
                elif selections:
                    selection=selections[0]
                    def opening():
                        from scripts.run_alpaca_dynamic_v1_orders_off import load_history
                        from scripts.equities_alpaca_paper_bridge import _parse_iso_utc
                        q=quotes
                        if q is None:
                            q={}
                            for pick in selection['picks']:
                                actual=native.client.latest_quote(pick['symbol']);stamp=_parse_iso_utc(actual['t'])
                                if stamp is None:raise ValueError('CYCLE_QUOTE_CLOCK')
                                q[pick['symbol']]=dict(ask=float(positive(actual['ap'])),
                                    quote_ts=int(stamp.timestamp()*1000),received_ms=clock(),source='ALPACA_IEX_LATEST_QUOTE')
                        return self.opening(native,load_history(bundle['history']),selection['selection_id'],
                            quotes=q,now_ms=clock(),apply=True,before_entry=lambda:finality(guarded=True))
                    out['opening']=attempt('OPENING',opening)
                    out['entry_status']='OPENING_PROCESSED' if out['opening'] else 'BLOCKED'
                else:out['entry_status']='OUTSIDE_MONTHLY_WINDOW'
            if out['issues']:out['entry_status']='BLOCKED'
            if notifications:
                from research_lab.alpaca_monthly_notifications_v1 import cycle_delivery
                out['notifications']=attempt('NOTIFICATION',lambda:cycle_delivery(notifications,native,
                    now_ms=clock(),failure=bool(out['issues']),sender=sender))
            return self._record('DISPATCH_TICK',out,clock())
