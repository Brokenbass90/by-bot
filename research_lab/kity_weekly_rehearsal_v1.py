"""KITY-specific file-only weekly rehearsal, not a broker executor.

Reuses the existing lifecycle journal and Decimal validation. Every fill, native
protection and cost finality below is explicitly SIMULATED. No sender, lease,
credentials, GO, selector or research outcomes are imported or executed.
"""
from datetime import datetime,timezone
from decimal import Decimal as D
import hashlib
import os
from pathlib import Path

from research_lab.att1_lifecycle_journal import LifecycleJournal,SCHEMA
from research_lab.kity_execution_micro_v1 import numeric
from research_lab.kity_bybit_c2 import safe_path,canonical
from research_lab.os2_shadow_journal import strict_json

DAY=86400000
DOMAIN='KITY_BYBIT_WEEKLY_ORDERS_OFF_V1'


def need(ok,reason):
    if not ok:raise ValueError('KITY_WEEKLY_'+reason)


def fee_number(value):
    need(not isinstance(value,bool) and value not in (None,''),'UNKNOWN_FEE')
    fee=D(str(value));need(fee.is_finite(),'NONFINITE_FEE');return fee


def make_profile(session,legs,source_pins,*,funding_intervals=None):
    day=datetime.strptime(session,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    start=int(day.timestamp()*1000)+DAY
    p=dict(schema=DOMAIN,mode='ORDERS_OFF',session=session,legs=legs,source_pins=source_pins,
           entry_reference_ms=start,exit_reference_ms=start+7*DAY,hold_days=7,
           funding_intervals=funding_intervals or {},funding_basis='EXPLICIT_SYNTHETIC_SCHEDULE_NOT_VENUE_PROOF',
           protection_contract='CONTINGENCY_FIXTURE_ONLY',money_authority=False,orders_allowed=False)
    validate(p);return p


def validate(p):
    need(p['schema']==DOMAIN and p['mode']=='ORDERS_OFF' and p['money_authority'] is False
         and p['orders_allowed'] is False and p['hold_days']==7,'ORDERS_OFF_ONLY')
    need(p['exit_reference_ms']-p['entry_reference_ms']==7*DAY,'HOLD_CLOCK')
    day=datetime.strptime(p['session'],'%Y-%m-%d').replace(tzinfo=timezone.utc)
    need(p['entry_reference_ms']==int(day.timestamp()*1000)+DAY,'CLOSE_REFERENCE_CLOCK')
    legs=p['legs'];need(len(legs) in (6,8,10),'CARDINALITY')
    need(len({v['symbol'] for v in legs})==len(legs) and
         sum(v['side']==1 for v in legs)==sum(v['side']==-1 for v in legs)==len(legs)//2,'SIDES')
    for v in legs:
        numeric(v['qty']);numeric(v['entry_reference_price'])
    need(all(isinstance(x,str) and len(x)==64 and set(x)<=set('0123456789abcdef') for x in p['source_pins'].values())
         and set(p['source_pins'])=={'signal','entry','c2'},'SOURCE_PINS')
    need(set(p['funding_intervals'])<=set(v['symbol'] for v in legs),'FUNDING_SYMBOLS')
    for interval in p['funding_intervals'].values():
        need(type(interval) is int and 0<interval<=1440 and 1440%interval==0,'FUNDING_CALENDAR')
    need(p['protection_contract']=='CONTINGENCY_FIXTURE_ONLY','NO_FROZEN_NATIVE_STOP_RULE')


def routing_check(active_scope,profile):
    validate(profile)
    return dict(schema='KITY_EXISTING_OWNER_ROUTE_CHECK_V1',admitted=False,orders_allowed=False,
                live_scope_change_required=True,active_owner=active_scope.get('schema','UNKNOWN'),
                reason='CURRENT_PUMP4_SCOPE_SINGLE_LIFECYCLE_NOT_KITY_AUTHORITY',
                next_gate='versioned common-owner dispatcher with separate exact scopes and union custody; separate GO')


class WeeklyRehearsal:
    def __init__(self,root,profile):
        validate(profile);self.profile=strict_json(canonical(profile));self.pin=hashlib.sha256(canonical(profile)).hexdigest()
        self.root=safe_path(Path(root).absolute());self.root.mkdir(parents=True,mode=0o700,exist_ok=True)
        self.config=self.root/'profile.json'
        if self.config.exists():
            need(not self.config.is_symlink() and self.config.stat().st_nlink==1
                 and strict_json(self.config.read_bytes())==profile,'PROFILE_DRIFT')
        else:
            need(not (self.root/'events.jsonl').exists(),'MISSING_PROFILE_NO_RESET')
            fd=os.open(self.config,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as out:out.write(canonical(profile));out.flush();os.fsync(out.fileno())
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
        self.events=LifecycleJournal(self.root/'events.jsonl')

    def state(self):return self.reduce(self.events.read())

    def append(self,event):
        # A replay must remain bound to the same immutable profile after restart.
        need(strict_json(self.config.read_bytes())==self.profile,'PROFILE_DRIFT')
        row=dict(event,schema_id=SCHEMA,domain=DOMAIN,profile_sha256=self.pin,simulated_only=True)
        self.reduce([*self.events.read(),row])
        self.events.append(row)
        return self.state()

    def reduce(self,rows):
        p=self.profile;legs={v['symbol']:v for v in p['legs']};held={s:D(0) for s in legs};entered=dict(held)
        average=dict(held);protected={};stop_prices={};fills={};funding={};seen={};timeline={s:[] for s in legs}
        fees={};realized=D(0);cash=D(0);unknown=set();failed=False;emergency=False;cost_final=False
        fail_streak=0;halt=False;clock=p['entry_reference_ms'];last_exit={}
        def held_at(s,ms):return sum((q for t,q in timeline[s] if t<=ms),D(0))
        for row in rows:
            need(row['schema_id']==SCHEMA and row['domain']==DOMAIN and row['profile_sha256']==self.pin
                 and row['simulated_only'] is True,'EVENT_BINDING')
            eid=row['event_id'];pin=hashlib.sha256(canonical(row)).hexdigest()
            if eid in seen:
                need(seen[eid]==pin,'CONFLICTING_EVENT');continue
            t=row['observed_ms'];need(type(t) is int and t>=clock,'EVENT_CLOCK');clock=t
            kind=row['kind'];s=row['symbol'];need(s in legs or s=='ALL','EVENT_SYMBOL')
            if kind=='OPERATIONAL_FAIL':fail_streak+=1;halt|=fail_streak>=2
            elif kind=='OPERATIONAL_PASS':fail_streak=0
            elif kind=='UNKNOWN_ENTRY_ACK':need(s in legs,'ACK_SYMBOL');unknown.add(s)
            elif kind=='ACK_RECONCILED':need(s in unknown,'UNKNOWN_ACK_MISSING');unknown.remove(s)
            elif kind=='MODEL_ENTRY_REJECT':failed=True
            elif kind in ('MODEL_ENTRY_FILL','MODEL_EXIT_FILL','MODEL_EMERGENCY_EXIT_FILL','MODEL_NATIVE_STOP_FILL'):
                need(s in legs,'FILL_SYMBOL');xid=row['exec_id'];need(isinstance(xid,str) and xid,'EXECUTION_ID')
                qty=numeric(row['qty']);price=numeric(row['price']);fee=row['fee_usdt']
                if fee is not None:fee=fee_number(fee)
                fp=canonical({**{k:row[k] for k in ('kind','symbol','exec_id','qty','price','fee_usdt')},
                              'source_execution_ms':row.get('source_execution_ms')})
                fill_t=row.get('source_execution_ms',t)
                need(type(fill_t) is int and p['entry_reference_ms']<=fill_t<=t,'SOURCE_EXECUTION_CLOCK')
                if xid in fills:
                    need(fills[xid]==fp,'CONFLICTING_EXECUTION');seen[eid]=pin;continue
                if kind=='MODEL_ENTRY_FILL':
                    need(not halt,'R5_ENTRY_HALT');need(not unknown,'ACK_RECONCILIATION_REQUIRED')
                    need(not failed and not emergency and not cost_final and not last_exit,'ENTRY_AFTER_CLOSE_OR_FAILURE')
                    need(t<p['exit_reference_ms'] and entered[s]+qty<=numeric(legs[s]['qty']),'ENTRY_SIZE_OR_WINDOW')
                    average[s]=(average[s]*held[s]+qty*price)/(held[s]+qty)
                    held[s]+=qty;entered[s]+=qty;timeline[s].append((fill_t,qty));cash-=D(legs[s]['side'])*qty*price
                else:
                    need(qty<=held[s],'EXIT_EXCEEDS_HELD')
                    if kind=='MODEL_EXIT_FILL':need(fill_t>=p['exit_reference_ms'],'EARLY_STRATEGY_EXIT')
                    else:
                        if kind=='MODEL_NATIVE_STOP_FILL':
                            need(protected.get(s)==held[s] and s in stop_prices and
                                 (price<=stop_prices[s] if legs[s]['side']==1 else price>=stop_prices[s]),'STOP_TRIGGER_OR_COVERAGE')
                        emergency=True
                    realized+=D(legs[s]['side'])*qty*(price-average[s]);held[s]-=qty
                    cash+=D(legs[s]['side'])*qty*price;timeline[s].append((fill_t,-qty));last_exit[s]=fill_t
                fills[xid]=fp;fees[xid]=fee;cost_final=False
            elif kind=='MODEL_FEE':
                xid=row['exec_id'];need(xid in fees,'UNKNOWN_FEE_EXECUTION');fee=fee_number(row['fee_usdt'])
                need(fees[xid] is None or fees[xid]==fee,'CONFLICTING_FEE')
                if fees[xid] is None:fees[xid]=fee;cost_final=False
            elif kind=='PROTECTION':
                need(s in legs and row['contract']=='CONTINGENCY_FIXTURE_ONLY','PROTECTION_CONTRACT')
                q=numeric(row['qty'],zero=True)
                if row['status']=='ACCEPTED':
                    stop=numeric(row['stop_price']);entry=numeric(legs[s]['entry_reference_price'])
                    need(q==held[s] and q>0 and (stop<entry if legs[s]['side']==1 else stop>entry),'PROTECTION_GEOMETRY')
                    protected[s]=q;stop_prices[s]=stop
                elif row['status']=='CANCELLED':need(held[s]==0 and q==0,'CANCEL_WHILE_HELD');protected.pop(s,None)
                else:protected.pop(s,None)
            elif kind=='MODEL_FUNDING':
                need(s in legs,'FUNDING_SYMBOL');settle=int(row.get('settlement_ms',row['settlement_id']))
                need(settle<=t and settle>p['entry_reference_ms'],'FUNDING_CLOCK')
                interval=p['funding_intervals'].get(s)
                need(interval is not None and settle%(interval*60000)==0,'FUNDING_CALENDAR')
                qty=numeric(row['qty']);mark=numeric(row['mark']);rate=D(str(row['rate']));amount=D(str(row['cash_usdt']))
                need(rate.is_finite() and abs(rate)<1 and amount.is_finite() and qty==held_at(s,settle)
                     and amount==-D(legs[s]['side'])*qty*mark*rate,'FUNDING_CASH_OR_QUANTITY')
                key=(s,settle);fp=(qty,mark,rate,amount)
                need(key not in funding or funding[key]==fp,'CONFLICTING_FUNDING')
                if key not in funding:funding[key]=fp;cost_final=False
            elif kind=='MODEL_COST_FINALITY':
                need(s=='ALL' and all(v==0 for v in held.values()) and not unknown and
                     row['fees_complete'] is True and row['funding_complete'] is True
                     and fills and all(v is not None for v in fees.values()),'COST_FINALITY_UNKNOWN')
                need(set(p['funding_intervals'])==set(legs),'UNKNOWN_FUNDING_CALENDAR')
                for sym in legs:
                    interval=p['funding_intervals'][sym]*60000
                    for stamp in range((p['entry_reference_ms']//interval+1)*interval,last_exit.get(sym,t)+1,interval):
                        if held_at(sym,stamp)>0:need((sym,stamp) in funding,'FUNDING_COVERAGE_INCOMPLETE')
                cost_final=True
            else:need(False,'UNKNOWN_EVENT')
            seen[eid]=pin
        all_entered=all(entered[s]==numeric(legs[s]['qty']) for s in legs)
        flat=all(q==0 for q in held.values());fee_total=sum((v for v in fees.values() if v is not None),D(0))
        funding_total=sum((v[3] for v in funding.values()),D(0))
        complete=flat and all_entered and not failed and not emergency and not unknown and cost_final and not protected
        return dict(schema='KITY_WEEKLY_MODEL_REPLAY_V1',held={s:str(q) for s,q in held.items()},
                    all_legs_entered=all_entered,failed_basket=failed,unknown_ack_symbols=sorted(unknown),r5_entry_halt=halt,
                    protected_full=not flat and all(q==0 or protected.get(s)==q for s,q in held.items()),
                    fees_known_usdt=str(fee_total),funding_cash_usdt=str(funding_total),trade_cash_usdt=str(cash),
                    gross_realized_usdt=str(realized),net_usdt=str(realized+funding_total-fee_total) if cost_final else None,
                    terminal_complete=complete,model_capital_released=complete,exit_early_by_strategy=False,
                    off_protocol_contingency=emergency,unresolved_costs=not cost_final,simulated_only=True,
                    real_cost_finality_proven=False,actual_broker_writes=0,orders_allowed=False,money_authority=False)
