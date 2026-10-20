"""Monthly source binding to the existing account-owner primitives.

Default OFF. No credential loader, scheduler, HALT release or owner permit is
provided here. An activated caller must still hold the original account lock,
pass the native LIVE binding/approval checks and supply its explicit client.
The disabled source CLI cannot call the applying methods.
"""
from datetime import datetime,timezone
import json
import hashlib
import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from research_lab import alpaca_strategy_parity_v1 as baseline
from research_lab.alpaca_dynamic_v1 import dec,digest,instant,positive
from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock,permit_write
from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
from research_lab import alpaca_dynamic_live_runtime_v1 as lifecycle
from research_lab.alpaca_monthly_binding_v1 import CONTRACT,entry_cid,result,monthly_picks,strategy_identity
from scripts import equities_alpaca_paper_bridge as native

ROOT=Path(__file__).resolve().parents[1]
STANDING_SCHEMA='ALPACA_MONTHLY_STANDING_OWNER_SCOPE_V1'
PENDING_FEE_POLICY='SOURCE_CLASSIFIED_WITHIN_EXISTING_RESERVE_V1'


def monthly_universe():
    from research_lab.alpaca_monthly_source_ops_v1 import required_symbols
    return required_symbols()


def standing_source_pins():
    """Same AST import-closure approach as existing readiness packaging, no imports run."""
    import ast
    names=set(baseline.source_pins())|{
        'research_lab/alpaca_monthly_native_binding_v1.py',
        'research_lab/alpaca_monthly_cycle_v1.py',
        'research_lab/alpaca_monthly_notifications_v1.py',
        'research_lab/alpaca_monthly_source_ops_v1.py',
        'scripts/run_alpaca_monthly_cycle_v1.py',
        'scripts/fetch_equities_yfinance.py'}
    queue=sorted(names)
    while queue:
        name=queue.pop()
        if not name.endswith('.py'):continue
        modules={'scripts.equities_earnings_filter'}
        for node in ast.walk(ast.parse((ROOT/name).read_bytes())):
            if isinstance(node,ast.Import):modules.update(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom) and not node.level:
                modules.add(node.module or '')
                modules.update((node.module+'.'+a.name) for a in node.names if node.module)
        for module in modules:
            target=module.replace('.','/')
            deps={target+'.py',target+'/__init__.py'}|{str(p/'__init__.py') for p in Path(target).parents}
            for dep in sorted(deps-names):
                if (ROOT/dep).is_file():names.add(dep);queue.append(dep)
    return {n:hashlib.sha256(lifecycle.safe_path(str(ROOT/n),exists=True).read_bytes()).hexdigest()
            for n in sorted(names)}


class MonthlyNativeBinding:
    def __init__(self,book,*,client,base_url,account_id,capital,runtime,lock_path,entry_halt_path,
                 liability_reserve_usd='0',live_scope_path=None,live_scope_sha256=None,owner_go_path=None,
                 pending_fee_admission=False):
        if book.contract!=CONTRACT:raise ValueError('MONTHLY_CONTRACT_CONFLICT')
        self.book=book;self.client=client;self.base_url=base_url;self.account=account_id
        self.capital=float(positive(capital))
        if self.capital>float(CONTRACT['capital_ceiling_usd']):raise ValueError('MONTHLY_CAPITAL_CAP')
        self.runtime=Path(runtime).absolute();self.lock_path=Path(lock_path).absolute()
        if any(p.is_symlink() for p in (self.runtime,*self.runtime.parents)):
            raise ValueError('MONTHLY_NATIVE_PATH')
        self.ledger=self.runtime/'native-floor.json';self.reentry=self.runtime/'native-intents.json'
        self.halt=lifecycle.safe_path(str(Path(entry_halt_path).absolute()))
        self.liability=dec(liability_reserve_usd)
        if self.liability<0:raise ValueError('MONTHLY_LIABILITY_RESERVE_INVALID')
        if type(pending_fee_admission) is not bool or (pending_fee_admission and self.liability<=0):
            raise ValueError('MONTHLY_PENDING_FEE_POSITIVE_RESERVE_REQUIRED')
        self.pending_fee_admission=pending_fee_admission;self.pending_fee_sources={}
        self.live_scope_path=live_scope_path;self.live_scope_sha256=live_scope_sha256
        self.owner_go_path=owner_go_path
        if self.halt==self.ledger or self.halt==self.reentry or self.halt==self.lock_path:
            raise ValueError('MONTHLY_HALT_PATH_CONFLICT')

    def _selection(self,key):
        found=next((s for s in self.book.rows('selections') if s['selection_id']==key),None)
        if found is None:raise ValueError('MONTHLY_SELECTION_UNKNOWN')
        return found

    def _native_authority(self):
        if getattr(self.client,'base_url',self.base_url)!=self.base_url:
            raise ValueError('MONTHLY_TRANSPORT_ENDPOINT_CONFLICT')
        if self.base_url==lifecycle.LIVE:self._live_custody()
        if not native._intended_lifecycle_enabled(self.base_url,account_id=self.account,
            capital=self.capital,require_enabled=True):
            raise native.IntendedPaperProtectionError('monthly_native_mode_not_enabled')
        if self.client.get_account().get('id')!=self.account:
            raise ValueError('MONTHLY_NATIVE_ACCOUNT_CONFLICT')

    def _live_custody(self):
        """Legacy Dynamic approval alone can never activate this Monthly owner."""
        if not self.live_scope_path or not self.owner_go_path:
            raise ValueError('MONTHLY_SEPARATE_OWNER_SCOPE_REQUIRED')
        path=lifecycle.safe_path(str(self.live_scope_path),exists=True)
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.live_scope_sha256:
            raise ValueError('MONTHLY_LIVE_SCOPE_PIN')
        scope=json.loads(raw)
        standing=scope.get('schema')==STANDING_SCHEMA
        expected=dict(schema=STANDING_SCHEMA if standing else 'ALPACA_MONTHLY_OWNER_SCOPE_V1',endpoint=self.base_url,
            account_id=self.account,contract_sha256=digest(CONTRACT),
            strategy_identity=strategy_identity(),
            capital_usd=str(dec(self.capital)),liability_reserve_usd=str(self.liability),
            book=str(self.book.path),runtime=str(self.runtime),lock_path=str(self.lock_path),
            entry_halt_path=str(self.halt),legacy_NET_adoption=False,legacy_entry_authority=False)
        if (any(scope.get(k)!=v for k,v in expected.items())
            or getattr(self.client,'order_contract',None)!=CONTRACT['schema']):
            raise ValueError('MONTHLY_LIVE_SCOPE_CONFLICT')
        if self.pending_fee_admission and scope.get('pending_fee_admission')!=PENDING_FEE_POLICY:
            raise ValueError('MONTHLY_PENDING_FEE_SCOPE_REQUIRED')
        if self.pending_fee_admission:
            pin=scope.get('pending_fee_protocol_sha256')
            if not isinstance(pin,str) or len(pin)!=64 or any(c not in '0123456789abcdef' for c in pin):
                raise ValueError('MONTHLY_PENDING_FEE_PROTOCOL_REQUIRED')
        count=scope.get('max_new_entries_per_session')
        if type(count) is not int or not 1<=count<=(4 if standing else 1):
            raise ValueError('MONTHLY_SESSION_ENTRY_LIMIT')
        if not 0<positive(scope['max_entry_notional_usd'])<=dec(self.capital)*dec('.70')*dec('.60'):
            raise ValueError('MONTHLY_LIVE_SCOPE_NOTIONAL_CAP')
        lock=lifecycle.safe_path(str(self.lock_path),exists=True).stat()
        if [lock.st_dev,lock.st_ino]!=scope.get('original_lock_identity'):
            raise ValueError('MONTHLY_ORIGINAL_ACCOUNT_LOCK_CHANGED')
        if not scope.get('source_files'):raise ValueError('MONTHLY_LIVE_SOURCE_UNBOUND')
        for row in scope['source_files']:
            source=lifecycle.safe_path(row['path'],exists=True)
            if hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('MONTHLY_LIVE_SOURCE_CHANGED')
        required={str(Path(m.__file__).resolve()) for m in (lifecycle,native)}|{str(Path(__file__).resolve())}
        if not required.issubset({r['path'] for r in scope['source_files']}):
            raise ValueError('MONTHLY_LIVE_IMPLEMENTATION_UNBOUND')
        if standing:
            actual={r['path']:r['sha256'] for r in scope['source_files']}
            expected_files={str(ROOT/n):h for n,h in standing_source_pins().items()}
            if (len(actual)!=len(scope['source_files']) or actual!=expected_files
                or scope.get('universe_sha256')!=digest(list(monthly_universe()))
                or scope.get('selection_policy')!='EXISTING_SEALED_FROZEN_MONTHLY_ONLY'
                or scope.get('legacy_NET_adoption') is not False
                or scope.get('legacy_entry_authority') is not False
                or any(k in scope for k in ('selection_id','symbol'))):
                raise ValueError('MONTHLY_STANDING_SOURCE_OR_POLICY_CONFLICT')
            start,end=scope.get('valid_from_ms'),scope.get('valid_until_ms')
            if (type(start) is not int or type(end) is not int or not 0<start<end
                or not 0<positive(scope['max_cumulative_net_loss_usd'])<=dec(self.capital)):
                raise ValueError('MONTHLY_STANDING_BOUNDS')
            revoke=self._revocation_path(scope)
            if revoke in {path,self.lock_path,self.halt,self.book.path,self.ledger,self.reentry,
                          Path(self.owner_go_path)}:raise ValueError('MONTHLY_STANDING_REVOKE_PATH')
        go=lifecycle.read_json(self.owner_go_path)
        if go!=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1' if standing else 'ALPACA_MONTHLY_EXACT_OWNER_GO_V1',
                    scope_sha256=self.live_scope_sha256,
                    owner_go_text=('GO ALPACA_MONTHLY_STANDING ' if standing else 'GO ALPACA_MONTHLY ')+self.live_scope_sha256):
            raise ValueError('MONTHLY_SEPARATE_OWNER_GO_REQUIRED')
        return scope

    @staticmethod
    def _revocation_path(scope):
        # The leaf is a stop-new-entry marker, never a custody/source file.
        # A directory or dangling symlink at that leaf must revoke, not disable
        # protection of positions already owned by this unchanged manager.
        path=Path(scope['revocation_path'])
        if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in path.parents):
            raise ValueError('MONTHLY_STANDING_REVOKE_PATH')
        return path

    @staticmethod
    def _standing_entry_state(scope,now):
        # Entry-only. Existing custody/recovery/protection never consults expiry.
        if not scope['valid_from_ms']<=now<scope['valid_until_ms']:
            raise ValueError('MONTHLY_STANDING_NOT_CURRENT')
        path=MonthlyNativeBinding._revocation_path(scope)
        if not path.parent.is_dir():raise ValueError('MONTHLY_STANDING_REVOKE_PARENT_UNKNOWN')
        os.stat(path.parent)  # inaccessible/missing parent is not proof of no marker
        if os.path.lexists(path):
            raise ValueError('MONTHLY_STANDING_REVOKED')

    def _entry_authority(self,ticket,now,*,reserved=False):
        scope=self._live_custody();selection=self._selection(ticket['selection_id'])
        if scope['schema']==STANDING_SCHEMA:
            self._standing_entry_state(scope,now)
            if (selection['source_code_sha256']!=baseline.source_pins()
                or ticket['symbol'] not in set(monthly_universe())-{'SPY'}
                or ticket['symbol'] not in {p['symbol'] for p in selection['picks']}):
                raise ValueError('MONTHLY_STANDING_SELECTION_REQUIRED')
        elif ticket['selection_id']!=scope.get('selection_id') or ticket['symbol']!=scope.get('symbol'):
            raise ValueError('MONTHLY_APPROVED_SELECTION_REQUIRED')
        if positive(ticket['notional'])>positive(scope['max_entry_notional_usd']):
            raise ValueError('MONTHLY_APPROVED_SELECTION_REQUIRED')
        entries=json.loads(self.reentry.read_bytes()).get('entry_intents',{}) if self.reentry.exists() else {}
        used=sum(1 for cid,i in entries.items() if i.get('entry_session')==selection['entry_session']
                 and not (reserved and cid==ticket['client_order_id']))
        if used>=scope['max_new_entries_per_session']:
            raise ValueError('MONTHLY_SESSION_ENTRY_ALREADY_CONSUMED')
        return scope

    def _admit_new_entry(self,ticket,now):
        """GET-only complete account check under the original writer lock."""
        started=time.monotonic()
        realized=None if self.pending_fee_admission else self._accounting_net()
        account=self.client.get_account();account_observed=now+int((time.monotonic()-started)*1000)
        clock=self.client.get_clock()
        stamp=native._parse_iso_utc(clock.get('timestamp',''))
        if (account.get('id')!=self.account or account.get('trading_blocked') is not False
            or account.get('account_blocked') is not False or clock.get('is_open') is not True
            or stamp is None or abs(int(stamp.timestamp()*1000)-now)>5000):
            raise ValueError('MONTHLY_FRESH_ACCOUNT_CLOCK_REQUIRED')
        if self.base_url==lifecycle.LIVE:
            scope=self._entry_authority(ticket,now)
        else:scope=None
        admission=None
        if self.pending_fee_admission:
            realized,admission=self._accounting_for_admission(account=account,now_ms=now)
        state=self._state();owned={p['symbol']:p for p in self.book.rows('positions')}
        positions=self.client.list_positions();orders=self.client.list_orders(status='open',limit=500)
        if (len(orders)>=500 or len({p['symbol'] for p in positions})!=len(positions)
            or set(state)!=set(owned) or {p['symbol'] for p in positions}!=set(owned)
            or ticket['symbol'] in owned):raise ValueError('MONTHLY_FOREIGN_OR_UNRECONCILED_POSITION')
        stop_ids=set()
        for actual in positions:
            p=owned[actual['symbol']];record=state[p['symbol']]
            if (p.get('protection_pending') or actual.get('side')!='long'
                or positive(actual['qty'])!=positive(p['qty'])
                or positive(actual['avg_entry_price'])!=positive(p['raw_entry']['filled_avg_price'])):
                raise ValueError('MONTHLY_PARTIAL_OR_UNPROTECTED_POSITION')
            execution_identity_v1(p['raw_entry'],self.client.get_order(p['entry_id']))
            stop=self.client.get_order(p['native_stop_id'])
            if (record['accepted_order_id']!=stop['id'] or record['entry_order_id']!=p['entry_id']
                or stop['status'] not in {'new','accepted'} or dec(stop.get('filled_qty','0'))!=0):
                raise ValueError('MONTHLY_FULL_NATIVE_STOP_REQUIRED')
            native._confirmed_intended_stop(self.client,stop,symbol=p['symbol'],
                qty=float(positive(p['qty'])),requested_stop=float(p['native_floor']))
            if stop['time_in_force']=='day':
                sent=native._parse_iso_utc(stop.get('submitted_at') or stop.get('created_at',''))
                if sent is None or sent.date()!=stamp.date() or sent>stamp:
                    raise ValueError('MONTHLY_DAY_STOP_NOT_CURRENT_SESSION')
            if positive(actual['current_price'])<=positive(p['native_floor']):
                raise ValueError('MONTHLY_STOP_ALREADY_BREACHED')
            stop_ids.add(stop['id'])
        if {o['id'] for o in orders}!=stop_ids or len(orders)!=len(stop_ids):
            raise ValueError('MONTHLY_FOREIGN_OR_UNRECONCILED_ORDER')
        if scope and scope['schema']==STANDING_SCHEMA:
            self._check_standing_loss(scope,realized,positions)
        notional=positive(ticket['notional']);equity=min(positive(account['equity']),dec(self.capital))
        cash=min(dec(account['cash']),dec(account['non_marginable_buying_power']))
        gross=sum((abs(dec(p['market_value'])) for p in positions),dec(0))
        weight=positive(ticket['entry_gate']['weight'])
        fresh_size=dec(float(equity)*.70*float(weight))
        if (len(positions)>=CONTRACT['max_positions'] or cash-self.liability<notional
            or gross+notional>equity*dec(CONTRACT['gross_ceiling'])
            or notional>fresh_size+dec('.000000001')):
            raise ValueError('MONTHLY_FRESH_CASH_GROSS_OR_POSITION_CAP')
        asset=self.client.get_asset(ticket['symbol']);quote=self.client.latest_quote(ticket['symbol'])
        quoted=native._parse_iso_utc(quote.get('t',''))
        if (asset.get('symbol')!=ticket['symbol'] or asset.get('status')!='active'
            or asset.get('tradable') is not True or asset.get('fractionable') is not True
            or quoted is None or not 0<=now-int(quoted.timestamp()*1000)<=300000):
            raise ValueError('MONTHLY_FRESH_ASSET_OR_QUOTE_REQUIRED')
        positive(quote['ap'])
        anchor=dict(schema='ALPACA_MONTHLY_CASH_ANCHOR_V1',account_id=self.account,
            client_order_id=ticket['client_order_id'],observed_ms=account_observed,account=account)
        if admission:anchor['pending_fee_admission']=admission
        return anchor

    @staticmethod
    def _check_standing_loss(scope,realized,positions):
        floating=sum((positive(p['qty'])*(positive(p['current_price'])-positive(p['avg_entry_price']))
                      for p in positions),dec(0))
        if realized+floating<=-positive(scope['max_cumulative_net_loss_usd']):
            raise ValueError('MONTHLY_STANDING_LOSS_ADMISSION_STOP')

    def _require_exit_accounting(self):
        self._accounting_net()

    def _accounting_for_admission(self,*,account,now_ms):
        liabilities=[]
        if self.pending_fee_admission:
            try:liabilities=[dec(account[k]) for k in ('accrued_fees','pending_reg_taf_fees')]
            except (KeyError,ValueError,TypeError,ArithmeticError):
                raise ValueError('MONTHLY_PENDING_FEE_LIABILITY_UNKNOWN') from None
            if (account.get('id')!=self.account or account.get('currency')!='USD'
                or any(v<0 for v in liabilities)):
                raise ValueError('MONTHLY_PENDING_FEE_LIABILITY_UNKNOWN')
        try:
            realized=self._accounting_net()
            if any(liabilities):raise ValueError('MONTHLY_PENDING_FEE_LIABILITY_UNCLASSIFIED')
            return realized,None
        except ValueError as exc:
            if str(exc)!='MONTHLY_ACCOUNTING_PENDING' or not self.pending_fee_admission:raise
        scope=self._live_custody() if self.base_url==lifecycle.LIVE else None
        from research_lab.alpaca_monthly_cost_source_v1 import pending_admission_net
        return pending_admission_net(self,account=account,now_ms=now_ms,owner_scope=scope)

    @staticmethod
    def _pending_dispatch_fresh(proof,now_ms):
        if proof and any(not 0<=now_ms-proof[k]<=5000 for k in ('source_observed_ms','source_coverage_end_ms')):
            raise ValueError('MONTHLY_PENDING_FEE_STALE_SOURCE')

    def _require_admission_accounting(self,*,now_ms):
        if not self.pending_fee_admission:return self._require_exit_accounting()
        return self._accounting_for_admission(account=self.client.get_account(),now_ms=now_ms)

    def _accounting_net(self,*,pending=None):
        realized=dec(0);used=set()
        for exited in self.book.rows('exits'):
            identity=digest(dict(schema=CONTRACT['schema'],entry_id=exited['entry_id']))
            path=self.runtime/'safety'/identity/'live.sqlite'
            row=None
            if path.is_file():
                with sqlite3.connect(lifecycle.safe_path(str(path),exists=True).as_uri()+'?mode=ro',uri=True) as db:
                    row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
            item=json.loads(row[0]) if row else {}
            if item and item.get('account')!=self.account:raise ValueError('MONTHLY_ACCOUNTING_OWNER_CONFLICT')
            if (not item.get('cost_finality')
                or item['cost_finality'].get('status')!='LIVE_TERMINAL_COST_FINALITY'):
                if pending is not None and exited['entry_id'] in pending:
                    used.add(exited['entry_id']);realized+=dec(pending[exited['entry_id']]);continue
                raise ValueError('MONTHLY_ACCOUNTING_PENDING')
            source=lifecycle.safe_path(item['monthly_cost_source_path'],exists=True)
            if hashlib.sha256(source.read_bytes()).hexdigest()!=item['cost_finality_sha256']:
                raise ValueError('MONTHLY_ACCOUNTING_SOURCE_CHANGED')
            for row in lifecycle.read_json(str(source))['source_files']:
                p=lifecycle.safe_path(row['path'],exists=True)
                if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
                    raise ValueError('MONTHLY_ACCOUNTING_SOURCE_CHANGED')
            realized+=dec(item['cost_finality']['net_usd_exact'])
        if pending is not None and set(pending)!=used:raise ValueError('MONTHLY_PENDING_FEE_BOOK_CONFLICT')
        return realized

    def finalize_exit(self,entry_id,cost_source_path,*,now_ms):
        """Reuse the existing broker/account cost finalizer; no orders or new GO."""
        exited=next((r for r in self.book.rows('exits') if r['entry_id']==entry_id),None)
        if exited is None:raise ValueError('MONTHLY_EXIT_UNKNOWN')
        p=exited['retired_position'];now=instant(now_ms)
        identity=digest(dict(schema=CONTRACT['schema'],entry_id=entry_id))
        source=lifecycle.safe_path(str(cost_source_path),exists=True)
        with account_lock(dict(lock_path=str(self.lock_path))):
            execution_identity_v1(p['raw_entry'],self.client.get_order(entry_id))
            orders=[self.client.get_order(o['id']) for o in exited['orders']]
            for old,current in zip(exited['orders'],orders):execution_identity_v1(old,current)
            active=self.client.list_orders(status='open',limit=500)
            if (len(active)>=500 or any(o['symbol']==p['symbol'] for o in active)
                or any(r['symbol']==p['symbol'] for r in self.client.list_positions())):
                raise ValueError('MONTHLY_ACCOUNTING_EXIT_NOT_FLAT')
            gross=sum((positive(o['filled_qty'])*(positive(o['filled_avg_price'])
                       -positive(p['raw_entry']['filled_avg_price'])) for o in orders),dec(0))
            terminal=dict(exit_orders=orders,gross_before_fees=str(gross),exit_kind=exited['reason'])
            with lifecycle.store(self.runtime/'safety'/identity) as db:
                row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
                item=json.loads(row[0]) if row else dict(id=identity,account=self.account,entry=p['raw_entry'],
                    intake=dict(plan=dict(slot_entry_order_id=entry_id,session=p['daily_state']['entry_session'])),
                    initial_full_protection_proven=not bool(p.get('protection_pending')))
                if item.get('account')!=self.account or item.get('entry')!=p['raw_entry']:
                    raise ValueError('MONTHLY_ACCOUNTING_OWNER_CONFLICT')
                item['observed_ms']=now
                out=lifecycle.finalize_costs(db,item,self.client,terminal,source)
                item['monthly_cost_source_path']=str(source);lifecycle.save(db,item)
                return out

    def _state(self):
        state=json.loads(self.ledger.read_text()) if self.ledger.exists() else {}
        intents=json.loads(self.reentry.read_text()).get('entry_intents',{}) if self.reentry.exists() else {}
        for symbol,r in state.items():
            if r.get('entry_selection_policy')==CONTRACT['schema']:continue
            # Native stop-response loss may leave its durable pending record
            # before the final selection tags were copied. Require the exact
            # reserved monthly CID and broker entry, never adopt by symbol.
            owned=[(cid,i) for cid,i in intents.items() if i.get('symbol')==symbol
                and i.get('baseline_contract')==CONTRACT['schema'] and i.get('status')=='reserved']
            if len(owned)!=1 or not r.get('protection_pending'):raise ValueError('MONTHLY_NATIVE_OWNER_CONFLICT')
            cid,intent=owned[0];entry=self.client.get_order_by_client_id(cid)
            if not entry or entry['id']!=r.get('entry_order_id'):raise ValueError('MONTHLY_NATIVE_OWNER_CONFLICT')
        for p in self.book.rows('positions'):
            r=state.get(p['symbol'])
            if not r or r['entry_order_id']!=p['entry_id']:
                raise ValueError('MONTHLY_NATIVE_OWNER_CONFLICT')
        return state

    def prepare_entry(self,history,selection_id,symbol,*,quote,now_ms,cash,open_equity):
        s=self._selection(selection_id)
        actions=self.book.monthly_actions(selection_id,now_ms=now_ms)
        if symbol not in actions.get('new_symbols',[]):return result('NO_SEND',reason='MONTHLY_NOT_ADMITTED')
        gate=baseline.entry_gate(history,s['calendar'],signal_session=s['signal_session'],
            intended_entry_session=s['entry_session'],entry_session=s['entry_session'],symbol=symbol,
            history_available_ms=s['source_available_ms'],quote=quote,now_ms=now_ms)
        if gate['status']!='ENTRY_PARITY_CANDIDATE':return gate
        gate['selection']=monthly_picks(gate['selection'])
        gate['receipt_sha256']=digest({k:v for k,v in gate.items() if k!='receipt_sha256'})
        if (gate['causal_history_sha256']!=s['causal_history_sha256']
            or gate['selection']!=s['picks']):raise ValueError('SEALED_SELECTION_REVALIDATION_CONFLICT')
        # Same frozen equity * gross * weight formula; existing capital ceiling
        # limits executable size. No cap renormalization or replacement symbol.
        equity=min(float(positive(open_equity)),self.capital)
        notional=min(float(positive(cash)),equity*.70*gate['weight'])
        if not 0<gate['weight']<=.60 or notional>self.capital*.70*.60+1e-9:
            raise ValueError('MONTHLY_WEIGHT_OR_NOTIONAL_CAP')
        out=result('MONTHLY_NATIVE_ENTRY_PREPARED_ORDERS_OFF',selection_id=selection_id,
            client_order_id=entry_cid(s,symbol),symbol=symbol,notional=notional,entry_gate=gate)
        out['ticket_sha256']=digest(out)
        return out

    def enter(self,ticket,*,now_ms,apply=False):
        started=time.monotonic()
        if type(apply) is not bool:raise ValueError('EXPLICIT_BOOLEAN_OPERATION_REQUIRED')
        if ticket.get('ticket_sha256')!=digest({k:v for k,v in ticket.items() if k!='ticket_sha256'}):
            raise ValueError('MONTHLY_TICKET_HASH_CONFLICT')
        if not apply:return result('MONTHLY_NATIVE_ENTRY_REHEARSAL_ORDERS_OFF',ticket_sha256=ticket['ticket_sha256'])
        s=self._selection(ticket['selection_id']);gate=ticket['entry_gate'];now=instant(now_ms)
        if ticket['client_order_id']!=entry_cid(s,ticket['symbol']):raise ValueError('MONTHLY_TICKET_OWNER_CONFLICT')
        with account_lock(dict(lock_path=str(self.lock_path))):
            self._native_authority()
            self._state()
            entries=json.loads(self.reentry.read_text()).get('entry_intents',{}) if self.reentry.exists() else {}
            cid=ticket['client_order_id']
            args=dict(client=self.client,base_url=self.base_url,account_id=self.account,capital=self.capital,
                reentry_path=self.reentry,state_path=self.ledger,state_dir=self.runtime/'halt')
            if cid in entries:
                # Recovery never repeats a buy. The native durable reservation
                # resolves exact CID or consumes a never-submitted reservation.
                if (entries[cid]['status']=='reserved'
                    and self.client.get_order_by_client_id(cid) is None):
                    raise ValueError('UNCERTAIN_ENTRY_NO_RESEND')
                native._recover_intended_entry_intents(**args)
            else:
                if self.halt.exists() or native.paper_entry_halted(base_url=self.base_url,state_dir=args['state_dir']):
                    raise ValueError('ENTRY_HALT_PRESERVED')
                window=next(c for c in s['calendar'] if c['session']==s['entry_session'])
                if (not window['open_ms']<=now<window['open_ms']+300000
                    or not 0<=now-gate['quote_ts']<=300000):raise ValueError('STALE_SIGNAL_RESELECT_FAIL')
                actions=self.book.monthly_actions(s['selection_id'],now_ms=now)
                if ticket['symbol'] not in actions.get('new_symbols',[]):raise ValueError('MONTHLY_NOT_ADMITTED')
                selected=next(p for p in s['picks'] if p['symbol']==ticket['symbol'])
                if (gate['receipt_sha256']!=digest({k:v for k,v in gate.items() if k!='receipt_sha256'})
                    or gate['atr20']!=selected['atr20'] or gate['weight']!=selected['weight']
                    or gate['causal_history_sha256']!=s['causal_history_sha256']
                    or not 0<positive(ticket['notional'])<=dec(self.capital*.70*selected['weight'])):
                    raise ValueError('MONTHLY_TICKET_SOURCE_OR_CAP_CONFLICT')
                anchor=self._admit_new_entry(ticket,now+int((time.monotonic()-started)*1000))
                from research_lab.kity_oct15_deadline_v1 import publish_once
                anchor_dir=self.runtime/'cash-anchors';anchor_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
                # Immutable source evidence before the native durable reservation
                # and POST. A crash here consumes no authority but cannot silently
                # replace the accounting baseline on an uncertain later retry.
                publish_once(anchor_dir/(cid+'.json'),lifecycle.canonical(anchor))
                final_clock=self.client.get_clock();stamp=native._parse_iso_utc(final_clock.get('timestamp',''))
                effective=now+int((time.monotonic()-started)*1000)
                if (final_clock.get('is_open') is not True or stamp is None
                    or abs(int(stamp.timestamp()*1000)-effective)>5000
                    or not window['open_ms']<=effective<window['open_ms']+300000):
                    raise ValueError('MONTHLY_FINAL_DISPATCH_WINDOW_OR_CLOCK')
                pick=SimpleNamespace(ticker=ticket['symbol'],entry_day=s['entry_session'],
                    entry_price=gate['signal_close'],stop_price=gate['signal_close']-2.*gate['atr20'])
                def final_dispatch():
                    # Code/source checks may be slow. Re-read time, expiry and
                    # revocation AFTER them, immediately before the native POST.
                    scope=None;pending_proof=None
                    if self.base_url==lifecycle.LIVE:
                        scope=self._entry_authority(ticket,now+int((time.monotonic()-started)*1000),reserved=True)
                    if self.pending_fee_admission:
                        _,pending_proof=self._accounting_for_admission(account=self.client.get_account(),
                            now_ms=now+int((time.monotonic()-started)*1000))
                    clock=self.client.get_clock();stamp=native._parse_iso_utc(clock.get('timestamp',''))
                    effective=now+int((time.monotonic()-started)*1000)
                    self._pending_dispatch_fresh(pending_proof,effective)
                    if (clock.get('is_open') is not True or stamp is None
                        or abs(int(stamp.timestamp()*1000)-effective)>5000
                        or not window['open_ms']<=effective<window['open_ms']+300000):
                        raise ValueError('MONTHLY_FINAL_DISPATCH_WINDOW_OR_CLOCK')
                    if self.halt.exists() or native.paper_entry_halted(base_url=self.base_url,state_dir=args['state_dir']):
                        raise ValueError('ENTRY_HALT_PRESERVED')
                    if scope and scope['schema']==STANDING_SCHEMA:
                        self._standing_entry_state(scope,effective)
                try:
                    native._submit_intended_reserved_entry(**args,pick=pick,notional=ticket['notional'],timeout_sec=0,
                        baseline_atr20=gate['atr20'],baseline_signal_session=s['signal_session'],
                        baseline_selection_sha256=s['selection_id'],baseline_entry_gate=gate,
                        baseline_dispatch_validator=final_dispatch)
                except native.AlpacaAPIError as exc:
                    saved=json.loads(self.reentry.read_text())['entry_intents'][cid]
                    if exc.status_code!=422 or not saved.get('baseline_stop_rejected_422'):raise
                    entry=self.client.get_order_by_client_id(cid)
                    p=self.book.bind_rejected_protection(s['selection_id'],entry)
                    record=json.loads(self.ledger.read_text())[ticket['symbol']]
                    return self._settle_owned(p,record,now_ms=now,unwind=True)
            state=self._state();record=state.get(ticket['symbol'])
            if not record:return result('NO_SEND',reason='NATIVE_RESERVATION_UNFILLED_OR_NOT_SUBMITTED')
            entry=self.client.get_order(record['entry_order_id']);stop=self.client.get_order(record['accepted_order_id'])
            native._confirmed_intended_stop(self.client,stop,symbol=ticket['symbol'],
                qty=float(positive(entry['filled_qty'])),requested_stop=float(record['accepted_stop_floor']))
            self.book.bind_fill(s['selection_id'],entry,stop)
            return result('MONTHLY_NATIVE_PROTECTED',symbol=ticket['symbol'],entry_order_id=entry['id'],
                stop_order_id=stop['id'],stop_price=record['accepted_stop_floor'])

    def rotate(self,selection_id,*,now_ms,apply=False):
        if type(apply) is not bool:raise ValueError('EXPLICIT_BOOLEAN_OPERATION_REQUIRED')
        s=self._selection(selection_id);plan=self.book.monthly_actions(selection_id,now_ms=now_ms)
        if not apply:return plan
        with account_lock(dict(lock_path=str(self.lock_path))):
            self._native_authority()
            self._recover_rotation_receipts(now_ms=now_ms)
            self._state()
            plan=self.book.monthly_actions(selection_id,now_ms=now_ms)
            if plan['status']=='NO_SEND':return plan
            out=native._rotate_intended_monthly(client=self.client,base_url=self.base_url,
                account_id=self.account,capital=self.capital,state_path=self.ledger,reentry_path=self.reentry,
                selected_symbols=set(plan['retain'])|set(plan['new_symbols']),entry_session=s['entry_session'],
                now=datetime.fromtimestamp(instant(now_ms)/1000,timezone.utc),
                rotation_client_ids={r['symbol']:r['client_order_id'] for r in plan['rotation_intentions']})
            if out['status']!='COMPLETE':return result('MONTHLY_ROTATION_PENDING',native=out)
            orders=self.client.list_orders(status='open',limit=100)
            if len(orders)>=100:raise ValueError('MONTHLY_ORDERS_INCOMPLETE')
            positions=self.client.list_positions()
            receipts=json.loads(self.reentry.read_text()).get('rotation_exits',{}) if self.reentry.exists() else {}
            for action in plan['rotation_intentions']:
                r=next((r for r in receipts.values() if r['exit_order']['client_order_id']==action['client_order_id']),None)
                if r is None:raise ValueError('MONTHLY_ROTATION_RECEIPT_MISSING')
                self.book.record_exit(action['symbol'],[r['exit_order']],reason='monthly_rotation_next_open',
                    observed_ms=now_ms,remaining_qty=sum(dec(p['qty']) for p in positions if p['symbol']==action['symbol']),
                    open_order_ids=[o['id'] for o in orders if o['symbol']==action['symbol']])
            return self.book.monthly_actions(selection_id,now_ms=now_ms)

    def _recover_rotation_receipts(self,*,now_ms,known_only=False):
        """Close the second journal after a crash between native/book commits."""
        if not self.reentry.exists():return
        native_state=json.loads(self.ledger.read_text()) if self.ledger.exists() else {}
        receipts=json.loads(self.reentry.read_text()).get('rotation_exits',{})
        for p in self.book.rows('positions'):
            if p['symbol'] in native_state:continue
            actions=[r for r in self.book.rows('rotations') if r['entry_id']==p['entry_id']]
            matched=[r for r in receipts.values() if r.get('entry_order_id')==p['entry_id']
                and any(a['client_order_id']==r['exit_order'].get('client_order_id') for a in actions)]
            if not matched and known_only:continue  # safety exits have their own recovery
            if len(matched)!=1:raise ValueError('MONTHLY_ROTATION_RECOVERY_SOURCE_REQUIRED')
            stored=matched[0]['exit_order'];current=self.client.get_order(stored['id'])
            execution_identity_v1(stored,current)
            orders=self.client.list_orders(status='open',limit=100)
            if len(orders)>=100:raise ValueError('MONTHLY_ORDERS_INCOMPLETE')
            self.book.record_exit(p['symbol'],[current],reason='monthly_rotation_next_open',observed_ms=now_ms,
                remaining_qty=sum(dec(v['qty']) for v in self.client.list_positions() if v['symbol']==p['symbol']),
                open_order_ids=[o['id'] for o in orders if o['symbol']==p['symbol']])

    def maintain(self,*,now_ms,apply=False):
        if type(apply) is not bool:raise ValueError('EXPLICIT_BOOLEAN_OPERATION_REQUIRED')
        if not apply:return self.book.stop_actions(now_ms=now_ms)
        with account_lock(dict(lock_path=str(self.lock_path))):
            self._native_authority()
            recovered=self._recover_safety_exits(now_ms=now_ms)
            if recovered and not self.book.rows('positions'):return recovered[-1]
            state=self._state();now=instant(now_ms);clock=self.client.get_clock()
            stamp=native._parse_iso_utc(clock['timestamp'])
            if stamp is None or abs(int(stamp.timestamp()*1000)-now)>5000:
                raise ValueError('MONTHLY_MANAGER_CLOCK_CONFLICT')
            if not clock['is_open']:return result('MONTHLY_WAITING_REGULAR_SESSION')
            session=stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            orders=self.client.list_orders(status='open',limit=100);positions=self.client.list_positions()
            if len(orders)>=100:raise ValueError('MONTHLY_ORDERS_INCOMPLETE')
            confirmed=[]
            for p in self.book.rows('positions'):
                symbol=p['symbol'];record=state[symbol]
                if p.get('protection_pending'):
                    return self._settle_owned(p,record,now_ms=now,unwind=True)
                execution_identity_v1(p['raw_entry'],self.client.get_order(p['entry_id']))
                matching=[v for v in positions if v['symbol']==symbol]
                if (len(matching)!=1 or positive(matching[0]['qty'])!=positive(p['qty'])
                    or positive(matching[0]['avg_entry_price'])!=positive(p['daily_state']['entry_fill'])):
                    return self._settle_owned(p,record,now_ms=now,unwind=False)
                active=[o for o in orders if o['symbol']==symbol]
                pending=[a for a in self.book.stop_actions(now_ms=now)['actions'] if a['entry_id']==p['entry_id']]
                action=max(pending,key=lambda a:(dec(a['stop_price']),a['not_before_ms'])) if pending else None
                target=max(dec(p['native_floor']),dec(action['stop_price']) if action else dec(p['native_floor']))
                if positive(matching[0]['current_price'])<=target:
                    return self._settle_owned(p,record,now_ms=now,unwind=True)
                if len(active)>1:raise ValueError('MONTHLY_MULTIPLE_STOPS')
                if active:
                    stop=active[0]
                    owned_replacement=(action and (stop.get('replaces')==action['prior_stop_id']
                        or stop.get('client_order_id')==action['client_order_id']))
                    if stop['id']!=p['native_stop_id'] and not owned_replacement:
                        raise ValueError('MONTHLY_STOP_OWNER_CONFLICT')
                    if dec(stop.get('filled_qty','0'))!=0:
                        raise ValueError('MONTHLY_PARTIAL_STOP_RECONCILIATION_REQUIRED')
                    native._confirmed_intended_stop(self.client,stop,symbol=symbol,qty=float(positive(p['qty'])),
                        requested_stop=float(p['native_floor']))
                    if action and positive(stop['stop_price'])<target:
                        key='replace:'+action['action_id'];payload=dict(stop_price=native._format_price(float(target)))
                        if not self.book.claim_dispatch(key,payload):raise ValueError('UNCERTAIN_STOP_NO_RESEND')
                        permit_write(self.client,'PATCH','/v2/orders/'+stop['id'],payload)
                        stop=self.client.replace_order(stop['id'],payload)
                else:
                    old=self.client.get_order(p['native_stop_id'])
                    if old['status'] not in {'expired','canceled','rejected'} or dec(old.get('filled_qty','0'))!=0:
                        raise ValueError('MONTHLY_STOP_EXIT_RECONCILIATION_REQUIRED')
                    if not action:action=self.book.prepare_rearm(symbol,session)
                    target=max(target,dec(action['stop_price']))
                    if positive(matching[0]['current_price'])<=target:
                        raise ValueError('MONTHLY_BELOW_FLOOR_EMERGENCY_EXIT_REQUIRED')
                    stop=self.client.get_order_by_client_id(action['client_order_id'])
                    if stop is None:
                        payload=dict(symbol=symbol,qty=str(p['qty']),stop_price=str(target),
                            time_in_force=native._persistent_exit_tif_for_qty('',float(positive(p['qty']))),
                            client_order_id=action['client_order_id'])
                        if not self.book.claim_dispatch('rearm:'+action['action_id'],payload):
                            raise ValueError('UNCERTAIN_STOP_NO_RESEND')
                        native._intended_lifecycle_enabled(self.base_url,account_id=self.account,
                            capital=self.capital,require_enabled=True)
                        permit_write(self.client,'POST','/v2/orders',dict(symbol=symbol,
                            qty=native._format_qty(float(positive(p['qty']))),side='sell',type='stop',
                            stop_price=native._format_price(float(target)),
                            time_in_force=payload['time_in_force'],client_order_id=payload['client_order_id']))
                        stop=self.client.submit_stop_sell(symbol,qty=float(positive(p['qty'])),stop_price=float(target),
                            time_in_force=payload['time_in_force'],client_order_id=payload['client_order_id'])
                stop=native._confirmed_intended_stop(self.client,stop,symbol=symbol,qty=float(positive(p['qty'])),
                    requested_stop=float(target))
                if action:self.book.confirm_stop(action['action_id'],stop,observed_ms=now)
                current=next(r for r in self.book.rows('positions') if r['symbol']==symbol)
                record.update(hwm=current['daily_state']['hwm'],accepted_stop_floor=current['native_floor'],
                    accepted_order_id=stop['id'],accepted_order_tif=stop['time_in_force'])
                state[symbol]=record;native._atomic_write_json(self.ledger,state)
                confirmed.append(stop['id'])
            return result('MONTHLY_NATIVE_PROTECTED',stop_order_ids=confirmed)

    def _settle_owned(self,p,record,*,now_ms,unwind):
        """Reuse the proven journaled cancel/unknown-send/exit implementation.

        Its five-minute price ratchet/weekly selection is NEVER called. Only
        ownership, scoped unwind and native exit finality are shared.
        """
        identity=digest(dict(schema=CONTRACT['schema'],entry_id=p['entry_id']))
        started=time.monotonic();observed=lambda:instant(now_ms)+int((time.monotonic()-started)*1000)
        binding=dict(halt_path=str(self.halt),account_id=self.account,ledger_path=str(self.ledger))
        with lifecycle.store(self.runtime/'safety'/identity) as db:
            row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
            if row:item=json.loads(row[0])
            else:
                entry=p['raw_entry'];payload={k:entry[k] for k in
                    ('symbol','side','type','time_in_force','client_order_id')}
                if entry.get('notional') is not None:payload['notional']=entry['notional']
                else:payload['qty']=entry['qty']
                item=dict(id=identity,account=self.account,entry=entry,observed_ms=now_ms,
                    intake=dict(entry_payload=payload,plan=dict(symbol=p['symbol'],
                        slot_entry_order_id=p['entry_id'],session=p['daily_state']['entry_session'])),
                    exit_sources=[self.client.get_order(id) for id in p['native_stop_history']],
                    phase='PROTECTED',initial_full_protection_proven=not bool(p.get('protection_pending')))
                lifecycle.save(db,item)
            item['observed_ms']=now_ms;lifecycle.save(db,item)
            if unwind:
                out=lifecycle.unwind(db,item,self.client,record,binding,observation_ms=observed)
            else:
                _,active,_,remaining,_=lifecycle.owned_snapshot(self.client,item,record,observation_ms=observed)
                if remaining:
                    if (len(active)!=1 or active[0]['type']!='stop' or active[0]['status']!='partially_filled'
                        or positive(active[0]['qty'])-dec(active[0]['filled_qty'])!=remaining
                        or positive(active[0]['stop_price'])<positive(p['native_floor'])):
                        raise ValueError('MONTHLY_PARTIAL_REMAINDER_NOT_PROTECTED')
                    return result('MONTHLY_PARTIAL_STOP_PROTECTED',remaining_qty=str(remaining))
                out=lifecycle.finish_exit(db,item,self.client,record,binding,observation_ms=observed)
            if out['status']!='LIVE_EXIT_PENDING_FINALITY':return out
            orders=out['exit_orders'];reason=('emergency_protection_failure' if p.get('protection_pending')
                else 'protective_stop_gap_open' if unwind else 'protective_stop_intraday')
            self.book.record_exit(p['symbol'],orders,reason=reason,observed_ms=observed(),remaining_qty='0',open_order_ids=[])
            return result('MONTHLY_EXIT_PENDING_ACCOUNTING',broker_flat=True,entry_reenabled=False,
                gross_before_fees=out['gross_before_fees'],net_pnl_status='NOT_PROVEN')

    def _recover_safety_exits(self,*,now_ms):
        state=json.loads(self.ledger.read_text()) if self.ledger.exists() else {};out=[]
        for p in self.book.rows('positions'):
            if p['symbol'] in state:continue
            identity=digest(dict(schema=CONTRACT['schema'],entry_id=p['entry_id']))
            path=self.runtime/'safety'/identity/'live.sqlite'
            if not path.is_file():raise ValueError('MONTHLY_SAFETY_RECOVERY_SOURCE_REQUIRED')
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
            item=json.loads(row[0]) if row else {}
            if item.get('phase')!='EXIT_PENDING_FINALITY' or not item.get('retired_record'):
                raise ValueError('MONTHLY_SAFETY_RECOVERY_SOURCE_REQUIRED')
            out.append(self._settle_owned(p,item['retired_record'],now_ms=now_ms,
                unwind=bool(item.get('dispatches',{}).get('exit'))))
        return out
