"""Durable versioned monthly/daily source binding, with no money transport.

Native order readbacks are inputs, never discovered/adopted by ticker. This book
is separate from the installed NET ledger and cannot enable its own dispatcher.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import date,datetime,timedelta,timezone
import hashlib
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from research_lab.alpaca_dynamic_v1 import canonical,dec,digest,instant,pin,positive
from research_lab import alpaca_strategy_parity_v1 as baseline
from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
from research_lab.alpaca_dynamic_live_intake_v1 import _Readbacks
from scripts.alpaca_adaptive_paper import prepare_intended_report
from scripts import equities_alpaca_paper_bridge as native


CONTRACT=dict(schema='ALPACA_BASELINE_MONTHLY_DAILY_V1',enabled=False,orders_allowed=False,
    money_authority=False,owner_choice_date='2026-10-16',reference_commit=baseline.REFERENCE_COMMIT,
    reference_trades_core_sha16=baseline.REFERENCE_CORE,selection='MONTH_END_NEXT_OPEN',
    ratchet='DAILY_CLOSE_NEXT_SESSION',initial_stop_anchor='ACTUAL_FILL_MINUS_RAW_2ATR20',
    reentry_calendar_days=21,capital_ceiling_usd='487.42',gross_ceiling='.70',
    maximum_weight='.60',max_positions=4)


def result(status,**fields):
    return dict(status=status,orders_allowed=False,money_authority=False,
                production_writer_installed=False,**fields)


def entry_cid(selection,symbol):
    return 'abm-'+digest(dict(selection_id=selection['selection_id'],symbol=symbol))[:32]


def monthly_picks(picks):
    """New production interface exposes raw ATR, never a signal-close stop."""
    return [{k:v for k,v in p.items() if k!='stop_price'} for p in picks]


def strategy_identity():
    """Recomputable identity uses relative names and bytes, never machine paths."""
    root=Path(__file__).resolve().parents[1]
    files=['research_lab/alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_native_binding_v1.py',
           'research_lab/alpaca_completed_session_source_v1.py','scripts/equities_alpaca_paper_bridge.py']
    material=dict(schema='ALPACA_MONTHLY_STRATEGY_IDENTITY_V1',contract=CONTRACT,
        reference_universe_sha256='36da070b2e1fb6c7a10d3df99716c94e2afcabc7bae57d3ca172441736107172',
        reference_trades_core_sha16=baseline.REFERENCE_CORE,
        files={**baseline.source_pins(),**{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}})
    return dict(strategy_id='ALPACA_MONTHLY_BASELINE_'+digest(material),material=material)


class MonthlyBook:
    def __init__(self,path,contract):
        if contract!=CONTRACT:raise ValueError('MONTHLY_CONTRACT_CONFLICT')
        self.path=Path(path).absolute();self.contract=deepcopy(contract)
        if any(p.is_symlink() for p in (self.path,*self.path.parents)):
            raise ValueError('MONTHLY_STATE_SYMLINK')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink!=1
                                  or self.path.stat().st_uid!=os.getuid()):
            raise ValueError('MONTHLY_STATE_IDENTITY')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            for name in ('selections','positions','closes','stops','exits','rotations','dispatches'):
                db.execute('CREATE TABLE IF NOT EXISTS '+name+' (key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY,kind TEXT,payload TEXT,previous_sha256 TEXT,sha256 TEXT)')
            stored=db.execute("SELECT value FROM meta WHERE key='contract'").fetchone()
            if stored and stored[0]!=digest(contract):raise ValueError('MONTHLY_CONTRACT_CHANGED')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('contract',?)",(digest(contract),))
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    @staticmethod
    def _rows(db,table):
        import json
        return [json.loads(r[0]) for r in db.execute('SELECT payload FROM '+table+' ORDER BY key')]

    def rows(self,table):
        if table not in {'selections','positions','closes','stops','exits','rotations','dispatches','events'}:
            raise ValueError('TABLE_REFUSED')
        with self.db() as db:
            if table=='events':return list(db.execute('SELECT kind,payload,previous_sha256,sha256 FROM events ORDER BY id'))
            return self._rows(db,table)

    @staticmethod
    def _save(db,table,key,value):
        db.execute('INSERT OR REPLACE INTO '+table+' VALUES (?,?)',(key,canonical(value).decode()))

    @staticmethod
    def _event(db,kind,value):
        previous=db.execute('SELECT sha256 FROM events ORDER BY id DESC LIMIT 1').fetchone()
        previous=previous[0] if previous else '0'*64
        payload=canonical(value).decode();sha=digest(dict(kind=kind,payload=value,previous_sha256=previous))
        db.execute('INSERT INTO events (kind,payload,previous_sha256,sha256) VALUES (?,?,?,?)',
                   (kind,payload,previous,sha))

    def seal_selection(self,history,calendar,*,signal_session,entry_session,
                       source_available_ms,source_sha256,now_ms):
        baseline.source_pins();baseline._calendar(calendar);pin(source_sha256)
        now=instant(now_ms);available=instant(source_available_ms)
        signal=next((r for r in calendar if r['session']==signal_session),None)
        entry=next((r for r in calendar if r['session']==entry_session),None)
        prior=[r for r in calendar if entry and r['close_ms']<entry['open_ms']]
        if (not signal or not entry or not prior or prior[-1]!=signal
            or signal_session[:7]==entry_session[:7]
            or not signal['close_ms']<=available<=now<entry['open_ms']+300000):
            raise ValueError('STALE_SIGNAL_RESELECT_FAIL')
        causal={s:[{**asdict(b),'session_date':b.session_date.isoformat()}
                   for b in rows if b.session_date<=date.fromisoformat(signal_session)]
                for s,rows in history.items()}
        identity=dict(signal_session=signal_session,entry_session=entry_session,
            calendar=calendar,causal_history_sha256=digest(causal),source_sha256=source_sha256,
            source_available_ms=available,contract_sha256=digest(self.contract))
        key=digest(identity)
        with self.db() as db:
            prior=[s for s in self._rows(db,'selections') if s['entry_session']==entry_session]
            if prior:
                if prior[0]['selection_id']!=key:raise ValueError('MONTHLY_SOURCE_CONFLICT')
                return prior[0]
            selection=prepare_intended_report(history,signal_session=date.fromisoformat(signal_session),
                entry_session=date.fromisoformat(entry_session))
            out={**identity,'selection_id':key,'picks':monthly_picks(selection['picks']),
                 'gate_ok':selection['gate_ok'],'reason':selection['reason'],
                 'source_code_sha256':baseline.source_pins()}
            self._save(db,'selections',key,out);self._event(db,'MONTHLY_SELECTION_SEALED',out)
        return out

    def _selection(self,db,key):
        found=next((r for r in self._rows(db,'selections') if r['selection_id']==key),None)
        if found is None:raise ValueError('MONTHLY_SELECTION_UNKNOWN')
        return found

    def monthly_actions(self,selection_id,*,now_ms):
        now=instant(now_ms)
        with self.db() as db:
            s=self._selection(db,selection_id)
            window=next(r for r in s['calendar'] if r['session']==s['entry_session'])
            if not window['open_ms']<=now<window['open_ms']+300000:
                return result('NO_SEND',reason='STALE_SIGNAL_RESELECT_FAIL')
            positions=self._rows(db,'positions');held={r['symbol'] for r in positions}
            picks={p['symbol'] for p in s['picks']} if s['gate_ok'] else set()
            current_date=datetime.fromtimestamp(now/1000,ZoneInfo('America/New_York')).date()
            blocked={r['symbol'] for r in self._rows(db,'exits') if r['reason'].startswith('protective_stop')
                and current_date<datetime.fromtimestamp(r['filled_ms']/1000,ZoneInfo('America/New_York')).date()+timedelta(days=21)}
            rotate=sorted(held-picks);rotations=[]
            for symbol in rotate:
                p=next(p for p in positions if p['symbol']==symbol)
                identity=digest(dict(selection_id=selection_id,entry_id=p['entry_id'],symbol=symbol))
                action=dict(symbol=symbol,entry_id=p['entry_id'],qty=p['qty'],
                    selection_id=selection_id,client_order_id='abr-'+identity[:32],
                    entry_session=s['entry_session'],orders_allowed=False)
                old=next((r for r in self._rows(db,'rotations') if r['client_order_id']==action['client_order_id']),None)
                if old and old!=action:raise ValueError('ROTATION_INTENTION_CONFLICT')
                if not old:
                    self._save(db,'rotations',action['client_order_id'],action)
                    self._event(db,'ROTATION_INTENTION_PREPARED',action)
                rotations.append(action)
            return result('MONTHLY_PLAN_ORDERS_OFF',selection_id=selection_id,
                retain=sorted(held&picks),rotate=rotate,rotation_intentions=rotations,
                new_symbols=[p['symbol'] for p in s['picks'] if p['symbol'] not in held|blocked] if s['gate_ok'] and not rotate else [],
                cooldown_symbols=sorted(blocked),native_rotation='scripts.equities_alpaca_paper_bridge._rotate_intended_monthly')

    def bind_fill(self,selection_id,entry,stop):
        with self.db() as db:
            s=self._selection(db,selection_id);symbol=entry['symbol']
            pick=next((p for p in s['picks'] if p['symbol']==symbol),None)
            if not pick or entry['client_order_id']!=entry_cid(s,symbol) or entry['side']!='buy':
                raise ValueError('ENTRY_OWNER_CONFLICT')
            old=next((r for r in self._rows(db,'positions') if r['symbol']==symbol),None)
            if old:
                if old['selection_id']!=selection_id:raise ValueError('NATIVE_LIFECYCLE_CONFLICT')
                execution_identity_v1(old['raw_entry'],entry)
                if (stop['id']!=old['native_stop_id'] or positive(stop['stop_price'])<dec(old['native_floor'])
                    or positive(stop['qty'])-dec(stop.get('filled_qty','0'))!=dec(old['qty'])):
                    raise ValueError('NATIVE_LIFECYCLE_CONFLICT')
                return old
            stamp=datetime.fromisoformat(entry['filled_at'].replace('Z','+00:00'))
            if stamp.tzinfo is None:raise ValueError('FILL_TIME_UNKNOWN')
            start=next(r['open_ms'] for r in s['calendar'] if r['session']==s['entry_session'])
            if (entry['status'] not in {'filled','canceled','expired'}
                or not start<=int(stamp.timestamp()*1000)<start+300000):raise ValueError('FILL_TIME_OR_STATUS_CONFLICT')
            qty=positive(entry['filled_qty']);price=positive(entry['filled_avg_price'])
            floor=baseline.initial_stop(price,pick['atr20'])
            if (stop['symbol']!=symbol or stop['side']!='sell' or stop['type']!='stop'
                or stop['status'] not in {'new','accepted'} or dec(stop.get('filled_qty','0'))!=0
                or positive(stop['qty'])!=qty or positive(stop['stop_price'])!=dec(floor)):
                raise ValueError('STOP_COVER_CONFLICT')
            try:
                native._confirmed_intended_stop(_Readbacks([entry,stop]),stop,
                    symbol=symbol,qty=float(qty),requested_stop=floor)
            except native.IntendedPaperProtectionError as exc:
                raise ValueError('STOP_COVER_CONFLICT:'+str(exc)) from exc
            out=dict(symbol=symbol,selection_id=selection_id,entry_id=entry['id'],qty=str(qty),
                atr20=pick['atr20'],raw_entry=entry,native_stop_id=stop['id'],
                native_stop_history=[stop['id']],
                native_floor=float(positive(stop['stop_price'])),
                daily_state=baseline.initial_state(symbol,price,pick['atr20'],s['entry_session']))
            out['daily_state']['active_stop']=out['native_floor']
            self._save(db,'positions',symbol,out);self._event(db,'NATIVE_FILL_BOUND',out)
            return out

    def bind_rejected_protection(self,selection_id,entry):
        """Durable real fill for safety recovery, explicitly NEVER protected."""
        with self.db() as db:
            s=self._selection(db,selection_id);symbol=entry['symbol']
            p=next(p for p in s['picks'] if p['symbol']==symbol)
            start=next(r['open_ms'] for r in s['calendar'] if r['session']==s['entry_session'])
            stamp=native._parse_iso_utc(entry['filled_at'])
            if (entry['client_order_id']!=entry_cid(s,symbol) or entry['side']!='buy'
                or entry['status'] not in {'filled','canceled','expired'} or stamp is None
                or not start<=int(stamp.timestamp()*1000)<start+300000):
                raise ValueError('PENDING_PROTECTION_OWNER_OR_TIME')
            price=positive(entry['filled_avg_price']);qty=positive(entry['filled_qty'])
            old=next((r for r in self._rows(db,'positions') if r['symbol']==symbol),None)
            if old:
                execution_identity_v1(old['raw_entry'],entry);return old
            out=dict(symbol=symbol,selection_id=selection_id,entry_id=entry['id'],qty=str(qty),
                atr20=p['atr20'],raw_entry=entry,native_stop_id=None,native_stop_history=[],
                native_floor=baseline.initial_stop(price,p['atr20']),protection_pending=True,
                daily_state=baseline.initial_state(symbol,price,p['atr20'],s['entry_session']))
            self._save(db,'positions',symbol,out);self._event(db,'NATIVE_PROTECTION_REJECTED',out)
            return out

    def observe_close(self,source,*,now_ms):
        now=instant(now_ms);available=instant(source['available_ms']);completed=instant(source['completed_ms'])
        if (source['schema']!='ALPACA_COMPLETED_SESSION_SOURCE_V1'
            or source['source'] not in {'RECORDED_REGULAR_SESSION_OHLC','ALPACA_FROZEN_HOURLY_REGULAR_SESSION_V1'}
            or digest(source['raw'])!=pin(source['raw_sha256']) or not available<=completed<=now):
            raise ValueError('DAILY_SOURCE_IDENTITY_OR_TIME')
        baseline._calendar(source['calendar']);key=digest(source)
        with self.db() as db:
            if any(r['source_id']==key for r in self._rows(db,'closes')):
                return result('DAILY_ALREADY_BOUND',source_id=key)
            positions=self._rows(db,'positions');raw=source['raw'];symbols=[r['symbol'] for r in raw]
            if len(symbols)!=len(set(symbols)) or set(symbols)!={p['symbol'] for p in positions}:
                raise ValueError('DAILY_OWNED_SYMBOL_COVERAGE')
            actions=[]
            for p in positions:
                if p.get('protection_pending'):raise ValueError('PROTECTION_RECONCILIATION_REQUIRED')
                selection=self._selection(db,p['selection_id'])
                if any(r not in source['calendar'] for r in selection['calendar']):
                    raise ValueError('DAILY_CALENDAR_SOURCE_CONFLICT')
                row=next(r for r in raw if r['symbol']==p['symbol']);bar={k:v for k,v in row.items() if k!='symbol'}
                session=next((r for r in source['calendar'] if r['session']==bar['session']),None)
                if session is None or available<session['close_ms']:raise ValueError('PARTIAL_DAILY_SOURCE')
                transition=baseline.daily_transition(p['daily_state'],bar,source['calendar'],available)
                if transition['status']=='REFERENCE_STOP_EXIT':
                    raise ValueError('BROKER_EXIT_RECONCILIATION_REQUIRED:'+p['symbol'])
                if transition['status']=='NOT_DUE':raise ValueError('PARTIAL_DAILY_SOURCE')
                if transition['status']=='ALREADY_OBSERVED':continue
                p['daily_state']=transition['state']
                if p['daily_state']['active_stop']>p['native_floor']:
                    future=next(r for r in source['calendar'] if r['session']==transition['stop_effective_session'])
                    action=dict(symbol=p['symbol'],entry_id=p['entry_id'],qty=p['qty'],
                        prior_stop_id=p['native_stop_id'],stop_price=p['daily_state']['active_stop'],
                        not_before_ms=future['open_ms'],effective_session=future['session'],
                        source_id=key,confirmed=False)
                    action['action_id']=digest(action)
                    action['client_order_id']='dyr-'+action['action_id'][:32]
                    self._save(db,'stops',action['action_id'],action);actions.append(action)
                self._save(db,'positions',p['symbol'],p)
            receipt=dict(source_id=key,source=source,completed_ms=completed)
            self._save(db,'closes',key,receipt);self._event(db,'DAILY_SOURCE_BOUND',receipt)
        return result('DAILY_SOURCE_BOUND',source_id=key,stop_intentions=len(actions))

    def stop_actions(self,*,now_ms):
        now=instant(now_ms)
        with self.db() as db:
            return result('STOP_INTENTIONS_ORDERS_OFF',actions=[a for a in self._rows(db,'stops')
                if a['confirmed'] is False and not a.get('retired_by_exit') and not a.get('superseded_by')
                and a['not_before_ms']<=now])

    def prepare_rearm(self,symbol,session):
        """Persist same-floor DAY renewal; no intraday price enters the ratchet."""
        with self.db() as db:
            p=next(p for p in self._rows(db,'positions') if p['symbol']==symbol)
            calendars=[s['calendar'] for s in self._rows(db,'selections')]
            calendars += [c['source']['calendar'] for c in self._rows(db,'closes')]
            rows=[r for cal in calendars for r in cal if r['session']==session]
            if not rows or any(r!=rows[0] for r in rows):raise ValueError('REARM_SESSION_UNKNOWN')
            action=dict(symbol=symbol,entry_id=p['entry_id'],qty=p['qty'],prior_stop_id=p['native_stop_id'],
                stop_price=p['native_floor'],not_before_ms=rows[0]['open_ms'],effective_session=session,
                source_id=digest(dict(entry_id=p['entry_id'],session=session)),confirmed=False)
            action['action_id']=digest(action);action['client_order_id']='dyr-'+action['action_id'][:32]
            old=next((a for a in self._rows(db,'stops') if a['action_id']==action['action_id']),None)
            if not old:self._save(db,'stops',action['action_id'],action);self._event(db,'DAY_REARM_PREPARED',action)
            return old or action

    def claim_dispatch(self,key,payload):
        """Fsync before I/O; an existing unresolved attempt is never resent."""
        with self.db() as db:
            old=next((r for r in self._rows(db,'dispatches') if r['key']==key),None)
            if old:
                if old['payload']!=payload:raise ValueError('DISPATCH_PAYLOAD_CONFLICT')
                return False
            out=dict(key=key,payload=payload,state='DISPATCHED')
            self._save(db,'dispatches',key,out);self._event(db,'NATIVE_DISPATCH_PREPARED',out)
            return True

    def confirm_stop(self,action_id,stop,*,observed_ms):
        now=instant(observed_ms)
        with self.db() as db:
            a=next((r for r in self._rows(db,'stops') if r['action_id']==action_id),None)
            if a is None:raise ValueError('STOP_INTENTION_UNKNOWN')
            if (now<a['not_before_ms'] or a.get('retired_by_exit')
                or not (stop.get('replaces')==a['prior_stop_id']
                        or stop.get('client_order_id')==a['client_order_id'])):
                raise ValueError('STOP_CONFIRMATION_OWNER_OR_TIME')
            p=next(r for r in self._rows(db,'positions') if r['symbol']==a['symbol'])
            if (stop['symbol']!=a['symbol'] or stop['side']!='sell' or stop['type']!='stop'
                or stop['status'] not in {'new','accepted'} or positive(stop['qty'])!=positive(a['qty'])
                or dec(stop.get('filled_qty','0'))!=0
                or positive(stop['stop_price'])!=max(dec(a['stop_price']),dec(p['native_floor']))):
                raise ValueError('STOP_CONFIRMATION_CONFLICT')
            try:
                native._confirmed_intended_stop(_Readbacks([stop]),stop,symbol=a['symbol'],
                    qty=float(positive(a['qty'])),requested_stop=float(a['stop_price']))
            except native.IntendedPaperProtectionError as exc:
                raise ValueError('STOP_CONFIRMATION_CONFLICT:'+str(exc)) from exc
            if a['confirmed']:
                if a['accepted_stop_id']!=stop['id']:raise ValueError('STOP_CONFIRMATION_CONFLICT')
                return
            a.update(confirmed=True,accepted_stop_id=stop['id'],raw_stop_sha256=digest(stop))
            p.update(native_floor=float(positive(stop['stop_price'])),native_stop_id=stop['id'])
            if stop['id'] not in p['native_stop_history']:p['native_stop_history'].append(stop['id'])
            self._save(db,'positions',p['symbol'],p);self._save(db,'stops',action_id,a)
            for prior in self._rows(db,'stops'):
                if (prior['entry_id']==p['entry_id'] and not prior['confirmed']
                    and prior['not_before_ms']<=now and dec(prior['stop_price'])<=dec(p['native_floor'])):
                    prior['superseded_by']=action_id;self._save(db,'stops',prior['action_id'],prior)
            self._event(db,'BROKER_STOP_CONFIRMED',dict(action=a,raw_stop=stop))

    def record_exit(self,symbol,orders,*,reason,observed_ms,remaining_qty,open_order_ids):
        now=instant(observed_ms)
        if reason not in {'protective_stop_intraday','protective_stop_gap_open','monthly_rotation_next_open',
                          'emergency_protection_failure'}:
            raise ValueError('EXIT_REASON_UNKNOWN')
        if dec(remaining_qty)!=0 or type(open_order_ids) is not list or open_order_ids:
            raise ValueError('EXIT_NOT_FLAT_OR_ORDERS_REMAIN')
        if not orders or len({o['id'] for o in orders})!=len(orders):raise ValueError('EXIT_SOURCES_UNKNOWN')
        with self.db() as db:
            p=next((p for p in self._rows(db,'positions') if p['symbol']==symbol),None)
            if p is None:
                prior=next((r for r in self._rows(db,'exits') if r['symbol']==symbol
                    and {o['id'] for o in r['orders']}=={o['id'] for o in orders}),None)
                if not prior or prior['reason']!=reason:raise ValueError('EXIT_LIFECYCLE_UNKNOWN')
                for o in orders:execution_identity_v1(next(old for old in prior['orders'] if old['id']==o['id']),o)
                return prior
            rotations=[r for r in self._rows(db,'rotations') if r['entry_id']==p['entry_id']]
            qty=dec(0);stamps=[]
            entry=datetime.fromisoformat(p['raw_entry']['filled_at'].replace('Z','+00:00'))
            for o in orders:
                if (o['symbol']!=symbol or o['side']!='sell' or o['status'] not in {'filled','canceled','expired'}
                    or positive(o['filled_qty'])>positive(o['qty'])):raise ValueError('EXIT_FILL_CONFLICT')
                if reason=='monthly_rotation_next_open':
                    if o['type']!='market' or not any(r['client_order_id']==o.get('client_order_id') for r in rotations):
                        raise ValueError('ROTATION_EXIT_OWNER_CONFLICT')
                elif o['type']=='market':
                    expected='dyx-'+digest(dict(schema=CONTRACT['schema'],entry_id=p['entry_id']))[:32]
                    if o.get('client_order_id')!=expected:raise ValueError('SAFETY_EXIT_OWNER_CONFLICT')
                elif o['type']!='stop' or o['id'] not in p['native_stop_history']:
                    raise ValueError('STOP_EXIT_OWNER_CONFLICT')
                stamp=datetime.fromisoformat(o['filled_at'].replace('Z','+00:00'))
                if stamp.tzinfo is None or not int(entry.timestamp()*1000)<=int(stamp.timestamp()*1000)<=now:
                    raise ValueError('EXIT_FILL_TIME_CONFLICT')
                positive(o['filled_avg_price']);qty+=positive(o['filled_qty']);stamps.append(int(stamp.timestamp()*1000))
            if qty!=positive(p['qty']):raise ValueError('EXIT_QUANTITY_CONFLICT')
            out=dict(symbol=symbol,entry_id=p['entry_id'],reason=reason,filled_ms=max(stamps),
                orders=orders,retired_position=p,net_pnl_status='NOT_COMPUTED_BY_SOURCE_BOOK')
            self._save(db,'exits',p['entry_id'],out);db.execute('DELETE FROM positions WHERE key=?',(symbol,))
            for a in self._rows(db,'stops'):
                if a['entry_id']==p['entry_id'] and not a['confirmed']:
                    a['retired_by_exit']=True;self._save(db,'stops',a['action_id'],a)
            self._event(db,'OWNED_EXIT_BOUND',out)
            return out
