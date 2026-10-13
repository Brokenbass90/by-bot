"""Owner-authorized inert preparation while actual PAPER fees are pending.

Separate from the original PASS-only installer and money gate. No broker client,
service activation, cron application, HALT clear or owner money permit exists here.
"""
import base64
import hashlib
import json
import os
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import canonical, digest
from research_lab.alpaca_live_readiness_v1 import BASE, POSTCHECK_MS, verify_package, write_new

PROPOSAL_PIN='422c638c968486da38fdf88d11025944d6865e18f9f6eacea793207795c7aa4a'
OLD_LINE='*/5 12-22 * * 1-5 /usr/bin/flock -n /root/by-bot/runtime/alpaca_intended_live/readonly.lock /bin/bash /root/by-bot/runtime/alpaca_intended_live/run.sh --send-orders >> /root/by-bot/runtime/alpaca_intended_live/logs/readonly.log 2>&1 # alpaca_intended_live_readonly'
PREFIX='# DYNAMIC_HANDOFF_ORDERS_OFF_PENDING_OWNER_GO '


def require(ok,reason):
    if not ok:raise ValueError(reason)


def physical_check(receipt):
    require(receipt['source_manifest_sha256']==digest(receipt['source_files']),'INSTALL_MANIFEST_CONFLICT')
    for row in receipt['source_files']:
        p=Path(row['path'])
        require(p.is_absolute() and not any(x.is_symlink() for x in (p,*p.parents))
            and p.is_file() and p.stat().st_nlink==1 and p.stat().st_uid==os.getuid()
            and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],
            'INSTALLED_FILE_DRIFT:'+str(p))


def install_orders_off(package,approval,execution,*,now_ms,target=None):
    verify_package(package)
    require(now_ms>=POSTCHECK_MS,'ORIGINAL_POSTCHECK_NOT_DUE')
    require(approval['schema']=='ALPACA_ORDERS_OFF_INSTALL_HANDOFF_AUTHORIZATION_V2'
        and approval['receipt_sha256']==digest({k:v for k,v in approval.items() if k!='receipt_sha256'})
        and approval['authorization_status']=='DIRECT_OWNER_APPROVED'
        and approval['fee_pending_install_allowed'] is True
        and approval['orders_allowed'] is False and approval['halt_clear_allowed'] is False
        and approval['proposal_sha256']==PROPOSAL_PIN
        and approval['package_sha256']==package['package_sha256'],'EXACT_ORDERS_OFF_APPROVAL_REQUIRED')
    require(execution['status']=='ACTUAL_EXECUTION_STAGES_PASS_COST_FINALITY_PENDING'
        and execution['actual_rearm'] is True and execution['full_owned_exit'] is True
        and execution['orders_allowed'] is False
        and execution['execution_validation']['status']=='BLOCKED_DATA'
        and execution['execution_validation']['reason']=='PAPER_COST_FINALITY_SOURCE_REQUIRED',
        'ACTUAL_EXECUTION_STAGES_REQUIRED')
    base=Path(target or BASE).absolute()
    require(not any(p.is_symlink() for p in (base,*base.parents)),'INSTALL_SYMLINK')
    expected={'app/'+n:base64.b64decode(r['content_b64'],validate=True) for n,r in package['files'].items()}
    expected.update({'disabled-unit-templates/'+n:t.encode() for n,t in package['units'].items()})
    expected.update({'unapproved-activation-templates/'+n:t.encode() for n,t in package['unapproved_activation_templates'].items()})
    destination=base/'disabled_install_orders_off_v2_receipt.json'
    if base.exists():
        require(destination.is_file() and not destination.is_symlink(),'PARTIAL_INSTALL_NO_REPAIR')
        prior=json.loads(destination.read_bytes())
        require(prior['package_sha256']==package['package_sha256']
            and prior['owner_authorization_sha256']==approval['receipt_sha256'],'INSTALL_IDENTITY_CONFLICT')
        require({r['path']:r['sha256'] for r in prior['source_files']}==
            {str(base/n):hashlib.sha256(raw).hexdigest() for n,raw in expected.items()},'INSTALL_FILE_SET_CONFLICT')
        physical_check(prior)
        return prior
    base.mkdir(mode=0o700)
    rows=[]
    for name,raw in sorted(expected.items()):
        p=base/name;write_new(p,raw)
        rows.append(dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest()))
    receipt=dict(schema='ALPACA_DYNAMIC_DISABLED_INSTALL_RECEIPT_V2',status='DISABLED_DEPLOYMENT_VERIFIED',
        base=str(base),enabled=False,orders_allowed=False,service_activation_count=0,installed_system_units=0,
        remote_app_mismatches=[],package_sha256=package['package_sha256'],paper_receipt_sha256=None,
        cost_finality_pending=True,execution_receipt_sha256=execution['receipt_sha256'],
        owner_authorization_sha256=approval['receipt_sha256'],observed_ms=now_ms,
        source_files=rows,source_manifest_sha256=digest(rows),
        rollback='retain disabled app/HALT; exact old cron restoration only flat/HALT and no Dynamic writer/fill')
    physical_check(receipt);write_new(destination,canonical(receipt))
    return receipt


def bind_final_paper(deployment,paper,*,now_ms):
    require(paper.get('status')=='PAPER_EXECUTION_PASS' and paper.get('live_orders_allowed') is False
        and paper.get('receipt_sha256')==digest({k:v for k,v in paper.items() if k!='receipt_sha256'}),
        'ACTUAL_PAPER_PASS_REQUIRED')
    require(deployment['status']=='DISABLED_DEPLOYMENT_VERIFIED'
        and deployment['enabled'] is False and deployment['orders_allowed'] is False
        and deployment['service_activation_count']==0,'DISABLED_INSTALL_REQUIRED')
    physical_check(deployment)
    return {**deployment,'paper_receipt_sha256':paper['receipt_sha256'],
            'cost_finality_pending':False,'observed_ms':now_ms,
            'original_install_receipt_sha256':digest(deployment)}


def retired_crontab(raw,*,before_pin):
    require(hashlib.sha256(raw).hexdigest()==before_pin,'CRON_BEFORE_PIN_CONFLICT')
    lines=raw.splitlines(keepends=True)
    require(sum(line.rstrip(b'\r\n')==OLD_LINE.encode() for line in lines)==1,'EXACT_ONE_OLD_MANAGER_LINE_REQUIRED')
    edited=b''.join(PREFIX.encode()+line if line.rstrip(b'\r\n')==OLD_LINE.encode() else line for line in lines)
    require(edited.replace(PREFIX.encode(),b'',1)==raw,'CRON_ROLLBACK_BYTES_CONFLICT')
    return edited
