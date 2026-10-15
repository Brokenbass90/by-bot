"""Single supervised physical owner; default GET-only, exact GO is separate.

Control clients never load credentials or send orders. Prepared dossiers do not
create a trading journal/reservation. One immutable active-plan lifetime only.
"""
import argparse,concurrent.futures as cf,json,os,re,socket,tempfile,time
from decimal import Decimal as D
from pathlib import Path

from bot.kity_m3_orders_off import digest,_levels,_vwap
from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,validate_plan,signed,numeric,record_funding_cash
from research_lab.kity_micro_account_bridge_v1 import MicroAccountBridge
from research_lab.kity_micro_physical_owner_v1 import (AccountLease,PhysicalOwner,SignedPostOnce,EvidenceReader,
    platform_verifier,load_bound_credentials,publish,sha,now_ms,batch_get,capture_account,rows)
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError,wire_get
from research_lab.kity_micro_preflight_v1 import build_preflight


def validate_control(x):
    if not isinstance(x,dict):raise SourceError('CONTROL_SCHEMA')
    allowed={'PREPARE':{'kind'},'REHEARSE':{'kind','plan_id'},'GO':{'kind','plan_id','exact_go'},'KILL':{'kind','plan_id'}}
    k=x.get('kind')
    if k not in allowed or set(x)!=allowed[k]:raise SourceError('CONTROL_SCOPE')
    if k!='PREPARE' and (not isinstance(x['plan_id'],str) or not re.fullmatch('[0-9a-f]{64}',x['plan_id'])):
        raise SourceError('CONTROL_PLAN_ID')
    if k=='GO' and x['exact_go']!='GO KITY_EXECUTION_MICRO_LIVE '+x['plan_id']:
        raise SourceError('EXACT_OWNER_GO_REQUIRED')
    return x


def recover_without_reentry(journal,at_ms):
    if journal.snapshot()['phase']!='TERMINAL':
        journal.append(dict(kind='UNWIND',reason='SUPERVISOR_RESTART_NO_REENTRY',at_ms=at_ms,
            source_sha256=journal.plan['plan_id'],event_id='restart-'+str(at_ms)))


def funding_calendar(state,spec):
    """Sourced calendar filtered by actual execution-time owned quantity."""
    result={s:[] for s,v in state['entries'].items() if D(v['filled'])>0}
    for symbol in result:
        fills=[v for v in state['fills'].values() if v['symbol']==symbol]
        if any(type(v.get('source_execution_ms')) is not int for v in fills):
            raise SourceError('FUNDING_FILL_CLOCK_UNKNOWN')
        ticks=sorted(fills,key=lambda f:f['source_execution_ms'])
        start=min(f['source_execution_ms'] for f in ticks)
        end=max(f['source_execution_ms'] for f in ticks)
        if D(state['held'][symbol])>0:end=now_ms()
        i=spec[symbol];n=int(i['next_funding_ms']);period=int(i['funding_interval_minutes'])*60000
        if period<=0 or n<=0:raise SourceError('FUNDING_CALENDAR_UNKNOWN')
        # next_funding_ms was pinned before the first execution; never extrapolate backwards.
        first=n+max(0,(start-n)//period+1)*period
        for t in range(first,end+1,period):
            held=sum((D(f['quantity'])*(1 if f['kind']=='ENTRY_FILL' else -1) for f in ticks if f['source_execution_ms']<t),D(0))
            if held>0:result[symbol].append(t)
    return result


def funding_reserve(state,spec,notionals,at):
    total=D(0)
    for s,q in state['held'].items():
        if D(q)<=0:continue
        i=spec[s];period=int(i['funding_interval_minutes'])*60000;n=int(i['next_funding_ms'])
        side=next(l['side'] for l in state['_plan']['legs'] if l['symbol']==s)
        rate=numeric(i['funding_upper'] if side=='Buy' else str(-D(i['funding_lower'])),zero=True)
        end=max(at,state['deadline_ms']);known={v['settlement_ms'] for v in state['funding'].values() if v['symbol']==s}
        count=sum(t not in known for t in range(n,end+1,period))
        total+=notionals[s]*rate*count
    return str(total)


class WarmReader:
    """Concurrent raw retrieval, serial journal replay; bounded 2s GET socket I/O."""
    def __init__(self,reader,state):
        self.reader=reader;self.cache={};tasks=[]
        for order in list(state['entries'].values())+list(state['exits'].values()):
            # Closed rows remain immutable; late fee UNKNOWN still needs refresh.
            unknown_fee=any(v['order_id']==order['order_id'] and v['fee_usdt'] is None for v in state['fills'].values())
            if order['terminal'] and D(order['terminal_quantity'])==D(order['filled']) and not unknown_fee:continue
            identity={'orderId':order['order_id']} if order.get('is_native_protection') else {'orderLinkId':order['link']}
            params=dict(category='linear',symbol=order['symbol'],**identity)
            tasks.extend((('/v5/order/realtime',dict(params,limit='50')),('/v5/order/history',dict(params,limit='50')),
                          ('/v5/execution/list',dict(params,limit='100'))))
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            jobs={pool.submit(reader.pages,path,params):(path,params) for path,params in tasks}
            for j in cf.as_completed(jobs):
                path,params=jobs[j];self.cache[(path,digest(params))]=j.result()
        self.skip_terminal=True
    def pages(self,path,params):
        key=(path,digest(params))
        return self.cache[key] if key in self.cache else self.reader.pages(path,params)


def sd_notify(message):
    address=os.environ.get('NOTIFY_SOCKET')
    if not address:return
    if address.startswith('@'):address='\0'+address[1:]
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:s.connect(address);s.sendall(message.encode())


class Supervisor:
    def __init__(self,config):
        self.config=config;self.root=Path(config['runtime_root']);self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.lease=AccountLease(self.root/'account.lock');key,secret=load_bound_credentials(config)
        self.check=platform_verifier(config)
        # No retry, redirect or alternate key; an active guard GET is bounded to 2s.
        wire=lambda method,url,headers,data,timeout:wire_get(method,url,headers,data,2)
        self.reader=EvidenceReader(BybitReadTransport(key,secret,wire=wire),self.root/'raw')
        self.writer=SignedPostOnce(key,secret,self.root/'wire');self.journal=None;self.owner=None;self.spec=None
        if (self.root/'active-plan.json').exists():
            self.bind(json.loads((self.root/'active-plan.json').read_bytes()))
            if (self.root/'owner-go.json').exists():self.owner.recover_go()
            elif self.journal.snapshot()['entries']:raise SourceError('RECOVERY_GO_SOURCE_MISSING')
            recover_without_reentry(self.journal,now_ms())
    def bind(self,dossier,*,create=False):
        if not create and not (self.root/'lifecycle.sqlite').is_file():raise SourceError('RECOVERY_JOURNAL_MISSING')
        self.spec={i['symbol']:i for i in dossier.get('execution_funding_instruments',dossier['instruments'])};self.dossier=dossier
        self.journal=MicroJournal(self.root/'lifecycle.sqlite',dossier['plan'])
        self.owner=PhysicalOwner(self.journal,self.reader,self.lease,self.root,platform_check=self.check,post=self.writer.post)
        self.bridge=MicroAccountBridge(self.journal,self.reader,owner=self.owner)
    def prepare(self):
        if (self.root/'rollback-request.json').exists():raise SourceError('CONTROL_CLOSED_FOR_ROLLBACK')
        if (self.root/'active-plan.json').exists():raise SourceError('ONE_EXPERIMENT_ALREADY_BOUND')
        self.check();cap=capture_account(self.reader)
        cap['response']['physical_config_sha256']=self.config['_config_sha256']
        path=self.root/'captures'/('prepare-'+str(cap['response']['started_ms'])+'.json');pin=publish(path,cap)
        bounds=json.loads((Path(self.config['app_root'])/self.config['bounds_file']).read_bytes())
        d=build_preflight(path,pin,bounds);p=d['plan'];validate_plan(p)
        if d['all_linear_usdt_positions'] or d['all_linear_usdt_open_orders']:raise SourceError('FRESH_ACCOUNT_NOT_FLAT')
        if not d['account_trade_permissions_observed']:raise SourceError('ACCOUNT_PERMISSION_UNKNOWN')
        # Engineering readiness is distinct from exact fixed-price fresh gates and GO.
        d.update(status='KITY_EXECUTION_MICRO_LIVE_PREPARED',actual_current_blocker=None,
            physical_config_sha256=self.config['_config_sha256'],
            writer_identity=self.config['unit']+' PID'+str(os.getpid()),
            static_blockers=[],fresh_only=p['blocked_reasons']+([] if d['common_clock_at_capture']['status']=='OBSERVED_COMMON_2S_PASS' else ['COMMON_2S_BASKET_UNKNOWN']),
            owner_go_template_active=True,owner_go_template_for_future_bound_ready_dossier='GO KITY_EXECUTION_MICRO_LIVE '+p['plan_id'])
        publish(self.root/'prepared'/(p['plan_id']+'.json'),d)
        return dict(status=d['status'],plan_id=p['plan_id'],dossier_path=str(self.root/'prepared'/(p['plan_id']+'.json')),
            gross=d['current_basket_gross_usdt'],fresh_only=d['fresh_only'],broker_writes=0,orders_allowed=False)
    def rehearsal(self,plan_id):
        d=json.loads((self.root/'prepared'/(plan_id+'.json')).read_bytes());p=d['plan'];validate_plan(p)
        if p['plan_id']!=plan_id:raise SourceError('PREPARED_PLAN_PIN_CONFLICT')
        out=[]
        # Dedicated throwaway journal, never the actual runtime ledger or a permit.
        with tempfile.TemporaryDirectory(prefix='no-send-',dir=self.root) as tmp:
            j=MicroJournal(Path(tmp)/'rehearsal.sqlite',p)
            o=PhysicalOwner(j,self.reader,self.lease,Path(tmp),platform_check=self.check,post=self.writer.post)
            for leg in p['legs']:
                sd_notify('WATCHDOG=1')
                try:o.validate_preflight(p,leg['request'],'ENTRY');status='FRESH_PREFLIGHT_PASS_POST_INHIBITED'
                except SourceError as exc:status=str(exc)
                try:o.post_once('/v5/order/create',leg['request'])
                except SourceError as exc:
                    if 'EXACT_OWNER_GO' not in str(exc):raise
                else:raise SourceError('ORDERS_OFF_REHEARSAL_BYPASS')
                out.append(dict(symbol=leg['symbol'],fresh_result=status))
            if j.snapshot()['entries']:raise SourceError('REHEARSAL_CREATED_ACTUAL_INTENT')
            j.close()
        return dict(status='NO_SEND_REHEARSAL_COMPLETE',plan_id=plan_id,legs=out,broker_writes=0,permits_created=0,
            actual_intents_created=0,physical_owner_pid=os.getpid(),static_blockers=[])
    def control(self,x):
        validate_control(x);k=x['kind']
        if k=='PREPARE':return self.prepare()
        if k=='REHEARSE':return self.rehearsal(x['plan_id'])
        if k=='GO':
            if (self.root/'rollback-request.json').exists():raise SourceError('CONTROL_CLOSED_FOR_ROLLBACK')
            if (self.root/'active-plan.json').exists():raise SourceError('ONE_EXPERIMENT_ALREADY_BOUND')
            d=json.loads((self.root/'prepared'/(x['plan_id']+'.json')).read_bytes())
            if (d['plan']['plan_id']!=x['plan_id'] or d.get('fresh_only')
                or d.get('physical_config_sha256')!=self.config['_config_sha256']):raise SourceError('PLAN_BLOCKED')
            self.check()
            # Complete authenticated account/ownership readback before persisting GO.
            ps=rows(self.reader,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
            orders=rows(self.reader,'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
            if any(numeric(v['size'],zero=True)>0 for v in ps) or orders:raise SourceError('GO_ACCOUNT_NOT_FLAT')
            # Account/funding state is fresh source evidence, never new order prices.
            fresh=batch_get(self.reader,[(k+':'+s,path,dict(category='linear',symbol=s))
                for s in (i['symbol'] for i in d['instruments'])
                for k,path in (('t','/v5/market/tickers'),('i','/v5/market/instruments-info'))])
            funding=[]
            for old in d['instruments']:
                symbol=old['symbol'];ts=self.reader.result(fresh['t:'+symbol])['list'];ins=self.reader.result(fresh['i:'+symbol])['list']
                if len(ts)!=1 or len(ins)!=1 or ts[0]['symbol']!=symbol or ins[0]['symbol']!=symbol:
                    raise SourceError('FUNDING_SYMBOL_SOURCE_UNKNOWN')
                if int(ts[0]['nextFundingTime'])<=now_ms() or int(ins[0]['fundingInterval'])<=0:
                    raise SourceError('FUNDING_CALENDAR_UNKNOWN')
                funding.append(dict(old,next_funding_ms=ts[0]['nextFundingTime'],funding_interval_minutes=ins[0]['fundingInterval'],
                    funding_upper=ins[0]['upperFundingRate'],funding_lower=ins[0]['lowerFundingRate']))
            d['execution_funding_instruments']=funding;d['funding_at_go_source_sha256']=digest(fresh)
            publish(self.root/'active-plan.json',d);self.bind(d,create=True);self.owner.accept_go(x['exact_go'])
            return dict(status='EXACT_GO_BOUND_ONE_EXPERIMENT',plan_id=x['plan_id'])
        if not self.journal or self.journal.plan['plan_id']!=x['plan_id']:raise SourceError('ACTIVE_PLAN_REQUIRED')
        self.unwind('OWNER_KILL');return dict(status='OWNED_UNWIND_REQUESTED')
    def unwind(self,reason):
        if self.journal and self.journal.snapshot()['phase']!='TERMINAL':
            at=now_ms();self.journal.append(dict(kind='UNWIND',reason=reason[:256],at_ms=at,
                source_sha256=digest(dict(reason=reason)),event_id='unwind-'+str(at)))
    def funding_and_risk(self):
        state=self.journal.snapshot();held={s for s,q in state['held'].items() if D(q)>0}
        if not held:return
        expected=funding_calendar(state,self.spec)
        if any(expected.values()):
            cash=rows(self.reader,'/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',
                startTime=str(state['first_send_ms']),endTime=str(now_ms()),limit='50'))
            found=set()
            for r in cash:
                pair=(r.get('symbol'),int(r.get('transactionTime','0')))
                if r.get('type')=='SETTLEMENT' and pair[0] in expected:
                    if pair[1] not in expected[pair[0]] or r.get('currency')!='USDT' or signed(r['change'])!=signed(r['funding']):
                        raise SourceError('FUNDING_SOURCE_CONFLICT')
                    record_funding_cash(self.journal,r,now_ms())
                    found.add(pair)
            if found!={(s,t) for s,ts in expected.items() for t in ts}:raise SourceError('FUNDING_CASH_PENDING')
        tasks=[]
        for s in held:
            tasks.extend((('fee:'+s,'/v5/account/fee-rate',dict(category='linear',symbol=s)),
                ('ticker:'+s,'/v5/market/tickers',dict(category='linear',symbol=s)),
                ('inst:'+s,'/v5/market/instruments-info',dict(category='linear',symbol=s))))
        sources=batch_get(self.reader,tasks);fees={}
        for s in held:
            fee=self.reader.result(sources['fee:'+s])['list'];ticker=self.reader.result(sources['ticker:'+s])['list'];i=self.reader.result(sources['inst:'+s])['list']
            if any(len(v)!=1 or v[0]['symbol']!=s for v in (fee,ticker,i)):raise SourceError('RISK_SYMBOL_SOURCE_UNKNOWN')
            spec=self.spec[s]
            if i[0]['fundingInterval']!=spec['funding_interval_minutes']:raise SourceError('FUNDING_CALENDAR_CHANGED')
            n=int(spec['next_funding_ms']);period=int(spec['funding_interval_minutes'])*60000;expected_next=n
            while expected_next<=now_ms():expected_next+=period
            if int(ticker[0]['nextFundingTime'])!=expected_next:raise SourceError('FUNDING_CALENDAR_CHANGED')
            fees[s]=fee[0]['takerFeeRate']
        books=batch_get(self.reader,[(s,'/v5/market/orderbook',dict(category='linear',symbol=s,limit='50')) for s in held])
        state=self.journal.snapshot()
        notionals={s:_vwap(_levels(self.reader.result(books[s])['b' if next(l['side'] for l in self.journal.plan['legs'] if l['symbol']==s)=='Buy' else 'a'],
            next(l['side'] for l in self.journal.plan['legs'] if l['symbol']==s)=='Buy'),D(state['held'][s]))[1] for s in held}
        state=self.journal.snapshot();state['_plan']=self.journal.plan
        reserve=funding_reserve(state,self.spec,notionals,now_ms())
        self.journal.observe_risk(books,fees,funding_reserve_usdt=reserve,now_ms=now_ms())
    def cycle(self):
        if not self.journal or self.journal.snapshot()['phase']=='TERMINAL':return
        self.owner.assert_exclusive(self.journal.plan);errors=[]
        self.journal.actions(now_ms()) # persist deadline before slow network
        try:
            warm=WarmReader(self.reader,self.journal.snapshot());self.bridge.reader=warm
            self.bridge.reconcile_orders()
        except Exception as exc:errors.append('ORDER_READBACK:'+type(exc).__name__)
        finally:self.bridge.reader=self.reader
        # Missing protection unwinds immediately; other proven owned legs remain recoverable.
        try:self.bridge.bind_native_protection()
        except Exception as exc:errors.append('PROTECTION:'+type(exc).__name__)
        try:self.bridge.reconcile_positions()
        except Exception as exc:errors.append('POSITION_READBACK:'+type(exc).__name__)
        try:self.funding_and_risk()
        except Exception as exc:errors.append('RISK_SOURCE:'+type(exc).__name__)
        if errors:self.unwind(';'.join(errors))
        # Try each known-leg recovery independently; unknown one cannot monopolize dispatch.
        excluded=set()
        for _ in range(20):
            actions=self.journal.actions(now_ms())
            if actions and actions[0]['kind']=='FINALITY_READBACK':
                try:self.bridge.finalize_accounting(funding_calendar(self.journal.snapshot(),self.spec))
                except Exception as exc:errors.append('FINALITY_PENDING:'+type(exc).__name__)
                break
            try:r=self.bridge.dispatch_next('GO KITY_EXECUTION_MICRO_LIVE '+self.journal.plan['plan_id'] if self.owner._authorized else None,exclude_symbols=excluded)
            except Exception as exc:
                self.unwind('DISPATCH_PREFLIGHT:'+str(exc));errors.append('DISPATCH:'+str(exc))
                # Isolate the failed leg; continue known exits on every other symbol.
                possible=[a for a in self.journal.actions(now_ms()) if a.get('symbol') not in excluded and a['kind'] in ('EXIT','CANCEL_NATIVE_PROTECTION')]
                if not possible:break
                excluded.add(possible[0]['symbol']);continue
            if r['status']=='ACK_REQUIRES_READBACK' or r['status'] not in ('DISPATCH_UNKNOWN','CANCEL_ACK_REQUIRES_READBACK','CANCEL_UNKNOWN_REQUIRES_READBACK'):
                break
        return errors
    def heartbeat(self,error=None):
        state=self.journal.snapshot() if self.journal else None
        publish(self.root/'heartbeat.json',dict(schema='kity_micro_owner_heartbeat_v1',pid=os.getpid(),at_ms=now_ms(),
            mode='EXACT_GO_SCOPED_MANAGEMENT' if self.owner and self.owner._authorized else 'ORDERS_OFF',
            account_lock_inode=self.lease.inode,active_plan_id=state['plan_id'] if state else None,
            phase=state['phase'] if state else 'NO_ACTIVE_PLAN',state=state,error=error,
            trading_post_attempts=len(list((self.root/'wire').glob('send-*.json')))),exclusive=False)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--config-sha256',required=True);ap.add_argument('--command')
    args=ap.parse_args();raw=Path(args.config).read_bytes()
    if sha(raw)!=args.config_sha256:raise SourceError('CONFIG_PIN_CONFLICT')
    config=json.loads(raw);config.update(_config_path=args.config,_config_sha256=args.config_sha256);runtime=Path(config['runtime_root'])
    if args.command:
        value=validate_control(json.loads(args.command));identifier=str(time.time_ns())
        publish(runtime/'commands'/(identifier+'.json'),value)
        print(json.dumps(dict(status='COMMAND_QUEUED',command_id=identifier,result=str(runtime/'results'/(identifier+'.json')))))
        return
    s=Supervisor(config);s.check();s.heartbeat();sd_notify('READY=1')
    while True:
        sd_notify('WATCHDOG=1');error=None
        for p in sorted((runtime/'commands').glob('*.json')):
            done=runtime/'results'/p.name
            if done.exists():continue
            # Claim before effects: a crash never repeats a GO/PREPARE automatically.
            claim=runtime/'claims'/p.name
            if claim.exists():
                publish(done,dict(status='CONTROL_INTERRUPTED_NOT_RETRIED',orders_allowed=False));continue
            publish(claim,dict(command_sha256=sha(p.read_bytes()),at_ms=now_ms()))
            try:result=s.control(json.loads(p.read_bytes()))
            except Exception as exc:result=dict(status='CONTROL_BLOCKED',reason=str(exc)[:2000],orders_allowed=False)
            publish(done,result)
        try:
            if not s.journal:s.check()
            error=s.cycle()
        except Exception as exc:
            error=type(exc).__name__+':'+str(exc)[:1024]
            s.unwind('SUPERVISOR_FAILURE:'+type(exc).__name__)
        s.heartbeat(error);sd_notify('WATCHDOG=1');time.sleep(1 if s.journal and s.journal.snapshot()['phase']!='TERMINAL' else 3)


if __name__=='__main__':main()
