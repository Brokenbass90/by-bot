"""One Monthly source/book/manager binding. No scheduler or money activation.

The installed CLI invokes only source and preview. Applying methods require an
explicit native client and its existing native/Monthly owner checks; tests pass
a broker whose HTTP implementation never leaves memory.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import uuid

from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_monthly_binding_v1 import MonthlyBook,CONTRACT
from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
from research_lab.alpaca_dynamic_v1 import digest,positive
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
    def guard(self):
        fd=os.open(self.root/'cycle.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
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

    def opening(self,native,history,selection_id,*,quotes,now_ms,apply=False,symbols=None):
        if type(apply) is not bool:raise ValueError('CYCLE_EXPLICIT_BOOLEAN_REQUIRED')
        self._custody(native)
        with self.guard():
            selected=next(s for s in self.book.rows('selections') if s['selection_id']==selection_id)
            allowed={p['symbol'] for p in selected['picks']}
            if symbols is not None:
                if not isinstance(symbols,list) or len(set(symbols))!=len(symbols) or not set(symbols)<=allowed:
                    raise ValueError('CYCLE_SELECTED_SCOPE_REQUIRED')
                allowed=set(symbols)
            if apply and native.base_url=='https://api.alpaca.markets':
                allowed&={native._live_custody()['symbol']}
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
                    recovered.append(native.enter(saved,now_ms=now_ms,apply=apply))
                    handled.add(saved['symbol'])
            plan=native.rotate(selection_id,now_ms=now_ms,apply=apply)
            actions=self.book.monthly_actions(selection_id,now_ms=now_ms)
            tickets=[];results=list(recovered)
            for symbol in actions.get('new_symbols',[]):
                if symbol not in allowed or symbol in handled:continue
                account=native.client.get_account()
                ticket=native.prepare_entry(history,selection_id,symbol,quote=quotes[symbol],now_ms=now_ms,
                    cash=account['cash'],open_equity=account['equity'])
                tickets.append(ticket)
                if ticket['status']=='MONTHLY_NATIVE_ENTRY_PREPARED_ORDERS_OFF':
                    path=self.root/'tickets'/(ticket['client_order_id']+'.json')
                    if path.exists():
                        if json.loads(path.read_bytes())!=ticket:raise ValueError('CYCLE_TICKET_REVISION')
                    elif apply:publish(path,ticket)
                    results.append(native.enter(ticket,now_ms=now_ms,apply=apply))
                else:results.append(ticket)
            return self._record('OPENING',dict(status='MONTHLY_OPENING_CYCLE',rotation=plan,
                tickets=tickets,results=results,orders_allowed=False,money_authority=False),now_ms)

    def maintain(self,native,*,now_ms,apply=False):
        self._custody(native)
        with self.guard():return self._record('MAINTAIN',native.maintain(now_ms=now_ms,apply=apply),now_ms)

    def finalize(self,native,entry_id,cost_source,*,now_ms):
        self._custody(native)
        with self.guard():return self._record('ACCOUNTING',native.finalize_exit(entry_id,cost_source,now_ms=now_ms),now_ms)
