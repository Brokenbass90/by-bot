"""Preloaded, one-attempt opening controller; engineering evidence, no LIVE path.

The caller supplies a reviewed source publisher and owns the existing shared
broker account lock throughout fresh→reservation→PAPER adapter. Declarations
and fixture timing do not authenticate a broker or authorize an actual attempt.
"""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time

from research_lab.alpaca_dynamic_v1 import canonical, dec, digest, instant, pin, policy_check, positive, session_at
from research_lab.alpaca_dynamic_paper import PAPER, execute_paper

STATIC_CHECKS = ('source_config', 'ownership', 'protection_eligibility', 'earnings',
                 'concentration', 'cost_protocol', 'reservation_handoff')
FRESH_BUDGET_MS = 30_000
RESERVE_BUDGET_MS = 5_000
ENTRY_PREFLIGHT_ALLOWANCE_MS = 120_000
START_BUDGET_MS = FRESH_BUDGET_MS + RESERVE_BUDGET_MS + ENTRY_PREFLIGHT_ALLOWANCE_MS
PROTECTION_DOCUMENT_SHA256 = 'b955a1ef86c0692ea62160f792e422c2f3198b6310e3867e1bb8482f16e0eef0'
PROTECTION_MAPPING = 'DAY fractional LIMIT buy / DAY STOP sell per official Trading API docs; actual acceptance still requires broker PAPER'

class WallClock:
    def wall_ms(self): return time.time_ns()//1_000_000
    def monotonic_ms(self): return time.monotonic_ns()//1_000_000


@contextmanager
def hard_budget(milliseconds):
    """Interrupt only pre-dispatch work; never an accepted entry's protection."""
    if (threading.current_thread() is not threading.main_thread()
        or signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0)):
        raise ValueError('EXCLUSIVE_MAIN_THREAD_BUDGET_REQUIRED')
    old = signal.getsignal(signal.SIGALRM)
    def expired(*_): raise TimeoutError('PRE_DISPATCH_HARD_TIME_BUDGET')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, milliseconds / 1000)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def receipt(status, **fields):
    return {'status': status, 'money_authority': False, 'live_orders_allowed': False,
            'evidence_kind': 'INPUT_PROVIDED_ENGINEERING', **fields}


def precompute_ranking(policy, history, blocked, source_pin, available_ms, prepared_ms, open_ms):
    """Compute the unchanged closed-data selector early; seal only at opening.

    This is a prospective draft with its actual preparation timestamp, not a
    backdated sealed ranking. Fresh survivor/context mismatch must reject it.
    """
    from scripts.alpaca_adaptive_paper import prepare_intended_report
    policy_check(policy)
    from research_lab.alpaca_dynamic_v1 import source_check
    source_check(policy,policy['calendar_sessions']);pin(source_pin)
    prepared_ms=instant(prepared_ms);available_ms=instant(available_ms)
    current=session_at(policy['calendar_sessions'],instant(open_ms))
    if (not current or current['open_ms']!=open_ms or open_ms<policy['first_window_ms']
        or prepared_ms>open_ms-900000 or set(history)!=set(policy['universe'])):
        raise ValueError('PRECOMPUTE_WINDOW_OR_UNIVERSE')
    week=date.fromisoformat(current['session']).isocalendar()[:2]
    first=min(r['open_ms'] for r in policy['calendar_sessions']
              if date.fromisoformat(r['session']).isocalendar()[:2]==week)
    if open_ms!=policy['first_window_ms'] and open_ms!=first:
        raise ValueError('NOT_WEEKLY_REFRESH')
    prior=[r for r in policy['calendar_sessions'] if r['close_ms']<open_ms]
    if not prior or not prior[-1]['close_ms']<=available_ms<=prepared_ms:
        raise ValueError('MISSING_OR_FUTURE_CLOSED_SOURCE')
    eligible={s:rows for s,rows in sorted(history.items()) if s=='SPY' or s not in set(blocked)}
    value=prepare_intended_report(eligible,signal_session=date.fromisoformat(prior[-1]['session']),
                                  entry_session=date.fromisoformat(current['session']))
    ranking={'policy_sha256':digest(policy),'window_ms':open_ms,'signal_session':prior[-1]['session'],
             'input_sha256':source_pin,'source_available_ms':available_ms,'gate_ok':value['gate_ok'],
             'picks':value['picks'],'blocked_symbols':sorted(set(blocked)),
             'selector_source_hashes':value['selector_source_hashes']}
    return receipt('PRECOMPUTED_NOT_SEALED',prepared_ms=prepared_ms,ranking=ranking)


def existing_paper_path(plan, policy, client, account_id, runtime, now_ms, *, send=False):
    """Exactly one existing adapter invocation; no duplicate GET rehearsal.

    Shared account lock and real source/attempt approval remain caller-owned.
    After dispatch the original adapter manages protection/recovery; never kill
    it with an opening timeout that would abandon an accepted entry.
    """
    if client.base_url != PAPER:
        return receipt('BLOCKED_DATA', reason='PAPER_ENDPOINT_ONLY')
    return execute_paper(plan, policy, client, account_id, runtime, now_ms, send=send)


class PreloadedSourcePublisher:
    """Small opening GET set; reviewed static mappings are loaded beforehand.

    The template supplies separately reviewed owner/terminal/earnings/context
    evidence. This adapter does not authenticate those declarations. Any new
    survivor, liability or source conflict blocks instead of rebuilding sources
    in the opening window. No history download or earnings query occurs here.
    """
    def __init__(self, policy, template, protocol, symbol, live_client, quote_reader, clock=None):
        self.policy=json.loads(canonical(policy));self.template=json.loads(canonical(template))
        self.protocol=json.loads(canonical(protocol));self.symbol=symbol
        self.live=live_client;self.quote_reader=quote_reader;self.clock=clock or WallClock()

    def capture(self):
        p=self.policy;s=json.loads(canonical(self.template));symbol=self.symbol
        if self.live.base_url!='https://api.alpaca.markets':raise ValueError('SOURCE_LIVE_GET_ENDPOINT')
        a=self.live.get_account()
        try:
            if (a['id']!=p['account_id'] or a['status']!='ACTIVE'
                or a['trading_blocked'] is not False or a['account_blocked'] is not False
                or dec(a['pending_reg_taf_fees'])!=0 or dec(a['accrued_fees'])!=0):
                raise ValueError('FRESH_CASH_OR_FEE_FINALITY_UNRESOLVED')
            cash=min(dec(a['cash']),dec(a['non_marginable_buying_power']))
            if cash<0:raise ValueError('NEGATIVE_SPENDABLE_CASH')
        except (KeyError,TypeError,ArithmeticError):
            raise ValueError('FRESH_ACCOUNT_SOURCE_INCOMPLETE') from None
        if s['single_owner_verified'] is not True or s['cash_finality_verified'] is not True:
            raise ValueError('PRELOADED_SOURCE_REVIEW_UNCONFIRMED')
        positions=self.live.list_positions();orders=self.live.list_orders(status='open',limit=100)
        if len(orders)>=100:raise ValueError('OPEN_ORDER_SOURCE_TRUNCATED')
        expected=sorted((r['symbol'],str(positive(r['qty']))) for r in s['positions'])
        actual=sorted((r['symbol'],str(positive(r['qty']))) for r in positions)
        if actual!=expected:raise ValueError('SURVIVOR_CHANGED_REVIEW_REQUIRED')
        asset=self.live._request('GET','/v2/assets/'+symbol)
        if (asset['symbol']!=symbol or asset['status']!='active'
            or asset['tradable'] is not True or asset['fractionable'] is not True):
            raise ValueError('FRESH_ASSET_NOT_ELIGIBLE')
        protocol=self.protocol;f=protocol['fractional_protocol']
        document=protocol.get('sources',{}).get('fractional.html',{})
        if (protocol.get('schema')!='ALPACA_PROTOCOL_SOURCE_CONTRACT_V1'
            or protocol.get('status')!='APPROVE_WITH_LIMITATIONS'
            or f.get('supported_execution')!=PROTECTION_MAPPING
            or document.get('url')!='https://docs.alpaca.markets/us/docs/fractional-trading'
            or document.get('sha256')!=PROTECTION_DOCUMENT_SHA256):
            raise ValueError('PROTECTION_PROTOCOL_MAPPING_UNCONFIRMED')
        if (protocol['account_id']!=p['account_id'] or protocol['commission_rate']!='0'
            or f['buy_minimum_notional_usd']!='1' or f['max_qty_decimal_places']!=9
            or f['requires_fresh_asset']!={'symbol':symbol,'status':'active','tradable':True,'fractionable':True}):
            raise ValueError('PRELOADED_PROTOCOL_MAPPING_CONFLICT')
        quoted=self.quote_reader(symbol);q=quoted['quote']
        raw_ms=int(datetime.fromisoformat(q['t'].replace('Z','+00:00')).timestamp()*1000)
        now=instant(self.clock.wall_ms())
        if (not 0<=now-raw_ms<=p['max_snapshot_age_ms']
            or not raw_ms<=instant(quoted['received_ms'])<=now):
            raise ValueError('FRESH_RAW_QUOTE_CLOCK')
        ask=positive(q['ap']);reference=s['quotes'][symbol]
        # Static reference distance is frozen from the ranked candidate. The
        # actual planner still owns all slot/risk/gross/cash sizing.
        distance=positive(reference['risk_distance']) if 'risk_distance' in reference else None
        if distance is None:
            # Explicit ceiling supplied by a reviewed static source is permitted
            # only as a CAT bound, never a requested quantity or risk override.
            ceiling=positive(reference['fee_quantity_ceiling'])
        else:
            stop=(ask-distance).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            distance=ask-stop
            if not 0<stop<ask:raise ValueError('INVALID_REFERENCE_RISK_DISTANCE')
            slot=sorted(p['inherited_slots'],key=lambda r:r['entry_order_id'])[0]
            ceiling=(min(positive(slot['notional_cap'])/ask,positive(slot['risk_cap'])/distance)
                     /Decimal('.000000001')).to_integral_value(rounding=ROUND_DOWN)*Decimal('.000000001')
        rate=dec(protocol['regulatory_model']['cat_nms_executed_share_rate'])
        if rate<0:raise ValueError('CAT_RATE_INVALID')
        reserve=(ceiling*rate/Decimal('.01')).to_integral_value(rounding='ROUND_CEILING')*Decimal('.01')
        if reserve<=0 or ceiling<=0:raise ValueError('CAT_CEILING_SOURCE_INVALID')
        sources={'account':a,'positions':positions,'open_orders':orders,'asset':asset,'quote':quoted,
                 'template_sha256':digest(self.template),'protocol_sha256':digest(protocol),
                 'protection_mapping':{'status':'SOURCE_ELIGIBILITY_ONLY','broker_acceptance':False,
                                       'document_sha256':PROTECTION_DOCUMENT_SHA256}}
        s.update(observed_ms=now,cash_usd=str(cash),fee_rate='0',liability_reserve_usd=str(reserve),
                 positions=positions,open_orders=orders,source_sha256=digest(sources))
        s['quotes']={symbol:{'ask':str(ask),'quote_ms':raw_ms,'received_ms':quoted['received_ms'],
            'qty_step':'.000000001','min_qty':'.000000001','min_notional':'1',
            'tradable':True,'fractionable':True,'fee_quantity_ceiling':str(ceiling)}}
        if s['gates'][symbol]['earnings'] is not True or s['gates'][symbol]['concentration'] is not True:
            raise ValueError('PRELOADED_CANDIDATE_GATE_UNCONFIRMED')
        s['gates'][symbol].update(symbol=True,protection=True)
        # Preserve credential-free GET responses with the snapshot; retaining
        # only their hash would prevent later source/recovery verification.
        s['source_evidence']=sources
        self.last_source=sources
        return s


class OpeningDispatcher:
    def __init__(self, runtime, policy, open_ms, static_paths, checks, clock=None, *, plan_store=None):
        self.runtime = Path(runtime).absolute()
        if any(p.is_symlink() for p in [self.runtime, *self.runtime.parents]):
            raise ValueError('DISPATCH_STATE_SYMLINK')
        self.policy = json.loads(canonical(policy))
        self.open_ms = instant(open_ms)
        self.paths = {name: Path(path).absolute() for name,path in static_paths.items()}
        self.checks = json.loads(canonical(checks))
        self.clock = clock or WallClock()
        self.plan_store = Path(plan_store).absolute() if plan_store else None
        self.preloaded = None
        policy_check(self.policy)
        current = session_at(self.policy['calendar_sessions'], self.open_ms)
        if not current or current['open_ms'] != self.open_ms:
            raise ValueError('UNKNOWN_TARGET_OPENING')
        self.session = current['session']

    @contextmanager
    def lock(self):
        self.runtime.mkdir(parents=True, exist_ok=True)
        path = self.runtime/'dispatch.lock'
        if path.is_symlink(): raise ValueError('DISPATCH_LOCK_SYMLINK')
        with path.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield

    def _read(self, name):
        p = self.runtime/name
        if not p.exists(): return None
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1:
            raise ValueError('DISPATCH_STATE_IDENTITY')
        raw = json.loads(p.read_text())
        if raw['sha256'] != digest(raw['value']): raise ValueError('DISPATCH_STATE_HASH')
        return raw['value']

    def _write(self, name, value):
        p = self.runtime/name
        raw = canonical({'value':value,'sha256':digest(value)})
        with p.open('xb') as handle:
            os.chmod(p,0o600); handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        fd=os.open(self.runtime,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return value

    def _pins(self):
        if not self.paths: raise ValueError('STATIC_SOURCE_PATHS_MISSING')
        loaded={}
        for name,path in self.paths.items():
            if (not name or any(p.is_symlink() for p in [path,*path.parents])
                    or not path.is_file() or path.stat().st_size > 20_000_000):
                raise ValueError('STATIC_SOURCE_PATH_OR_SIZE')
            loaded[name]=path.read_bytes()
        self.preloaded=loaded
        return {name:hashlib.sha256(raw).hexdigest() for name,raw in loaded.items()}

    def _source_intents(self):
        if self.plan_store is None or not self.plan_store.is_file():
            raise ValueError('EXISTING_SOURCE_BOOK_REQUIRED')
        if any(p.is_symlink() for p in [self.plan_store,*self.plan_store.parents]):
            raise ValueError('SOURCE_BOOK_SYMLINK')
        with sqlite3.connect(self.plan_store.as_uri()+'?mode=ro',uri=True) as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM intents')]

    def _check_declarations(self):
        if set(self.checks) != set(STATIC_CHECKS):raise ValueError('STATIC_SOURCE_REVIEW_INCOMPLETE')
        for name,item in self.checks.items():
            expected='CLEAR_OR_REVIEWED' if name=='reservation_handoff' else 'VERIFIED'
            if item['status'] != expected:raise ValueError('STATIC_SOURCE_REVIEW_UNKNOWN:'+name)
            pin(item['source_sha256'])

    def _terminal(self,status,reason,**fields):
        old=self._read('terminal.json')
        return old or self._write('terminal.json',receipt(status,reason=reason,**fields))

    def prepare(self):
        with self.lock():
            old=self._read('terminal.json')
            if old:return old
            try:
                now=instant(self.clock.wall_ms())
                if now>self.open_ms-900000:raise ValueError('STATIC_T_MINUS_15_MISSED')
                self._check_declarations()
                pins=self._pins()
                if self._source_intents():raise ValueError('UNRESOLVED_SOURCE_RESERVATION')
                if self.clock.wall_ms()>self.open_ms-900000:raise ValueError('STATIC_T_MINUS_15_MISSED')
                value=receipt('STATIC_PREPARED',prepared_ms=now,open_ms=self.open_ms,
                    policy_sha256=digest(self.policy),static_sha256=pins,checks_sha256=digest(self.checks),
                    source_book=str(self.plan_store),broker_truth_authenticated=False)
                old=self._read('prepared.json')
                if old and old!=value:raise ValueError('STATIC_PREPARATION_CONFLICT')
                result=old or self._write('prepared.json',value)
                if self.clock.wall_ms()>self.open_ms-900000:raise ValueError('STATIC_T_MINUS_15_MISSED')
                return result
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
                return self._terminal('BLOCKED_DATA',str(exc))

    def ready(self):
        with self.lock():
            old=self._read('terminal.json')
            if old:return old
            try:
                prep=self._read('prepared.json');now=instant(self.clock.wall_ms())
                if not prep:raise ValueError('STATIC_NOT_PREPARED')
                if not prep['prepared_ms']<=now<=self.open_ms-60000:
                    return self._terminal('BLOCKED_EXECUTION','READY_T_MINUS_1_MISSED')
                self._validate_static(prep)
                if self._source_intents():raise ValueError('UNRESOLVED_SOURCE_RESERVATION')
                value=receipt('READY_TO_DISPATCH',ready_ms=now,open_ms=self.open_ms,
                    prepared_sha256=digest(prep),operational_authority=False)
                old=self._read('ready.json')
                result=old or self._write('ready.json',value)
                if self.clock.wall_ms()>self.open_ms-60000:
                    return self._terminal('BLOCKED_EXECUTION','READY_T_MINUS_1_MISSED')
                return result
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
                return self._terminal('BLOCKED_DATA',str(exc))

    def _validate_static(self,prep):
        if (prep['policy_sha256']!=digest(self.policy) or prep['open_ms']!=self.open_ms
            or prep['checks_sha256']!=digest(self.checks)
            or prep['source_book']!=str(self.plan_store) or prep['static_sha256']!=self._pins()):
            raise ValueError('PRELOADED_SOURCE_CHANGED')

    def _fresh_check(self,s,now):
        if (s['account_id']!=self.policy['account_id'] or s['single_owner_verified'] is not True
            or s['cash_finality_verified'] is not True
            or not 0<=now-instant(s['observed_ms'])<=self.policy['max_snapshot_age_ms']):
            raise ValueError('FRESH_ACCOUNT_OWNER_OR_CASH')
        pin(s['source_sha256'])
        if not isinstance(s['positions'],list) or not isinstance(s['open_orders'],list):
            raise ValueError('POSITION_OR_ORDER_SOURCE_UNKNOWN')
        for q in s['quotes'].values():
            # Raw exchange clock, not HTTP receive time alone; same frozen5m age.
            if not 0<=now-instant(q['quote_ms'])<=self.policy['max_snapshot_age_ms']:
                raise ValueError('RAW_QUOTE_STALE_OR_FUTURE')
            if not q['quote_ms']<=instant(q['received_ms'])<=now:
                raise ValueError('RAW_QUOTE_RECEIVE_LINEAGE')

    def run(self,*,fresh,reserve,execute):
        with self.lock():
            old=self._read('terminal.json')
            if old:return old
            timings=[];entered=False
            try:
                if self._read('invoking_adapter.json'):
                    return self._terminal('BLOCKED_EXECUTION','UNCERTAIN_ADAPTER_NO_REINVOKE')
                prep=self._read('prepared.json');ready=self._read('ready.json')
                if not prep or not ready or ready['prepared_sha256']!=digest(prep):
                    raise ValueError('NOT_PREPARED_AND_READY')
                self._validate_static(prep)
                now=instant(self.clock.wall_ms())
                if not self.open_ms<=now<self.open_ms+300000-START_BUDGET_MS:
                    return self._terminal('BLOCKED_EXECUTION','OPENING_START_BUDGET')
                if self._source_intents():
                    return self._terminal('BLOCKED_EXECUTION','PLAN_NOT_NEW_FOR_THIS_ATTEMPT')
                def step(name,call,budget):
                    started=instant(self.clock.wall_ms());mono=self.clock.monotonic_ms()
                    completed=False
                    try:
                        with hard_budget(budget):
                            value=call()
                            self._write(name+'.json',{'start_ms':started,'budget_ms':budget,
                                                     'value_sha256':digest(value),'value':value})
                        completed=True
                    finally:
                        elapsed=self.clock.monotonic_ms()-mono
                        timings.append({'name':name,'start_ms':started,'end_ms':self.clock.wall_ms(),
                                        'elapsed_ms':elapsed,'budget_ms':budget,
                                        'includes_evidence_persistence':True,'completed':completed})
                    if elapsed<0 or elapsed>budget:raise TimeoutError(name.upper()+'_TIME_BUDGET')
                    if not self.open_ms<=self.clock.wall_ms()<self.open_ms+300000:
                        raise TimeoutError('OPENING_EXPIRED_'+name.upper())
                    return value
                snapshot=step('fresh',fresh,FRESH_BUDGET_MS)
                self._fresh_check(snapshot,self.clock.wall_ms())
                if self.clock.wall_ms()+RESERVE_BUDGET_MS+ENTRY_PREFLIGHT_ALLOWANCE_MS>=self.open_ms+300000:
                    raise TimeoutError('INSUFFICIENT_BUDGET_BEFORE_RESERVATION')
                plan=step('reserve',lambda:reserve(snapshot),RESERVE_BUDGET_MS)
                if plan['status']!='RESERVED_ORDERS_OFF':
                    return self._terminal('BLOCKED_EXECUTION',plan.get('reason',plan['status']),timings=timings)
                if (plan['session']!=self.session or plan['prepared_ms']<timings[-1]['start_ms']
                    or plan['prepared_ms']>self.clock.wall_ms() or plan['snapshot_sha256']!=digest(snapshot)):
                    raise ValueError('PLAN_NOT_NEW_FOR_THIS_ATTEMPT')
                quantity_bound=snapshot['quotes'][plan['symbol']].get('fee_quantity_ceiling')
                if quantity_bound is not None and positive(plan['qty'])>positive(quantity_bound):
                    raise ValueError('SOURCE_FEE_QUANTITY_CEILING_EXCEEDED')
                if self.clock.wall_ms()+ENTRY_PREFLIGHT_ALLOWANCE_MS>=self.open_ms+300000:
                    raise TimeoutError('INSUFFICIENT_ADAPTER_PREFLIGHT_BUDGET')
                # Persist this boundary before calling; a crash never re-invokes a
                # possibly sending adapter. Recovery is existing owned maintenance.
                self._write('invoking_adapter.json',{'parent_receipt_id':plan['receipt_id'],
                    'invoked_ms':self.clock.wall_ms(),'plan_sha256':digest(plan)})
                entered=True;start=self.clock.wall_ms();mono=self.clock.monotonic_ms()
                result=execute(plan)
                timings.append({'name':'existing_paper_adapter','start_ms':start,'end_ms':self.clock.wall_ms(),
                                'elapsed_ms':self.clock.monotonic_ms()-mono,'budget_ms':None,
                                'protection_not_aborted_by_dispatch_deadline':True})
                if result['status'].startswith('BLOCKED'):
                    return self._terminal(result['status'],result.get('reason','ADAPTER_BLOCKED'),
                                          execution=result,timings=timings)
                return self._write('terminal.json',receipt('OPENING_PATH_COMPLETED',execution=result,
                    timings=timings,broker_lifecycle_pass=False,local_path_only=True))
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,TimeoutError) as exc:
                kind='BLOCKED_EXECUTION' if entered or isinstance(exc,TimeoutError) else 'BLOCKED_DATA'
                return self._terminal(kind,str(exc),timings=timings,adapter_invoked=entered)
