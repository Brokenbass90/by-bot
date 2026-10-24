"""Read-only legacy retirement evidence. No unit mutation or broker API."""
import hashlib
import re
import shlex
import subprocess
import time
from pathlib import Path
from research_lab.alpaca_dynamic_v1 import digest

UNITS=tuple(p+s for p in ('alpaca-oct15-owned-manager','alpaca-dynamic-next-entry-20261019')
            for s in ('.service','.timer'))
SCHEMA='ALPACA_MONTHLY_LEGACY_RETIREMENT_V1'
PROPERTIES='Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,Transient,NeedDaemonReload,MainPID,ControlPID,Job,TriggeredBy,Triggers'
LEGACY_PATHS=('/opt/bybot-research/alpaca-next-entry-20261019-v1/manager-wrapper.py',
    '/opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/control-v1.py',
    '/opt/bybot-research/alpaca-dynamic-live-20261013/repairs/oct16-entry-identity-v2/control-v1.py')
CRON_REFERENCES=('alpaca_intended_live','run_alpaca_dynamic_live_v1','run_alpaca_monthly_cycle_v1',
    'alpaca_next_entry_control_v1',
    'alpaca_protective_exit_manager','alpaca-oct15-owned-manager','alpaca-dynamic-next-entry-20261019',
    'run_alpaca_live_v38_once','run_alpaca_protective_exit_manager',*LEGACY_PATHS)
READONLY_CRON_SOURCES=('/root/by-bot/runtime/alpaca_intended_live/run.sh',
    '/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app/scripts/run_alpaca_intended_live.sh',
    '/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app/scripts/run_alpaca_adaptive_paper.sh',
    '/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app/scripts/alpaca_adaptive_paper.py',
    '/root/by-bot/runtime/alpaca_intended_live/profile.env')
PROCESS_NAMES={'run_alpaca_live_v38_once.sh','run_alpaca_protective_exit_manager.sh',
    'alpaca_protective_exit_manager.py','run_alpaca_dynamic_live_v1.py','alpaca_next_entry_control_v1.py'}
MAX_CAPTURE_MS=2000
MAX_AGE_MS=5000


def _pin(pin):
    if not isinstance(pin,str) or not re.fullmatch('[a-f0-9]{64}',pin):raise ValueError('MONTHLY_HANDOFF_PIN')


def _file(path,pin):
    _pin(pin);p=Path(path)
    if (not p.is_absolute() or '..' in p.parts or any(q.is_symlink() for q in (p,*p.parents))
        or not p.is_file() or p.stat().st_nlink!=1):raise ValueError('MONTHLY_HANDOFF_FILE')
    if hashlib.sha256(p.read_bytes()).hexdigest()!=pin:raise ValueError('MONTHLY_HANDOFF_FILE_DRIFT')


def validate_policy(policy):
    if (not isinstance(policy,dict) or set(policy)!={'schema','units','cron_projection_sha256','readonly_cron'}
        or policy['schema']!=SCHEMA or not isinstance(policy['units'],dict) or set(policy['units'])!=set(UNITS)):
        raise ValueError('MONTHLY_LEGACY_HANDOFF_REQUIRED')
    _pin(policy['cron_projection_sha256'])
    for unit,row in policy['units'].items():
        if (not isinstance(row,dict) or set(row)!={'fragment_path','sha256'}
            or not isinstance(row['fragment_path'],str) or Path(row['fragment_path']).name!=unit):
            raise ValueError('MONTHLY_HANDOFF_UNIT_SCOPE')
        _pin(row['sha256'])
    if not isinstance(policy['readonly_cron'],dict):raise ValueError('MONTHLY_HANDOFF_CRON_SCOPE')
    for pin,files in policy['readonly_cron'].items():
        _pin(pin)
        if not isinstance(files,dict) or set(files)!=set(READONLY_CRON_SOURCES):raise ValueError('MONTHLY_HANDOFF_READONLY_CRON_UNBOUND')
        for value in files.values():_pin(value)
    return policy


def _systemctl_show():
    return subprocess.run(['/usr/bin/systemctl','show',*UNITS,'--no-pager','--property='+PROPERTIES],
        check=True,capture_output=True,text=True,timeout=2,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).stdout


def _legacy_crontab():
    # Missing/inaccessible cron is UNKNOWN, not an empty schedule.
    return subprocess.run(['/usr/bin/crontab','-l'],check=True,capture_output=True,text=True,
        timeout=2,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).stdout


def _legacy_processes():
    return subprocess.run(['/usr/bin/ps','-eo','args='],check=True,capture_output=True,text=True,
        timeout=2,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).stdout


def cron_projection(raw):
    lines=[s for s in raw.splitlines() if any(ref in s for ref in CRON_REFERENCES)]
    return digest(lines),lines


def readonly_cron_command(line):
    # Only the existing pinned source chain, with a literal non-writing mode.
    # Shell nesting/separators/expansion are unsupported even when row-hashed.
    fields=line.split(None,5)
    if len(fields)!=6:return False
    base='/root/by-bot/runtime/alpaca_intended_live/'
    pattern=(r'(?:/usr/bin/flock -n '+re.escape(base+'data.lock')+r' )?'
        r'(?:/bin/bash )?'+re.escape(base+'run.sh')+
        r'(?: --(?:read-only|prepare|preflight))?'
        r'(?: >> '+re.escape(base+'logs/prepare.log')+r' 2>&1)?'
        r'(?: # alpaca_intended_live_data)?')
    return re.fullmatch(pattern,fields[5]) is not None


def capture_retirement(policy,cid,*,now_ms):
    policy=validate_policy(policy);started=time.monotonic()
    def physical():
        for row in policy['units'].values():_file(row['fragment_path'],row['sha256'])
        for files in policy['readonly_cron'].values():
            for path,pin in files.items():_file(path,pin)
    physical();raw=_systemctl_show();rows={}
    for block in raw.strip().split('\n\n'):
        row={}
        for line in block.splitlines():
            k,sep,v=line.partition('=')
            if not sep or k in row:raise ValueError('MONTHLY_HANDOFF_SYSTEMD_SCHEMA')
            row[k]=v
        unit=row.get('Id')
        if unit not in UNITS or unit in rows:raise ValueError('MONTHLY_HANDOFF_UNIT_IDENTITY')
        expected=policy['units'][unit]
        conditions=dict(LoadState='loaded',ActiveState='inactive',SubState='dead',DropInPaths='',
            Transient='no',NeedDaemonReload='no',Job='',FragmentPath=expected['fragment_path'])
        if any(row.get(k)!=v for k,v in conditions.items()):raise ValueError('MONTHLY_LEGACY_NOT_RETIRED:'+unit)
        if unit.endswith('.timer'):
            # A pinned timer without an [Install] section becomes static when
            # its enablement symlink is removed. Inactivity/jobs/source/cron
            # checks still apply; static does not mean an active schedule.
            if (row.get('UnitFileState') not in {'disabled','static'} or row.get('TriggeredBy')!=''
                or row.get('Triggers')!=unit.removesuffix('.timer')+'.service'):
                raise ValueError('MONTHLY_LEGACY_TIMER_NOT_DISABLED:'+unit)
        elif (row.get('UnitFileState') not in {'static','disabled'}
              or row.get('MainPID')!='0' or row.get('ControlPID')!='0'
              or row.get('Triggers')!=''
              or not set(row.get('TriggeredBy','').split())<={unit.removesuffix('.service')+'.timer'}):
            raise ValueError('MONTHLY_LEGACY_SERVICE_NOT_RETIRED:'+unit)
        rows[unit]=row
    if set(rows)!=set(UNITS):raise ValueError('MONTHLY_HANDOFF_UNIT_COVERAGE')
    cron_sha,lines=cron_projection(_legacy_crontab())
    if cron_sha!=policy['cron_projection_sha256']:raise ValueError('MONTHLY_HANDOFF_CRON_DRIFT')
    for line in lines:
        if line.lstrip().startswith('#'):continue
        pin=hashlib.sha256(line.encode()).hexdigest()
        if not readonly_cron_command(line) or pin not in policy['readonly_cron']:
            raise ValueError('MONTHLY_LEGACY_CRON_NOT_RETIRED')
    for line in _legacy_processes().splitlines():
        if not any(name in line for name in (*PROCESS_NAMES,*LEGACY_PATHS)):continue
        if any(Path(t).name in PROCESS_NAMES or t in LEGACY_PATHS for t in shlex.split(line)):
            raise ValueError('MONTHLY_LEGACY_PROCESS_ACTIVE')
    physical();elapsed=int((time.monotonic()-started)*1000)
    if not 0<=elapsed<=MAX_CAPTURE_MS:raise ValueError('MONTHLY_HANDOFF_CAPTURE_STALE')
    proof=dict(schema='ALPACA_MONTHLY_LEGACY_RETIREMENT_CAPTURE_V1',status='LEGACY_RETIREMENT_CONFIRMED',
        policy_sha256=digest(policy),client_order_id=cid,started_ms=now_ms,completed_ms=now_ms+elapsed,
        elapsed_ms=elapsed,units=rows,cron_projection_sha256=cron_sha,legacy_process_count=0,
        broker_writes=0,unit_changes=0)
    return {**proof,'check_sha256':digest(proof)}


def require_fresh(proof,policy,cid,*,now_ms):
    if (not isinstance(proof,dict) or proof.get('check_sha256')!=digest({k:v for k,v in proof.items() if k!='check_sha256'})
        or proof.get('status')!='LEGACY_RETIREMENT_CONFIRMED' or proof.get('client_order_id')!=cid
        or proof.get('policy_sha256')!=digest(policy)
        or not 0<=now_ms-proof['completed_ms']<=MAX_AGE_MS):
        raise ValueError('MONTHLY_HANDOFF_FINAL_PROOF_STALE_OR_CONFLICT')
    return proof
