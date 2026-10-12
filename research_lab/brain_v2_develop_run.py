"""Hash-gated, one-shot A5/A6 historical runner. No clients or order authority."""
from datetime import datetime, timezone
from dataclasses import asdict
from bisect import bisect_right
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import numpy as np

from research_lab.brain_v2_frozen_primitives import BrainBlocked, canonical, digest, _require
from research_lab.brain_v2_sources import PinnedSources
from research_lab.brain_v2_develop import (
    DevelopEngine,FoldTable,FundingA6,Outcome,START,END,HOUR,TICK,A5_PIN,A6_PIN,
)

BASE=Path('reports/evidence/brain_v2_develop_20261012')
SOURCE=Path('.superpowers/sdd/brain-v2-develop-20261012/source')
MAX_RAW_BYTES=256*1024*1024
MIN_FREE_BYTES=512*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()


def save_exclusive(path,value):
    with Path(path).open('xb') as f:
        f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())


def verify_inputs(root,raw,expected_pin):
    """Before any start marker/outcome use: every published source/code/table pin."""
    guard=PinnedSources(root,raw,expected_manifest_sha256=expected_pin)
    guard.verify()
    d=json.loads(raw)
    _require(d.get('scope')=='BRAIN_V2_A5_A6_SINGLE_DEVELOPING_FILTER'
             and d.get('filter_runs_allowed')==1 and d.get('a5_sha256')==A5_PIN
             and d.get('a6_sha256')==A6_PIN,'run_manifest_scope')
    adapter_raw=guard.read(str(BASE/'adapter_manifest.json'))
    adapter=PinnedSources(Path(root)/SOURCE,adapter_raw,
                          expected_manifest_sha256=d['adapter_manifest_sha256'])
    adapter.verify()
    publication=json.loads(guard.read(str(BASE/'TABLE_HASH_PUBLICATION.json')))
    _require(len(publication['tables'])==4 and publication['filter_started'] is False,
             'train_table_publication')
    tables=tuple(FoldTable(guard.read(r['path']),expected_pin=r['sha256'],cutoff=r['cutoff'])
                 for r in publication['tables'])
    return adapter,tables


def execute_once(output,manifest_pin,driver):
    """A failed/crashed run remains spent. No automatic retry or repair."""
    output=Path(output)
    _require(not output.exists(),'single_run_already_started')
    output.mkdir(mode=0o700)  # Exclusive mkdir arbitrates concurrent starts.
    start=dict(schema='BRAIN_V2_DEVELOP_FILTER_STARTED',manifest_sha256=manifest_pin,
               started_at_utc=datetime.now(timezone.utc).isoformat(),orders_allowed=False,
               permitted_attempts=1)
    save_exclusive(output/'STARTED.json',start)
    try:
        report=driver(output)
    except Exception as error:
        report=dict(status='BLOCKED_DATA' if isinstance(error,BrainBlocked) else 'BLOCKED_IMPLEMENTATION',
                    reason=str(error),exception_type=type(error).__name__,filter_runs=1,
                    orders_allowed=False,money_authority=False)
    report={**report,'manifest_sha256':manifest_pin,
            'finished_at_utc':datetime.now(timezone.utc).isoformat(),
            'run_permission_consumed':True}
    save_exclusive(output/'TERMINAL.json',report)
    return report


class CompressedLedger:
    """Offline evidence only. No restart writer, broker journal or state repair."""
    def __init__(self,path):
        self.path=Path(path);self.file=self.path.open('xb')
        self.zip=gzip.GzipFile(filename='',mode='wb',fileobj=self.file,mtime=0)
        self.count,self.raw_bytes,self.last_hash=0,0,'0'*64

    def append(self,data):
        body=dict(sequence=self.count+1,previous_sha256=self.last_hash,data=data)
        pin=digest(body);raw=canonical({**body,'sha256':pin})+b'\n'
        _require(self.raw_bytes+len(raw)<=MAX_RAW_BYTES,'offline_ledger_bound')
        self.zip.write(raw);self.count+=1;self.raw_bytes+=len(raw);self.last_hash=pin

    def close(self):
        self.zip.close();self.file.flush();os.fsync(self.file.fileno());self.file.close()
        raw=self.path.read_bytes()
        return dict(path=self.path.name,records=self.count,raw_bytes=self.raw_bytes,
                    compressed_bytes=len(raw),compressed_sha256=sha(raw),last_record_sha256=self.last_hash)


class RealInputs:
    """Reuse exact frozen context functions; causal entry projection separate from outcomes."""
    def __init__(self,adapter):
        self.adapter=adapter;self.entries={};self._raw={};self._rows={};self._funding={};self._vol={};self._context_cache={}
        for name,row in adapter.rows.items():
            if row['role']!='trade_stream':continue
            raw=adapter.read(name);records=json.loads(raw)
            sleeves=tuple(sorted({r['leg'] for r in records}))
            archive=adapter.stream(name,sleeves=sleeves)
            entries=archive.entries(start_ms=START,end_ms=END)
            by_metadata={(r['leg'],r['sym'],r['side'],r['ts']):r for r in records}
            for entry in entries:
                op=entry.opportunity
                _require(op.id not in self._rows,'cross_stream_duplicate')
                self.entries.setdefault(op.t_available,[]).append(entry)
                self._rows[op.id]=by_metadata[(op.sleeve,op.symbol,op.side,op.t_signal)]
        self._load_frozen_helpers()

    def _load_frozen_helpers(self):
        # The modules' complete transitive sources are pinned by adapter_manifest.
        lab=self.adapter.root/'research_lab'
        spec=importlib.util.spec_from_file_location('brain_develop_frozen_mu',lab/'brain_v2/mu_sigma.py')
        self.mu=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mu)
        self.regimes=self.mu.W.metki_v1() # closed BTC H4; no B3 judge/main.

    def context(self,entry):
        op=entry.opportunity;hour=op.t_available//HOUR*HOUR;key=(op.symbol,hour)
        if key in self._context_cache:return self._context_cache[key]
        if op.symbol not in self._vol:
            name=f'research_lab/data/h1/{op.symbol}.npz'
            import io
            with np.load(io.BytesIO(self.adapter.read(name)),allow_pickle=False) as z:
                # Exactly original seed; future rows cannot influence an earlier ATR.
                ts=z['ts'].astype(np.int64);prices=z['ohlcv'].astype(float)
                mask=ts<END;ts=ts[mask];prices=prices[mask]
            natr,continuous=self.mu.natr_series(ts,prices)
            self._vol[op.symbol]=(ts,natr,continuous)
        ts,natr,continuous=self._vol[op.symbol]
        i=int(np.searchsorted(ts,hour-HOUR,side='right'))-1
        vol=self.mu.vol_bucket(natr,continuous,i) if i>=0 and ts[i]==hour-HOUR else 'UNKNOWN'
        raw=self.regimes.get(hour)
        regime={'BULL_TREND':'BULL','BEAR_TREND':'BEAR','NEUTRAL':'NEUTRAL'}.get(raw,'UNKNOWN')
        self._context_cache[key]=(regime,vol)
        return regime,vol

    def outcome(self,entry):
        """Called only after the exclusive one-shot marker, never during preflight."""
        op=entry.opportunity;row=self._rows[op.id]
        if op.symbol not in self._funding:
            name=f'external/funding/{op.symbol}.json'
            raw=self.adapter.read(name) if name in self.adapter.rows else None
            pin=self.adapter.rows[name]['sha256'] if raw is not None else None
            self._funding[op.symbol]=FundingA6(raw,source_hash=pin,symbol=op.symbol)
        hours=row['hours']
        _require(type(hours) is int and 1<=hours<=op.max_hold_h,'source_hold_hours')
        funding=self._funding[op.symbol].summary(start_ms=op.t_available,end_ms=op.t_available+hours*HOUR)
        return Outcome(hours,row['R'],funding)


def evaluate(adapter,tables,output):
    inputs=RealInputs(adapter);engine=DevelopEngine(tables)
    files={key:CompressedLedger(output/(key+'.jsonl.gz')) for key in (
        'paired_decisions','equity_ticks','closed_RAW_SAFE','closed_FOUNDATION','closed_BRAIN_DET')}
    artifacts={};at=START
    try:
        while at<END or any(a['positions'] for a in engine.arms.values()):
            entries=inputs.entries.get(at,[]) if at<END else []
            contexts={e.opportunity.id:inputs.context(e) for e in entries}
            outcomes={e.opportunity.id:inputs.outcome(e) for e in entries}
            result=engine.step(at,entries,contexts,outcomes)
            files['equity_ticks'].append(dict(tick_ms=at,arms=result['ticks'],before_current_packet=True))
            for e in sorted(entries,key=lambda x:x.opportunity.id):
                key=e.opportunity.id
                files['paired_decisions'].append(dict(tick_ms=at,opportunity=asdict(e.opportunity),
                    opportunity_id=key,entry_metadata=dict(e.metadata),context=contexts[key],arms=result['decisions'][key]))
            for arm,rows in result['closed'].items():
                for row in rows:files['closed_'+arm].append(row)
            at+=TICK
            if (at-START)%(365*24*4*TICK)==0:
                print(json.dumps(dict(progress_tick_ms=at,decisions=len(engine.seen),orders_allowed=False)),flush=True)
    finally:
        for key,ledger in files.items():artifacts[key]=ledger.close()
        save_exclusive(output/'ARTIFACTS.json',artifacts)
    report=engine.report()
    return {**report,'artifacts':artifacts,'test_start_ms':START,'new_entry_end_exclusive_ms':END,
            'last_tick_ms':engine.last_tick,'release_only_tail':engine.last_tick>=END,
            'opportunities':len(engine.seen),'source_manifest_sha256':adapter.manifest_sha256,
            'research_scope':'SPENT_HISTORY_DEVELOPING_NONINFERIORITY_NOT_INDEPENDENT_EDGE',
            'B3_runs':0,'new_holdout_decisions':0,'live_or_vps_operations':0}


def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',required=True)
    ap.add_argument('--expected-pin',required=True);ap.add_argument('--output',required=True)
    args=ap.parse_args();root=Path.cwd()
    _require(shutil.disk_usage(root).free>=MIN_FREE_BYTES,'disk_preflight')
    adapter,tables=verify_inputs(root,Path(args.manifest).read_bytes(),args.expected_pin)
    output=Path(args.output)
    report=execute_once(output,args.expected_pin,lambda out:evaluate(adapter,tables,out))
    print(json.dumps({k:report[k] for k in ('status','manifest_sha256','filter_runs','orders_allowed')},indent=2))


if __name__=='__main__':main()
