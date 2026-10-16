"""One complete account readback per entering cycle, serial owned reduction.

All raw pages and their actual account-wide request parameters are retained.
Only the consumer filters rows by an already durable owned ID/link+symbol.
No order/position/book authority, retries, fabricated pages or dispatch here.
"""
import concurrent.futures as cf
from decimal import Decimal
from bot.kity_m3_orders_off import digest
from research_lab.kity_micro_low_latency_v1 import CycleSources,ParallelReadBridge
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError

CONTRACT='ACCOUNT_READBACK_V2'


def account_tasks(first_send_ms):
    if type(first_send_ms) is not int or first_send_ms<=0:raise SourceError('ACCOUNT_READBACK_START_UNKNOWN')
    common=dict(category='linear',settleCoin='USDT',limit='50')
    return dict(open=('/v5/order/realtime',dict(common,openOnly='0')),
        closed=('/v5/order/realtime',dict(common,openOnly='1')),
        history=('/v5/order/history',dict(category='linear',startTime=str(first_send_ms),limit='50')),
        executions=('/v5/execution/list',dict(category='linear',startTime=str(first_send_ms),limit='100')))


class AccountCycleSources(CycleSources):
    def __init__(self,reader,state):
        self.reader=reader;self.captures={};self.groups={};self.account_groups={}
        self.owned=list(state['entries'].values())+list(state['exits'].values())
        active=[]
        for o in self.owned:
            unknown=any(f['order_id']==o['order_id'] and f['fee_usdt'] is None for f in state['fills'].values())
            if not o['terminal'] or Decimal(o['terminal_quantity'])!=Decimal(o['filled']) or unknown:active.append(o)
        self.tasks=account_tasks(state['first_send_ms']) if active else {}
        jobspec=[('pages',name,path,p) for name,(path,p) in self.tasks.items()]
        metadata=[('/v5/account/fee-rate',dict(category='linear'))]
        for symbol in state['entries']:
            metadata.extend((path,dict(category='linear',symbol=symbol)) for path in (
                '/v5/market/tickers','/v5/market/instruments-info'))
        jobspec.extend(('get',digest(dict(path=path,params=p)),path,p) for path,p in metadata)
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            jobs={pool.submit(getattr(reader,kind),path,p):(kind,key) for kind,key,path,p in jobspec}
            for job in cf.as_completed(jobs):
                kind,key=jobs[job]
                (self.account_groups if kind=='pages' else self.captures)[key]=job.result()

    def pages(self,path,params):
        # Discovery and complete live position/open-order custody retain their
        # original fresh GETs. Only lookups of a durable owned order are shared.
        identity=next((k for k in ('orderId','orderLinkId') if k in params),None)
        owned=identity and any(o['symbol']==params.get('symbol') and
            params[identity]==o['order_id' if identity=='orderId' else 'link'] for o in self.owned)
        if not owned or not self.account_groups or set(params)!={'category','symbol',identity,'limit'}:
            return self.reader.pages(path,params)
        names={'/v5/order/realtime':('open','closed'),'/v5/order/history':('history',),
            '/v5/execution/list':('executions',)}.get(path)
        if not names:return self.reader.pages(path,params)
        expected_limit='100' if path=='/v5/execution/list' else '50'
        if params['category']!='linear' or params['limit']!=expected_limit:
            raise SourceError('ACCOUNT_READBACK_CONSUMER_SCOPE')
        groups=[self.account_groups[n] for n in names]
        return dict(source_contract=CONTRACT,requested_params=dict(params),
            actual_requests=[dict(endpoint=self.tasks[n][0],params=self.tasks[n][1]) for n in names],
            pages=[cap for group in groups for cap in group['pages']],
            complete=all(g.get('complete') is True for g in groups))


class AccountReadBridge(ParallelReadBridge):
    def _rows(self,path,params):
        group=self.reader.pages(path,params)
        if group.get('source_contract')!=CONTRACT:
            # Avoid asking the reader for the same non-shared source twice.
            return self._actual_rows(group)
        if group.get('requested_params')!=params:raise SourceError('ACCOUNT_READBACK_SELECTION_CONFLICT')
        rows=self._actual_rows(group)
        identity=next(k for k in ('orderId','orderLinkId') if k in params)
        selected=[]
        for row in rows:
            if row.get(identity)!=params[identity]:continue
            if row.get('symbol')!=params['symbol']:raise SourceError('ACCOUNT_READBACK_OWNED_SYMBOL_CONFLICT')
            selected.append(row)
        return selected

    @staticmethod
    def _actual_rows(group):
        if group.get('complete') is not True:raise SourceError('ORDER_HISTORY_OR_EXECUTIONS_INCOMPLETE')
        allowed={(v['endpoint'],digest(v['params'])) for v in group.get('actual_requests',[])}
        rows=[]
        for cap in group['pages']:
            if group.get('source_contract')==CONTRACT:
                source=(cap.get('endpoint'),digest({k:v for k,v in cap.get('params',{}).items() if k!='cursor'}))
                if cap.get('method')!='GET' or source not in allowed:
                    raise SourceError('ACCOUNT_READBACK_ACTUAL_SOURCE_CONFLICT')
            result=BybitReadTransport.result(cap)
            if group.get('source_contract')==CONTRACT and result.get('category')!='linear':
                raise SourceError('ACCOUNT_READBACK_CATEGORY_CONFLICT')
            if not isinstance(result.get('list'),list):raise SourceError('INVALID_READBACK_LIST')
            if any(not isinstance(row,dict) for row in result['list']):raise SourceError('INVALID_READBACK_ROW')
            rows.extend(result['list'])
        return rows
