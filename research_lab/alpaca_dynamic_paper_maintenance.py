"""PAPER-only upkeep of one existing Dynamic intent using native bridge helpers.

Caller holds the original broker account writer lock. No new entry/ranking,
LIVE endpoint, account-wide flatten, risk tuning or fee-finality assumption.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from research_lab.alpaca_dynamic_paper import PAPER,_plan_check,_store,_save,result
from research_lab.alpaca_dynamic_v1 import digest,positive,instant,dec
from scripts import equities_alpaca_paper_bridge as bridge


def rearm_cid(parent,account,session):
    return 'dyr-'+digest({'parent':parent,'paper_account':account,'session':session})[:32]


def unwind_cid(parent,account):
    return 'dyu-'+digest({'parent':parent,'paper_account':account})[:32]


def _exit_observation(client,item,record,now_ms):
    """Read only the native stop/dispatch IDs; flatness never invents a fill."""
    symbol=item['plan']['symbol'];rows={}
    cids=[item['stop_cid'],*[x['cid'] for x in item.get('rearms',{}).values()]]
    if item.get('unwind_dispatched'):cids.append(unwind_cid(item['plan']['receipt_id'],item['account']))
    for cid in cids:
        order=client.get_order_by_client_id(cid)
        if order:
            expected_type='market' if cid==unwind_cid(item['plan']['receipt_id'],item['account']) else 'stop'
            if order.get('client_order_id')!=cid or order.get('type')!=expected_type:
                raise ValueError('EXIT_CLIENT_ID_CONFLICT')
            rows[order['id']]=order
    for row in item.get('kill_receipt',{}).get('order_results',[]):
        if row.get('close_order_id'):
            order=client.get_order(row['close_order_id'])
            if order['id']!=row['close_order_id']:raise ValueError('EXIT_ORDER_ID_CONFLICT')
            rows[order['id']]=order
    if item.get('terminal_preparation'):
        for saved in item['terminal_preparation']['exit_orders']:
            order=client.get_order(saved['id'])
            if order!=saved:raise ValueError('TERMINAL_SOURCE_CHANGED')
            rows[order['id']]=order
    filled=dec(0);gross=dec(0);actual=[];active=[]
    for order in rows.values():
        if order.get('symbol')!=symbol or order.get('side')!='sell' or order.get('type') not in {'stop','market'}:
            raise ValueError('EXIT_SOURCE_OWNERSHIP_CONFLICT')
        q=dec(order.get('filled_qty','0'))
        if q<0 or q>positive(order['qty']):raise ValueError('INVALID_EXIT_FILLED_QUANTITY')
        if order.get('status') in bridge._ACTIVE_ORDER_STATUSES:active.append(order)
        elif order.get('status') not in bridge._TERMINAL_ORDER_STATUSES:raise ValueError('UNKNOWN_EXIT_STATUS')
        if q:
            at=bridge._parse_iso_utc(order.get('filled_at',''))
            start=bridge._parse_iso_utc(record['lifecycle_first_seen_at_utc'])
            if at is None or start is None or not start<=at<=datetime.fromtimestamp((now_ms+5000)/1000,timezone.utc):
                raise ValueError('NONCAUSAL_EXIT_FILL')
            price=positive(order['filled_avg_price']);filled+=q;gross+=q*(price-positive(record['entry_price']));actual.append(order)
    qty=positive(record['entry_fill_qty']);remaining=qty-filled
    if remaining<0:raise ValueError('EXIT_OVERFILL')
    positions=[r for r in client.list_positions() if r['symbol']==symbol]
    if remaining:
        if (len(positions)!=1 or positive(positions[0]['qty'])!=remaining
            or positive(positions[0]['avg_entry_price'])!=positive(record['entry_price'])):
            raise ValueError('EXIT_REMAINING_OWNERSHIP_CONFLICT')
        return result('PAPER_UNWIND_PENDING' if active else 'BLOCKED_EXECUTION',
                      reason='OWNED_EXIT_PENDING' if active else 'UNCERTAIN_OR_PARTIAL_UNWIND_NO_RESEND')
    if positions or active:raise ValueError('EXIT_FLAT_NOT_FINAL')
    orders=client.list_orders(status='open',limit=100,symbols=[symbol])
    if len(orders)>=100 or orders:raise ValueError('EXIT_OPEN_ORDERS_NOT_FINAL')
    kinds={r['type'] for r in actual}
    kind='NATIVE_STOP' if kinds=={'stop'} else 'EMERGENCY_MARKET' if kinds=={'market'} else 'MIXED_NATIVE_STOP_EMERGENCY'
    status='PAPER_STOP_EXIT_PENDING_FINALITY' if kind=='NATIVE_STOP' else 'PAPER_EMERGENCY_EXIT_PENDING_FINALITY'
    return result(status,exit_kind=kind,exit_orders=sorted(actual,key=lambda r:r['id']),
                  gross_before_fees=str(gross),net_pnl_status='NOT_PROVEN',
                  **({'kill_receipt':item['kill_receipt']} if item.get('kill_receipt') else {}))


def _finish_exit(client,item,record,db,path,state,now_ms,send):
    terminal=_exit_observation(client,item,record,now_ms)
    if terminal['status'] in {'PAPER_UNWIND_PENDING','BLOCKED_EXECUTION'} or not send:
        return terminal
    reconciled_record=dict(record)
    if terminal['exit_kind']=='NATIVE_STOP' and len(terminal['exit_orders'])==1:
        stop=terminal['exit_orders'][0]
        if stop['id']!=record['accepted_order_id']:
            attempt=next((a for a in item.get('rearms',{}).values() if a['cid']==stop.get('client_order_id')),None)
            if (not attempt or positive(attempt['qty'])!=positive(record['qty'])
                or positive(attempt['floor'])!=positive(record['accepted_stop_floor'])
                or positive(stop['qty'])!=positive(record['qty'])
                or positive(stop['stop_price'])<positive(record['accepted_stop_floor'])
                or stop.get('time_in_force')!=bridge._persistent_exit_tif_for_qty('',float(record['qty']))):
                raise ValueError('FILLED_REARM_LINEAGE_NOT_PROVEN')
            reconciled_record.update(accepted_order_id=stop['id'],accepted_order_tif=stop['time_in_force'],
                                     accepted_stop_floor=float(positive(stop['stop_price'])))
    preparation={'terminal':terminal,'owned_record':record,'reconciled_record':reconciled_record,
                 'exit_orders':terminal['exit_orders']}
    if item.get('terminal_preparation') and item['terminal_preparation']!=preparation:
        raise ValueError('TERMINAL_PREPARATION_CONFLICT')
    item['terminal_preparation']=preparation;_save(db,item)  # before native retirement
    symbol=item['plan']['symbol'];state_path=path/'protective_exit_hwm.json'
    if symbol in state:
        if terminal['exit_kind']=='NATIVE_STOP' and len(terminal['exit_orders'])==1:
            bridge._reconcile_intended_stop_exits(client=client,state={**state,symbol:reconciled_record},state_path=state_path,
                reentry_path=path/'reentry.json',positions={},open_orders=[],account_id=item['account'],
                state_dir=path,now=datetime.fromtimestamp(now_ms/1000,timezone.utc))
        else:
            bridge._atomic_write_json(path/'paper_terminal_exits.json',preparation)
            bridge._atomic_write_json(state_path,{k:v for k,v in state.items() if k!=symbol})
    item['terminal']=terminal;_save(db,item)
    return terminal


def _unwind(client,item,record,db,path,state,now_ms):
    """Once-only owned emergency. Pending/partial/lost results are GET-recovered."""
    if item.get('unwind_dispatched'):
        return _finish_exit(client,item,record,db,path,state,now_ms,True)
    proof={'account_id':item['account'],'reason':'unprotected_after_reconcile','positions':[
        {'symbol':item['plan']['symbol'],'entry_order_id':record['entry_order_id'],
         'qty':record['entry_fill_qty'],'avg_entry_price':record['entry_price']}]}
    bridge._validated_paper_kill_scope(proof=proof,client=client,base_url=PAPER)
    item['unwind_dispatched']=True;_save(db,item)
    if hasattr(client,'authorize_owned_unwind'):
        client.authorize_owned_unwind(proof,unwind_cid(item['plan']['receipt_id'],item['account']))
    changes={'ALPACA_SEND_ORDERS':'1','ALPACA_ALLOW_NEW_ENTRIES':'0','ALPACA_PAPER_KILL_ACK':'PAPER_OWNED_EXITS_ONLY'}
    previous={k:os.environ.get(k) for k in changes}
    try:
        os.environ.update(changes)
        receipt=bridge.run_paper_owned_kill(proof=proof,client=client,base_url=PAPER,apply=True,state_dir=path)
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
    item['kill_receipt']=receipt;_save(db,item)
    return _finish_exit(client,item,record,db,path,state,now_ms,True)


def maintain_paper(*,plan,policy,client,expected_paper_id,runtime,now_ms,send=False,unwind=False):
    """No entry path. Read-only by default; actual PAPER lifecycle is future evidence."""
    try:
        if client.base_url!=PAPER or expected_paper_id==policy['account_id']:
            raise ValueError('EXACT_DISTINCT_PAPER_ENDPOINT_REQUIRED')
        _plan_check(plan,policy);now_ms=instant(now_ms)
        account=client.get_account()
        if account['id']!=expected_paper_id:raise ValueError('PAPER_ACCOUNT_MISMATCH')
        identity=digest({'parent':plan['receipt_id'],'paper_account':account['id']})
        with _store(runtime) as (db,path):
            row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
            if not row:raise ValueError('NO_EXISTING_PAPER_INTENT')
            item=json.loads(row[0])
            if item['plan']!=plan or item['account']!=account['id']:
                raise ValueError('PAPER_INTENT_CONFLICT')
            prior=item.get('receipt',{})
            if prior.get('status')!='PAPER_PROTECTED':
                raise ValueError('INITIAL_FULL_NATIVE_PROTECTION_NOT_PROVEN')
            state_path=path/'protective_exit_hwm.json'
            state,error=bridge._load_protective_floor_state(state_path)
            if error or set(state) not in ({plan['symbol']},set()):
                raise ValueError('SINGLE_OWNED_LEDGER_REQUIRED')
            preparation=item.get('terminal_preparation')
            if not preparation and set(state)!={plan['symbol']}:
                raise ValueError('OWNED_LEDGER_MISSING_WITHOUT_TERMINAL_PREPARATION')
            record=bridge._validated_existing_intended_lifecycle(
                preparation['owned_record'] if preparation else state[plan['symbol']],account['id'])
            entry=client.get_order(prior['entry_order_id'])
            if (record['entry_order_id']!=prior['entry_order_id'] or entry.get('client_order_id')!=item['entry_cid']
                or entry.get('symbol')!=plan['symbol'] or entry.get('side')!='buy'
                or entry.get('status') not in {'filled','canceled','expired'}
                or positive(entry['filled_qty'])!=positive(record['entry_fill_qty'])
                or positive(entry['filled_qty'])!=positive(prior['filled_qty'])
                or positive(entry['filled_qty'])>positive(plan['qty'])
                or positive(entry['filled_avg_price'])!=positive(prior['filled_price'])
                or positive(entry['filled_avg_price'])!=positive(record['entry_price'])):
                raise ValueError('PAPER_ENTRY_OWNERSHIP_CONFLICT')
            history=client.list_orders(status='all',limit=500,symbols=[plan['symbol']])
            if len(history)>=500:raise ValueError('PAPER_HISTORY_INCOMPLETE')
            buys=[o for o in history if o.get('symbol')==plan['symbol'] and o.get('side')=='buy'
                  and bridge._safe_float(o.get('filled_qty'),0)>0]
            if not buys or max(buys,key=lambda o:bridge._parse_iso_utc(o.get('filled_at','')))['id']!=entry['id']:
                raise ValueError('PAPER_LATEST_FILLED_BUY_CONFLICT')
            if preparation:
                return _finish_exit(client,item,record,db,path,state,now_ms,send)
            orders=client.list_orders(status='open',limit=100,symbols=[plan['symbol']])
            if len(orders)>=100:raise ValueError('PAPER_ORDERS_INCOMPLETE')
            known={item['stop_cid']}|{v['cid'] for v in item.get('rearms',{}).values()}
            allowed=known|({unwind_cid(plan['receipt_id'],account['id'])} if item.get('unwind_dispatched') else set())
            if any(o.get('symbol')==plan['symbol'] and (o.get('side')!='sell'
                   or o.get('type') not in {'stop','market'} or o.get('client_order_id') not in allowed) for o in orders):
                raise ValueError('PAPER_FOREIGN_ACTIVE_ORDER')
            if item.get('unwind_dispatched'):
                return _finish_exit(client,item,record,db,path,state,now_ms,send)
            positions=[p for p in client.list_positions() if p['symbol']==plan['symbol']]
            if not positions:
                return _finish_exit(client,item,record,db,path,state,now_ms,send)
            if (len(positions)!=1 or positive(positions[0]['qty'])!=positive(record['qty'])
                or positive(positions[0]['avg_entry_price'])!=positive(record['entry_price'])
                or positions[0].get('side','long')!='long'):
                raise ValueError('PAPER_POSITION_OWNERSHIP_MISMATCH')
            if item.get('unwind_dispatched'):
                return result('BLOCKED_EXECUTION',reason='UNCERTAIN_UNWIND_NO_RESEND')
            if unwind:
                if not send:return result('PAPER_UNWIND_REQUIRED')
                return _unwind(client,item,record,db,path,state,now_ms)
            stop=client.get_order(record['accepted_order_id'])
            if stop.get('client_order_id') not in known:
                raise ValueError('PAPER_STOP_OWNERSHIP_CONFLICT')
            if orders:
                if len(orders)!=1:raise ValueError('PAPER_MULTIPLE_ACTIVE_STOPS')
                confirmed=bridge._confirmed_intended_stop(client,orders[0],symbol=plan['symbol'],
                    qty=float(record['qty']),requested_stop=float(record['accepted_stop_floor']))
                if orders[0]['id']!=record['accepted_order_id']:
                    attempt=next((a for a in item.get('rearms',{}).values() if a['cid']==orders[0]['client_order_id']),None)
                    if not attempt or positive(attempt['qty'])!=positive(record['qty']) or positive(attempt['floor'])!=positive(record['accepted_stop_floor']):
                        raise ValueError('PAPER_UNPROVEN_REARM_RECOVERY')
                    if not send:return result('PAPER_MAINTENANCE_REQUIRED',reason='NATIVE_LEDGER_RECOVERY')
                    confirmed=bridge._rearm_intended_position(client=client,symbol=plan['symbol'],position=positions[0],
                        existing_stops=orders,state=state,state_path=state_path,account_id=account['id'])
                    item['managed_stop_order_id']=confirmed['id'];_save(db,item)
                return result('PAPER_PROTECTED',stop_order_id=confirmed['id'],net_pnl_status='NOT_PROVEN')
            if stop.get('status') not in {'expired','canceled','rejected'} or positive(record['qty'])<=0 or bridge._safe_float(stop.get('filled_qty'),-1)!=0:
                raise ValueError('TERMINAL_UNFILLED_OLD_STOP_REQUIRED')
            if not send:return result('PAPER_MAINTENANCE_REQUIRED',reason='DAY_PROTECTION_ABSENT')
            clock=client.get_clock();clock_ms=int(datetime.fromisoformat(clock['timestamp'].replace('Z','+00:00')).timestamp()*1000)
            if abs(now_ms-clock_ms)>5000:raise ValueError('PAPER_MAINTENANCE_CLOCK')
            if clock.get('is_open') is not True:return result('PAPER_WAITING_NEXT_REGULAR_SESSION')
            session=datetime.fromisoformat(clock['timestamp'].replace('Z','+00:00')).date().isoformat()
            attempt=item.setdefault('rearms',{}).get(session)
            cid=rearm_cid(plan['receipt_id'],account['id'],session)
            found=client.get_order_by_client_id(cid)
            if found and attempt is None:raise ValueError('UNOWNED_REARM_CLIENT_ID')
            expected={'cid':cid,'qty':str(record['qty']),'floor':str(record['accepted_stop_floor'])}
            if attempt is not None and attempt!=expected:raise ValueError('REARM_JOURNAL_CONFLICT')
            class RearmClient:
                def get_order(self,oid):return client.get_order(oid)
                def submit_stop_sell(self,symbol,**kwargs):
                    nonlocal found
                    if found:return found
                    if attempt is not None:raise RuntimeError('UNCERTAIN_REARM_NO_RESEND')
                    item['rearms'][session]=expected;_save(db,item)
                    try:
                        found=client.submit_stop_sell(symbol,client_order_id=cid,**kwargs)
                    except Exception:
                        found=client.get_order_by_client_id(cid)
                        if not found:raise
                    return found
            try:
                confirmed=bridge._rearm_intended_position(client=RearmClient(),symbol=plan['symbol'],
                    position=positions[0],existing_stops=[],state=state,state_path=state_path,account_id=account['id'])
                item['managed_stop_order_id']=confirmed['id'];_save(db,item)
                return result('PAPER_PROTECTED',stop_order_id=confirmed['id'],net_pnl_status='NOT_PROVEN')
            except (RuntimeError,TimeoutError,ConnectionError):
                return _unwind(client,item,record,db,path,state,now_ms)
    except Exception as error:
        return result('BLOCKED_EXECUTION',reason=str(error) or type(error).__name__)
