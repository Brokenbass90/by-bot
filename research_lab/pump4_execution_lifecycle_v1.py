"""PUMP4 V1 durable ORDERS_OFF Bybit lifecycle. No network/credentials/GO.

Produces concrete order/create requests for the future separately authorized
owner. Observations are caller-supplied, not authenticated account evidence.
Reserving an action is a durable uncertainty barrier, never proof of dispatch.
Reuse existing lease, immutable publication and hash-chain storage. No KITY
policy, account ownership, runtime or financial permission is imported.
"""
from decimal import Decimal as D
import json
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.kity_micro_physical_owner_v1 import AccountLease, publish
from research_lab.pump4_execution_plan_v1 import HOUR_MS, frozen_sources
from research_lab.pump4_native_stop_v1 import verify_mapping
from research_lab.pump4_entry_binding_v1 import verify_binding

DOMAIN='PUMP4_BYBIT_EXECUTION_ORDERS_OFF_V1'
TERMINAL={'Filled','Cancelled','Rejected','Deactivated','PartiallyFilledCanceled'}
ACTIVE={'New','PartiallyFilled','Untriggered','Triggered'}


def need(ok,reason):
    if not ok:raise ValueError('PUMP4_EXECUTION_'+reason)


def number(value,*,zero=False):
    need(isinstance(value,(str,int,float)) and not isinstance(value,bool),'NUMBER')
    n=D(str(value));need(n.is_finite() and (n>=0 if zero else n>0),'NUMBER')
    return n


class Pump4Lifecycle:
    """One original plan, one position, no re-entry or exposure adoption.

    A future owner must bind authenticated complete GET captures, exact account,
    global single-writer ownership, risk/fee/funding policy and send-once gateway.
    This module deliberately cannot activate that authority or spend money.
    """
    def __init__(self,root,plan,*,qty,qty_step,min_qty,min_notional,tick_size,native_stop_mapping=None,entry_binding=None):
        self.root=Path(root).absolute()
        need('..' not in self.root.parts and not any(p.is_symlink() for p in (self.root,*self.root.parents)),'ROOT_CUSTODY')
        frozen_sources()
        need(plan['schema']=='PUMP4_V1_REFERENCE_EXECUTION_PLAN_V1'
            and plan['plan_sha256']==digest({k:v for k,v in plan.items() if k!='plan_sha256'})
            and plan['source_pins']==frozen_sources() and plan['fractions']==[.4,.6]
            and plan['hold_bars']==168 and plan['stop_checked_first'] is True
            and plan['orders_allowed'] is False and plan['money_authority'] is False,'FROZEN_PLAN')
        q,step,mq,mn,tick=map(number,(qty,qty_step,min_qty,min_notional,tick_size))
        need(q%step==0 and q*D('.4')%step==0 and q*D('.6')%step==0
            and min(q*D('.4'),q*D('.6'))>=mq and q*number(plan['entry'])>=mn,'LOT_40_60_OR_MINIMUM')
        if native_stop_mapping is None:need(number(plan['stop'])%tick==0,'STOP_TICK_UNREPRESENTABLE')
        else:verify_mapping(plan,tick_size,native_stop_mapping)
        self.config=dict(domain=DOMAIN,plan=plan,qty=str(q),qty_step=str(step),min_qty=str(mq),
            min_notional=str(mn),tick_size=str(tick),orders_allowed=False,money_authority=False)
        if native_stop_mapping is not None:self.config['native_stop_mapping']=json.loads(json.dumps(native_stop_mapping))
        if entry_binding is not None:
            verify_binding(plan,entry_binding,now_ms=entry_binding['observed_ms'])
            need(number(entry_binding['native_stop'])==number(native_stop_mapping['native_stop'] if native_stop_mapping is not None else plan['stop']),'ENTRY_NATIVE_BINDING')
            self.config['entry_binding']=json.loads(json.dumps(entry_binding))
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        p=self.root/'execution-config.json'
        try:publish(p,self.config)
        except FileExistsError:need(json.loads(p.read_bytes())==self.config,'CONFIG_CONFLICT')
        self.journal=LifecycleJournal(self.root/'execution.jsonl')
        self.observations=LifecycleJournal(self.root/'observations.jsonl')

    @classmethod
    def resume(cls,root):
        c=json.loads((Path(root)/'execution-config.json').read_bytes())
        return cls(root,c['plan'],**{k:c[k] for k in ('qty','qty_step','min_qty','min_notional','tick_size')},
            **{k:c[k] for k in ('native_stop_mapping','entry_binding') if k in c})

    def check_entry(self,observation,now_ms):
        p=self.config['plan'];price=number(observation['price']);stored=self.config.get('entry_binding')
        intended=number(self.config['native_stop_mapping']['native_stop'] if 'native_stop_mapping' in self.config else p['stop'])
        if stored is None:
            need(p['entry_bar_open_ms']<=now_ms<=p['entry_bar_open_ms']+5000,'NEXT_OPEN_WINDOW')
            need(price==number(p['entry']),'NEXT_OPEN_PRICE_CONFLICT')
        else:
            fresh=observation.get('entry_binding');need(isinstance(fresh,dict),'FRESH_ENTRY_BINDING_REQUIRED')
            verify_binding(p,fresh,now_ms=now_ms)
            need(fresh['policy_sha256']==stored['policy_sha256'] and fresh['valid_until_ms']==stored['valid_until_ms']
                and number(fresh['native_stop'])==intended and number(fresh['last_price'])==price,'ENTRY_BINDING_CONFLICT')
        need(price<intended if p['side']=='short' else intended<price,'NATIVE_TRIGGER_GEOMETRY')

    def _events(self):
        rows=self.journal.read();pin=digest(self.config)
        for i,e in enumerate(rows):
            need(e['domain']==DOMAIN and e['config_sha256']==pin and e['kind']=='RESERVED_ACTION'
                and e['event_id']=='pump4-action-'+pin[:20]+'-'+str(i),'JOURNAL_DOMAIN')
        return rows

    def requests(self):return [e['request'] for e in self._events()]

    def _result(self,status,**values):
        return dict(status=status,request=None,orders_allowed=False,money_authority=False,tiny_ready=False,
            observation_provenance='CALLER_PROVIDED_NOT_ACCOUNT_AUTHENTICATION',**values)

    def advance(self,observation,*,now_ms):
        """Validate complete cumulative observations and fsync next action.

        A prepared CID with no exchange record is reconciliation-only forever:
        absence does not prove an order was never submitted. A later terminal
        partial may create a new CID for only the proven remaining quantity.
        """
        lease=AccountLease(self.root/'execution.lock')
        try:
            lease.assert_held();return self._advance(observation,now_ms)
        finally:lease.close()

    def _advance(self,o,now):
        c=self.config;p=c['plan'];events=self._events();short=p['side']=='short'
        mapping=c.get('native_stop_mapping')
        if mapping is not None:verify_mapping(p,c['tick_size'],mapping)
        intended=number(mapping['native_stop']) if mapping is not None else number(p['stop'])
        def accepted_stop(value):
            stop=number(value)
            return stop==intended if mapping is not None else (stop<=intended if short else stop>=intended)
        need(type(now) is int and o['schema']=='PUMP4_BYBIT_OBSERVATION_V1'
            and type(o['source_ms']) is int and type(o['observed_ms']) is int
            and 0<=now-o['source_ms']<=5000 and o['source_ms']<=o['observed_ms']<=now
            and o['pagination_complete'] is True,'FRESH_COMPLETE_SNAPSHOT')
        need(o['symbol']==p['symbol'] and o['positionIdx']==0
            and o['position_side']==('Sell' if short else 'Buy'),'POSITION_IDENTITY')
        held=number(o['held_qty'],zero=True);price=number(o['price'])
        orders=o['orders'];fills=o['executions']
        need(isinstance(orders,list) and isinstance(fills,list),'OBSERVATION_SCHEMA')
        bycid={};fillids=set();orderids=set()
        for row in orders:
            need(row['orderLinkId'] not in bycid and row['orderId'] not in orderids,'DUPLICATE_ORDER')
            bycid[row['orderLinkId']]=row;orderids.add(row['orderId'])
        requests={e['request']['orderLinkId']:e for e in events}
        need(set(bycid)<=set(requests),'FOREIGN_ORDER')
        history=self.observations.read();stops=set();previous=None
        for e in history:
            need(e['domain']==DOMAIN and e['config_sha256']==digest(c)
                and e['kind']=='OBSERVATION' and e['event_id']=='pump4-observation-'+digest(e['observation']),
                'OBSERVATION_DOMAIN')
            previous=e['observation']
            if e['verified_native_stop_id']:stops.add(e['verified_native_stop_id'])
        if previous:
            need(now>=previous['observed_ms'],'OBSERVATION_CLOCK_REVERSED')
            known_fills={f['execId']:f for f in previous['executions']}
            current_fills={f['execId']:f for f in fills}
            need(all(current_fills.get(k)==v for k,v in known_fills.items()),'EXECUTION_HISTORY_REWRITTEN')
            current_orders={r['orderLinkId']:r for r in orders}
            for old in previous['orders']:
                new=current_orders.get(old['orderLinkId'])
                need(new is not None and all(new[k]==old[k] for k in
                    ('orderId','orderLinkId','symbol','side','qty','reduceOnly','positionIdx')),'ORDER_HISTORY_REWRITTEN')
                need(number(new['cumExecQty'],zero=True)>=number(old['cumExecQty'],zero=True)
                    and (old['orderStatus'] not in TERMINAL or new==old),'ORDER_TERMINAL_REWRITTEN')
            current_funding={r['id']:r for r in o['funding']}
            need(all(current_funding.get(r['id'])==r for r in previous['funding']),'FUNDING_HISTORY_REWRITTEN')
        # The hash-chain snapshot preserves known native IDs across a restart.
        native=o['native_stop']
        if native:
            need(native['symbol']==p['symbol'] and native['side']==('Buy' if short else 'Sell')
                and native['positionIdx']==0 and native['stopOrderType']=='StopLoss','NATIVE_STOP_IDENTITY')
            if (held>0 and native['orderStatus']=='Untriggered'
                and number(native['qty'],zero=True)==held
                and accepted_stop(native['triggerPrice'])):
                stops.add(native['orderId'])
        entry=D(0);exit_qty=D(0);fee=D(0);fees_known=True;percid={cid:D(0) for cid in requests}
        for fill in fills:
            need(fill['execId'] not in fillids,'DUPLICATE_EXECUTION');fillids.add(fill['execId'])
            need(fill['symbol']==p['symbol'],'EXECUTION_SYMBOL')
            q=number(fill['execQty']);number(fill['execPrice'])
            cid=fill['orderLinkId'];known=requests.get(cid)
            if known:
                need(cid in bycid and fill['orderId']==bycid[cid]['orderId']
                    and fill['side']==known['request']['side'],'EXECUTION_OWNERSHIP')
                percid[cid]+=q
                if known['role']=='ENTRY':entry+=q
                else:exit_qty+=q
            else:
                need(fill['orderId'] in stops and fill['side']==('Buy' if short else 'Sell'),'FOREIGN_EXECUTION')
                exit_qty+=q
            if fill.get('feeCurrency')!='USDT' or fill.get('execFee') is None:fees_known=False
            else:
                value=D(str(fill['execFee']));need(value.is_finite(),'FEE_NUMBER');fee+=value
        for cid,e in requests.items():
            row=bycid.get(cid)
            if not row:
                need(percid[cid]==0,'FILL_WITHOUT_ORDER');continue
            req=e['request']
            need(row['symbol']==req['symbol'] and row['side']==req['side']
                and row['positionIdx']==0 and row['reduceOnly'] is req['reduceOnly']
                and number(row['qty'])==number(req['qty']),'ORDER_REQUEST_CONFLICT')
            amount=number(row['cumExecQty'],zero=True)
            need(amount==percid[cid] and amount<=number(req['qty'])
                and row['orderStatus'] in TERMINAL|ACTIVE,'EXECUTION_TOTAL_OR_STATUS')
        need(entry<=number(c['qty']) and exit_qty<=entry and held==entry-exit_qty,'POSITION_RECONCILIATION')
        funding=o['funding'];ids=set();funding_sum=D(0)
        for row in funding:
            need(row['id'] not in ids and row['currency']=='USDT','FUNDING_IDENTITY');ids.add(row['id'])
            value=D(str(row['amount']));need(value.is_finite(),'FUNDING_NUMBER');funding_sum+=value
        protected=False
        if held:
            if native and native['orderStatus']=='Untriggered' and number(native['qty'],zero=True)==held:
                stop=number(native['triggerPrice']);protected=accepted_stop(native['triggerPrice'])
        # Preserve validated financial facts even when protection prevents action.
        # Unverified stop IDs are retained as evidence but never trusted for fills.
        self.observations.append(dict(schema_id=SCHEMA,event_id='pump4-observation-'+digest(o),
            domain=DOMAIN,config_sha256=digest(c),kind='OBSERVATION',observation=o,
            verified_native_stop_id=native['orderId'] if protected else None))
        if held:
            if not protected:return self._result('NATIVE_PROTECTION_UNKNOWN')
            if (price>=stop if short else price<=stop):return self._result('NATIVE_STOP_TRIGGER_WAIT')
        pending=[e for e in events if e['request']['orderLinkId'] not in bycid
            or bycid[e['request']['orderLinkId']]['orderStatus'] not in TERMINAL]
        if pending:
            status='ENTRY_PENDING_PROTECTED' if held and all(e['role']=='ENTRY' for e in pending) else 'RECONCILE_ONLY'
            return self._result(status)
        if events and not held:
            done=o['costs_complete'] is True and fees_known
            return self._result('FLAT_COSTS_RECONCILED_ORDERS_OFF' if done else 'FLAT_COSTS_PENDING',
                actual_fees_usdt=str(fee) if fees_known else None,funding_usdt=str(funding_sum),
                finality_provenance='CALLER_DECLARED_NOT_BROKER_FINALITY')
        if not events:
            self.check_entry(o,now)
            role='ENTRY';qty=number(c['qty'])
        else:
            role=None;qty=D(0)
            if now>=p['entry_bar_open_ms']+p['hold_bars']*HOUR_MS:role='TIME_EXIT';qty=held
            else:
                if entry*D('.4')%number(c['qty_step']) or min(entry*D('.4'),entry*D('.6'))<number(c['min_qty']):
                    return self._result('PARTIAL_SPLIT_UNREPRESENTABLE')
                tp1=sum((percid[e['request']['orderLinkId']] for e in events if e['role']=='TP1'),D(0))
                target=entry*D('.4')
                if tp1<target and (price<=number(p['targets'][0]) if short else price>=number(p['targets'][0])):
                    role='TP1';qty=target-tp1
                elif tp1==target and (price<=number(p['targets'][1]) if short else price>=number(p['targets'][1])):
                    role='TP2';qty=held
            if role is None:return self._result('PROTECTED_WAIT')
        need(qty>0 and qty%number(c['qty_step'])==0 and (role=='ENTRY' or qty<=held),'REQUEST_QUANTITY')
        cid='p4-'+digest(self.config)[:20]+'-'+str(len(events))
        request=dict(category='linear',symbol=p['symbol'],side=('Sell' if short else 'Buy') if role=='ENTRY' else ('Buy' if short else 'Sell'),
            orderType='Market',qty=str(qty),positionIdx=0,reduceOnly=role!='ENTRY',orderLinkId=cid)
        if role=='ENTRY':request.update(stopLoss=mapping['native_stop'] if mapping is not None else str(p['stop']),slTriggerBy='LastPrice',tpslMode='Full')
        event=dict(schema_id=SCHEMA,event_id='pump4-action-'+digest(self.config)[:20]+'-'+str(len(events)),
            domain=DOMAIN,config_sha256=digest(self.config),kind='RESERVED_ACTION',role=role,request=request,
            observed_ms=now,observation_sha256=digest(o),native_stop_id=native['orderId'] if native else None)
        self.journal.append(event)
        result=self._result('ACTION_RESERVED_ORDERS_OFF',role=role)
        result['request']=request;return result
