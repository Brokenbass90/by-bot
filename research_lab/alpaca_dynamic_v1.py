"""Prospective reserve replacement book. Local plans only; no broker/order API.

Inputs are caller-provided evidence, not authenticated broker truth. Even a
reserved plan has no money/promotion authority. Existing LIVE files are unused.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def dec(x):
    if isinstance(x,bool):raise ValueError('INVALID_NUMBER')
    d=Decimal(str(x))
    if not d.is_finite():raise ValueError('INVALID_NUMBER')
    return d

def positive(x):
    d=dec(x)
    if d<=0:raise ValueError('NONPOSITIVE_NUMBER')
    return d

def pin(x):
    if not isinstance(x,str) or not re.fullmatch('[0-9a-f]{64}',x):raise ValueError('INVALID_SOURCE_PIN')
    return x

def instant(x):
    if type(x) is not int or x<0:raise ValueError('INVALID_TIME')
    return x

def day(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).date()

def session_at(calendar,now):
    if not calendar:raise ValueError('MISSING_CALENDAR')
    previous=None;seen=set()
    for row in calendar:
        d=date.fromisoformat(row['session']);start=instant(row['open_ms']);end=instant(row['close_ms'])
        if d in seen or day(start)!=d or start>=end or (previous and previous['close_ms']>=start):raise ValueError('INVALID_CALENDAR')
        seen.add(d);previous=row
    return next((r for r in calendar if r['open_ms']<=now<r['open_ms']+300000),None)

def policy_check(p):
    if (p['schema']!='ALPACA_DYNAMIC_V1' or p['mode']!='ORDERS_OFF' or p['money_authority'] is not False
        or dec(p['capital_usd'])!=Decimal('487.42') or dec(p['gross'])!=Decimal('.70')
        or p['max_positions']!=4 or p['max_new_entries_per_session']!=1
        or p['max_snapshot_age_ms']!=300000 or p['forced_rotation'] is not False or p['daily_refresh_enabled'] is not False):raise ValueError('POLICY_BOUNDARY')
    if instant(p['sealed_ms'])>=instant(p['first_window_ms']):raise ValueError('INVALID_EPOCH')
    pin(p['source_snapshot_sha256']);ids=set();symbols=set();total=Decimal(0)
    if p['reentry_calendar_days']!=21 or len(set(p['universe']))!=len(p['universe']) or 'SPY' not in p['universe']:raise ValueError('POLICY_BOUNDARY')
    pin(p['universe_source_sha256']);pin(p['calendar_raw_sha256'])
    if digest(p['calendar_sessions'])!=pin(p['calendar_sha256']) or instant(p['calendar_source_available_ms'])>p['sealed_ms']:raise ValueError('CALENDAR_SOURCE_CONFLICT')
    session_at(p['calendar_sessions'],p['first_window_ms'])
    for slot in p['inherited_slots']:
        if not slot['entry_order_id'] or slot['entry_order_id'] in ids or slot['symbol'] in symbols:raise ValueError('DUPLICATE_SLOT')
        ids.add(slot['entry_order_id']);symbols.add(slot['symbol'])
        if not 0<instant(slot['entry_ms'])<=p['sealed_ms']:raise ValueError('INVALID_INHERITED_ENTRY_TIME')
        n=positive(slot['notional_cap']);risk=positive(slot['risk_cap'])
        if n!=positive(slot['qty'])*positive(slot['entry_price']) or risk>=n or n>dec(p['capital_usd'])*dec(p['gross'])*Decimal('.60'):raise ValueError('SLOT_CAP')
        total+=n
    if len(ids)>4 or total>dec(p['capital_usd'])*dec(p['gross']):raise ValueError('PORTFOLIO_CAP')


def source_check(policy,calendar):
    """Calendar completeness and selector dependency pins were sealed before ranking."""
    if digest(calendar)!=policy['calendar_sha256']:raise ValueError('CALENDAR_SOURCE_CONFLICT')
    from scripts.alpaca_adaptive_paper import ROOT, _frozen_source_hashes
    if _frozen_source_hashes()!=policy['selector_source_hashes']:raise ValueError('SELECTOR_SOURCE_CONFLICT')
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=value for name,value in policy['selector_file_sha256'].items()):raise ValueError('SELECTOR_SOURCE_CONFLICT')


def build_ranking(policy,calendar,history,blocked_symbols,source_pin,source_available_ms,now_ms):
    """Reuse the existing selector on closed bars after contemporaneous exclusions."""
    policy_check(policy);source_check(policy,calendar);pin(source_pin);now_ms=instant(now_ms);available=instant(source_available_ms)
    if set(history)!=set(policy['universe']):raise ValueError('UNIVERSE_SOURCE_CONFLICT')
    current=session_at(calendar,now_ms)
    if current is None or current['open_ms']<policy['first_window_ms']:raise ValueError('NOT_SELECTION_WINDOW')
    week=date.fromisoformat(current['session']).isocalendar()[:2]
    weekly=min((r['open_ms'] for r in calendar if date.fromisoformat(r['session']).isocalendar()[:2]==week))
    if current['open_ms']!=policy['first_window_ms'] and current['open_ms']!=weekly:raise ValueError('NOT_WEEKLY_REFRESH')
    prior=[r for r in calendar if r['close_ms']<current['open_ms']]
    if not prior or not prior[-1]['close_ms']<=available<=now_ms:raise ValueError('MISSING_OR_FUTURE_SOURCE')
    cutoff=date.fromisoformat(prior[-1]['session']);blocked=set(blocked_symbols)
    from scripts.alpaca_adaptive_paper import prepare_intended_report
    eligible={s:rows for s,rows in sorted(history.items()) if s=='SPY' or s not in blocked}
    report=prepare_intended_report(eligible,signal_session=cutoff,entry_session=date.fromisoformat(current['session']))
    return {'policy_sha256':digest(policy),'window_ms':current['open_ms'],'signal_session':cutoff.isoformat(),
        'input_sha256':source_pin,'source_available_ms':available,'gate_ok':report['gate_ok'],
        'picks':report['picks'],'blocked_symbols':sorted(blocked),'selector_source_hashes':report['selector_source_hashes']}


class DynamicBook:
    def __init__(self,path,policy):
        policy_check(policy);self.policy=json.loads(canonical(policy));self.path=Path(path).absolute();self.policy_hash=digest(policy)
        if any(p.is_symlink() for p in [self.path,*self.path.parents]):raise ValueError('STATE_SYMLINK')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink!=1 or self.path.stat().st_uid!=os.getuid()):raise ValueError('STATE_IDENTITY')
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS rankings (window INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS slots (entry TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS intents (entry TEXT PRIMARY KEY,session TEXT NOT NULL,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS exits (entry TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            prior=db.execute("SELECT value FROM meta WHERE key='policy'").fetchone()
            if prior and prior[0]!=self.policy_hash:raise ValueError('POLICY_CONFLICT')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('policy',?)",(self.policy_hash,))
            for s in policy['inherited_slots']:db.execute('INSERT OR IGNORE INTO slots VALUES (?,?)',(s['entry_order_id'],canonical(s).decode()))
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def seal_ranking(self,ranking,calendar,now_ms):
        r=json.loads(canonical(ranking));p=self.policy;window=instant(r['window_ms'])
        source_check(p,calendar)
        if r.get('selector_source_hashes')!=p['selector_source_hashes']:raise ValueError('SELECTOR_SOURCE_CONFLICT')
        if (r['policy_sha256']!=self.policy_hash or window<p['first_window_ms'] or now_ms<window
            or now_ms>=window+300000 or instant(r['source_available_ms'])>now_ms
            or date.fromisoformat(r['signal_session'])>=day(window) or type(r['gate_ok']) is not bool):raise ValueError('INVALID_RANKING')
        current=session_at(calendar,now_ms)
        week=day(window).isocalendar()[:2]
        first=min(v['open_ms'] for v in calendar if day(v['open_ms']).isocalendar()[:2]==week)
        prior=[v for v in calendar if v['close_ms']<window]
        if (not current or current['open_ms']!=window or (window!=p['first_window_ms'] and window!=first)
            or not prior or r['signal_session']!=prior[-1]['session'] or r['source_available_ms']<prior[-1]['close_ms']):raise ValueError('INVALID_REFRESH_WINDOW')
        pin(r['input_sha256']);seen=set()
        for pick in r['picks']:
            if pick['symbol'] in seen or pick['symbol'] in r['blocked_symbols'] or pick['symbol'] not in p['universe']:raise ValueError('INVALID_RANKING')
            seen.add(pick['symbol'])
            if not positive(pick['signal_close'])>positive(pick['stop_price']):raise ValueError('INVALID_REFERENCE_STOP')
        with self.db() as db:
            old=db.execute('SELECT payload FROM rankings WHERE window=?',(window,)).fetchone();raw=canonical(r).decode()
            if old and old[0]!=raw:raise ValueError('RANKING_CONFLICT')
            db.execute('INSERT OR IGNORE INTO rankings VALUES (?,?)',(window,raw))
        return digest(r)

    def intent_count(self):
        with self.db() as db:return db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]

    def ranking_at(self,window_ms):
        with self.db() as db:
            row=db.execute('SELECT payload FROM rankings WHERE window=?',(window_ms,)).fetchone()
            return json.loads(row[0]) if row else None

    def propose(self,snapshot,calendar,now_ms):
        try:
            with self.db() as db:return self._propose(db,snapshot,calendar,instant(now_ms))
        except (ValueError,KeyError,TypeError,ArithmeticError) as e:return self.result('BLOCKED_DATA',reason=str(e))

    @staticmethod
    def result(status,**fields):return {'status':status,'money_authority':False,'orders_allowed':False,'evidence_kind':'INPUT_PROVIDED_ORDERS_OFF',**fields}

    def _propose(self,db,s,calendar,now):
        p=self.policy;source_check(p,calendar);current=session_at(calendar,now)
        if not current or current['open_ms']<p['first_window_ms']:return self.result('NOT_SELECTION_WINDOW')
        fresh=instant(s['observed_ms'])
        if s['account_id']!=p['account_id'] or s['single_owner_verified'] is not True or s['cash_finality_verified'] is not True or not 0<=now-fresh<=p['max_snapshot_age_ms']:raise ValueError('BROKER_OR_CASH_UNCONFIRMED')
        pin(s['source_sha256']);cash=dec(s['cash_usd']);reserve=dec(s['liability_reserve_usd']);fee=dec(s['fee_rate'])
        if min(cash,reserve,fee)<0:raise ValueError('INVALID_COST_OR_CASH')
        ranking=db.execute('SELECT payload FROM rankings WHERE window<=? ORDER BY window DESC LIMIT 1',(current['open_ms'],)).fetchone()
        if not ranking:raise ValueError('MISSING_RANKING')
        ranking=json.loads(ranking[0]);week=day(current['open_ms']).isocalendar()[:2]
        if day(ranking['window_ms']).isocalendar()[:2]!=week:raise ValueError('WEEKLY_RANKING_EXPIRED')
        if not ranking['gate_ok']:return self.result('NO_ELIGIBLE_CANDIDATE',reason='SPY200_CASH_GATE')
        slots={entry:json.loads(raw) for entry,raw in db.execute('SELECT entry,payload FROM slots')}
        held={r['symbol'] for r in s['positions']};open_names={r['symbol'] for r in s['open_orders']}
        if len(held)!=len(s['positions']):raise ValueError('DUPLICATE_POSITION')
        if any(positive(r['qty'])<=0 for r in s['positions']):raise ValueError('INVALID_POSITION')
        if any(r.get('side')=='buy' for r in s['open_orders']):raise ValueError('PENDING_ENTRY')
        vacancies=[]
        for exit in s['exits']:
            slot=slots.get(exit['entry_order_id'])
            if not slot or slot['symbol'] in held|open_names:continue
            total=Decimal(0);valid=bool(exit['orders']);ids=set()
            for order in exit['orders']:
                qty=dec(order['filled_qty']);valid &= (order['id'] not in ids and order['symbol']==slot['symbol'] and order['side']=='sell'
                    and order['status'] in {'filled','canceled','expired'} and slot['entry_ms']<=instant(order['filled_ms'])<=fresh and qty>0 and positive(order['filled_avg_price'])>0)
                ids.add(order['id']);total+=qty
            if valid and total==positive(slot['qty']):
                vacancies.append(slot)
                raw=canonical(exit).decode();old=db.execute('SELECT payload FROM exits WHERE entry=?',(slot['entry_order_id'],)).fetchone()
                if old and old[0]!=raw:raise ValueError('EXIT_SOURCE_CONFLICT')
                db.execute('INSERT OR IGNORE INTO exits VALUES (?,?)',(slot['entry_order_id'],raw))
        if not vacancies:return self.result('NO_CONFIRMED_VACANCY')
        consumed={entry:json.loads(raw) for entry,raw in db.execute('SELECT entry,payload FROM intents')}
        free=sorted((v for v in vacancies if v['entry_order_id'] not in consumed),key=lambda r:r['entry_order_id'])
        if not free:return consumed[vacancies[0]['entry_order_id']]
        for intent in consumed.values():
            children=[slot for slot in slots.values() if slot.get('parent_receipt_id')==intent['receipt_id']]
            if not children:return self.result('PENDING_RESERVATION',reason='UNRESOLVED_PRIOR_INTENT',receipt_id=intent['receipt_id'])
            child=children[0]
            if child['symbol'] not in held and child not in vacancies:raise ValueError('PAPER_POSITION_UNRECONCILED')
        if db.execute('SELECT COUNT(*) FROM intents WHERE session=?',(current['session'],)).fetchone()[0]>=1:return self.result('SESSION_ENTRY_BUDGET')
        if len(held)>=p['max_positions']:return self.result('NO_ELIGIBLE_CANDIDATE',reason='POSITION_CAP')
        gross=sum((positive(r['market_value']) for r in s['positions']),Decimal(0))
        if gross<0:raise ValueError('INVALID_GROSS')
        available_gross=dec(p['capital_usd'])*dec(p['gross'])-gross;slot=free[0]
        recorded_exits=[json.loads(raw) for raw, in db.execute('SELECT payload FROM exits')]
        cooldown=held|set(s['blocked_symbols'])|{slots[e['entry_order_id']]['symbol'] for e in recorded_exits
            if now-max(o['filled_ms'] for o in e['orders'])<p['reentry_calendar_days']*86400000}
        for pick in ranking['picks']:
            symbol=pick['symbol'];g=s['gates'].get(symbol,{});q=s['quotes'].get(symbol,{})
            if symbol in cooldown or not all(g.get(k) is True for k in ('earnings','concentration','symbol','protection')):continue
            try:
                if q['tradable'] is not True or not 0<=now-instant(q['received_ms'])<=p['max_snapshot_age_ms']:continue
                price=positive(q['ask']);step=positive(q['qty_step']);minimum=positive(q['min_qty']);min_n=max(Decimal(1),positive(q['min_notional']))
                distance=positive(pick['signal_close'])-positive(pick['stop_price']);stop=(price-distance).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                if not 0<stop<price or step<Decimal('.000000001'):continue
                distance=price-stop;notional=min(positive(slot['notional_cap']),available_gross,dec(p['capital_usd'])*dec(p['gross'])*Decimal('.60'),(cash-reserve)/(1+fee))
                qty=(min(notional/price,positive(slot['risk_cap'])/distance)/step).to_integral_value(rounding=ROUND_DOWN)*step
                if qty<minimum or qty*price<min_n or (qty!=qty.to_integral_value() and q['fractionable'] is not True):continue
            except (ValueError,KeyError,ArithmeticError):continue
            core={'epoch_sha256':self.policy_hash,'slot_entry_order_id':slot['entry_order_id'],'symbol':symbol,
                'qty':format(qty,'f'),'reference_ask':str(price),'stop_price':str(stop),'risk_distance':str(distance),
                'notional_usd':str(qty*price),'modeled_stop_risk_usd':str(qty*distance),'protection_qty':format(qty,'f'),
                'notional_limit_usd':str(notional),'funding_limit_usd':str(notional*(1+fee)),'fee_rate':str(fee),
                'protection_tif':'gtc' if qty==qty.to_integral_value() else 'day','ranking_sha256':digest(ranking),
                'snapshot_sha256':digest(s),'source_sha256':s['source_sha256'],'session':current['session'],'prepared_ms':now}
            identity=digest(core);result=self.result('RESERVED_ORDERS_OFF',**core,receipt_id=identity,client_order_id='dyn1-'+identity[:32])
            db.execute('INSERT INTO intents VALUES (?,?,?)',(slot['entry_order_id'],current['session'],canonical(result).decode()));return result
        return self.result('NO_ELIGIBLE_CANDIDATE')

    def register_paper_fill(self,receipt_id,fill):
        """Accept a synthetic PAPER lifecycle only; never authenticate LIVE execution."""
        with self.db() as db:
            plans=[json.loads(raw) for raw, in db.execute('SELECT payload FROM intents')];plan=next((p for p in plans if p['receipt_id']==receipt_id),None)
            if not plan:raise ValueError('UNKNOWN_PARENT_INTENT')
            if fill['evidence_kind']!='PAPER_SIMULATED' or fill['account_id']!=self.policy['account_id'] or fill['symbol']!=plan['symbol'] or fill['entry_status']!='filled' or fill['stop_status']!='new':raise ValueError('INVALID_PAPER_FILL')
            qty=positive(fill['qty']);price=positive(fill['price']);stop=positive(fill['stop_price'])
            if qty>positive(plan['qty']) or positive(fill['stop_qty'])!=qty or stop<price-positive(plan['risk_distance']) or stop>=price:raise ValueError('UNPROTECTED_OR_OVERFILL')
            if qty*price>positive(plan['notional_limit_usd']) or qty*price*(1+dec(plan['fee_rate']))>positive(plan['funding_limit_usd']):raise ValueError('FILL_EXCEEDS_PLAN_BUDGET')
            parent=json.loads(db.execute('SELECT payload FROM slots WHERE entry=?',(plan['slot_entry_order_id'],)).fetchone()[0])
            if qty*price>positive(parent['notional_cap']) or qty*(price-stop)>positive(parent['risk_cap']):raise ValueError('FILL_EXCEEDS_SLOT_CAP')
            if instant(fill['filled_ms'])<plan['prepared_ms']:raise ValueError('FILL_BEFORE_PARENT')
            slot={'entry_ms':fill['filled_ms'],'entry_order_id':fill['entry_order_id'],'symbol':fill['symbol'],'qty':str(qty),'entry_price':str(price),
                'notional_cap':str(min(qty*price,positive(parent['notional_cap']))),'risk_cap':str(min(qty*(price-stop),positive(parent['risk_cap']))),'parent_receipt_id':receipt_id}
            old=db.execute('SELECT payload FROM slots WHERE entry=?',(slot['entry_order_id'],)).fetchone();raw=canonical(slot).decode()
            if old and old[0]!=raw:raise ValueError('FILL_CONFLICT')
            existing=[json.loads(v) for v, in db.execute('SELECT payload FROM slots') if json.loads(v).get('parent_receipt_id')==receipt_id]
            if existing and existing[0]['entry_order_id']!=slot['entry_order_id']:raise ValueError('DUPLICATE_PARENT_FILL')
            db.execute('INSERT OR IGNORE INTO slots VALUES (?,?)',(slot['entry_order_id'],raw));return slot
