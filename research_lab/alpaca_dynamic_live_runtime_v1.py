"""Isolated Dynamic LIVE lifecycle; OFF by default, no env/monthly-role override.

Nothing installs or activates this module. A future deployment must supply the
original shared lock, an independent LIVE source book and a separately approved
exact owner-GO file. Native ledger, re-arm and ratchet primitives are reused.
Every POST/PATCH is journaled before dispatch; unknown outcomes are never resent.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import re
from urllib import request, error
from urllib.parse import urlsplit, urlencode, parse_qs

from research_lab.alpaca_dynamic_live_intake_v1 import LIVE, compile_intake, native_handoff
from research_lab.alpaca_dynamic_v1 import DynamicBook, canonical, dec, digest, instant, positive, session_at
from scripts import equities_alpaca_paper_bridge as native
from scripts import alpaca_protective_exit_manager as ratchet

SCHEMA = 'ALPACA_DYNAMIC_LIVE_RUNTIME_V1'
# Existing Oct2 profile/defaults, not a new stop challenger.
RATCHET = dict(activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=.5,
               min_raise_bps=10., market_gap_bps=10.)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('LIVE_HTTP_REDIRECT_REFUSED')


class DynamicLiveClient(native.AlpacaClient):
    """Exact hosts; no proxies, global env, redirects, retries or flatten route.

    Even a writes-enabled client needs a one-use exact payload permit from the
    source/GO/lock-validated runtime *after* its durable dispatch commit.
    """
    def __init__(self,key,secret,*,writes_enabled=False,order_contract=SCHEMA):
        if order_contract not in {SCHEMA,'ALPACA_BASELINE_MONTHLY_DAILY_V1'}:
            raise ValueError('LIVE_ORDER_CONTRACT_UNKNOWN')
        super().__init__(LIVE,key,secret)
        self.order_contract=order_contract
        self.writes_enabled=writes_enabled
        self.write_permit=None
        self.opener=request.build_opener(request.ProxyHandler({}),NoRedirect(),
            request.HTTPSHandler(context=self._ssl_ctx))

    def permit_write(self,method,path,payload=None):
        if not self.writes_enabled:raise ValueError('LIVE_TRANSPORT_ORDERS_OFF')
        self.write_permit=(method,path,canonical(payload))

    def _request(self,method,path,payload=None):
        parts=urlsplit(path);route=parts.path
        if self.base_url!=LIVE or parts.scheme or parts.netloc or parts.fragment:
            raise ValueError('EXACT_LIVE_ENDPOINT_REQUIRED')
        order=bool(re.fullmatch(r'/v2/orders/[A-Za-z0-9_-]{1,128}',route))
        asset=bool(re.fullmatch(r'/v2/assets/[A-Z0-9.]{1,16}',route))
        if method=='GET':
            allowed=route in {'/v2/account','/v2/clock','/v2/positions','/v2/orders','/v2/orders:by_client_order_id'} or order or asset
            query=parse_qs(parts.query,keep_blank_values=True)
            valid_query=(not parts.query if route not in {'/v2/orders','/v2/orders:by_client_order_id'}
                else set(query).issubset({'status','direction','limit','symbols'} if route=='/v2/orders' else {'client_order_id'}))
            if not allowed or not valid_query or payload is not None:raise ValueError('LIVE_READ_ROUTE_REFUSED')
        else:
            permit=self.write_permit;self.write_permit=None  # consume before I/O
            if (not self.writes_enabled or permit!=(method,path,canonical(payload)) or parts.query
                or not ((method=='POST' and route=='/v2/orders') or (method in {'PATCH','DELETE'} and order))):
                raise ValueError('LIVE_EXACT_WRITE_PERMIT_REQUIRED')
            if method=='POST':
                if self.order_contract=='ALPACA_BASELINE_MONTHLY_DAILY_V1':
                    self._monthly_payload(payload)
                elif (not isinstance(payload,dict) or payload.get('notional') is not None
                    or (payload.get('side'),payload.get('type')) not in {('buy','limit'),('sell','stop'),('sell','market')}
                    or not str(payload.get('client_order_id','')).startswith(('dyl-','dyf-','dyr-','dyx-'))):
                    raise ValueError('LIVE_QUANTITY_OWNED_ROUTE_REQUIRED')
            if method=='PATCH' and set(payload)!={'stop_price'}:raise ValueError('STOP_PRICE_ONLY_REPLACEMENT')
        return self._http(LIVE+path,method,payload)

    @staticmethod
    def _monthly_payload(payload):
        """Same restricted transport, separate exact frozen Monthly wire shape."""
        if not isinstance(payload,dict):raise ValueError('MONTHLY_WIRE_PAYLOAD_REQUIRED')
        shared={'symbol','side','type','time_in_force','client_order_id'}
        kind=(payload.get('side'),payload.get('type'))
        cid=str(payload.get('client_order_id',''))
        if not re.fullmatch('[A-Z0-9.]{1,16}',str(payload.get('symbol',''))):
            raise ValueError('MONTHLY_WIRE_SYMBOL')
        if kind==('buy','market'):
            if (set(payload)!=shared|{'notional'} or payload['time_in_force']!='day'
                or not re.fullmatch(r'abm-[0-9a-f]{32}',cid)
                or not re.fullmatch(r'[0-9]+\.[0-9]{9}',str(payload['notional']))):
                raise ValueError('MONTHLY_NOTIONAL_MARKET_WIRE_REQUIRED')
            positive(payload['notional'])
        elif kind in {('sell','stop'),('sell','market')}:
            extra={'qty','stop_price'} if kind[1]=='stop' else {'qty'}
            prefixes='(?:abf|dyr)' if kind[1]=='stop' else '(?:abr|dyx)'
            if (set(payload)!=shared|extra or not re.fullmatch(prefixes+r'-[0-9a-f]{32}',cid)
                or payload['time_in_force'] not in ({'day','gtc'} if kind[1]=='stop' else {'day'})):
                raise ValueError('MONTHLY_OWNED_EXIT_WIRE_REQUIRED')
            positive(payload['qty'])
            if kind[1]=='stop':positive(payload['stop_price'])
        else:raise ValueError('MONTHLY_ORDER_TYPE_REFUSED')

    def _http(self,url,method,payload=None):
        body=canonical(payload) if payload is not None else None
        req=request.Request(url,data=body,headers=self._headers(),method=method)
        try:
            with self.opener.open(req,timeout=10) as response:raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('LIVE_RESPONSE_TOO_LARGE')
            return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            raise native.AlpacaAPIError(exc.code,'ALPACA_HTTP_'+str(exc.code)) from exc

    def get_asset(self,symbol):
        return self._request('GET','/v2/assets/'+symbol)

    def latest_quote(self,symbol):
        if not re.fullmatch('[A-Z0-9.]{1,16}',symbol):raise ValueError('QUOTE_SYMBOL_INVALID')
        # IEX source is explicit and not called NBBO.
        raw=self._http('https://data.alpaca.markets/v2/stocks/'+symbol+'/quotes/latest?feed=iex','GET')
        return raw['quote']


def permit_write(client,method,path,payload=None):
    if hasattr(client,'permit_write'):client.permit_write(method,path,payload)


def result(status, **fields):
    return dict(status=status, ready_for_live_go=False, **fields)


def safe_path(value, *, exists=False):
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('PATH_IDENTITY')
    if path.exists():
        s=path.stat()
        if not path.is_file() or s.st_nlink!=1 or s.st_uid!=os.getuid():
            raise ValueError('FILE_CUSTODY')
    elif exists:
        raise ValueError('SOURCE_MISSING')
    return path


def read_json(path):
    p=safe_path(path,exists=True)
    def pairs(rows):
        if len(dict(rows))!=len(rows): raise ValueError('DUPLICATE_JSON_KEY')
        return dict(rows)
    return json.loads(p.read_text(),object_pairs_hook=pairs)


def custody(binding,intake,policy):
    """Verify physical source files, not merely boolean compiler declarations."""
    if (binding['schema']!=SCHEMA or binding['endpoint']!=LIVE
        or binding['account_id']!=policy['account_id']
        or binding['policy_sha256']!=digest(policy)
        or binding['intake_sha256']!=intake['intake_sha256']
        or intake['intake_sha256']!=digest({k:v for k,v in intake.items() if k!='intake_sha256'})
        or intake['endpoint']!=LIVE or intake['account_id']!=policy['account_id']):
        raise ValueError('LIVE_BINDING_CONFLICT')
    from research_lab.alpaca_dynamic_paper import _plan_check
    _plan_check(intake['plan'],policy)
    expected=compile_intake(intake['plan'],policy,intake['scope'],intake['prepared_ms'])
    if (expected['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF'
        or intake['status']!=expected['status'] or intake['orders_allowed'] is not False
        or intake['money_authority'] is not False or intake['compatibility']!=expected['compatibility']
        or intake['entry_payload']!=expected['entry_payload']
        or intake['stop_client_order_id']!=expected['stop_client_order_id']):
        raise ValueError('DERIVED_LIVE_PAYLOAD_CONFLICT')
    sources={}
    for name,row in binding['sources'].items():
        p=safe_path(row['path'],exists=True)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('SOURCE_HASH_CONFLICT:'+name)
        sources[name]=read_json(p)
    for name,key in [('authority','original_shared_lock_sha256'),('paper','paper_lifecycle_sha256'),
                     ('old_terminal','old_terminal_sha256'),('cost','cost_source_sha256')]:
        if binding['sources'][name]['sha256']!=intake['scope'][key]:
            raise ValueError('INTAKE_SOURCE_PIN_CONFLICT:'+name)
    cost=sources['cost']
    if (cost['account_id']!=policy['account_id'] or cost['endpoint']!=LIVE
        or cost['source_status']!='SOURCE_BOUND'
        or dec(cost['commission_rate'])!=dec(intake['plan']['fee_rate'])
        or min(dec(cost['buy_regulatory_reserve_usd']),dec(cost['unresolved_liability_usd']))<0
        or dec(intake['scope']['liability_reserve_usd'])<dec(cost['buy_regulatory_reserve_usd'])+dec(cost['unresolved_liability_usd'])):
        raise ValueError('COST_RESERVE_SOURCE_CONFLICT')
    if (hashlib.sha256(Path(ratchet.__file__).read_bytes()).hexdigest()!=intake['scope']['native_manager_source_sha256']
        or hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()!=binding['native_bridge_sha256']):
        raise ValueError('NATIVE_MANAGER_SOURCE_CONFLICT')
    authority=sources['authority'];old=sources['old_terminal']
    if (authority['account_id']!=policy['account_id'] or authority['endpoint']!=LIVE
        or any(authority[k] is not True for k in ('single_entry_owner_verified','single_manager_verified','old_monthly_entries_off'))
        or sources['paper']['status']!='PAPER_EXECUTION_PASS'
        or sources['paper']['live_orders_allowed'] is not False
        or old['status']!='TERMINAL_FINAL' or old['evidence_kind']!='BROKER_LIVE'
        or old['account_id']!=policy['account_id']
        or old['entry_order_id']!=intake['scope']['old_terminal_entry_order_id']
        or positive(old['qty'])!=positive(intake['scope']['old_terminal_qty'])):
        raise ValueError('AUTHORITY_OR_TERMINAL_SOURCE_CONFLICT')
    root=Path(binding['broker_root']);runtime=Path(binding['runtime'])
    if not root.is_absolute() or '..' in root.parts or any(p.is_symlink() for p in [root,*root.parents]):
        raise ValueError('BROKER_ROOT_CONFLICT')
    for field in ('lock_path','ledger_path','halt_path'):
        p=safe_path(binding[field])
        if not p.is_relative_to(root/'runtime'): raise ValueError('ORIGINAL_RUNTIME_SCOPE_REQUIRED')
    if (str(runtime)!=str(Path(binding['ledger_path']).parent)
        or not runtime.is_relative_to(root/'runtime')
        or authority['lock_path']!=binding['lock_path'] or authority['ledger_path']!=binding['ledger_path']):
        raise ValueError('ORIGINAL_LOCK_OR_LEDGER_MAPPING_CONFLICT')
    book=safe_path(binding['source_book'],exists=True)
    if book.is_relative_to(runtime): raise ValueError('SOURCE_AND_DISPATCH_BOOK_MUST_BE_SEPARATE')
    with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as db:
        meta=dict(db.execute('SELECT key,value FROM meta'))
        if meta.get('policy')!=digest(policy) or meta.get('runtime_kind')!='LIVE_DYNAMIC_SEPARATE':
            raise ValueError('LIVE_SOURCE_BOOK_IDENTITY')
        matches=[p for p in DynamicBook.active_from_db(db) if p['receipt_id']==intake['plan']['receipt_id']]
        if matches!=[intake['plan']]: raise ValueError('EXACT_ACTIVE_SOURCE_PLAN_REQUIRED')
    return runtime


def owner_permit(path,binding,intake,*,first_intent_path=None,policy=None):
    go=read_json(path)
    if first_intent_path is not None:
        from research_lab.alpaca_dynamic_first_intent_v1 import intent_permit
        return intent_permit(go,read_json(str(first_intent_path)),binding,intake,policy)
    expected=dict(schema='ALPACA_DYNAMIC_EXACT_OWNER_GO_V1',account_id=intake['account_id'],endpoint=LIVE,
        intake_sha256=intake['intake_sha256'],binding_sha256=digest(binding),
        owner_go_text='GO ALPACA_DYNAMIC_V1 '+intake['intake_sha256'],session=intake['plan']['session'])
    if go!=expected: raise ValueError('EXACT_SEPARATE_OWNER_GO_REQUIRED')
    return digest(go)


@contextmanager
def account_lock(binding):
    p=safe_path(binding['lock_path']);p.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(p,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if not native._acquire_account_writer_lock(fd,0): raise BlockingIOError('ACCOUNT_WRITER_BUSY')
        yield
    finally: os.close(fd)


@contextmanager
def store(path):
    path.mkdir(parents=True,exist_ok=True)
    target=safe_path(str(path/'live.sqlite'))
    if (path/'paper.sqlite').exists(): raise ValueError('PAPER_RUNTIME_REFUSED')
    db=sqlite3.connect(target)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS intents(id TEXT PRIMARY KEY,slot TEXT UNIQUE,session TEXT UNIQUE,payload TEXT)')
        db.commit();target.chmod(0o600)
        yield db
    finally: db.close()


def save(db,item):
    db.execute('INSERT INTO intents VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
        (item['id'],item['intake']['plan']['slot_entry_order_id'],item['intake']['plan']['session'],canonical(item).decode()))
    db.commit()


def halt(binding,reason):
    p=safe_path(binding['halt_path'])
    # Never clear an existing HALT or overwrite its provenance.
    if not p.exists(): native._atomic_write_json(p,dict(halted=True,reason=reason,account_id=binding['account_id']))


def order_contract(row,payload):
    if not row or not row.get('id'): raise ValueError('ORDER_READBACK_MISSING')
    for k,v in payload.items():
        if k in {'qty','limit_price','stop_price'}:
            if positive(row[k])!=positive(v): raise ValueError('ORDER_READBACK_CONFLICT:'+k)
        elif row.get(k)!=v: raise ValueError('ORDER_READBACK_CONFLICT:'+k)
    return row


def dispatch(db,item,client,payload,key):
    """Lookup before dispatch; persisted pending never resends even after timeout."""
    found=client.get_order_by_client_id(payload['client_order_id'])
    attempt=item.setdefault('dispatches',{}).get(key)
    if found:
        if attempt is None: raise ValueError('UNOWNED_BROKER_CLIENT_ID')
        checked=order_contract(client.get_order(found['id']),payload)
        if attempt['payload']!=payload:raise ValueError('PERSISTED_DISPATCH_PAYLOAD_CONFLICT')
        attempt.update(state='CONFIRMED',order_id=checked['id']);save(db,item)
        return checked
    if attempt is not None: raise ValueError('UNCERTAIN_'+key.upper()+'_NO_RESEND')
    item['dispatches'][key]=dict(payload=payload,state='DISPATCHED')
    save(db,item)
    try:
        permit_write(client,'POST','/v2/orders',payload)
        posted=client._request('POST','/v2/orders',payload)
        checked=order_contract(client.get_order(posted['id']),payload)
        item['dispatches'][key].update(state='CONFIRMED',order_id=checked['id']);save(db,item)
        return checked
    except native.AlpacaAPIError as e:
        if e.status_code==422:
            item['dispatches'][key]['state']='REJECTED_422';save(db,item)
        raise


def owned_snapshot(client,item,record,*,observation_ms=None):
    """Bounded exhaustive symbol history + exact original entry and exit lineage."""
    symbol=item['intake']['plan']['symbol'];entry=item['entry']
    current=client.get_order(entry['id'])
    order_contract(current,item['intake']['entry_payload'])
    # REST may round the original nanosecond event timestamp and add the
    # documented access-key source. Keep both raw orders intact; use the same
    # strict identity proof as PAPER finality rather than blocking DAY re-arm
    # on a representation change. Material execution/ownership drift rejects.
    from research_lab.alpaca_live_readiness_v1 import execution_identity_v1
    try:
        item['entry_identity_v1']=execution_identity_v1(entry,current)
    except ValueError as exc:
        raise ValueError('ENTRY_FILL_SOURCE_CHANGED:'+str(exc)) from exc
    history=client.list_orders(status='all',limit=500,symbols=[symbol])
    orders=client.list_orders(status='open',limit=100,symbols=[symbol])
    if observation_ms is not None:item['observed_ms']=observation_ms()
    if len(history)>=500 or len(orders)>=100: raise ValueError('ORDER_HISTORY_INCOMPLETE')
    buys=[o for o in history if o['side']=='buy' and dec(o.get('filled_qty','0'))>0]
    if not buys or max(buys,key=lambda o:o.get('filled_at',''))['id']!=entry['id']:
        raise ValueError('LATEST_OWNED_BUY_CONFLICT')
    known={a['payload']['client_order_id'] for a in item.get('dispatches',{}).values()}
    known_ids={entry['id']}|{o['id'] for o in item.get('exit_sources',[])}
    if record.get('accepted_order_id'):known_ids.add(record['accepted_order_id'])
    known_ids.update(a.get('accepted_id','') for a in item.get('replacements',{}).values())
    replacement_sources={a['old_id'] for a in item.get('replacements',{}).values()}
    owned=[]
    for order in history:
        if order.get('side')!='sell': continue
        # Replacement responses are recovered by their explicit replaces chain.
        if (order.get('client_order_id') in known or order['id'] in known_ids
            or order.get('replaces') in replacement_sources):
            if order['type'] not in {'stop','market'}:raise ValueError('EXIT_TYPE_CONFLICT')
            owned.append(order)
    owned_ids={o['id'] for o in owned}
    if any(o['id'] not in owned_ids for o in orders): raise ValueError('FOREIGN_ACTIVE_ORDER')
    qty=positive(entry['filled_qty']);filled=dec(0);gross=dec(0)
    for o in owned:
        q=dec(o.get('filled_qty','0'))
        if not 0<=q<=positive(o['qty']):raise ValueError('EXIT_FILL_CONFLICT')
        if q:
            stamp=native._parse_iso_utc(o.get('filled_at',''))
            start=native._parse_iso_utc(entry['filled_at'])
            if (stamp is None or start is None or stamp<start
                or int(stamp.timestamp()*1000)>item['observed_ms']):raise ValueError('EXIT_FILL_TIME_CONFLICT')
            filled+=q;gross+=q*(positive(o['filled_avg_price'])-positive(entry['filled_avg_price']))
    remaining=qty-filled
    if remaining<0:raise ValueError('EXIT_OVERFILL')
    positions=[p for p in client.list_positions() if p['symbol']==symbol]
    if remaining:
        if (len(positions)!=1 or positive(positions[0]['qty'])!=remaining
            or positive(positions[0]['avg_entry_price'])!=positive(entry['filled_avg_price'])
            or positions[0].get('side','long')!='long'):raise ValueError('OWNED_REMAINING_POSITION_CONFLICT')
    elif positions or orders:raise ValueError('FLAT_NOT_TERMINAL')
    return positions,orders,owned,remaining,gross


def finish_exit(db,item,client,record,binding,*,observation_ms=None):
    positions,orders,owned,remaining,gross=owned_snapshot(client,item,record,observation_ms=observation_ms)
    if remaining:return result('BLOCKED_EXECUTION',reason='PARTIAL_OR_UNCERTAIN_EXIT_NO_RESEND',remaining_qty=str(remaining))
    actual=[o for o in owned if dec(o.get('filled_qty','0'))>0]
    if not actual:raise ValueError('NO_ACTUAL_EXIT_FILL')
    kinds={o['type'] for o in actual}
    kind='NATIVE_STOP' if kinds=={'stop'} else 'EMERGENCY_MARKET' if kinds=={'market'} else 'MIXED_NATIVE_STOP_EMERGENCY'
    item['exit_sources']=actual;item['phase']='EXIT_PENDING_FINALITY';save(db,item)
    # Keep provenance in the dispatch journal before removing the managed record.
    ledger=safe_path(binding['ledger_path'],exists=True);state=read_json(ledger)
    if item['intake']['plan']['symbol'] in state:
        item['retired_record']=record;save(db,item)
        native._atomic_write_json(ledger,{k:v for k,v in state.items() if k!=item['intake']['plan']['symbol']})
    return result('LIVE_EXIT_PENDING_FINALITY',exit_kind=kind,gross_before_fees=str(gross),
                  net_pnl_status='NOT_PROVEN',exit_orders=actual,slot_released=False,
                  initial_full_protection_proven=item.get('initial_full_protection_proven',False))


def finalize_costs(db,item,client,terminal,path):
    """Consume a source-pinned external account/day reconciliation, never guess it.

    Native order fills and fresh account cash are independently read back here.
    Fee publication/allocation closure is supplied by the explicit source report;
    flatness, missing fee events and pending=0 alone do not produce such a report.
    This is accounting integration, never a research/money promotion verdict.
    """
    source=read_json(path);source_hash=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if item.get('cost_finality_sha256') and item['cost_finality_sha256']!=source_hash:
        raise ValueError('FINAL_COST_SOURCE_CHANGED')
    if (source['schema']!='ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1'
        or source['account_id']!=item['account'] or source['intake_sha256']!=item['id']
        or source['closure_status']!='ACCOUNT_DAY_FEES_RECONCILED'
        or source['exit_orders_sha256']!=digest(terminal['exit_orders'])
        or dec(source['gross_before_fees'])!=dec(terminal['gross_before_fees'])
        or not 0<=instant(source['observed_ms'])<=item['observed_ms']
        or not source['source_files'] or source['source_manifest_sha256']!=digest(source['source_files'])):
        raise ValueError('EXACT_BROKER_COST_FINALITY_REQUIRED')
    for row in source['source_files']:
        raw=safe_path(row['path'],exists=True)
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('FINALITY_SOURCE_PIN_CONFLICT')
    last=max(int(native._parse_iso_utc(o['filled_at']).timestamp()*1000) for o in terminal['exit_orders'])
    if not last<=instant(source['coverage_end_ms'])<=source['observed_ms']:
        raise ValueError('FINALITY_COVERAGE_UNKNOWN')
    commission,regulatory,unresolved=(dec(source[k]) for k in ('commission_usd','regulatory_fees_usd','unresolved_liability_usd'))
    if min(commission,regulatory,unresolved)<0 or unresolved!=0:raise ValueError('COST_LIABILITY_PENDING')
    net=dec(terminal['gross_before_fees'])-commission-regulatory
    cash=(dec(source['cash_before_entry'])+net+dec(source['other_cash_net_usd'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    account=client.get_account()
    if (account['id']!=item['account'] or cash!=dec(source['cash_after_exit'])
        or dec(account['cash'])!=cash):raise ValueError('TERMINAL_CASH_RECONCILIATION_CONFLICT')
    out=result('LIVE_TERMINAL_COST_FINALITY',net_usd_exact=str(net),broker_cash_after=str(cash),
        exit_kind=terminal['exit_kind'],cost_source_sha256=source_hash,
        source_manifest_sha256=source['source_manifest_sha256'],
        evidence_kind='SOURCE_BOUND_EXTERNAL_FEES_WITH_BROKER_ORDER_CASH_READBACK',
        initial_full_protection_proven=item.get('initial_full_protection_proven',False),
        source_observed_ms=source['observed_ms'],new_entry_authority=False)
    item['cost_finality_sha256']=source_hash;item['cost_finality']=out;save(db,item)
    return out


def unwind(db,item,client,record,binding,*,observation_ms=None):
    halt(binding,'OWNED_EXIT_IN_PROGRESS')  # blocks entries, never stops maintenance
    for key,attempt in item.get('replacements',{}).items():
        if not attempt.get('accepted_id'):
            history=client.list_orders(status='all',limit=500,symbols=[item['intake']['plan']['symbol']])
            if len(history)>=500:raise ValueError('ORDER_HISTORY_INCOMPLETE')
            matches=[o for o in history if o.get('replaces')==key]
            if (len(matches)!=1 or matches[0]['type']!='stop' or matches[0]['side']!='sell'
                or matches[0]['symbol']!=item['intake']['plan']['symbol']
                or positive(matches[0]['stop_price'])<positive(attempt['payload']['stop_price'])):
                raise ValueError('UNKNOWN_REPLACEMENT_OWNER_ACTION_REQUIRED')
            attempt['accepted_id']=matches[0]['id'];save(db,item)
    for key,attempt in item.get('dispatches',{}).items():
        if attempt['payload']['type']=='stop' and attempt['state']=='DISPATCHED':
            row=client.get_order_by_client_id(attempt['payload']['client_order_id'])
            if not row:raise ValueError('UNKNOWN_STOP_DISPATCH_OWNER_ACTION_REQUIRED')
            order_contract(row,attempt['payload'])
    positions,orders,owned,remaining,gross=owned_snapshot(client,item,record,observation_ms=observation_ms)
    if not remaining:return finish_exit(db,item,client,record,binding,observation_ms=observation_ms)
    for o in orders:
        if o['side']!='sell' or o['type']!='stop': raise ValueError('UNWIND_ACTIVE_CONFLICT')
        if o['id'] not in item.setdefault('cancel_dispatches',[]):
            item['cancel_dispatches'].append(o['id']);save(db,item)
            permit_write(client,'DELETE','/v2/orders/'+o['id'])
            client.cancel_order(o['id'])
        if client.get_order(o['id'])['status'] not in native._TERMINAL_ORDER_STATUSES:
            return result('BLOCKED_EXECUTION',reason='UNCERTAIN_CANCEL_NO_RESEND')
    positions,orders,owned,remaining,gross=owned_snapshot(client,item,record,observation_ms=observation_ms)
    if not remaining:return finish_exit(db,item,client,record,binding,observation_ms=observation_ms)
    if orders:raise ValueError('UNWIND_REQUIRES_TERMINAL_STOP_CANCELLATION')
    payload=dict(symbol=item['intake']['plan']['symbol'],side='sell',type='market',
                 qty=str(remaining),time_in_force='day',client_order_id='dyx-'+item['id'][:32])
    # Freeze remaining quantity once: changing it later cannot create a new order.
    prior=item.get('dispatches',{}).get('exit')
    if prior:payload=prior['payload']
    dispatch(db,item,client,payload,'exit')
    return finish_exit(db,item,client,record,binding,observation_ms=observation_ms)


def initial(db,item,client,binding,now_ms,*,allow_new_entry=False):
    started=time.monotonic()
    observed=lambda:now_ms+int((time.monotonic()-started)*1000)
    intake=item['intake'];plan=intake['plan'];symbol=plan['symbol']
    if not allow_new_entry and 'entry' not in item.get('dispatches',{}):
        raise ValueError('RESERVATION_WITHOUT_DISPATCH_NO_LATE_BUY')
    entry=dispatch(db,item,client,intake['entry_payload'],'entry')
    if entry['status'] in {'canceled','expired','rejected'} and dec(entry.get('filled_qty','0'))==0:
        item['phase']='NO_FILL_TERMINAL';save(db,item)
        return result('LIVE_NO_FILL_TERMINAL',no_resend=True,slot_released=False)
    if entry['status'] in native._ACTIVE_ORDER_STATUSES:
        # Native terminal helper may cancel; journal that cancellation first and
        # never repeat it when the result is ambiguous.
        if entry['id'] not in item.setdefault('cancel_dispatches',[]):
            item['cancel_dispatches'].append(entry['id']);save(db,item)
            permit_write(client,'DELETE','/v2/orders/'+entry['id'])
            client.cancel_order(entry['id'])
        entry=order_contract(client.get_order(entry['id']),intake['entry_payload'])
        if entry['status'] in native._ACTIVE_ORDER_STATUSES:raise ValueError('UNCERTAIN_ENTRY_CANCEL_NO_RESEND')
        if entry['status'] in {'canceled','expired','rejected'} and dec(entry.get('filled_qty','0'))==0:
            item['phase']='NO_FILL_TERMINAL';save(db,item)
            return result('LIVE_NO_FILL_TERMINAL',no_resend=True,slot_released=False)
    entry=native._terminal_intended_entry(client,entry,expected_symbol=symbol,timeout_sec=0)
    order_contract(entry,intake['entry_payload'])
    qty=positive(entry['filled_qty']);price=positive(entry['filled_avg_price'])
    if qty>positive(plan['qty']) or price>positive(intake['entry_payload']['limit_price']):
        raise ValueError('FILL_EXCEEDS_RESERVED_PLAN')
    positions=[p for p in client.list_positions() if p['symbol']==symbol]
    if len(positions)!=1 or positive(positions[0]['qty'])!=qty or positive(positions[0]['avg_entry_price'])!=price:
        raise ValueError('ENTRY_POSITION_CONFLICT')
    item['entry']=entry;save(db,item)
    ledger=safe_path(binding['ledger_path'])
    state=read_json(ledger) if ledger.exists() else {}
    if symbol not in state:
        native._persist_intended_pending_fill(ledger,account_id=item['account'],symbol=symbol,entry=entry)
        state=read_json(ledger)
        state[symbol].update(entry_selection_policy='ALPACA_DYNAMIC_V1',dynamic_intake_sha256=intake['intake_sha256'])
        native._atomic_write_json(ledger,state)
    record=native._validated_existing_intended_lifecycle(state[symbol],item['account'],allow_pending=True)
    if record['entry_order_id']!=entry['id']:raise ValueError('NATIVE_LEDGER_OWNER_CONFLICT')
    floor=(price-positive(plan['risk_distance'])).quantize(Decimal('.01'),rounding=ROUND_CEILING)
    payload=dict(symbol=symbol,side='sell',type='stop',qty=str(qty),stop_price=format(floor,'.2f'),
        time_in_force=native._persistent_exit_tif_for_qty('',float(qty)),client_order_id=intake['stop_client_order_id'])
    if item.get('dispatches',{}).get('stop',{}).get('state')=='REJECTED_422':
        return unwind(db,item,client,record,binding,observation_ms=observed)
    try:stop=dispatch(db,item,client,payload,'stop')
    except native.AlpacaAPIError as e:
        if e.status_code==422:return unwind(db,item,client,record,binding,observation_ms=observed)
        raise
    item['observed_ms']=observed()  # receive/use time, not CLI invocation time
    if dec(stop.get('filled_qty','0'))>0:
        # Broker can execute the stop before our first readback. This is a real
        # STOP exit, never fabricated initial full-protection acceptance.
        item['initial_full_protection_proven']=False
        positions,orders,owned,remaining,gross=owned_snapshot(client,item,record,observation_ms=observed)
        if not remaining:return finish_exit(db,item,client,record,binding,observation_ms=observed)
        if (stop['status']!='partially_filled' or len(orders)!=1 or orders[0]['id']!=stop['id']
            or positive(stop['qty'])-dec(stop['filled_qty'])!=remaining
            or positive(stop['stop_price'])<floor or stop['time_in_force']!=payload['time_in_force']):
            raise ValueError('INITIAL_PARTIAL_STOP_REMAINDER_NOT_PROVEN')
        updated={**record,'qty':float(remaining),'accepted_stop_floor':float(positive(stop['stop_price'])),
            'accepted_order_id':stop['id'],'accepted_order_tif':stop['time_in_force'],
            'protection_pending':False,'initial_full_protection_proven':False}
        native._validated_existing_intended_lifecycle(updated,item['account'])
        native._atomic_write_json(ledger,{**state,symbol:updated})
        item['phase']='PROTECTED';item['native_record']=updated;save(db,item)
        return result('LIVE_PARTIAL_STOP_PROTECTED',remaining_qty=str(remaining),
                      initial_full_protection_proven=False,net_pnl_status='NOT_PROVEN')
    handoff=native_handoff(intake,entry,stop,observed_ms=observed(),
                          existing=record if not record.get('protection_pending') else None)
    if handoff['status']!='NATIVE_HANDOFF_PREPARED_ORDERS_OFF':raise ValueError(handoff['reason'])
    native._atomic_write_json(ledger,{**state,symbol:handoff['native_record']})
    item['phase']='PROTECTED';item['native_record']=handoff['native_record']
    item['initial_full_protection_proven']=True;save(db,item)
    return result('LIVE_PROTECTED',entry_order_id=entry['id'],stop_order_id=stop['id'],filled_qty=str(qty),
                  stop_price=str(floor),net_pnl_status='NOT_PROVEN')


def maintain(db,item,client,binding,now_ms,kill):
    started=time.monotonic()
    observed=lambda:now_ms+int((time.monotonic()-started)*1000)
    symbol=item['intake']['plan']['symbol'];ledger=safe_path(binding['ledger_path'],exists=True)
    state=read_json(ledger);record=state.get(symbol) or item.get('retired_record')
    native._validated_existing_intended_lifecycle(record,item['account'],allow_pending=True)
    if record.get('dynamic_intake_sha256')!=item['intake']['intake_sha256']:raise ValueError('MANAGER_LINEAGE_CONFLICT')
    positions,orders,owned,remaining,gross=owned_snapshot(client,item,record,observation_ms=observed)
    if not remaining:return finish_exit(db,item,client,record,binding,observation_ms=observed)
    if kill or item.get('dispatches',{}).get('exit'):return unwind(db,item,client,record,binding,observation_ms=observed)
    clock=client.get_clock();stamp=native._parse_iso_utc(clock['timestamp'])
    if stamp is None or abs(int(stamp.timestamp()*1000)-observed())>5000:raise ValueError('MANAGER_CLOCK_CONFLICT')
    if not clock['is_open']:return result('LIVE_WAITING_REGULAR_SESSION',protection_present=bool(orders))
    if record.get('protection_pending'):
        rejection=item.get('dispatches',{}).get('stop',{}).get('state')=='REJECTED_422'
        if rejection:return unwind(db,item,client,record,binding,observation_ms=observed)
        raise ValueError('UNKNOWN_INITIAL_PROTECTION_OWNER_ACTION_REQUIRED')
    if dec(record['qty'])!=remaining:
        # Partial stop fills leave only the proven remainder under management.
        record={**record,'qty':float(remaining)};state[symbol]=record
        native._atomic_write_json(ledger,state)
    if orders:
        if len(orders)!=1 or orders[0]['type']!='stop':raise ValueError('ONE_NATIVE_STOP_REQUIRED')
        stop=orders[0]
        if positive(stop['qty'])-dec(stop.get('filled_qty','0'))!=remaining:raise ValueError('EXACT_STOP_COVER_REQUIRED')
        if stop['status']=='partially_filled':
            if positive(stop['stop_price'])<positive(record['accepted_stop_floor']):raise ValueError('PARTIAL_STOP_FLOOR_CONFLICT')
            return result('LIVE_PARTIAL_STOP_PROTECTED',remaining_qty=str(remaining),net_pnl_status='NOT_PROVEN')
        native._confirmed_intended_stop(client,stop,symbol=symbol,qty=float(remaining),requested_stop=float(record['accepted_stop_floor']))
        # Native ratchet strips selection metadata; merge its output into the
        # source-validated existing record instead of losing Dynamic ownership.
        rows,next_state=ratchet.build_ratchet_plan(positions,[stop],{symbol:record},**RATCHET)
        proposed={**record,**next_state[symbol]}
        state[symbol]=proposed;native._atomic_write_json(ledger,state)
        row=rows[0]
        if row['action']=='escalate_below_accepted_floor':return unwind(db,item,client,proposed,binding,observation_ms=observed)
        if row['action']=='blocked':raise ValueError(row['reason'])
        if row['action']=='replace_stop':
            key=stop['id'];attempt=item.setdefault('replacements',{}).get(key)
            target=ratchet.build_stop_replace_payload(row['target_stop'])
            if attempt:
                target=attempt['payload']
                matches=[o for o in owned if o.get('replaces')==key]
                if len(matches)!=1:raise ValueError('UNCERTAIN_REPLACE_NO_RESEND')
                replaced=matches[0]
            else:
                item['replacements'][key]=dict(old_id=key,payload=target);save(db,item)
                permit_write(client,'PATCH','/v2/orders/'+key,target)
                replaced=client.replace_order(key,target)
            confirmed=native._confirmed_intended_stop(client,replaced,symbol=symbol,qty=float(remaining),requested_stop=float(target['stop_price']))
            if (positive(confirmed['qty'])-dec(confirmed.get('filled_qty','0'))!=remaining
                or confirmed.get('replaces')!=key):raise ValueError('REPLACEMENT_SOURCE_CONFLICT')
            item['replacements'][key]['accepted_id']=confirmed['id'];save(db,item)
            state[symbol].update(accepted_stop_floor=max(state[symbol]['accepted_stop_floor'],float(confirmed['stop_price'])),
                accepted_order_id=confirmed['id'],accepted_order_tif=confirmed['time_in_force'])
            native._atomic_write_json(ledger,state);stop=confirmed
        else:
            state[symbol].update(accepted_order_id=stop['id'],accepted_order_tif=stop['time_in_force'])
            native._atomic_write_json(ledger,state)
        return result('LIVE_PROTECTED',stop_order_id=stop['id'],net_pnl_status='NOT_PROVEN')
    previous=client.get_order(record['accepted_order_id'])
    if previous['status'] not in {'expired','canceled','rejected'} or dec(previous.get('filled_qty','0'))!=0:
        raise ValueError('UNFILLED_TERMINAL_STOP_REQUIRED_FOR_REARM')
    session=stamp.date().isoformat();cid='dyr-'+digest(dict(parent=item['id'],session=session))[:32]
    payload=dict(symbol=symbol,side='sell',type='stop',qty=str(remaining),
        stop_price=format(positive(record['accepted_stop_floor']),'.2f'),
        time_in_force=native._persistent_exit_tif_for_qty('',float(remaining)),client_order_id=cid)
    if positive(positions[0]['current_price'])<=positive(record['accepted_stop_floor']):
        return unwind(db,item,client,record,binding,observation_ms=observed)
    try:stop=dispatch(db,item,client,payload,'rearm:'+session)
    except native.AlpacaAPIError as e:
        if e.status_code==422:return unwind(db,item,client,record,binding,observation_ms=observed)
        raise
    native._rearm_intended_position(client=client,symbol=symbol,position=positions[0],existing_stops=[stop],
        state=state,state_path=ledger,account_id=item['account'])
    return result('LIVE_PROTECTED',stop_order_id=stop['id'],net_pnl_status='NOT_PROVEN')


def run_once(*,intake,policy,binding,client,now_ms,apply=False,owner_go_path=None,maintenance=False,kill=False,
             cost_finality_path=None,first_intent_path=None):
    """Entry default OFF; separate exact GO + nonhalted entry + original lock.

    HALT never inhibits management of this runtime's already-owned fill. No code
    removes HALT. Read-only calls do not create a runtime or reserve a lifecycle.
    Caller credentials are explicit; no global env, PAPER fallback or role hack.
    """
    dispatched=False;started=time.monotonic();allow_new_entry=False
    try:
        if any(type(flag) is not bool for flag in (apply,maintenance,kill)):
            raise ValueError('EXPLICIT_BOOLEAN_OPERATION_REQUIRED')
        now_ms=instant(now_ms);runtime=custody(binding,intake,policy)
        if client.base_url!=LIVE or client.get_account()['id']!=binding['account_id']:
            raise ValueError('EXACT_LIVE_ACCOUNT_REQUIRED')
        if not apply:
            if first_intent_path is not None:
                from research_lab.alpaca_dynamic_first_intent_v1 import check_first_intent
                check_first_intent(read_json(str(first_intent_path)),binding,intake,policy)
            source=safe_path(str(runtime/'live.sqlite'))
            if source.exists():
                with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
                    if db.execute('SELECT 1 FROM intents').fetchone():
                        return result('LIVE_READ_ONLY_RECOVERY_REQUIRED',orders_allowed=False)
            if maintenance or kill:return result('LIVE_READ_ONLY_MAINTENANCE_REQUIRED',orders_allowed=False)
            check=compile_intake(intake['plan'],policy,intake['scope'],now_ms)
            if check['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF':return check
            return result('LIVE_READ_ONLY_READY',orders_allowed=False,money_authority=False)
        go_hash=owner_permit(owner_go_path,binding,intake,first_intent_path=first_intent_path,policy=policy)
        with account_lock(binding):
            with store(runtime) as db:
                row=db.execute('SELECT payload FROM intents WHERE id=?',(intake['intake_sha256'],)).fetchone()
                item=json.loads(row[0]) if row else None
                dispatched=item is not None
                if item and (item['intake']!=intake or item['binding_sha256']!=digest(binding) or item['owner_go_sha256']!=go_hash):
                    raise ValueError('PERSISTED_RUNTIME_SCOPE_CONFLICT')
                if not item:
                    if first_intent_path is not None and db.execute('SELECT 1 FROM intents').fetchone():
                        raise ValueError('FIRST_DYNAMIC_ENTRY_ALREADY_CONSUMED')
                    if maintenance or kill:raise ValueError('NO_OWNED_LIVE_INTENT')
                    if safe_path(binding['halt_path']).exists():raise ValueError('ENTRY_HALTED')
                    ledger=safe_path(binding['ledger_path'])
                    if ledger.exists():
                        existing=read_json(ledger)
                        if not isinstance(existing,dict) or intake['plan']['symbol'] in existing:
                            raise ValueError('PRE_ENTRY_NATIVE_OWNER_CONFLICT')
                    check=compile_intake(intake['plan'],policy,intake['scope'],now_ms)
                    if check['status']!='LIVE_INTAKE_PREPARED_ORDERS_OFF':raise ValueError(check['reason'])
                    account=client.get_account();clock=client.get_clock();stamp=native._parse_iso_utc(clock['timestamp'])
                    if (account['id']!=binding['account_id'] or account.get('trading_blocked') is not False
                        or account.get('account_blocked') is not False or not clock['is_open'] or stamp is None
                        or abs(int(stamp.timestamp()*1000)-(now_ms+int((time.monotonic()-started)*1000)))>5000):raise ValueError('FRESH_ACCOUNT_CLOCK_REQUIRED')
                    cash=min(dec(account['cash']),dec(account['non_marginable_buying_power']))
                    if cash-dec(intake['scope']['liability_reserve_usd'])<positive(intake['plan']['funding_limit_usd']):
                        raise ValueError('FRESH_LIABILITY_CASH_REJECT')
                    positions=client.list_positions();orders=client.list_orders(status='open',limit=500)
                    if 'portfolio_bindings' in binding:
                        from research_lab.alpaca_dynamic_portfolio_admission_v1 import check_owned_portfolio
                        check_owned_portfolio(db,binding,policy,client,positions=positions,orders=orders,
                            target_symbol=intake['plan']['symbol'],observed_ms=now_ms+int((time.monotonic()-started)*1000))
                    elif len(orders)>=500 or any(p['symbol']==intake['plan']['symbol'] for p in positions) or orders:
                        raise ValueError('FOREIGN_POSITION_OR_ORDER')
                    if (len(positions)!=intake['scope']['positions_before']
                        or len(positions)>=policy['max_positions']):raise ValueError('FRESH_POSITION_CAP_CONFLICT')
                    gross=sum((abs(dec(p['market_value'])) for p in positions),dec(0))
                    if gross+positive(intake['plan']['notional_usd'])>dec(policy['capital_usd'])*dec(policy['gross']):
                        raise ValueError('FRESH_GROSS_CAP_REJECT')
                    if db.execute('SELECT 1 FROM intents WHERE session=? OR slot=?',
                        (intake['plan']['session'],intake['plan']['slot_entry_order_id'])).fetchone():
                        raise ValueError('SESSION_OR_SLOT_ALREADY_CONSUMED')
                    for cid in (intake['entry_payload']['client_order_id'],intake['stop_client_order_id']):
                        if client.get_order_by_client_id(cid) is not None:raise ValueError('UNOWNED_CLIENT_ID')
                    asset=client.get_asset(intake['plan']['symbol'])
                    if (asset['symbol']!=intake['plan']['symbol'] or asset.get('status')!='active'
                        or asset.get('tradable') is not True
                        or (positive(intake['plan']['qty'])!=positive(intake['plan']['qty']).to_integral_value()
                            and asset.get('fractionable') is not True)):
                        raise ValueError('FRESH_ASSET_INELIGIBLE')
                    quote=client.latest_quote(intake['plan']['symbol'])
                    qts=native._parse_iso_utc(quote.get('t',''))
                    effective_ms=now_ms+int((time.monotonic()-started)*1000)
                    if qts is None or not 0<=effective_ms-int(qts.timestamp()*1000)<=policy['max_snapshot_age_ms']:
                        raise ValueError('RAW_QUOTE_CTS_REQUIRED')
                    positive(quote['ap'])
                    final_clock=client.get_clock();cts=native._parse_iso_utc(final_clock['timestamp'])
                    effective_ms=now_ms+int((time.monotonic()-started)*1000)
                    if (not session_at(policy['calendar_sessions'],effective_ms) or not final_clock['is_open']
                        or cts is None or abs(effective_ms-int(cts.timestamp()*1000))>5000):
                        raise ValueError('FINAL_DISPATCH_WINDOW_OR_CLOCK')
                    item=dict(id=intake['intake_sha256'],account=binding['account_id'],intake=intake,
                        binding_sha256=digest(binding),owner_go_sha256=go_hash,phase='RESERVED')
                    save(db,item);dispatched=True;allow_new_entry=True
                    if not session_at(policy['calendar_sessions'],now_ms+int((time.monotonic()-started)*1000)):
                        raise ValueError('PERSISTED_DISPATCH_EXPIRED_NO_RESEND')
                if item['phase']=='NO_FILL_TERMINAL':return result('LIVE_NO_FILL_TERMINAL',no_resend=True)
                item['observed_ms']=now_ms+int((time.monotonic()-started)*1000)
                if item.get('entry') and item['phase'] in {'PROTECTED','EXIT_PENDING_FINALITY'}:
                    out=maintain(db,item,client,binding,item['observed_ms'],kill)
                    if cost_finality_path:
                        if out['status']!='LIVE_EXIT_PENDING_FINALITY':raise ValueError('OWNED_EXIT_NOT_TERMINAL')
                        return finalize_costs(db,item,client,out,cost_finality_path)
                    if item.get('cost_finality') and out['status']=='LIVE_EXIT_PENDING_FINALITY':
                        return {**item['cost_finality'],'restored_dated_finality':True}
                    return out
                if kill and item.get('entry'):
                    state=read_json(binding['ledger_path'])
                    return unwind(db,item,client,state[intake['plan']['symbol']],binding,
                        observation_ms=lambda:now_ms+int((time.monotonic()-started)*1000))
                return initial(db,item,client,binding,item['observed_ms'],allow_new_entry=allow_new_entry)
    except Exception as error:
        if apply and dispatched:
            try:halt(binding,'DYNAMIC_RUNTIME_'+type(error).__name__)
            except Exception:pass
        return result('BLOCKED_EXECUTION' if dispatched or isinstance(error,BlockingIOError) else 'BLOCKED_DATA',
                      reason=str(error) or type(error).__name__,orders_allowed=False,no_blind_retry=True)
