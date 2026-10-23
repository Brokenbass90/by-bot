"""PUMP4 account-owner candidate: existing lock/journal/send-once/lifecycle.

No credential loader, default wire, installer or authority minting. A future
selected runner must provide the source-pinned physical-owner verifier and exact
human GO. This candidate is tested only with fictional accounts/memory wire.
The first proposed pilot admits one lifecycle; unknown final costs never release
it or create authority for another trade. Risk triggers inhibit entries only.
"""
import copy,hashlib,json,os
from datetime import datetime,timezone
from decimal import Decimal as D,ROUND_FLOOR
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.att1_lifecycle_journal import LifecycleJournal,SCHEMA
from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce,publish
from research_lab.kity_oct15_deadline_v1 import stable_bytes,decode
from research_lab.pump4_account_adapter_v1 import owned_observation,execution_feasibility,checked_order_ack,frozen_plan
from research_lab.pump4_bybit_sources_v1 import account_view,checked,number,H
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle

DOMAIN='PUMP4_ACCOUNT_OWNER_V1'

def need(ok,why):
    if not ok:raise ValueError('PUMP4_OWNER_'+why)

def safe(p):
    p=Path(p).absolute();need('..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'PATH_CUSTODY')
    return p

def source_sizing(plan,bundle,public,policy,*,fingerprint,now_ms):
    """Fully bound conservative scenario sizing; still not financial authority."""
    frozen_plan(plan);view=account_view(bundle,expected_fingerprint=fingerprint,now_ms=now_ms)
    symbol=plan['symbol'];cap=bundle['captures']['symbol_position']
    need(cap['params']==dict(category='linear',symbol=symbol),'SYMBOL_MODE_QUERY')
    mode=checked(cap,'/v5/position/list',now_ms=now_ms,private=True,fingerprint=fingerprint)
    rows=mode['list'];need(mode.get('nextPageCursor','')=='' and len(rows)==1
        and rows[0]['symbol']==symbol and type(rows[0]['positionIdx']) is int and rows[0]['positionIdx']==0,'EXPLICIT_ONE_WAY_REQUIRED')
    pages=public['instruments'];need(pages['complete'] is True and 1<=len(pages['pages'])<=8,'INSTRUMENT_PAGES')
    cursor='';seen=set();instruments={};stamps=[view['source_ms']]
    for index,c in enumerate(pages['pages']):
        need(c['params']==dict(category='linear',limit=1000,**({'cursor':cursor} if cursor else {})),'INSTRUMENT_QUERY')
        result=checked(c,'/v5/market/instruments-info',now_ms=now_ms,private=False)
        need(0<=now_ms-c['request_ms']<=5000 and 0<=now_ms-c['body']['time']<=5000,'INSTRUMENT_STALE')
        stamps.extend((c['body']['time'],c['request_ms']))
        for row in result['list']:
            need(row['symbol'] not in instruments,'DUPLICATE_INSTRUMENT');instruments[row['symbol']]=row
        cursor=result['nextPageCursor'];need(type(cursor) is str and cursor not in seen,'INSTRUMENT_CURSOR')
        if cursor:seen.add(cursor)
        need(bool(cursor)==(index<len(pages['pages'])-1),'INSTRUMENT_INCOMPLETE')
    quote=public['quote'];need(quote['params']==dict(category='linear') and quote==bundle['captures']['quote'],'QUOTE_SOURCE_IDENTITY')
    quotes=checked(quote,'/v5/market/tickers',now_ms=now_ms,private=False)['list']
    need(0<=now_ms-quote['request_ms']<=5000 and 0<=now_ms-quote['body']['time']<=5000,'QUOTE_STALE')
    ticks=[r for r in quotes if r['symbol']==symbol];need(len(ticks)==1 and symbol in instruments and symbol in view['fees'],'SYMBOL_COVERAGE')
    instrument=instruments[symbol];ticker=ticks[0]
    diagnostic=execution_feasibility(plan,instrument,ticker,view['fees'][symbol],view,
        dict(policy,schema='PUMP4_TINY_PROPOSAL_ONLY_V1',orders_allowed=False),now_ms=now_ms)
    need(diagnostic['status']=='FEASIBLE_PROPOSAL_ONLY',diagnostic.get('blocker','FEASIBILITY'))
    price=number(ticker['bid1Price'] if plan['side']=='short' else ticker['ask1Price'])
    slip=number(policy['slippage_bps'],zero=True)/10000;fee=number(view['fees'][symbol]['takerFeeRate'],zero=True)
    adverse=price*(1-slip if plan['side']=='short' else 1+slip)
    distance=max(abs(number(plan['entry'])-number(plan['stop'])),abs(adverse-number(plan['stop'])))
    rate=max(D(0),-D(instrument['lowerFundingRate']) if plan['side']=='short' else D(instrument['upperFundingRate']))
    # Constant-price/current-cap stress, never a bound on future caps or gap loss.
    funding=price*rate*D(diagnostic['funding_intervals']);unit_cost=2*price*(fee+slip)+funding
    lot=number(instrument['lotSizeFilter']['qtyStep']);unit=5*lot
    quantity=(min(number(diagnostic['quantity']),number(policy['risk_usdt'])/(distance+unit_cost))/unit).to_integral_value(rounding=ROUND_FLOOR)*unit
    minimum=number(instrument['lotSizeFilter']['minOrderQty'])
    need(quantity>0 and min(quantity*D('.4'),quantity*D('.6'))>=minimum
        and quantity*price>=number(instrument['lotSizeFilter']['minNotionalValue']),'COST_INCLUSIVE_CAPACITY')
    cost=quantity*unit_cost
    need(quantity*price+cost+number(policy['reserve_usdt'],zero=True)<=min(number(view['available_balance'],zero=True),number(policy['allocation_usdt'])),'COST_INCLUSIVE_RESERVE')
    return dict(quantity=str(quantity),qty_step=str(lot),min_qty=str(minimum),
        min_notional=str(instrument['lotSizeFilter']['minNotionalValue']),tick_size=str(instrument['priceFilter']['tickSize']),
        scenario_stop_and_cost_usdt=str(quantity*distance+cost),cost_scenario_usdt=str(cost),
        guaranteed_loss_bound=False,source_ms=min(*stamps,quote['body']['time'],quote['request_ms']),source_bundle_sha256=digest(dict(bundle=bundle,public=public)),
        orders_allowed=False,money_authority=False)


class Pump4AccountOwner:
    """One shared account lease, one durable admitted lifecycle, no reset API."""
    def __init__(self,scope,*,lease,key,secret,wire,platform_check,clock):
        self.scope=copy.deepcopy(scope);s=self.scope;p=s['policy']
        need(s['schema']=='PUMP4_ACCOUNT_OWNER_SCOPE_V1' and s['mode'] in {'ORDERS_OFF','OWNER_TINY_LIVE'},'SCOPE')
        need(type(s['valid_from_ms']) is int and type(s['valid_until_ms']) is int and s['valid_from_ms']<s['valid_until_ms'],'AUTHORITY_WINDOW')
        need(type(p['max_entries']) is int and p['max_entries']==1 and type(p['max_positions']) is int and p['max_positions']==1,'FIRST_PILOT_SINGLE_LIFECYCLE')
        for field in ('allocation_usdt','gross_usdt','risk_usdt','day_loss_usdt','week_loss_usdt','drawdown_usdt'):number(p[field])
        need(number(p['reserve_usdt'],zero=True)<number(p['allocation_usdt']) and number(p['slippage_bps'],zero=True)<10000,'POLICY')
        self.root=safe(s['root']);self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.scope_sha256=digest(s);self.lease,self.key,self.secret=lease,key,secret
        self.wire,self.platform_check,self.clock=wire,platform_check,clock
        self._exclusive()
        target=self.root/'owner-scope.json'
        new_scope=False
        try:publish(target,s);new_scope=True
        except FileExistsError:need(decode(stable_bytes(target))==s,'SCOPE_DRIFT_NO_RESET')
        self.barrier_path=safe(self.root/'send-barriers');binding=self.root/'send-barrier-binding.json'
        if new_scope:
            need(not self.barrier_path.exists() and not os.path.lexists(binding),'BARRIER_ALREADY_EXISTS')
            self.barrier_path.mkdir(mode=0o700)
            st=self.barrier_path.stat();publish(binding,dict(path=str(self.barrier_path),device=st.st_dev,inode=st.st_ino))
        need(binding.is_file(),'BARRIER_BINDING_MISSING_NO_RESET')
        self.barrier_binding=decode(stable_bytes(binding));self._barrier_custody()
        self.risk=LifecycleJournal(self.root/'risk.jsonl')
        self.flows=self.root/'flows';self.flows.mkdir(mode=0o700,exist_ok=True)

    def _exclusive(self):
        need(digest(self.scope)==self.scope_sha256,'SCOPE_MUTATED')
        snapshot=self.root/'owner-scope.json'
        if snapshot.exists():need(decode(stable_bytes(snapshot))==self.scope,'SCOPE_FILE_DRIFT')
        self.lease.assert_held()
        need(self.lease.path==safe(self.scope['account_lock_path']) and self.lease.inode==self.scope['account_lock_inode'],'ORIGINAL_GLOBAL_LOCK_REQUIRED')
        need(hashlib.sha256(self.key.encode()).hexdigest()==self.scope['account_fingerprint'],'EXACT_ACCOUNT_KEY')
        self.platform_check()
        if hasattr(self,'barrier_binding'):self._barrier_custody()

    def _barrier_custody(self):
        path=safe(self.barrier_path);need(path.is_dir(),'BARRIER_DIRECTORY_REQUIRED');st=path.stat()
        need(st.st_uid==os.geteuid() and self.barrier_binding==dict(path=str(path),device=st.st_dev,inode=st.st_ino)
            and decode(stable_bytes(self.root/'send-barrier-binding.json'))==self.barrier_binding,'BARRIER_CUSTODY_CHANGED')

    def _authority(self,role):
        need(self.scope['mode']=='OWNER_TINY_LIVE','ORDERS_OFF')
        path=self.root/'owner-go.json';need(path.is_file() and not path.is_symlink(),'EXACT_OWNER_GO_REQUIRED');st=path.stat()
        need(st.st_uid==os.geteuid() and st.st_nlink==1 and st.st_mode&0o777==0o600,'GO_CUSTODY')
        go=decode(stable_bytes(path));need(go==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=self.scope_sha256,owner_go_text='GO PUMP4_TINY '+self.scope_sha256),'EXACT_OWNER_GO')
        if role=='ENTRY':
            need(self.scope['valid_from_ms']<=self.clock()<self.scope['valid_until_ms'],'ENTRY_AUTHORITY_EXPIRED')
            need(not os.path.lexists(self.root/'entry-revoked.json'),'ENTRY_REVOKED')

    def _flow(self,flow):
        need(flow.root==self.flows/flow.config['plan']['plan_sha256'],'FLOW_CUSTODY')
        need(digest(flow.config)==digest(decode(stable_bytes(flow.root/'execution-config.json'))),'FLOW_SOURCE_DRIFT')

    def prepare(self,plan,bundle,public):
        self._exclusive();frozen_plan(plan);path=self.flows/plan['plan_sha256']
        if (path/'execution-config.json').exists():
            flow=Pump4Lifecycle.resume(path);need(flow.config['plan']==plan,'PLAN_CHANGED');return flow
        sizing=source_sizing(plan,bundle,public,self.scope['policy'],fingerprint=self.scope['account_fingerprint'],now_ms=self.clock())
        return Pump4Lifecycle(path,plan,**{k:sizing[k] for k in ('quantity','qty_step','min_qty','min_notional','tick_size') if k!='quantity'},qty=sizing['quantity'])

    def _risk_rows(self):
        rows=self.risk.read()
        for i,e in enumerate(rows):need(e['domain']==DOMAIN and e['scope_sha256']==self.scope_sha256 and e['event_id']=='pump4-risk-'+str(i),'RISK_HISTORY')
        return rows

    def _record_risk(self,flow,observation):
        previous=self._risk_rows();last=previous[-1] if previous else None
        now=observation['observed_ms'];need(last is None or now>=last['observed_ms'],'RISK_CLOCK_REVERSED')
        held=number(observation['held_qty'],zero=True);mark=number(observation['price']);cash=D(0)
        for fill in observation['executions']:
            fee=D(fill['execFee']);need(fee.is_finite() and fill['feeCurrency']=='USDT','RISK_FEE_UNKNOWN')
            amount=number(fill['execQty'])*number(fill['execPrice'])
            cash+=(amount if fill['side']=='Sell' else -amount)-fee
        for funding in observation['funding']:
            amount=D(funding['amount']);need(amount.is_finite() and funding['currency']=='USDT','RISK_FUNDING_UNKNOWN');cash+=amount
        total=cash+held*mark*(-1 if flow.config['plan']['side']=='short' else 1)
        stamp=datetime.fromtimestamp(now/1000,timezone.utc);day=stamp.date().isoformat();week=list(stamp.isocalendar()[:2])
        prior=D(last['total_net_usdt']) if last else D(0)
        daybase=D(last['day_baseline_usdt']) if last and last['day']==day else prior
        weekbase=D(last['week_baseline_usdt']) if last and last['week']==week else prior
        hwm=max(D(0),D(last['high_water_usdt']) if last else D(0),total)
        p=self.scope['policy'];reasons=[]
        if total-daybase<=-number(p['day_loss_usdt']):reasons.append('DAY')
        if total-weekbase<=-number(p['week_loss_usdt']):reasons.append('WEEK')
        if total-hwm<=-number(p['drawdown_usdt']):reasons.append('DRAWDOWN')
        row=dict(schema_id=SCHEMA,event_id='pump4-risk-'+str(len(previous)),domain=DOMAIN,scope_sha256=self.scope_sha256,
            observed_ms=now,day=day,week=week,day_baseline_usdt=str(daybase),week_baseline_usdt=str(weekbase),high_water_usdt=str(hwm),
            total_net_usdt=str(total),observation_sha256=digest(observation),final_costs_proven=False,reasons=reasons)
        self.risk.append(row)
        if reasons and not os.path.lexists(self.root/'entry-loss-stop.json'):
            publish(self.root/'entry-loss-stop.json',dict(scope_sha256=self.scope_sha256,observed_ms=now,reasons=reasons,reset='SEPARATE_EXACT_OWNER_GO_NOT_IMPLEMENTED'))
        return row

    def cycle(self,flow,bundle,public,*,apply=False):
        self._exclusive();self._flow(flow);now=self.clock();plan=flow.config['plan'];new=not flow.requests()
        if apply:self._authority('ENTRY' if new else 'CUSTODY')
        else:need(self.scope['mode']=='ORDERS_OFF','ISOLATED_ORDERS_OFF_ROOT_REQUIRED')
        observation=owned_observation(bundle,plan,flow.requests(),first_send_ms=plan['entry_bar_open_ms'],expected_fingerprint=self.scope['account_fingerprint'],now_ms=now,
            known_native_ids=[e['verified_native_stop_id'] for e in flow.observations.read() if e['verified_native_stop_id']])
        admission=self.root/'admitted-lifecycle.json'
        identity=dict(scope_sha256=self.scope_sha256,plan_sha256=plan['plan_sha256'],flow_root=str(flow.root),execution_config_sha256=digest(flow.config))
        if new:
            self._risk_rows();need(not os.path.lexists(self.root/'entry-loss-stop.json'),'ENTRY_LOSS_LATCHED')
            need(not os.path.lexists(admission),'ACCOUNT_LIFECYCLE_ALREADY_RESERVED')
            size=source_sizing(plan,bundle,public,self.scope['policy'],fingerprint=self.scope['account_fingerprint'],now_ms=now)
            need(D(size['quantity'])==D(flow.config['qty']),'SOURCE_SIZING_CHANGED')
            publish(admission,identity) # Before reservation/POST: never a second lifecycle on reply loss.
        else:need(decode(stable_bytes(admission))==identity,'OWNED_LIFECYCLE_REQUIRED')
        result=flow.advance(observation,now_ms=now)
        try:self._record_risk(flow,observation)
        except Exception:
            if new:raise
            # Unknown portfolio risk inhibits entries; proven owned custody may
            # continue using the independent immutable admission and lifecycle.
            if not os.path.lexists(self.root/'entry-loss-stop.json'):
                publish(self.root/'entry-loss-stop.json',dict(scope_sha256=self.scope_sha256,reason='RISK_UNKNOWN'))
        if not result['request'] or not apply:return result
        source_ms=min(observation['source_ms'],size['source_ms']) if new else observation['source_ms']
        ticket=dict(scope_sha256=self.scope_sha256,request=result['request'],role=result['role'],entry_sizing=size if new else None,
            observation_sha256=digest(observation),source_ms=source_ms,source_capture_sha256=observation['source_capture_sha256'])
        publish(self.root/'tickets'/(result['request']['orderLinkId']+'.json'),ticket)
        try:
            reply=self.post_reserved(flow,result['request'],result['role'],source_ms=source_ms)
            return dict(status='ACK_RECONCILE_REQUIRED',role=result['role'],ack=reply,fill_proven=False)
        except Exception as error:return dict(status='WIRE_UNKNOWN_RECONCILE_ONLY',role=result['role'],error_type=type(error).__name__,no_retry=True)

    def post_reserved(self,flow,request,role,*,source_ms):
        self._exclusive();self._flow(flow);self._authority(role)
        events=flow._events();need(events and events[-1]['request']==request and events[-1]['role']==role,'EXACT_LAST_RESERVED_REQUEST')
        ticket_path=self.root/'tickets'/(request['orderLinkId']+'.json');need(ticket_path.is_file(),'ACCOUNT_DISPATCH_TICKET_REQUIRED')
        ticket_raw=stable_bytes(ticket_path);ticket=decode(ticket_raw);observation=flow.observations.read()[-1]['observation']
        sizing=ticket['entry_sizing'];need((role=='ENTRY')==isinstance(sizing,dict),'DISPATCH_TICKET_SIZING')
        need(source_ms==(min(observation['source_ms'],sizing['source_ms']) if sizing else observation['source_ms']),'DISPATCH_SIZING_TIME')
        need(ticket==dict(scope_sha256=self.scope_sha256,request=request,role=role,entry_sizing=sizing,observation_sha256=digest(observation),source_ms=source_ms,
            source_capture_sha256=observation['source_capture_sha256']) and events[-1]['observation_sha256']==ticket['observation_sha256'],'DISPATCH_TICKET_IDENTITY')
        identity=decode(stable_bytes(self.root/'admitted-lifecycle.json'))
        need(identity==dict(scope_sha256=self.scope_sha256,plan_sha256=flow.config['plan']['plan_sha256'],flow_root=str(flow.root),execution_config_sha256=digest(flow.config)),'ADMISSION_SCOPE')
        if role=='ENTRY':need(not os.path.lexists(self.root/'entry-loss-stop.json'),'ENTRY_LOSS_LATCHED')
        def guarded_wire(method,url,headers,data,timeout):
            self._exclusive();self._authority(role)
            need(stable_bytes(ticket_path)==ticket_raw,'DISPATCH_TICKET_CHANGED')
            need(method=='POST' and url=='https://api.bybit.com/v5/order/create' and json.loads(data)==request,'WIRE_SCOPE')
            need(0<=self.clock()-source_ms<=2000,'FINAL_WIRE_SOURCE_EXPIRED')
            if role=='ENTRY':need(not os.path.lexists(self.root/'entry-loss-stop.json'),'ENTRY_LOSS_LATCHED')
            return self.wire(method,url,headers,data,timeout)
        self._barrier_custody()
        sender=SignedPostOnce(self.key,self.secret,self.barrier_path,wire=guarded_wire,clock=self.clock)
        return checked_order_ack(sender.post('/v5/order/create',request),request)
