"""Narrow operator handoff, no broker write capability. Exact pins and receipts.

Apply only under the owner's separate physical handoff authorization. Money GO
is never created here. Original sources/cron and all unrelated units stay intact.
"""
import argparse,json,os,signal,subprocess,time
from decimal import Decimal as D
from pathlib import Path

from research_lab.kity_micro_physical_owner_v1 import (publish,sha,now_ms,load_bound_credentials,rows,unit_state)
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError

OLD_UNITS=('bybot.service','trading-journal-web.service')


def require_flat(positions,orders):
    if any(not D(str(r['size'])).is_finite() or D(str(r['size']))!=0 for r in positions) or orders:
        raise SourceError('ACCOUNT_NOT_FLAT_OR_ORDERS_NOT_FINAL')


def rollback_safe(state):
    return (not state.get('ownership_conflict') and state.get('broker_flat_proven') is True
        and not any(D(str(v))!=0 for v in state['held'].values())
        and all(v.get('terminal') and D(v['filled'])==D(v['terminal_quantity'])
            for v in list(state['entries'].values())+list(state['exits'].values())))


def run(*args):
    r=subprocess.run(list(args),capture_output=True,text=True,timeout=25)
    if r.returncode:raise SourceError('COMMAND_FAILED:'+args[0]+':'+str(r.returncode)+':'+r.stderr[-1000:])
    return r.stdout


def config_from(path,pin):
    raw=Path(path).read_bytes()
    if sha(raw)!=pin:raise SourceError('CONFIG_PIN_CONFLICT')
    c=json.loads(raw);c.update(_config_path=path,_config_sha256=pin);return c


def verify_files(c):
    for name,pin in c['source_files'].items():
        p=Path(c['app_root'])/name
        if p.is_symlink() or sha(p.read_bytes())!=pin:raise SourceError('PACKAGE_PIN_CONFLICT:'+name)
    for path,pin in c['guard_source_files'].items():
        if sha(Path(path).read_bytes())!=pin:raise SourceError('LEGACY_SOURCE_DRIFT:'+path)
    if sha(run('crontab','-l').encode())!=c['original_cron_sha256']:raise SourceError('CRON_DRIFT')


def fresh_flat(reader,label,root):
    at=now_ms();ps=reader.pages('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))
    osrc=reader.pages('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
    recent=reader.pages('/v5/order/history',dict(category='linear',startTime=str(at-600000),endTime=str(now_ms()),limit='50'))
    executions=reader.pages('/v5/execution/list',dict(category='linear',startTime=str(at-600000),endTime=str(now_ms()),limit='100'))
    source=dict(started_ms=at,completed_ms=now_ms(),positions=ps,orders=osrc,recent_history=recent,recent_executions=executions)
    pin=publish(root/('flat-'+label+'-'+str(at)+'.json'),source)
    groups=[ps,osrc,recent,executions]
    if any(not g.get('complete') for g in groups):raise SourceError('HANDOFF_SOURCE_COVERAGE_UNKNOWN')
    decoded=[[r for p in g['pages'] for r in reader.result(p)['list']] for g in groups]
    require_flat(decoded[0],decoded[1])
    # Recent history/executions are retained for original owner's terminality,
    # never adopted as KITY evidence. Any activity during quiescence is a conflict.
    return dict(positions=len(decoded[0]),open_orders=len(decoded[1]),recent_orders=len(decoded[2]),
        recent_executions=len(decoded[3]),source_sha256=pin,completed_ms=source['completed_ms'])


def apply(c):
    root=Path(c['runtime_root']);verify_files(c)
    if (root/'handoff-applied.json').exists():raise SourceError('HANDOFF_ALREADY_APPLIED_NO_REPEAT')
    key,secret=load_bound_credentials(c);reader=BybitReadTransport(key,secret)
    if unit_state(c['unit'])['ActiveState'] not in ('inactive','failed'):raise SourceError('NEW_OWNER_ALREADY_ACTIVE')
    before={u:unit_state(u) for u in OLD_UNITS}
    for u,v in before.items():
        if v['MainPID']!=c['original_units'][u]['MainPID'] or v['ActiveState']!='active':raise SourceError('ORIGINAL_PID_CAS_CONFLICT')
    frozen=fresh_flat(reader,'before-freeze',root)
    publish(root/'handoff-started.json',dict(at_ms=now_ms(),original_units=before,source=frozen,
        authority='OWNER_SCOPED_HANDOFF_ORDERS_OFF',money_go=False,broker_writes=0))
    # Stop application threads before final account observation. SIGKILL on the
    # subsequent systemd stop prevents graceful-shutdown broker POST callbacks.
    frozen_units=[];changed=[];stopped=[]
    try:
        for u in OLD_UNITS:
            run('systemctl','kill','--kill-who=all','--signal=SIGSTOP',u);frozen_units.append(u)
        time.sleep(2)
        final=fresh_flat(reader,'frozen',root)
        if final['recent_orders'] or final['recent_executions']:
            raise SourceError('RECENT_ORIGINAL_EXECUTION_NEEDS_OWNER_FINALITY_REVIEW')
        publish(Path(c['inhibit_marker']),dict(authority='OWNER_ORDERS_OFF_HANDOFF',at_ms=now_ms()))
        for u in OLD_UNITS:
            p=Path('/etc/systemd/system')/(u+'.d')/'90-kity-micro-inhibit.conf';p.parent.mkdir(exist_ok=True)
            text=c['inhibitor_text']
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'w') as f:f.write(text);f.flush();os.fsync(f.fileno())
            changed.append(p)
        run('systemctl','daemon-reload')
        for u in OLD_UNITS:run('systemctl','stop',u);stopped.append(u)
        for u in OLD_UNITS:
            if unit_state(u)['MainPID']!='0':raise SourceError('ORIGINAL_OWNER_NOT_QUIESCENT')
        post=fresh_flat(reader,'after-stop',root)
        if post['recent_orders'] or post['recent_executions']:raise SourceError('LATE_ORIGINAL_EXECUTION_UNKNOWN')
        # Verify the actual restart path is inhibited, without starting a writer.
        for u in OLD_UNITS:
            run('systemctl','start',u)
            if unit_state(u)['MainPID']!='0':raise SourceError('OLD_OWNER_INHIBITION_FAILED')
        verify_files(c)
        run('systemctl','enable',c['unit']);run('systemctl','start',c['unit'])
        applied=dict(schema='kity_micro_physical_handoff_receipt_v1',status='HANDOFF_APPLIED_ORDERS_OFF',
            at_ms=now_ms(),config_sha256=c['_config_sha256'],original_units=before,
            old_units_after={u:unit_state(u) for u in OLD_UNITS},flat_source=post,
            new_owner=unit_state(c['unit']),broker_writes=0,money_go=False,original_cron_unchanged=True)
        publish(root/'handoff-applied.json',applied)
        return applied
    except Exception:
        # Never restore a competing owner while a replacement can still run.
        if (root/'active-plan.json').exists():
            publish(root/('handoff-needs-owner-'+str(now_ms())+'.json'),dict(status='ACTIVE_PLAN_KEEP_EXCLUSIVE_RECOVERY',at_ms=now_ms()))
            raise
        run('systemctl','stop',c['unit']);run('systemctl','disable',c['unit'])
        if unit_state(c['unit'])['MainPID']!='0':raise SourceError('REPLACEMENT_STILL_ACTIVE_KEEP_INHIBITORS')
        # No micro orders/GO were authorized or created during apply. Restore only
        # our exact inhibitor files; preserve unknown altered files for owner review.
        for p in changed:
            if sha(p.read_bytes())==sha(c['inhibitor_text'].encode()):p.unlink()
        marker=Path(c['inhibit_marker'])
        if marker.exists():marker.unlink()
        run('systemctl','daemon-reload')
        for u in frozen_units:
            if u in stopped:run('systemctl','start',u)
            else:
                try:run('systemctl','kill','--kill-who=all','--signal=SIGCONT',u)
                except SourceError:pass
        raise


def rollback(c):
    root=Path(c['runtime_root']);verify_files(c)
    key,secret=load_bound_credentials(c);reader=BybitReadTransport(key,secret)
    if not (root/'rollback-request.json').exists():
        publish(root/'rollback-request.json',dict(at_ms=now_ms(),reason='SCOPED_OWNER_RETURN_REQUESTED'))
    # The entry fence is rechecked after durable intent, just before wire I/O.
    # Active-plan publication precedes every possible send; therefore absence
    # of an active plan after this fence, or a terminal ledger, is race-safe.
    active=root/'active-plan.json'
    if active.exists():
        # Stop cannot race a new dispatch: rollback first requires the terminal
        # journal, no unresolved send/native order and a fresh broker flat readback.
        from research_lab.kity_execution_micro_runtime_v1 import MicroJournal
        d=json.loads(active.read_bytes());j=MicroJournal(root/'lifecycle.sqlite',d['plan']);s=j.snapshot();j.close()
        if not rollback_safe(s):raise SourceError('ROLLBACK_OWNED_RISK_OR_UNCERTAIN_SEND')
    if any((root/'commands').glob('*.json')):
        for p in (root/'commands').glob('*.json'):
            if not (root/'results'/p.name).exists():raise SourceError('ROLLBACK_UNPROCESSED_COMMAND')
    fresh=fresh_flat(reader,'rollback-before',root)
    run('systemctl','stop',c['unit']);run('systemctl','disable',c['unit'])
    # Account cannot change through this owner now. Preserve evidence forever.
    fresh_flat(reader,'rollback-after-stop',root)
    for u,pin in c['inhibitors'].items():
        p=Path('/etc/systemd/system')/(u+'.d')/'90-kity-micro-inhibit.conf'
        if sha(p.read_bytes())!=pin:raise SourceError('ROLLBACK_INHIBITOR_CAS_CONFLICT')
    for u in OLD_UNITS:(Path('/etc/systemd/system')/(u+'.d')/'90-kity-micro-inhibit.conf').unlink()
    Path(c['inhibit_marker']).unlink();run('systemctl','daemon-reload')
    for u in OLD_UNITS:run('systemctl','start',u)
    receipt=dict(status='ROLLED_BACK_TO_ORIGINAL_OWNERS',at_ms=now_ms(),flat=fresh,broker_writes=0,
        restored_units={u:unit_state(u) for u in OLD_UNITS})
    publish(root/('rollback-'+str(now_ms())+'.json'),receipt);return receipt


def main():
    a=argparse.ArgumentParser();a.add_argument('--config',required=True);a.add_argument('--config-sha256',required=True);a.add_argument('--action',choices=('apply','rollback'),required=True)
    args=a.parse_args();c=config_from(args.config,args.config_sha256)
    print(json.dumps(apply(c) if args.action=='apply' else rollback(c)))


if __name__=='__main__':main()
