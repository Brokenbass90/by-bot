"""Timely marginal Brain shadow pairs from existing public PUMP4 publications.

No account, broker, credentials, research producer or outcome reader. Published
pure policies are byte-pinned and AST-selected, never imported as an application.
Model units are not money. UNKNOWN funding and net/gross prior caveat persist.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace

from research_lab.att1_lifecycle_journal import LifecycleJournal, SCHEMA
from research_lab.pump4_execution_plan_v1 import build_plan, SOURCE_PINS
from research_lab.pump4_source_probe_v1 import Probe

H=3600000
POLICY_SOURCE_SHA='2d9c24b8e8399abcd212c4835eb1d3193a3e76e8d3416d6a08904c352e90b928'
FROZEN_SIGNAL_PINS=SOURCE_PINS
DOMAIN='PUMP4_BRAIN_TIMELY_SHADOW_V1'

class SourcePending(ValueError):
    """Completed public file still in producer's atomic hardlink window."""


def need(ok,why):
    if not ok:raise ValueError('BRAIN_TIMELY_'+why)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def stamp(v):return type(v) is int and v>=0


def read_bytes(path,limit=2*1024*1024):
    p=Path(path).absolute()
    need(not any(x.is_symlink() for x in (p,*p.parents)),'SOURCE_SYMLINK')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and 1<=a.st_nlink<=2 and a.st_size<=limit,'SOURCE_BOUND')
        if a.st_nlink==2:raise SourcePending('BRAIN_TIMELY_SOURCE_PUBLISHING')
        raw=os.read(fd,limit+1);b=os.fstat(fd)
        if b.st_nlink==2:raise SourcePending('BRAIN_TIMELY_SOURCE_PUBLISHING')
        need((a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns)
             and len(raw)==a.st_size,'SOURCE_CHANGED')
        return raw
    finally:os.close(fd)


def decode(raw):
    def pairs(items):
        d={}
        for k,v in items:
            need(k not in d,'DUPLICATE_KEY');d[k]=v
        return d
    def bad(_):raise ValueError('BRAIN_TIMELY_NONFINITE')
    def finite(v):
        f=float(v);need(math.isfinite(f),'NONFINITE');return f
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad,parse_float=finite)


def read_json(path):return decode(read_bytes(path))


class FrozenBrain:
    """Only exact, unchanged pure functions/constants from published research."""
    version='BRAIN_V3'
    def __init__(self,path):
        raw=read_bytes(path);need(hashlib.sha256(raw).hexdigest()==POLICY_SOURCE_SHA,'POLICY_SOURCE_PIN')
        wanted={'PRIORY','RISK','BRAIN','POLICY_SHA','PRIORY_V3','SHA_V3',
                'baseline_v1','brain_v1','risk_engine'}
        selected=[];seen=set()
        for node in ast.parse(raw).body:
            names={node.name} if isinstance(node,ast.FunctionDef) else (
                {n.id for n in node.targets if isinstance(n,ast.Name)} if isinstance(node,ast.Assign) else set())
            if names & wanted:selected.append(node);seen|=names & wanted
        need(seen==wanted,'POLICY_AST_CONTRACT')
        env={'hashlib':hashlib,'json':json,'H':H,'DEN':24*H,'U':'UNKNOWN'}
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),env)
        self.env=env;self.sha=env['SHA_V3']
    def evaluate(self,risk_pct):
        if risk_pct is None:
            return dict(baseline=dict(action='NO_OPPORTUNITY',allocation_units=0,reasons=['no_frozen_signal']),
                        brain=dict(action='NO_OPPORTUNITY',allocation_units=0,reasons=['no_frozen_signal']),
                        net_economics_qualified=False)
        need(type(risk_pct) in (int,float) and math.isfinite(risk_pct) and risk_pct>0,'RISK_GEOMETRY')
        p=self.env['PRIORY_V3']['PUMP4'];gross=p['R']*risk_pct*100;unc=p['R_se']*risk_pct*100
        costs=[p[k] for k in ('fee','spread','slip','funding')]
        v=dict(sleeve='PUMP4',symbol='ONE_OPPORTUNITY',side=-1,prior_status=p['status'],
               exp_gross_bps=gross,uncertainty_bps=unc,
               exp_net_bps='UNKNOWN' if 'UNKNOWN' in costs else gross-sum(costs),
               cost_fee_bps=p['fee'],cost_spread_bps=p['spread'],cost_slip_bps=p['slip'],cost_funding_bps=p['funding'])
        result={}
        for name,fn in [('baseline','baseline_v1'),('brain','brain_v1')]:
            desired,reasons=self.env[fn](v,[]);units,caps=self.env['risk_engine'](v,desired,[])
            result[name]=dict(action='TAKE_SHADOW' if units>0 else 'SKIP_SHADOW',allocation_units=units,reasons=reasons+caps)
        return dict(result,risk_pct=risk_pct,funding_bps=p['funding'],prior_ref=p['ref'],
                    comparison_scope='MARGINAL_ONE_OPPORTUNITY_NOT_PORTFOLIO',
                    prior_semantics='PUBLISHED_TAKER_NET_PRIOR_IN_GROSS_FIELD_NOT_REPAIRED',
                    net_economics_qualified=False)


def pair_event(publication,*,policy,observed_ms,epoch_ms,next_open=None):
    p=publication
    need(isinstance(p,dict) and p.get('status')=='CLOSED_H1_INTAKE_PASS' and p.get('mode')=='CURRENT_CLOSED_BAR','PUBLICATION_MODE')
    need(p.get('source_kind')=='CONFIRMED_WS_WITH_FROZEN_JOURNAL_PREFIX','PUBLICATION_SOURCE')
    need(p.get('orders_allowed') is False and p.get('money_authority') is False and p.get('broker_writes')==0,'PUBLICATION_AUTHORITY')
    need(isinstance(p.get('decisions'),list) and len(p['decisions'])==1,'PUBLICATION_DECISIONS')
    o=p['decisions'][0];d=o['decision'];s=d.get('symbol');t=d.get('bar_open_ms')
    need(isinstance(s,str) and re.fullmatch('[A-Z0-9]{1,24}USDT',s) and p.get('symbol')==s,'SYMBOL')
    need(stamp(t) and t>0 and t%H==0,'BAR_TIME');hour=t+H
    need(o.get('schema')=='PUMP4_DATA_DECISION_OBSERVATION_V1' and o.get('mode')=='CURRENT_CLOSED_BAR'
         and o.get('orders_allowed') is False and o.get('money_authority') is False
         and d.get('orders_allowed') is False and d.get('money_authority') is False,'OBSERVATION_AUTHORITY')
    need(d.get('source_pins')==FROZEN_SIGNAL_PINS,'FROZEN_PINS')
    core={k:d[k] for k in ('domain_schema','symbol','bar_open_ms','history_sha256','source_pins','signal')}
    need(core['domain_schema']=='PUMP4_CLOSED_H1_INTAKE_V1' and d.get('decision_id')=='pump4-'+digest(core),'DECISION_IDENTITY')
    times=[hour,d.get('available_ms'),d.get('first_observed_ms'),p.get('publication_completed_ms'),observed_ms]
    need(all(stamp(v) for v in times) and times==sorted(times) and stamp(epoch_ms),'PUBLICATION_CLOCK')
    need(p.get('pair_received_ms')==d['available_ms'],'PAIR_CLOCK')
    signal=d['signal'];risk=None;reference=None
    if signal is not None:
        need(isinstance(signal,dict) and signal.get('symbol')==s and signal.get('side') in ('long','short'),'SIGNAL_IDENTITY')
        need(next_open is not None,'REFERENCE_PLAN_REQUIRED')
        reference=build_plan(SimpleNamespace(**signal),signal_bar_open_ms=t,next_open_ms=hour,next_open=next_open)
        risk=round(abs(reference['stop']-reference['entry'])/reference['entry']*100,3)
    need(o.get('status')==('NO_SIGNAL' if signal is None else 'STREAM_SIGNAL_REQUIRES_FRESH_HTTPS'),'SIGNAL_STATUS')
    return dict(schema_id=SCHEMA,event_id=f'brain-pump4:{hour}:{s}:pair',domain=DOMAIN,
                kind='NO_OPPORTUNITY' if signal is None else 'SHADOW_PAIR',source_sha256=digest(p),
                source_decision_id=d['decision_id'],source_publication_ms=p['publication_completed_ms'],
                hour_ms=hour,symbol=s,observed_ms=observed_ms,epoch_ms=epoch_ms,policy_sha=policy.sha,
                policy_source_sha256=POLICY_SOURCE_SHA,brain_version=policy.version,
                comparison=policy.evaluate(risk),reference_plan=reference,
                context_status='REGIME_UNKNOWN_NOT_USED_BY_PINNED_POLICY',
                pre_live_decision_proven='UNKNOWN',mode='SHADOW',money_authority=False,orders_allowed=False)


def reduce_events(events):
    found={}
    for e in events:
        need(e.get('domain')==DOMAIN and e.get('schema_id')==SCHEMA and e.get('money_authority') is False
             and e.get('orders_allowed') is False,'JOURNAL_DOMAIN')
        need(e['event_id'] not in found,'JOURNAL_DUPLICATE');found[e['event_id']]=e
    return found


def record_pair(path,event,*,clock):
    journal=LifecycleJournal(path,max_bytes=16*1024*1024)
    existing=reduce_events(journal.read());key=event['event_id'];new=False
    if key in existing:
        old=existing[key]
        need(all(old.get(k)==event.get(k) for k in ('source_sha256','policy_sha','policy_source_sha256','epoch_ms')),'SOURCE_CONFLICT')
        event=old
    else:
        new,_=journal.append_checked(event,reduce_events)
    witness_id=key.replace(':pair',':witness')
    if witness_id in existing:return dict(new=False,witness=existing[witness_id])
    completed=clock();need(stamp(completed) and completed>=event['observed_ms'],'DURABLE_CLOCK')
    witness=dict(schema_id=SCHEMA,event_id=witness_id,domain=DOMAIN,kind='DURABILITY_WITNESS',
                 pair_sha256=digest(event),hour_ms=event['hour_ms'],symbol=event['symbol'],
                 decision_durable_by_ms=completed,recovered=not new,
                 prospective=event['source_publication_ms']>=event['epoch_ms'],
                 within_entry_60s=(event['source_publication_ms']>=event['epoch_ms'] and 0<=completed-event['hour_ms']<=60000),
                 money_authority=False,orders_allowed=False)
    journal.append_checked(witness,reduce_events)
    return dict(new=new,witness=witness)


def next_open_from_source(source_root,publication):
    """Replay only allowlisted public WS frames, never follow capture paths."""
    d=publication['decisions'][0]['decision'];s=d.get('symbol');t=d.get('bar_open_ms')
    need(isinstance(s,str) and re.fullmatch('[A-Z0-9]{1,24}USDT',s) and s==publication.get('symbol'),'SYMBOL')
    need(stamp(t) and t>0 and t%H==0,'BAR_TIME');hour=t+H
    folder=Path(source_root)/str(hour);batch=read_json(folder/'batches'/(s+'.json'))
    need(batch['symbol']==s and batch['archive_id']==publication['decisions'][0]['archive_id'],'BATCH_IDENTITY')
    pins=batch.get('raw_captures');need(isinstance(pins,list) and 0<len(pins)<=100,'FRAME_BOUND')
    probe=Probe(hour,[s])
    for pin in pins:
        # Recorded absolute filenames are evidence, not arbitrary read authority.
        name=Path(pin['path']).name;need(re.fullmatch('[1-9][0-9]*[.]json',name) is not None,'FRAME_NAME')
        cap=read_json(folder/'frames'/name)
        need(digest(cap)==pin['sha256'] and cap.get('schema')=='PUMP4_WS_RAW_CAPTURE_V1'
             and cap.get('endpoint')=='wss://stream.bybit.com/v5/public/linear'
             and hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['raw_sha256'],'FRAME_PIN')
        probe.add(cap['raw'],received_ms=cap['received_ms'],connection=cap['connection'])
    summary=probe.summary()['symbols'][s]
    need(not summary['conflict'] and summary['same_connection'] and summary['pair_first_received_ms']==d['available_ms'],'FRAME_PAIR')
    return float(probe.opened[s]['value'])
