"""Monthly source binding to the existing account-owner primitives.

Default OFF. No credential loader, scheduler, HALT release or owner permit is
provided here. An activated caller must still hold the original account lock,
pass the native LIVE binding/approval checks and supply its explicit client.
The disabled source CLI cannot call the applying methods.
"""
from datetime import datetime,timezone
import json
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
from research_lab.alpaca_monthly_binding_v1 import CONTRACT,entry_cid,result,monthly_picks
from scripts import equities_alpaca_paper_bridge as native


class MonthlyNativeBinding:
    def __init__(self,book,*,client,base_url,account_id,capital,runtime,lock_path,entry_halt_path):
        if book.contract!=CONTRACT:raise ValueError('MONTHLY_CONTRACT_CONFLICT')
        self.book=book;self.client=client;self.base_url=base_url;self.account=account_id
        self.capital=float(positive(capital))
        if self.capital>float(CONTRACT['capital_ceiling_usd']):raise ValueError('MONTHLY_CAPITAL_CAP')
        self.runtime=Path(runtime).absolute();self.lock_path=Path(lock_path).absolute()
        if any(p.is_symlink() for p in (self.runtime,*self.runtime.parents)):
            raise ValueError('MONTHLY_NATIVE_PATH')
        self.ledger=self.runtime/'native-floor.json';self.reentry=self.runtime/'native-intents.json'
        self.halt=lifecycle.safe_path(str(Path(entry_halt_path).absolute()))
        if self.halt==self.ledger or self.halt==self.reentry or self.halt==self.lock_path:
            raise ValueError('MONTHLY_HALT_PATH_CONFLICT')

    def _selection(self,key):
        found=next((s for s in self.book.rows('selections') if s['selection_id']==key),None)
        if found is None:raise ValueError('MONTHLY_SELECTION_UNKNOWN')
        return found

    def _native_authority(self):
        if not native._intended_lifecycle_enabled(self.base_url,account_id=self.account,
            capital=self.capital,require_enabled=True):
            raise native.IntendedPaperProtectionError('monthly_native_mode_not_enabled')
        if self.client.get_account().get('id')!=self.account:
            raise ValueError('MONTHLY_NATIVE_ACCOUNT_CONFLICT')

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
                pick=SimpleNamespace(ticker=ticket['symbol'],entry_day=s['entry_session'],
                    entry_price=gate['signal_close'],stop_price=gate['signal_close']-2.*gate['atr20'])
                try:
                    native._submit_intended_reserved_entry(**args,pick=pick,notional=ticket['notional'],timeout_sec=0,
                        baseline_atr20=gate['atr20'],baseline_signal_session=s['signal_session'],
                        baseline_selection_sha256=s['selection_id'],baseline_entry_gate=gate)
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
            self.book.bind_fill(s['selection_id'],entry,stop)
            return result('MONTHLY_NATIVE_PROTECTED',symbol=ticket['symbol'],entry_order_id=entry['id'],
                stop_order_id=stop['id'],stop_price=record['accepted_stop_floor'])

    def rotate(self,selection_id,*,now_ms,apply=False):
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

    def _recover_rotation_receipts(self,*,now_ms):
        """Close the second journal after a crash between native/book commits."""
        if not self.reentry.exists():return
        native_state=json.loads(self.ledger.read_text()) if self.ledger.exists() else {}
        receipts=json.loads(self.reentry.read_text()).get('rotation_exits',{})
        for p in self.book.rows('positions'):
            if p['symbol'] in native_state:continue
            actions=[r for r in self.book.rows('rotations') if r['entry_id']==p['entry_id']]
            matched=[r for r in receipts.values() if r.get('entry_order_id')==p['entry_id']
                and any(a['client_order_id']==r['exit_order'].get('client_order_id') for a in actions)]
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
