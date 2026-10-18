"""First physical ETS2S decision intake into the existing shadow HedgeBook.

Only the pinned producer's ordered decision prefix is decoded. Parsing stops
before non-decision fields, including terminal R/rr/PnL. No producer, regime
calculator, outcome evaluator, broker or monetary controller is run.
Intake receipts are not prospective hedge decisions or parity credit.
"""
from collections import Counter
import json
import os
from pathlib import Path
import stat

from research_lab.elder_hedge_orders_off_v1 import HedgeBook, sha, H, control_geometry, report_event

PRODUCER_SHA256='2eb740e6a3c0df0d72b1c40a92ab8a1b5cec920d1ae6200f70e66e4c6d988d6f'
FIELDS={'ts','sym','side','zapisano','zapozdanie_ch','vovremya','geom'}
MAX_BYTES=16*1024*1024


def decision_prefix(raw):
    """Decode decision fields in producer order; never decode a terminal value."""
    text=raw.decode('utf-8');decoder=json.JSONDecoder();out={};i=0
    def space(p):
        while p<len(text) and text[p].isspace():p+=1
        return p
    i=space(i)
    if i>=len(text) or text[i]!='{':raise ValueError('ELDER_DECISION_OBJECT')
    i+=1
    while True:
        i=space(i)
        if i>=len(text):raise ValueError('ELDER_DECISION_PREFIX_INCOMPLETE')
        if text[i]=='}':return out,text[:i].encode()
        key,i=decoder.raw_decode(text,i);i=space(i)
        if not isinstance(key,str) or i>=len(text) or text[i]!=':':raise ValueError('ELDER_DECISION_KEY')
        if key not in FIELDS:return out,text[:i].encode()
        if key in out:raise ValueError('ELDER_DECISION_DUPLICATE_KEY')
        value,i=decoder.raw_decode(text,space(i+1));out[key]=value
        if key=='geom':return out,text[:i].encode()
        i=space(i)
        if i<len(text) and text[i]==',':i+=1
        elif i>=len(text) or text[i]!='}':raise ValueError('ELDER_DECISION_PREFIX_INCOMPLETE')


def bounded_source(path):
    p=Path(path).absolute()
    if any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('ELDER_SOURCE_SYMLINK')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>MAX_BYTES:raise ValueError('ELDER_SOURCE_BOUND')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(MAX_BYTES+1)
        after=os.fstat(fd)
        if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):raise ValueError('ELDER_SOURCE_CHANGED')
        if raw and not raw.endswith(b'\n'):raise ValueError('ELDER_SOURCE_PARTIAL_TAIL')
        return raw
    finally:os.close(fd)


def contexts_from_brain(opportunities,*,now_ms):
    """Join the existing hash-chained ContextRecord, never recompute its regime.

    bar_ts is a closed H1 bar OPEN in the pinned producer. Availability is the
    actual outer record time, never the earlier backfilled decision time.
    """
    from research_lab.brain_shadow_readonly_bridge_v1 import _read_chain
    out={}
    for row in _read_chain(Path(opportunities)):
        if row.get('sleeve')!='ELDER' or row.get('side')!=-1:continue
        ref=row.get('source_ref','')
        if not ref.startswith('data/ten_ETS2S.jsonl#'):continue
        symbol,ts=ref.split('#',1)[1].rsplit(':',1);ts=int(ts)
        if symbol!=row['symbol'] or row['t_observation_ms']!=ts+H:raise ValueError('ELDER_CONTEXT_JOIN_IDENTITY')
        ctx=row['context'];bar=ctx.get('bar_ts');available=row['t_recorded_ms']
        if type(bar) is not int or type(available) is not int or not 0<bar+H<=ts+H<=available<=now_ms:
            continue # UNKNOWN context remains missing; no artificial timestamp
        key=symbol+':'+str(ts)
        value=dict(signal_bar_open_ms=ts,observed_ms=bar+H,available_ms=available,
            rezhim_v1=ctx.get('rezhim_v1'),source_sha256=row['record_hash'],
            brain_decision_source_sha256=row['source_sha256'])
        if key in out and out[key]!=value:raise ValueError('ELDER_CONTEXT_DUPLICATE_CONFLICT')
        out[key]=value
    return out


def receive(source,*,producer,producer_sha256,book,contexts,now_ms):
    if sha(Path(producer).read_bytes())!=producer_sha256:raise ValueError('ELDER_PRODUCER_PIN')
    if type(now_ms) is not int or now_ms<=0:raise ValueError('ELDER_INTAKE_CLOCK')
    raw=bounded_source(source);source_id=sha(str(Path(source).absolute()).encode())
    rows=[];seen=set()
    for line_no,line in enumerate(raw.splitlines(keepends=True),1):
        if not line.strip():raise ValueError('ELDER_SOURCE_BLANK_ROW')
        if len(line)>131072:raise ValueError('ELDER_SOURCE_ROW_BOUND')
        fields,prefix=decision_prefix(line)
        ts,symbol=fields.get('ts'),fields.get('sym')
        if type(ts) is not int or ts<=0 or not isinstance(symbol,str):raise ValueError('ELDER_DECISION_IDENTITY')
        key=(symbol,ts)
        if key in seen:continue
        seen.add(key) # first physical record wins, including a long/geometry-free row
        if fields.get('side')!='short':continue
        rows.append((line_no,line,fields,prefix))
    store=HedgeBook(book);new=0;already=0;counts=Counter();joined=0
    try:
        prior=[json.loads(x[0]) for x in store.db.execute('SELECT body FROM elder_intents')]
        if any(x.get('source_id')!=source_id for x in prior):raise ValueError('ELDER_INTAKE_SOURCE_IDENTITY')
        for seal in (x for x in prior if x.get('receipt_kind')=='SOURCE_PREFIX_SEAL'):
            n=seal['prefix_bytes']
            if len(raw)<n or sha(raw[:n])!=seal['prefix_sha256']:raise ValueError('ELDER_SOURCE_PREFIX_CONFLICT')
        indexed={x['opportunity_id']:x for x in prior}
        for line_no,line,fields,prefix in rows:
            key='intake-'+sha(f"{source_id}|{fields['sym']}|{fields['ts']}".encode())[:32]
            old=indexed.get(key)
            if old:
                if old['raw_first_row_sha256']!=sha(line):raise ValueError('ELDER_FIRST_ROW_CONFLICT')
                record=old;already+=1
            else:
                ctx=contexts.get(f"{fields['sym']}:{fields['ts']}")
                reason=None
                try:geometry=control_geometry(fields)
                except (ValueError,KeyError,TypeError):geometry=None;reason='FIRST_RECORD_GEOMETRY_INVALID'
                if geometry is None:reason=reason or 'FIRST_RECORD_GEOMETRY_MISSING'
                elif fields.get('vovremya') is not True:reason='FIRST_RECORD_NOT_TIMELY'
                elif fields['ts']%H or not fields['ts']+H<=fields.get('zapisano',0)<=now_ms:
                    reason='FIRST_RECORD_CLOCK_CONFLICT'
                elif now_ms-fields['ts']>6*H:reason='STALE_AT_INTAKE_NO_BACKDATED_DECISION'
                elif ctx is None:reason='CAUSAL_CONTEXT_REQUIRED'
                else:
                    valid=(ctx.get('signal_bar_open_ms')==fields['ts']
                        and type(ctx.get('observed_ms')) is int and 0<ctx['observed_ms']<=fields['ts']+H
                        and type(ctx.get('available_ms')) is int and ctx['observed_ms']<=ctx['available_ms']<=now_ms
                        and ctx.get('rezhim_v1') in ('BULL_TREND','BEAR_TREND','NEUTRAL','UNKNOWN')
                        and isinstance(ctx.get('source_sha256'),str) and len(ctx['source_sha256'])==64)
                    if ctx.get('brain_decision_source_sha256'):
                        original={k:fields.get(k) for k in ('ts','sym','side','zapisano','vovremya','zapozdanie_ch')}
                        valid=valid and sha(json.dumps(original,sort_keys=True).encode())==ctx['brain_decision_source_sha256']
                    reason='RISK_AND_INSTRUMENT_SNAPSHOT_REQUIRED' if valid else 'CAUSAL_CONTEXT_CONFLICT'
                record=dict(schema='ELDER_FIRST_DECISION_INTAKE_V1',receipt_kind='FIRST_DECISION',
                    opportunity_id=key,source_id=source_id,source_ref=str(Path(source).absolute())+':'+str(line_no),
                    raw_first_row_sha256=sha(line),decision_prefix_sha256=sha(prefix),decision_fields=fields,
                    producer_sha256=producer_sha256,context=ctx,decided_ms=now_ms,reason=reason,
                    symbol=fields['sym'],status='DATA_ONLY_INTAKE_NOT_PARITY_OR_MONEY_PASS',mode='SHADOW',orders_allowed=False,
                    research_evidence_eligible=False,prospective_events_credited=0)
                record['report_event']=report_event(record)
                store.record(record);new+=1
            counts[record['reason']]+=1
            joined+=record['context'] is not None
        seal=dict(receipt_kind='SOURCE_PREFIX_SEAL',source_id=source_id,prefix_bytes=len(raw),
            prefix_sha256=sha(raw),producer_sha256=producer_sha256,mode='SHADOW',orders_allowed=False,
            opportunity_id='seal-'+sha(f'{source_id}|{len(raw)}'.encode()))
        store.record(seal)
    finally:store.close()
    return dict(status='ELDER_EVENT_INTAKE_ORDERS_OFF',source_rows=len(raw.splitlines()),
        source_prefix_bytes=len(raw),source_prefix_sha256=sha(raw),first_short_records=len(rows),
        new_first_short_records=new,already_recorded=already,context_joined=joined,blockers=dict(counts),
        prospective_events_credited=0,orders_allowed=False,broker_requests=0,broker_writes=0)
