"""Micro journal <-> existing single physical account owner adapter.

No credentials, HTTP writer, daemon or default owner. The real owner must supply
assert_exclusive(plan), validate_preflight(plan,request,role) and post_once().
These are code integration interfaces, NOT boolean readiness attestations.
Until the reviewed physical handoff/integration exists, dispatch is unbound.
"""
from decimal import Decimal
import time

from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import BASKET,signed,numeric
from research_lab.kity_execution_micro_bybit_v1 import execution_event,order_events
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError


class MicroAccountBridge:
    def __init__(self,journal,reader,*,owner=None,clock=None):
        self.journal,self.reader,self.owner=journal,reader,owner
        self.clock=clock or (lambda:time.time_ns()//1_000_000)

    def dispatch_next(self,exact_go=None):
        """Delegate at most ONE call to an already exclusive physical owner.

        Exact GO is required for entry. Owned emergency recovery does not depend
        on a second owner answer after a fill/restart. Fresh entry gates belong
        to the physical owner; exits retain scoped ownership without entry gates.
        """
        if self.owner is None:raise SourceError('PHYSICAL_OWNER_UNBOUND')
        plan=self.journal.plan;self.owner.assert_exclusive(plan)
        actions=self.journal.actions(self.clock())
        if not actions:return dict(status='TERMINAL',orders_allowed=False)
        action=next((a for a in actions if a['kind']=='EXIT'),actions[0])
        if action['kind'] not in ('ENTRY','EXIT','CANCEL_NATIVE_PROTECTION'):
            return dict(status=action['kind'],action=action,orders_allowed=False)
        role=action['kind'];request=dict(action['request']);symbol=action['symbol']
        if role=='ENTRY' and exact_go!='GO KITY_EXECUTION_MICRO_LIVE '+plan['plan_id']:
            raise SourceError('EXACT_OWNER_GO_REQUIRED')
        self.owner.validate_preflight(plan,request,role)
        at=self.clock();pin=digest(request)
        if role=='CANCEL_NATIVE_PROTECTION':
            self.journal.append(dict(kind='NATIVE_CANCEL_INTENT',symbol=symbol,
                order_link_id=action['order_link_id'],at_ms=at,source_sha256=pin,
                event_id='cancel-intent-'+action['order_link_id']))
            try:
                response=self.owner.post_once('/v5/order/cancel',request)
                if (type(response.get('retCode')) is not int or response['retCode']!=0
                    or response.get('result',{}).get('orderId')!=request['orderId']):
                    raise SourceError('CANCEL_ACK_UNKNOWN')
            except Exception as exc:
                return dict(status='CANCEL_UNKNOWN_REQUIRES_READBACK',reason=type(exc).__name__,orders_allowed=False)
            return dict(status='CANCEL_ACK_REQUIRES_READBACK',orders_allowed=False)
        event=dict(kind=role+'_INTENT',symbol=symbol,at_ms=at,source_sha256=pin,
                   event_id='send-intent-'+request['orderLinkId'])
        if role=='EXIT':event['quantity']=action['quantity']
        if not self.journal.append(event):  # durable BEFORE the one possible physical call
            return dict(status='RECONCILE',orders_allowed=False)
        try:
            response=self.owner.post_once('/v5/order/create',request)
            result=response.get('result',{})
            if (type(response.get('retCode')) is not int or response['retCode']!=0
                or not isinstance(result.get('orderId'),str) or not result['orderId']
                or result.get('orderLinkId')!=request['orderLinkId']):
                raise SourceError('ACK_UNKNOWN_OR_CONFLICTING')
            self.journal.append(dict(kind=role+'_ACK',symbol=symbol,order_link_id=request['orderLinkId'],
                order_id=result['orderId'],at_ms=self.clock(),source_sha256=digest(response),
                event_id='ack-'+request['orderLinkId']))
        except Exception as exc:
            self.journal.append(dict(kind='DISPATCH_UNKNOWN',symbol=symbol,
                order_link_id=request['orderLinkId'],at_ms=self.clock(),source_sha256=pin,
                event_id='unknown-'+request['orderLinkId']))
            return dict(status='DISPATCH_UNKNOWN',reason=type(exc).__name__,orders_allowed=False)
        return dict(status='ACK_REQUIRES_READBACK',order_link_id=request['orderLinkId'],orders_allowed=False)

    def _rows(self,path,params):
        group=self.reader.pages(path,params)
        if group.get('complete') is not True:raise SourceError('ORDER_HISTORY_OR_EXECUTIONS_INCOMPLETE')
        rows=[]
        for cap in group['pages']:
            result=BybitReadTransport.result(cap)
            if not isinstance(result.get('list'),list):raise SourceError('INVALID_READBACK_LIST')
            rows.extend(result['list'])
        return rows

    def reconcile_orders(self):
        """Always consult realtime AND history AND execution pages, never resend."""
        try:return self._reconcile_orders()
        except (ValueError,TypeError,ArithmeticError) as exc:
            if self.journal.snapshot()['phase']!='TERMINAL':
                self.journal.append(dict(kind='UNWIND',reason='ORDER_READBACK_CONFLICT_OR_UNKNOWN',
                    at_ms=self.clock(),source_sha256=digest(dict(reason=type(exc).__name__)),
                    event_id='readback-conflict-'+str(self.clock())))
            raise

    def _reconcile_orders(self):
        if self.reader is None:raise SourceError('AUTHENTICATED_READER_UNBOUND')
        original=self.journal.snapshot()
        orders=list(original['entries'].values())+list(original['exits'].values())
        matched=0
        for order in orders:
            symbol,link=order['symbol'],order['link']
            params=dict(category='linear',symbol=symbol,orderLinkId=link,limit='100')
            realtime=self._rows('/v5/order/realtime',dict(params,limit='50'))
            history=self._rows('/v5/order/history',dict(params,limit='50'))
            executions=self._rows('/v5/execution/list',params)
            pending_terminal=[]
            for row in realtime+history:
                state=self.journal.snapshot()
                normalized=order_events(self.journal.plan,state,row,observed_ms=self.clock())
                if link in {v['link'] for v in state['entries'].values()}:
                    leg=next(l for l in self.journal.plan['legs'] if l['symbol']==symbol)
                    if (Decimal(row.get('price','NaN'))!=Decimal(leg['request']['price'])
                        or row.get('timeInForce')!='IOC'):
                        raise SourceError('EXACT_ENTRY_PRICE_OR_TIF_CONFLICT')
                self.journal.append(normalized[0]);pending_terminal.extend(normalized[1:]);matched+=1
            for row in executions:
                e=execution_event(self.journal.plan,self.journal.snapshot(),row,observed_ms=self.clock())
                self.journal.append(e)
            # Terminal cumulative quantities never invent their execution rows.
            for e in pending_terminal:self.journal.append(e)
        return dict(status='ORDER_EXECUTION_RECONCILED',matched_order_rows=matched,
                    owned_orders=len(orders),state=self.journal.snapshot(),orders_allowed=False)

    def reconcile_positions(self):
        """Complete linear-USDT readback; foreign same-symbol quantity is conflict."""
        positions=self._rows('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
        orders=self._rows('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
        scoped={s:'0' for s,_ in BASKET};seen=set();links=[]
        for row in positions:
            symbol=row.get('symbol')
            if symbol not in scoped:continue
            if symbol in seen or type(row.get('positionIdx')) is not int or row['positionIdx']!=0:
                raise SourceError('ONE_WAY_POSITION_IDENTITY_CONFLICT')
            seen.add(symbol);size=numeric(row.get('size'),zero=True)
            if size and row.get('side') not in ('Buy','Sell'):raise SourceError('POSITION_SIDE_UNKNOWN')
            scoped[symbol]=str(size*(-1 if row.get('side')=='Sell' else 1))
        known_native={v['order_id']:v for v in self.journal.snapshot()['exits'].values() if v.get('is_native_protection')}
        for row in orders:
            if row.get('symbol') in scoped:
                # Empty link on a foreign/native order cannot look like no order.
                native=known_native.get(row.get('orderId'))
                if native and native['symbol']!=row['symbol']:raise SourceError('NATIVE_PROTECTION_SYMBOL_CONFLICT')
                links.append(native['link'] if native else row.get('orderLinkId') or 'UNOWNED-BROKER-ID-'+str(row.get('orderId')))
        at=self.clock();source=digest(dict(positions=positions,orders=orders))
        self.journal.append(dict(kind='BROKER_SNAPSHOT',positions=scoped,open_order_links=links,
            at_ms=at,source_sha256=source,event_id='positions-'+digest(dict(source=source,at=at))))
        return self.journal.snapshot()

    def bind_native_protection(self):
        """Discover exact attached SLs only inside exclusive clean symbol custody.

        The physical owner must have excluded other writers before entry. A
        symbol/price resemblance by itself does not establish that custody.
        """
        if self.owner is None:raise SourceError('PHYSICAL_OWNER_UNBOUND')
        self.owner.assert_exclusive(self.journal.plan)
        try:return self._bind_native_protection()
        except (ValueError,TypeError,ArithmeticError) as exc:
            self.journal.append(dict(kind='UNWIND',reason='NATIVE_PROTECTION_SOURCE_UNKNOWN',
                at_ms=self.clock(),source_sha256=digest(dict(reason=type(exc).__name__)),
                event_id='native-source-unknown-'+str(self.clock())))
            return self.journal.snapshot()

    def _bind_native_protection(self):
        state=self.journal.snapshot()
        for leg in self.journal.plan['legs']:
            symbol=leg['symbol'];entry=state['entries'].get(symbol);req=leg['request']
            if (not entry or Decimal(state['held'][symbol])<=0
                or Decimal(entry['protected'])==Decimal(state['held'][symbol])
                or (state['entry_blocked'] and entry['stop_id'] is not None)):
                continue
            if not req.get('stopLoss') or not entry['terminal'] or Decimal(entry['terminal_quantity'])!=Decimal(entry['filled']):
                continue
            params=dict(category='linear',symbol=symbol,limit='50')
            rows=self._rows('/v5/order/realtime',params)+self._rows('/v5/order/history',dict(params,startTime=str(state['first_send_ms'])))
            candidates={}
            for row in rows:
                if (row.get('symbol')==symbol and row.get('stopOrderType')=='StopLoss'
                    and row.get('orderType')=='Market' and row.get('reduceOnly') is True
                    and type(row.get('positionIdx')) is int and row['positionIdx']==0
                    and row.get('side')==('Sell' if leg['side']=='Buy' else 'Buy')
                    and row.get('orderLinkId') in ('',None)
                    and Decimal(row.get('triggerPrice','NaN'))==Decimal(req['stopLoss'])
                    and numeric(row.get('qty'))==Decimal(state['held'][symbol])
                    and str(row.get('createdTime','')).isdecimal()
                    and state['first_send_ms']<=int(row['createdTime'])<=self.clock()
                    and isinstance(row.get('orderId'),str) and row['orderId']):
                    candidates[row['orderId']]=row
            if len(candidates)!=1:
                self.journal.append(dict(kind='UNWIND',reason='NATIVE_PROTECTION_NOT_UNAMBIGUOUS',
                    at_ms=self.clock(),source_sha256=digest(rows),event_id='protection-unknown-'+symbol+'-'+str(self.clock())))
                continue
            row=next(iter(candidates.values()))
            self.journal.append(dict(kind='NATIVE_PROTECTION_BIND',symbol=symbol,order_id=row['orderId'],
                quantity=row['qty'],trigger_price=row['triggerPrice'],side=row['side'],reduce_only=True,position_idx=0,
                at_ms=self.clock(),source_sha256=digest(row),event_id='native-bind-'+row['orderId']))
        return self.journal.snapshot()

    def finalize_accounting(self,expected_settlements):
        """Close only actual owned transaction rows after proven flat/readback.

        expected_settlements is supplied by the physical owner's source-bound
        entry/exit funding calendar, not inferred from an empty transaction page.
        The unbound bridge never invents that calendar or finality automatically.
        """
        if self.owner is None:raise SourceError('PHYSICAL_OWNER_UNBOUND')
        self.owner.assert_exclusive(self.journal.plan)
        state=self.reconcile_positions()
        if not state['broker_flat_proven']:raise SourceError('BROKER_FLAT_NOT_PROVEN')
        symbols={v['symbol'] for v in state['fills'].values() if v['kind']=='ENTRY_FILL'}
        if not symbols or not isinstance(expected_settlements,dict) or set(expected_settlements)!=symbols:
            raise SourceError('FUNDING_CALENDAR_SOURCE_REQUIRED')
        expected={(s,t) for s,ts in expected_settlements.items() for t in ts}
        if any(type(t) is not int or t<=state['first_send_ms'] or t>self.clock() for _,t in expected):
            raise SourceError('FUNDING_CALENDAR_CLOCK_CONFLICT')
        rows=self._rows('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',
            startTime=str(state['first_send_ms']),endTime=str(self.clock()),limit='50'))
        unique={}
        for row in rows:
            identifier=row.get('id')
            if not isinstance(identifier,str) or not identifier:raise SourceError('CASH_ROW_ID_UNKNOWN')
            if identifier in unique and unique[identifier]!=row:raise SourceError('CASH_ROW_ID_CONFLICT')
            unique[identifier]=row
        net=Decimal(0);own_ids={v['order_id'] for v in state['fills'].values()}
        for xid,fill in state['fills'].items():
            matched=[r for r in unique.values() if r.get('type')=='TRADE' and r.get('tradeId')==xid]
            if not matched:raise SourceError('OWNED_EXECUTION_CASH_SOURCE_MISSING')
            for r in matched:
                if (r.get('orderId')!=fill['order_id'] or r.get('symbol')!=fill['symbol']
                    or r.get('currency')!='USDT' or r.get('category')!='linear'):
                    raise SourceError('OWNED_CASH_IDENTITY_CONFLICT')
            if (sum((numeric(r.get('qty')) for r in matched),Decimal(0))!=Decimal(fill['quantity'])
                or fill['fee_usdt'] is None
                or sum((signed(r.get('fee')) for r in matched),Decimal(0))!=Decimal(fill['fee_usdt'])):
                raise SourceError('OWNED_CASH_QUANTITY_OR_FEE_CONFLICT')
            net+=sum((signed(r.get('change')) for r in matched),Decimal(0))
        observed=set()
        for row in unique.values():
            if row.get('type')=='TRADE' and row.get('orderId') in own_ids and row.get('tradeId') not in state['fills']:
                raise SourceError('UNRECONCILED_OWNED_EXECUTION_CASH')
            if row.get('type')=='SETTLEMENT' and row.get('symbol') in symbols:
                t=int(row.get('transactionTime','0'));pair=(row['symbol'],t)
                if pair not in expected or pair in observed or row.get('currency')!='USDT' or row.get('category')!='linear':
                    raise SourceError('FUNDING_IDENTITY_OR_CALENDAR_CONFLICT')
                amount=signed(row.get('funding'))
                if amount!=signed(row.get('change')):raise SourceError('FUNDING_CASH_SOURCE_CONFLICT')
                self.journal.append(dict(kind='FUNDING_CASH',symbol=row['symbol'],settlement_id=row['id'],
                    settlement_ms=t,cash_usdt=str(amount),at_ms=self.clock(),source_sha256=digest(row),
                    event_id='funding-'+digest(row)))
                observed.add(pair);net+=amount
        if observed!=expected:raise SourceError('FUNDING_CASH_SOURCE_MISSING')
        self.journal.append(dict(kind='FINALITY',funding_complete=True,net_cash_usdt=str(net),
            at_ms=self.clock(),source_sha256=digest(rows),event_id='finality-'+digest(rows)))
        return self.journal.snapshot()
