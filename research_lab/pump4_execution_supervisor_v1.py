"""Bounded selected-owner loop; no installation, authority writing or retry API.

Physical ownership and exact GO are always checked by selected_owner. Production
sources are loaded only inside that context. The optional source factory/clock
are for offline acceptance; there is no CLI physical-verifier override.
"""
import os
import threading
import uuid

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.kity_fresh_eligibility_watch_v1 import notify_once
from research_lab.pump4_account_owner_v1 import safe
from research_lab.pump4_selected_runner_v1 import pinned, selected_owner, config_sha
from research_lab.pump4_supervisor_v1 import selected_tick, read


def need(ok, reason):
    if not ok:raise ValueError('PUMP4_EXECUTION_SUPERVISOR_'+reason)


def trusted_sources(config, owner):
    from research_lab.pump4_runtime_sources_v1 import TrustedSources
    return TrustedSources(config, owner)


def run(config_path=None, config_sha256=None, *, dispatch=False, orders_off=False,
        once=False, max_ticks=None, poll_seconds=5, source_factory=None, stop=None,
        clock=None, alert=None, on_receipt=None):
    """Hold the original account lease until stop/finite completion, even on GET errors.

    Config authority owns epoch/delay; neither is accepted as a caller override.
    A candidate is consumed durably before account reads, including failed reads.
    Existing admission always takes precedence and continues reconciliation.
    Receipt persistence failure inhibits future entries but preserves custody.
    Unbounded loops retain only the latest result in memory, all receipts on disk.
    """
    need(type(dispatch) is bool and type(orders_off) is bool and not (dispatch and orders_off),'EXPLICIT_MODE')
    if not dispatch and not orders_off:
        return [dict(status='ORDERS_OFF_NO_REQUESTS',broker_writes=0)]
    need(type(once) is bool and (max_ticks is None or type(max_ticks) is int and max_ticks>0),'FINITE_TICKS')
    need(type(poll_seconds) is int and 5<=poll_seconds<=30,'POLL_SECONDS')
    need(config_path is not None and isinstance(config_sha256,str),'CONFIG_REQUIRED')
    config=pinned(dict(path=str(config_path),sha256=config_sha256))
    mode='OWNER_TINY_LIVE' if dispatch else 'ORDERS_OFF'
    need(config.get('mode')==mode,'CONFIG_MODE')
    notifications_requested=config.get('notifications') is not None
    epoch=config.get('epoch_started_ms');delay=config.get('entry_max_delay_ms')
    need(type(epoch) is int and epoch>0,'CONFIG_EPOCH')
    need(type(delay) is int and 0<delay<=60000,'CONFIG_ENTRY_DELAY')
    stop=stop if stop is not None else threading.Event()
    receipts=[];ticks=0;run_id=uuid.uuid4().hex;observation_fault=False
    with selected_owner(config_path,config_sha256,dispatch=dispatch,clock=clock) as owner:
        need(owner.scope['mode']==mode and owner.scope['runner_config_sha256']==config_sha(config),'CONFIG_AUTHORITY')
        root=safe(owner.root/'supervisor')
        # Exactly one construction; a failed constructor never becomes an
        # implicit new source session or a replacement account lease.
        sources=None;source_error=None
        try:sources=(source_factory or trusted_sources)(config,owner)
        except Exception as exc:source_error=type(exc).__name__
        if alert is None and notifications_requested and sources is not None:
            # The source owns the existing pinned sender. Bind only after the
            # physical owner has been selected; notification failure cannot
            # relinquish this lease or interrupt lifecycle reconciliation.
            try:alert=sources.alert
            except Exception:pass
        def candidate():
            need(not observation_fault,'RECEIPT_FAILURE_ENTRY_INHIBITED')
            value=sources.candidate()
            if value is None:return None
            need(set(value)=={'intake','decision_id','captures'} and isinstance(value['decision_id'],str)
                 and bool(value['decision_id']),'CAUSAL_CANDIDATE')
            identity=dict(scope_sha256=owner.scope_sha256,decision_id=value['decision_id'])
            target=safe(root/'attempts'/(digest(identity)+'.json'))
            need(not os.path.lexists(target),'CANDIDATE_ALREADY_ATTEMPTED_NO_RETRY')
            publish(target,dict(identity,observed_ms=owner.clock(),status='ATTEMPT_CONSUMED_BEFORE_ACCOUNT_READ'))
            return value
        while not stop.is_set():
            ticks+=1
            try:
                if sources is None:raise RuntimeError(source_error)
                result=selected_tick(owner,sources.account,candidate,
                    epoch_started_ms=epoch,max_delay_ms=delay,apply=dispatch)
            except Exception as exc:
                result=dict(status='BLOCKED_OBSERVATION',error_type=type(exc).__name__,
                    custody_required=True,finality_proven=False)
            receipt=dict(schema='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1',
                run_id=run_id,pid=os.getpid(),tick=ticks,observed_ms=owner.clock(),scope_sha256=owner.scope_sha256,
                runner_config_sha256=config_sha256,mode=mode,result=result,
                broker_writes=None if dispatch else 0,final_costs_proven=False)
            try:
                publish(safe(root/'receipts'/(run_id+'-'+str(ticks)+'.json')),receipt)
            except Exception:
                observation_fault=True
                receipt=dict(receipt,receipt_persisted=False)
            if once or max_ticks is not None:receipts.append(receipt)
            else:receipts[:]=[receipt]
            if alert is not None:
                # Repeated unchanged status is quiet, including after restart.
                event=dict(scope_sha256=owner.scope_sha256,mode=mode,status=result['status'],
                    role=result.get('role'),error_type=result.get('error_type'),reason=result.get('reason'))
                event['terminal_id']=digest(event)
                target=safe(root/'alerts'/event['terminal_id'])
                try:
                    try:publish(target/'terminal.json',event)
                    except FileExistsError:need(read(target/'terminal.json')==event,'ALERT_IDENTITY')
                    notify_once(target,event,alert)
                except Exception:pass  # Notification cannot relinquish owned custody.
            if on_receipt is not None:
                try:on_receipt(receipt)
                except Exception:pass
            if once or max_ticks is not None and ticks>=max_ticks:break
            stop.wait(poll_seconds)
    return receipts
