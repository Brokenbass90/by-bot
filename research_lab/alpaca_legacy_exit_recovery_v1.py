"""UNSELECTED candidate for the existing owned NET actor, no standalone runner.

No credentials, new ownership, market retries, live installation or authority.
Caller must be the source/GO-validated runtime under its original account lock.
The proposed runtime wrapper calls this guard before any subsequent stop cancel.
Unknown/active market orders require reconciliation and owner action, never a
competing stop. HTTP422 alone is not proof of a rejected broker order.
"""

def _blocked(rt,reason,*,remaining=None):
    return rt.result('BLOCKED_EXECUTION',reason=reason,owner_action_required=True,
        recovery_mode='READ_ONLY_RECONCILE_NO_MARKET_RESEND',remaining_qty=remaining,
        protection_present=False,no_blind_retry=True)


def _recover(rt,db,item,client,record,binding,observation_ms):
    started=rt.time.monotonic()
    hold=item['exit_recovery_hold'];attempt=item['dispatches']['exit'];payload=attempt['payload']
    if hold['exit_client_order_id']!=payload['client_order_id']:raise ValueError('EXIT_RECOVERY_SCOPE_CHANGED')
    positions,orders,owned,remaining,gross=rt.owned_snapshot(client,item,record,observation_ms=observation_ms)
    if not remaining:return rt.finish_exit(db,item,client,record,binding,observation_ms=observation_ms)
    if any(o['type']!='stop' for o in orders):return _blocked(rt,'EXIT_RECOVERY_ACTIVE_SELL',remaining=str(remaining))
    row=client.get_order_by_client_id(payload['client_order_id'])
    if row is None:return _blocked(rt,'EXIT_RECOVERY_UNKNOWN_MARKET_NO_COMPETING_STOP',remaining=str(remaining))
    row=rt.order_contract(client.get_order(row['id']),payload)
    if row['status'] not in {'filled','canceled','expired','rejected'}:
        return _blocked(rt,'EXIT_RECOVERY_MARKET_NOT_TERMINAL',remaining=str(remaining))
    if not any(o['id']==row['id'] and o==row for o in owned):raise ValueError('EXIT_RECOVERY_TERMINAL_SOURCE_CONFLICT')
    clock=client.get_clock();stamp=rt.native._parse_iso_utc(clock.get('timestamp',''))
    now=observation_ms() if observation_ms else item['observed_ms']
    if (not clock.get('is_open') or stamp is None or abs(now-int(stamp.timestamp()*1000))>5000
        or client.get_account()['id']!=item['account']):raise ValueError('EXIT_RECOVERY_FRESH_ACCOUNT_CLOCK_REQUIRED')
    symbol=item['intake']['plan']['symbol'];path=rt.safe_path(binding['ledger_path'],exists=True)
    current=rt.read_json(path)[symbol]
    if current['entry_order_id']!=item['entry']['id'] or current['dynamic_intake_sha256']!=item['id']:
        raise ValueError('EXIT_RECOVERY_LEDGER_LINEAGE_CONFLICT')
    floor=max(rt.positive(record['accepted_stop_floor']),rt.positive(current['accepted_stop_floor']))
    session=stamp.date().isoformat();key='exit-protection:'+payload['client_order_id']+':'+session
    # Durable hold remains even after protection, so ordinary and kill cycles
    # cannot reenter original unwind and cancel the restored stop.
    if orders:
        if len(orders)!=1:raise ValueError('EXIT_RECOVERY_ONE_STOP_REQUIRED')
        stop=orders[0]
    else:
        if rt.time.monotonic()-started>5:raise ValueError('EXIT_RECOVERY_SNAPSHOT_EXPIRED')
        # A new DAY session is not permission to abandon an unknown older stop.
        # Every previous recovery intent must have exact terminal broker truth.
        for prior_key,prior in item['dispatches'].items():
            if not prior_key.startswith('exit-protection:'):continue
            known=client.get_order_by_client_id(prior['payload']['client_order_id'])
            if known is None:return _blocked(rt,'EXIT_RECOVERY_OLD_STOP_UNKNOWN',remaining=str(remaining))
            known=rt.order_contract(client.get_order(known['id']),prior['payload'])
            if known['status'] not in {'filled','canceled','expired','rejected'}:
                return _blocked(rt,'EXIT_RECOVERY_OLD_STOP_NOT_TERMINAL',remaining=str(remaining))
            if not any(o['id']==known['id'] and o==known for o in owned):
                raise ValueError('EXIT_RECOVERY_OLD_STOP_SOURCE_CONFLICT')
        cid='dyr-'+rt.digest(dict(domain='NET_EXIT_RECOVERY_V1',parent=item['id'],exit=payload['client_order_id'],session=session))[:32]
        request=dict(symbol=symbol,side='sell',type='stop',qty=str(remaining),stop_price=format(floor,'.2f'),
            time_in_force=rt.native._persistent_exit_tif_for_qty('',float(remaining)),client_order_id=cid)
        if rt.time.monotonic()-started>5:raise ValueError('EXIT_RECOVERY_SNAPSHOT_EXPIRED')
        class DeadlineStopClient:
            def __getattr__(self,name):return getattr(client,name)
            def _request(self,method,path,payload=None):
                if method!='POST' or path!='/v2/orders' or payload!=request:
                    raise ValueError('EXIT_RECOVERY_EXACT_STOP_ONLY')
                if rt.time.monotonic()-started>5:raise ValueError('EXIT_RECOVERY_SNAPSHOT_EXPIRED')
                return client._request(method,path,payload)
        # dispatch performs another CID GET. Recheck after that GET at the wire
        # boundary too; an expired intent remains reserved, never blindly reset.
        stop=rt.dispatch(db,item,DeadlineStopClient(),request,key)
    # A stop may fill before its first ACK readback. Never rearm the pre-fill qty.
    positions,open_orders,owned,remaining,gross=rt.owned_snapshot(client,item,record,observation_ms=observation_ms)
    if not remaining:return rt.finish_exit(db,item,client,record,binding,observation_ms=observation_ms)
    stop=client.get_order(stop['id'])
    if (stop['status'] not in {'new','accepted','partially_filled'} or stop['symbol']!=symbol
        or stop['side']!='sell' or stop['type']!='stop'
        or rt.positive(stop['qty'])-rt.dec(stop.get('filled_qty','0'))!=remaining
        or rt.positive(stop['stop_price'])<floor
        or len(open_orders)!=1 or open_orders[0]['id']!=stop['id']
        or stop['time_in_force']!=rt.native._persistent_exit_tif_for_qty('',float(remaining))):
        raise ValueError('EXIT_RECOVERY_PROTECTION_READBACK_CONFLICT')
    state=rt.read_json(path)
    current=state[symbol]
    if current['entry_order_id']!=item['entry']['id'] or current['dynamic_intake_sha256']!=item['id']:
        raise ValueError('EXIT_RECOVERY_LEDGER_LINEAGE_CONFLICT')
    if rt.positive(current['accepted_stop_floor'])>rt.positive(stop['stop_price']):
        raise ValueError('EXIT_RECOVERY_FLOOR_ADVANCED_DURING_READBACK')
    updated={**current,'qty':float(remaining),'accepted_order_id':stop['id'],
        'accepted_stop_floor':max(float(floor),float(stop['stop_price'])),
        'accepted_order_tif':stop['time_in_force'],'protection_pending':False}
    rt.native._validated_existing_intended_lifecycle(updated,item['account'])
    rt.native._atomic_write_json(path,{**state,symbol:updated})
    hold.update(status='PROTECTION_CONFIRMED_EXIT_HELD',accepted_stop_id=stop['id']);rt.save(db,item)
    return rt.result('LIVE_EXIT_RECOVERY_PROTECTED',owner_action_required=True,
        protection_present=True,remaining_qty=str(remaining),stop_order_id=stop['id'],
        new_exit_authorized=False,no_blind_retry=True)


def guarded_unwind(rt,original,db,item,client,record,binding,*,observation_ms=None):
    """Existing actor/lock only; original exit CID never cleared or reused."""
    def held():
        if not item.get('exit_recovery_hold'):
            item['exit_recovery_hold']=dict(schema='NET_EXIT_RECOVERY_HOLD_V1',
                exit_client_order_id=item['dispatches']['exit']['payload']['client_order_id'])
            rt.save(db,item)
        try:return _recover(rt,db,item,client,record,binding,observation_ms)
        except Exception as error:
            return _blocked(rt,'EXIT_RECOVERY_UNKNOWN_'+type(error).__name__)
    if item.get('exit_recovery_hold') or item.get('dispatches',{}).get('exit'):return held()
    try:result=original(db,item,client,record,binding,observation_ms=observation_ms)
    except Exception:
        if item.get('dispatches',{}).get('exit'):return held()
        raise
    if result['status']=='BLOCKED_EXECUTION' and item.get('dispatches',{}).get('exit'):return held()
    return result


def build_overlay_candidate(source):
    """Pure build of a new, unselected overlay from the exact inspected source.

    No writes/install/selection. The future reviewed spec must separately pin
    both generated bytes and this helper; existing source/GO pins stay intact.
    """
    import hashlib
    if type(source) is not bytes or hashlib.sha256(source).hexdigest()!='a0710690e43ffbb4a96329de33ec8f65edf1d4c4ab11e549ed9b1911249548e4':
        raise ValueError('NET_RECOVERY_BASE_SOURCE_PIN')
    import inspect
    embedded='\n\n'.join(inspect.getsource(f) for f in (_blocked,_recover,guarded_unwind)).encode()
    return source+b'\n\n'+embedded+b'''\n\n# Proposed recovery guard: UNSELECTED; new exact owner-reviewed pins required.
_unwind_before_exit_recovery_v1=unwind

def unwind(db,item,client,record,binding,*,observation_ms=None):
    from types import SimpleNamespace
    return guarded_unwind(SimpleNamespace(**globals()),_unwind_before_exit_recovery_v1,
        db,item,client,record,binding,observation_ms=observation_ms)
'''


def build_helper_candidate(source):
    """Pure, pinned bootstrap repair; original financial functions unchanged.

    The accepted helper imports a publisher absent from its production app.
    Embed only the existing no-overwrite publisher and its stdlib dependencies,
    so the replacement packet can pin its complete executable helper bytes.
    """
    import hashlib
    import inspect
    from research_lab import kity_oct15_deadline_v1 as publisher
    if type(source) is not bytes or hashlib.sha256(source).hexdigest()!='f0af81fac7b31b4cd7824c42ebcb29596dd85821a3e4dc746e3bfe4dc3f42565':
        raise ValueError('NET_RECOVERY_HELPER_BASE_SOURCE_PIN')
    if hashlib.sha256(inspect.getsource(publisher).encode()).hexdigest()!='aef82f0f413eea0b2da2937e75d3f972f6907845647dcbdd9f6b0d1f88d2a62b':
        raise ValueError('NET_RECOVERY_PUBLISHER_SOURCE_PIN')
    missing=b'    from research_lab.kity_oct15_deadline_v1 import publish_once\n'
    main=b"if __name__=='__main__':raise SystemExit(main())"
    assert source.count(missing)==1 and source.count(main)==1
    embedded='\n\n'.join(inspect.getsource(f) for f in (publisher.path,publisher.fsync_dir,publisher.publish_once)).encode()
    return source.replace(missing,b'').replace(main,b'import uuid\n\n'+embedded+b'\n\n'+main)
