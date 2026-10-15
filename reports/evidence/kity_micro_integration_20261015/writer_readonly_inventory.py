"""Bounded process/unit/source custody reader. No import of trading code or writes."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def main():
    root=Path('/root/by-bot');started=time.time_ns()//1_000_000
    p=Path('/proc/1648585')
    if not p.exists(): raise RuntimeError('ORIGINAL_WRITER_PID_CHANGED')
    raw=(root/'smart_pump_reversal_bot.py').read_bytes();source=raw.decode()
    if hashlib.sha256(raw).hexdigest()!='c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1':
        raise RuntimeError('WRITER_SOURCE_DRIFT')
    tree=ast.parse(source);functions=[]
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            endpoints=sorted({v.value for v in ast.walk(n) if isinstance(v,ast.Constant)
                and isinstance(v.value,str) and v.value.startswith('/v5/')})
            if endpoints:
                functions.append(dict(name=n.name,line=n.lineno,endpoints=endpoints))
    cgroup=(p/'cgroup').read_text()
    units=re.findall(r'([^/\n]+\.service)',cgroup)
    if len(set(units))!=1: raise RuntimeError('WRITER_UNIT_AMBIGUOUS')
    unit=units[0]
    props=['Id','ActiveState','SubState','MainPID','NRestarts','UnitFileState',
           'Restart','KillMode','ExecMainStartTimestamp','FragmentPath',
           'Requires','Wants','PartOf','BindsTo','Before','After','Conflicts']
    show=subprocess.run(['systemctl','show',unit,'--no-pager']+
        ['--property='+v for v in props],capture_output=True,text=True,timeout=8,check=True).stdout
    info=dict(line.split('=',1) for line in show.splitlines() if '=' in line)
    if info.get('MainPID')!='1648585': raise RuntimeError('WRITER_UNIT_PID_CONFLICT')
    cron=subprocess.run(['crontab','-l'],capture_output=True,timeout=8).stdout
    env=dict(v.split(b'=',1) for v in (p/'environ').read_bytes().split(b'\0') if b'=' in v)
    anchors=[dict(line=n,text=line.strip()) for n,line in enumerate(source.splitlines(),1)
             if '_ENTRY_RESERVATION_LOCK' in line or re.search(r'\bflock\s*\(',line)]
    related=[]
    for candidate in ('bybot-web.service','bybot-att1-lifecycle-shadow.service'):
        result=subprocess.run(['systemctl','show',candidate,'--no-pager',
            '--property=Id,LoadState,ActiveState,SubState,MainPID,NRestarts'],
            capture_output=True,text=True,timeout=8)
        related.append(dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line))
    out=dict(schema='kity_micro_physical_writer_inventory_v1',started_ms=started,
        completed_ms=time.time_ns()//1_000_000,pid=1648585,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        proc_start_ticks=(p/'stat').read_text().split(') ',1)[1].split()[19],
        unit=info,related_units=related,cron_sha256=hashlib.sha256(cron).hexdigest(),
        dry_run_env=env.get(b'DRY_RUN',b'').decode(),
        request_endpoint_functions=functions,entry_reservation_lock_anchors=anchors,
        broker_requests=0,remote_writes=0,process_changes=0)
    print(json.dumps(out,allow_nan=False))


if __name__=='__main__': main()
