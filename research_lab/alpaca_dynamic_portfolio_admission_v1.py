"""GET-only admission of existing, source-bound, fully protected LIVE holdings.

Call under the original account lock, immediately before a distinct entry. No
HALT override, slot reservation, broker mutation or management is performed.
Unproven/partially closed lifecycles require reconciliation before another buy.
"""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import digest, positive, dec
from research_lab.alpaca_dynamic_live_runtime_v1 import custody, safe_path, read_json, owned_snapshot
from scripts import equities_alpaca_paper_bridge as native


def check_owned_portfolio(db,binding,policy,client,*,positions,orders,target_symbol,observed_ms):
    pins=binding.get('portfolio_bindings',[])
    if not isinstance(pins,list) or len(pins)>policy['max_positions']:
        raise ValueError('PORTFOLIO_BINDING_CARDINALITY')
    bindings={}
    for pin in pins:
        path=safe_path(pin['path'],exists=True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin['sha256']:
            raise ValueError('PORTFOLIO_BINDING_SOURCE_CHANGED')
        prior=read_json(path)
        for field in ('endpoint','account_id','policy_sha256','source_book','runtime','lock_path',
                      'ledger_path','halt_path','broker_root','native_bridge_sha256'):
            if prior[field]!=binding[field]:raise ValueError('PORTFOLIO_ACCOUNT_OR_CUSTODY_CONFLICT')
        key=digest(prior)
        if key in bindings:raise ValueError('PORTFOLIO_DUPLICATE_BINDING')
        bindings[key]=prior
    items=[json.loads(row[0]) for row in db.execute('SELECT payload FROM intents')]
    if len(items)!=len(bindings):raise ValueError('PORTFOLIO_RUNTIME_BINDING_MISMATCH')
    if len(orders)>=500 or len({p['symbol'] for p in positions})!=len(positions):
        raise ValueError('PORTFOLIO_SOURCE_INCOMPLETE')
    state=read_json(binding['ledger_path']) if items else {}
    held=set();stops=set();used=set()
    for saved in items:
        item=copy.deepcopy(saved);symbol=item['intake']['plan']['symbol']
        if (item.get('phase')!='PROTECTED' or item.get('initial_full_protection_proven') is not True
            or item.get('account')!=binding['account_id'] or symbol==target_symbol or symbol in held):
            raise ValueError('PORTFOLIO_UNRECONCILED_LIFECYCLE')
        prior=bindings.get(item['binding_sha256'])
        if prior is None or item['binding_sha256'] in used:raise ValueError('PORTFOLIO_UNBOUND_LIFECYCLE')
        custody(prior,item['intake'],policy);used.add(item['binding_sha256'])
        record=native._validated_existing_intended_lifecycle(state[symbol],binding['account_id'])
        if (record['entry_order_id']!=item['entry']['id']
            or record.get('dynamic_intake_sha256')!=item['intake']['intake_sha256']):
            raise ValueError('PORTFOLIO_NATIVE_OWNER_CONFLICT')
        item['observed_ms']=observed_ms
        actual,active,owned,remaining,gross=owned_snapshot(client,item,record)
        if remaining!=positive(item['entry']['filled_qty']) or len(actual)!=1 or len(active)!=1:
            raise ValueError('PORTFOLIO_PARTIAL_OR_UNPROTECTED_HOLDING')
        stop=active[0]
        if (stop['id']!=record['accepted_order_id'] or stop['status'] not in {'new','accepted'}
            or dec(stop.get('filled_qty','0'))!=0 or positive(stop['qty'])!=remaining
            or positive(record['qty'])!=remaining):
            raise ValueError('PORTFOLIO_FULL_NATIVE_STOP_REQUIRED')
        try:
            confirmed=native._confirmed_intended_stop(client,stop,symbol=symbol,qty=float(remaining),
                requested_stop=float(record['accepted_stop_floor']))
        except native.IntendedPaperProtectionError as exc:
            raise ValueError('PORTFOLIO_NATIVE_READBACK:'+str(exc)) from exc
        if (positive(confirmed['qty'])!=remaining or dec(confirmed.get('filled_qty','0'))!=0
            or confirmed.get('leaves_qty') not in (None,'') and positive(confirmed['leaves_qty'])!=remaining):
            raise ValueError('PORTFOLIO_NATIVE_EXACT_REMAINING')
        stop=confirmed
        if positive(confirmed['stop_price'])<positive(record['accepted_stop_floor']):
            raise ValueError('PORTFOLIO_NATIVE_FLOOR_CONFLICT')
        if stop['time_in_force']=='day':
            stamp=native._parse_iso_utc(stop.get('submitted_at') or stop.get('created_at',''))
            now=datetime.fromtimestamp(observed_ms/1000,timezone.utc)
            if stamp is None or stamp.date()!=now.date() or stamp>now:
                raise ValueError('PORTFOLIO_DAY_REARM_NOT_CURRENT_SESSION')
        if positive(actual[0]['current_price'])<=positive(record['accepted_stop_floor']):
            raise ValueError('PORTFOLIO_STOP_ALREADY_BREACHED')
        observed=next((p for p in positions if p['symbol']==symbol),None)
        if (observed is None or positive(observed['qty'])!=remaining
            or positive(observed['avg_entry_price'])!=positive(actual[0]['avg_entry_price'])):
            raise ValueError('PORTFOLIO_POSITION_CHANGED')
        held.add(symbol);stops.add(stop['id'])
    if set(p['symbol'] for p in positions)!=held or set(o['id'] for o in orders)!=stops or set(state)!=held:
        raise ValueError('PORTFOLIO_FOREIGN_POSITION_OR_ORDER')
    return dict(status='OWNED_PORTFOLIO_PROTECTION_PASS',held_symbols=sorted(held),
                stop_order_ids=sorted(stops),broker_writes=0)
