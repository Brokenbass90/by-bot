#!/usr/bin/env python3
"""One bounded SSH observation, reusing inspected GET-only probes; no remote writes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [
    "reports/evidence/money_morning_20261008/alpaca_broker_read_only.py",
    "reports/evidence/money_morning_20261008/alpaca_quote_lineage_read_only.py",
]
EXTRA = r'''
from pathlib import Path
import hashlib, json, time, subprocess, os, stat, signal
def read_bound(path, cap=2_000_000):
    p=Path(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size>cap: raise ValueError('SOURCE_BOUND')
        with os.fdopen(fd,'rb',closefd=False) as f: raw=f.read(cap+1)
        if len(raw)>cap: raise ValueError('SOURCE_BOUND')
        return {'path':str(p),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'raw':raw.decode()}
    finally: os.close(fd)
public=Path('/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20261002-paired-observation')
cfg=read_bound(public.parents[1]/'app/configs/research/att1_lifecycle_public_v2.json')
config=json.loads(cfg['raw'])
if config['runtime_dir']!=str(public): raise ValueError('PUBLIC_EPOCH_CONFLICT')
hb_before=read_bound(public/'heartbeat.json')
paths=sorted((public/'sessions').glob('*.jsonl'))
if len(paths)>256: raise ValueError('SESSION_COUNT_BOUND')
records={};total=0
for p in paths:
    member=read_bound(p,500_000);total+=member['bytes']
    if total>8_000_000: raise ValueError('SESSION_BYTES_BOUND')
    records[p.name]=member
hb_after=read_bound(public/'heartbeat.json')
pid=int(subprocess.check_output(['systemctl','show','bybot.service','-p','MainPID','--value'],text=True))
proc=dict(x.split('=',1) for x in Path(f'/proc/{pid}/environ').read_bytes().decode().split('\0') if '=' in x)
# Serialize only the non-secret retirement flag, never the environment.
retirement={'pid':pid,'ATT1_ENTRY_RETIRED':proc.get('ATT1_ENTRY_RETIRED')}
probes={}
for name in ('transport','funding'):
    root=Path('/opt/bybot-research/att1-execution-research-20261004/runtime')/name
    if (root/'heartbeat.json').exists(): probes[name]=read_bound(root/'heartbeat.json')
result={'schema':'OCT9_OVERNIGHT_PUBLIC_READ_ONLY_V1','observed_ms':time.time_ns()//1000000,
 'config':cfg,'heartbeat_before':hb_before,'heartbeat_after':hb_after,
 'session_members':records,'source_consistency':'bounded individual pinned files; active heartbeat may advance during capture',
 'old_entry_retirement':retirement,'completed_probe_heartbeats':probes,
 'services':{name:subprocess.check_output(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True).splitlines() for name in ('att1-transport-probe-48h','att1-funding-probe-48h')},
 'orders_allowed':False,'remote_writes':False}
print(json.dumps(result))
'''


def main():
    output = Path(sys.argv[1])
    if output.exists() or not output.parent.is_dir():
        raise ValueError("EXCLUSIVE_LOCAL_OUTPUT_REQUIRED")
    sources = {p: (ROOT / p).read_text() for p in SOURCES}
    sources["extra_public_observation"] = EXTRA
    pins = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in sources.items()}
    encoded = base64.b64encode(json.dumps(sources).encode()).decode()
    remote = """import base64,json,io,contextlib,signal
sources=json.loads(base64.b64decode(ENCODED));result={}
for name,code in sources.items():
 out=io.StringIO()
 with contextlib.redirect_stdout(out): exec(compile(code,name,'exec'),{})
 result[name]=json.loads(out.getvalue())
print(json.dumps(result))
""".replace("ENCODED", repr(encoded))
    args = ["ssh", "-i", str(Path.home() / ".ssh/by-bot"), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
            "root@64.226.73.119", "/root/by-bot/.venv/bin/python -B -"]
    process = subprocess.run(args, input=remote.encode(), capture_output=True, timeout=110)
    if process.returncode:
        sys.stderr.write(process.stderr.decode(errors="replace")[-2000:])
        raise SystemExit(process.returncode)
    if len(process.stdout) > 12_000_000:
        raise ValueError("LOCAL_RESPONSE_BOUND")
    data = json.loads(process.stdout)
    archive = json.dumps({"capture_source_pins": pins, "response": data}, indent=2).encode() + b"\n"
    with output.open("xb") as f:
        os.chmod(output, 0o600)
        f.write(archive);f.flush();os.fsync(f.fileno())
    print(json.dumps({"archive": str(output), "sha256": hashlib.sha256(archive).hexdigest(),
                      "bytes": len(archive), "broker_writes": 0, "remote_writes": 0}))


if __name__ == "__main__":
    main()
