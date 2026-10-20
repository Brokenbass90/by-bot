"""Disabled scheduling and isolated rollback acceptance. No systemctl/writes API."""
import json
from pathlib import Path
import re

from research_lab.alpaca_day_monitor_v1 import atomic
from research_lab.alpaca_monthly_cycle_v1 import publish
from research_lab.alpaca_monthly_source_ops_v1 import safe_path


def unit_templates(app,python,spec,pin,*,dispatch_spec=None,dispatch_sha256=None):
    if (dispatch_spec is None)!=(dispatch_sha256 is None):raise ValueError('UNIT_DISPATCH_PAIR')
    for p in (app,python,spec,*([dispatch_spec] if dispatch_spec else [])):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',p) or '..' in Path(p).parts:raise ValueError('UNIT_PATH')
    if not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('UNIT_SPEC_PIN')
    if dispatch_sha256 is not None and not re.fullmatch('[0-9a-f]{64}',dispatch_sha256):raise ValueError('UNIT_DISPATCH_PIN')
    base=python+' -B '+app+'/scripts/run_alpaca_monthly_cycle_v1.py --spec '+spec+' --spec-sha256 '+pin
    out={}
    for mode,flag in [('source',' --source'),('manager','')]:
        name='alpaca-monthly-owned-'+mode
        command=base+flag
        if mode=='manager' and dispatch_spec:
            command=python+' -B '+app+'/scripts/run_alpaca_monthly_cycle_v1.py --spec '+dispatch_spec+' --spec-sha256 '+dispatch_sha256+' --dispatch'
        out[name+'.service']='''[Unit]
Description=Monthly isolated ORDERS_OFF '''+mode+'''
After=network-online.target
[Service]
Type=oneshot
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ExecStart='''+command+'''
TimeoutStartSec=600
'''
        out[name+'.timer']='''[Unit]
Description=Disabled Monthly ORDERS_OFF '''+mode+'''
[Timer]
OnCalendar=*-*-* *:00/'''+('10' if mode=='source' else '5')+''':30 UTC
AccuracySec=1s
Persistent=false
Unit='''+name+'''.service
[Install]
WantedBy=timers.target
'''
    return out


def rollback_snapshot(manager):
    p=manager.root/'book/monthly-orders-off.sqlite'
    if not p.exists():return dict(owned_positions=0,pending_dispatches=0,accounting_pending=False)
    native=manager.native(None,base_url='https://paper-api.alpaca.markets')
    held={p['symbol'] for p in manager.book.rows('positions')}
    if native.ledger.exists():
        ledger=json.loads(safe_path(native.ledger).read_bytes())
        if not isinstance(ledger,dict):raise ValueError('ROLLBACK_UNCERTAIN_NATIVE_SOURCE')
        held|=set(ledger)
    reentry=native.reentry;pending=0
    if reentry.exists():
        entries=json.loads(safe_path(reentry).read_bytes()).get('entry_intents')
        if not isinstance(entries,dict):raise ValueError('ROLLBACK_UNCERTAIN_NATIVE_SOURCE')
        pending=sum(1 for row in entries.values() if row.get('status')!='complete')
    try:native._require_exit_accounting();accounting=False
    except (ValueError,OSError,KeyError):accounting=True
    return dict(owned_positions=len(held),pending_dispatches=pending,accounting_pending=accounting)


def rollback_disabled(path,*,current,previous,snapshot):
    """Only a false-authority local pointer; never an enabled unit or process."""
    path=safe_path(path);value=json.loads(path.read_bytes())
    if value.get('schema')!='MONTHLY_DISABLED_RELEASE_POINTER_V1' or value.get('orders_allowed') is not False:
        raise ValueError('ROLLBACK_DISABLED_POINTER_ONLY')
    if (type(snapshot['owned_positions']) is not int or snapshot['owned_positions']<0
        or type(snapshot['pending_dispatches']) is not int or snapshot['pending_dispatches']<0
        or type(snapshot['accounting_pending']) is not bool):raise ValueError('ROLLBACK_SOURCE_UNKNOWN')
    if snapshot['owned_positions'] or snapshot['pending_dispatches'] or snapshot['accounting_pending']:
        return dict(status='ROLLBACK_BLOCKED_KEEP_OWNED_MANAGER',entry_admission=False,
            broker_writes=0,financial_units_changed=0)
    receipt=path.with_suffix('.rollback.json')
    expected=dict(schema='MONTHLY_DISABLED_ROLLBACK_V1',current=current,previous=previous,snapshot=snapshot)
    if value['selected']==previous:
        if not receipt.exists() or json.loads(receipt.read_bytes())!=expected:raise ValueError('ROLLBACK_UNKNOWN_POINTER_CHANGE')
        return dict(status='DISABLED_ROLLBACK_ALREADY_RECORDED',broker_writes=0,financial_units_changed=0)
    if value['selected']!=current:raise ValueError('ROLLBACK_CURRENT_CHANGED')
    if receipt.exists():
        if json.loads(receipt.read_bytes())!=expected:raise ValueError('ROLLBACK_RECEIPT_CONFLICT')
    else:publish(receipt,expected)
    atomic(path,dict(value,selected=previous))
    return dict(status='DISABLED_ROLLBACK_ACCEPTED',broker_writes=0,financial_units_changed=0)
