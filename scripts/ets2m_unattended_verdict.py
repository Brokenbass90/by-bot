#!/usr/bin/env python3
"""One-shot frozen ETS2M evaluator; independent of Codex, no live imports/writes.

The original judge functions execute unchanged against an isolated snapshot.
Completion is not strategy PASS, READY_FOR_BUILD or money authorization.
"""
import argparse
import ast
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types

DUE_MS=1791658800000  # October10 19:00UTC, never overridden by CLI/manifest.
MAX_BYTES=64*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def bounded_read(path):
    if path.is_symlink():raise ValueError('SYMLINK_SOURCE')
    with path.open('rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('SOURCE_TOO_LARGE')
    return raw


def read_rows(path,keys):
    raw=bounded_read(path);rows=[];seen={}
    if raw and not raw.endswith(b'\n'):raise ValueError('INCOMPLETE_JSONL')
    for line in raw.splitlines():
        if not line.strip():continue
        try:r=json.loads(line);identity=tuple(r[k] for k in keys) if keys else (len(rows),);pin=sha(canonical(r))
        except (ValueError,TypeError,KeyError):raise ValueError('MALFORMED_JSONL')
        if identity in seen:
            if seen[identity]!=pin:raise ValueError('CONFLICTING_RECORD')
            continue
        seen[identity]=pin;rows.append(r)
    return rows


def verify_inputs(manifest):
    if manifest.get('schema_id')!='ets2m_unattended_v1' or manifest.get('due_utc')!='2026-10-10T19:00:00Z':raise ValueError('INVALID_MANIFEST')
    root=Path(manifest['source_root']).resolve()
    for name,pin in manifest['pins'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('INVALID_SOURCE_PATH')
        p=root/relative
        if not p.resolve().is_relative_to(root) or sha(bounded_read(p))!=pin:raise ValueError('SOURCE_PIN_MISMATCH:'+name)
    p=root/'research_lab/data/yadro/ETS2M'
    kg=sorted(read_rows(p/'vhody.jsonl',('id',)),key=lambda r:(r['ts'],r['sym']))[:900]
    if len(kg)!=900 or sha(canonical(kg))!=manifest['cohort_sha256']:raise ValueError('COHORT_PIN_MISMATCH')
    return root,kg


def isolated_judge(source_bytes,mirror):
    """Exact function bodies; no collector/strategy/module bootstrap execution."""
    import numpy as np
    cluster=types.ModuleType('vnutri');cluster.__dict__.update(np=np)
    tree=ast.parse(source_bytes['research_lab/vnutri.py'])
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'klaster_st','klaster_z_bystro'}]
    if len(nodes)!=2:raise ValueError('CLUSTER_CLOSURE_MISSING')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'frozen-vnutri','exec'),cluster.__dict__)
    tree=ast.parse(source_bytes['research_lab/yadro.py'])
    nodes=[];constants={};functions=set()
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'KONFIG','DVIGATELI','KONTROL'}:
            constants[n.targets[0].id]=ast.literal_eval(n.value)
        elif isinstance(n,ast.FunctionDef) and n.name in {'papka','chitat_jsonl','istochnik_vhodov','paritet_istochnika','otsenit'}:
            nodes.append(n);functions.add(n.name)
    if functions!={'papka','chitat_jsonl','istochnik_vhodov','paritet_istochnika','otsenit'} or set(constants)!={'KONFIG','DVIGATELI','KONTROL'}:raise ValueError('JUDGE_CLOSURE_MISSING')
    namespace=dict(constants,np=np,json=json,Path=Path,defaultdict=defaultdict,KOREN=mirror,DATA=mirror/'research_lab/data',YADRO=mirror/'research_lab/data/yadro',sys=types.SimpleNamespace(path=[]))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'frozen-yadro','exec'),namespace)
    previous=sys.modules.get('vnutri');sys.modules['vnutri']=cluster
    try:
        output=io.StringIO()
        with redirect_stdout(output):
            parity=namespace['paritet_istochnika']('ETS2M')
            code=namespace['otsenit']('ETS2M',900) if parity==0 else 2
        return code,output.getvalue()
    finally:
        if previous is None:sys.modules.pop('vnutri',None)
        else:sys.modules['vnutri']=previous


def evaluate(manifest,runtime,now_ms=None):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    if now_ms<DUE_MS:return {'status':'NOT_DUE','orders_allowed':False}
    root,kg=verify_inputs(manifest);runtime=Path(runtime);runtime.mkdir(parents=True,exist_ok=True)
    p=root/'research_lab/data/yadro/ETS2M'
    # Outcome data is first opened only after the fixed due gate.
    isp=read_rows(p/'ispolnenie.jsonl',('id',));ish=read_rows(p/'ishody.jsonl',('id','dvigatel'))
    # Preserve the first900 only; later research entries cannot change this cohort.
    ids={r['id'] for r in kg};isp=[r for r in isp if r['id'] in ids];ish=[r for r in ish if r['id'] in ids]
    source_bytes={name:bounded_read(root/name) for name in ('research_lab/yadro.py','research_lab/vnutri.py')}
    if any(sha(raw)!=manifest['pins'][name] for name,raw in source_bytes.items()):raise ValueError('SOURCE_CHANGED_DURING_CAPTURE')
    epoch=bounded_read(p/'epoha.json')
    if sha(epoch)!=manifest['pins']['research_lab/data/yadro/ETS2M/epoha.json']:raise ValueError('EPOCH_CHANGED_DURING_CAPTURE')
    keys={(r['sym'],r['ts']) for r in kg}
    source_rows=read_rows(root/'research_lab/data/ten_ETS2S.jsonl',None)
    source_rows=[r for r in source_rows if (r.get('sym'),r.get('ts')) in keys]
    eligible={}
    for row in source_rows:
        if row.get('R') is None or row.get('stop_dolya') is None:continue
        key=(row['sym'],row['ts']);pin=sha(canonical(row))
        if key in eligible and eligible[key]!=pin:raise ValueError('CONFLICTING_SOURCE_RECORD')
        eligible[key]=pin
    rows={'vhody.jsonl':kg,'ispolnenie.jsonl':isp,'ishody.jsonl':ish}
    pins={name:sha(canonical(data)) for name,data in rows.items()}
    with tempfile.TemporaryDirectory(prefix='ets2m-judge-',dir=runtime) as tmp:
        mirror=Path(tmp);target=mirror/'research_lab/data/yadro/ETS2M';target.mkdir(parents=True)
        for name,data in rows.items():(target/name).write_bytes(b''.join(canonical(r)+b'\n' for r in data))
        (target/'epoha.json').write_bytes(epoch)
        (mirror/'research_lab/data/ten_ETS2S.jsonl').write_bytes(b''.join(canonical(r)+b'\n' for r in source_rows))
        pins['source_cohort_rows']=sha(canonical(source_rows))
        code,output=isolated_judge(source_bytes,mirror)
    return {'schema_id':'ets2m_unattended_result_v1','status':'EVALUATED_RESEARCH_ONLY' if code==0 else 'BLOCKED_DATA',
            'evaluator_returncode':code,'evaluator_stdout':output,'cohort_count':900,'cohort_sha256':manifest['cohort_sha256'],
            'snapshot_pins':pins,'manifest_sha256':sha(canonical(manifest)),'observed_ms':now_ms,
            'parity_scope':'frozen first900 only; later source population excluded','due_ms':DUE_MS,'orders_allowed':False,'money_ready':False,'strategy_pass_inferred_from_exit_code':False,
            'next_gate':'Apply frozen prereg acceptance/parity and second-window gate; no READY_FOR_BUILD/money inference'}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--check',action='store_true');ap.add_argument('--wait',action='store_true');a=ap.parse_args()
    manifest=json.loads(bounded_read(a.manifest));verify_inputs(manifest)
    if a.check:print(json.dumps({'status':'INPUT_PINS_PASS','due_ms':DUE_MS,'outcomes_read':False}));return 0
    a.runtime.mkdir(parents=True,exist_ok=True)
    with (a.runtime/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt=a.runtime/'terminal.json'
        if receipt.exists():
            existing=json.loads(bounded_read(receipt))
            if sha(canonical(existing['result']))!=existing['sha256']:raise ValueError('TERMINAL_HASH_MISMATCH')
            if existing['result']['manifest_sha256']!=sha(canonical(manifest)):raise ValueError('TERMINAL_MANIFEST_MISMATCH')
            print(existing['result']['status']);return 0
        if a.wait:
            (a.runtime/'schedule.json').write_bytes(canonical({'pid':os.getpid(),'due_ms':DUE_MS,'armed_ms':int(time.time()*1000),'manifest_sha256':sha(canonical(manifest))}))
            while int(time.time()*1000)<DUE_MS:time.sleep(min(60,max(0.01,(DUE_MS-int(time.time()*1000))/1000)))
        try:result=evaluate(manifest,a.runtime)
        except Exception as exc:result={'status':'BLOCKED_DATA','reason':str(exc),'manifest_sha256':sha(canonical(manifest)),'observed_ms':int(time.time()*1000),'orders_allowed':False,'money_ready':False}
        if result['status']=='NOT_DUE':print('NOT_DUE');return 2
        raw=canonical({'result':result,'sha256':sha(canonical(result))})
        fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        print(result['status']);return 0 if result['status']=='EVALUATED_RESEARCH_ONLY' else 2


if __name__=='__main__':raise SystemExit(main())
