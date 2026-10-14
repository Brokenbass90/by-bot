"""Independent KITY_BYBIT C2 reconstruction, frozen cb47f0e; orders OFF.

Read the closed-day raw trades and independently captured closed candles.
No import of Claude's shadow/comparator, account client, network or PnL judge.
Source validation failures are BLOCKED_DATA, never a smaller padded universe.
"""
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path

RESEARCH_REF='cb47f0eb57e7a64ea5fcb948d7ae12d617c2abe1'
DAY=86400000
MAX_COMPRESSED=1024**3
MAX_UNCOMPRESSED=8*1024**3


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def safe_path(value,*,exists=False):
    p=Path(value)
    require(p.is_absolute() and '..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'SOURCE_PATH_IDENTITY')
    if exists:require(p.is_file() and p.stat().st_nlink==1 and p.stat().st_uid==os.getuid(),'SOURCE_FILE_CUSTODY')
    return p


def read_json(value):
    def pairs(rows):
        require(len(dict(rows))==len(rows),'DUPLICATE_JSON_KEY');return dict(rows)
    return json.loads(safe_path(value,exists=True).read_text(),object_pairs_hook=pairs)


def require(ok,reason):
    if not ok:raise ValueError(reason)


def finite(value,reason):
    require(not isinstance(value,bool),reason)
    x=float(value);require(math.isfinite(x) and x>=0,reason);return x


def timestamp(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(t.tzinfo is not None,'SOURCE_TIMEZONE_REQUIRED')
    return int(t.timestamp()*1000)


def verified_path(row):
    p=safe_path(row['path'],exists=True)
    with p.open('rb') as f:
        h=hashlib.file_digest(f,'sha256').hexdigest()
    require(h==row['sha256'],'SOURCE_PIN_CONFLICT')
    return p


def candle_eligible(row,symbol,start,now_ms):
    capture=read_json(str(verified_path(row)))
    require(capture['venue']=='BYBIT' and capture['endpoint']=='/v5/market/kline'
        and capture['params']['category']=='linear' and capture['params']['symbol']==symbol
        and capture['params']['interval']=='D' and capture['params']['end']==start-1,'CANDLE_REQUEST_IDENTITY')
    require(0<=capture['request_ms']<=capture['receive_ms']<=now_ms,'CANDLE_CAPTURE_FUTURE')
    require(capture['request_ms']>=start,'CANDLE_CAPTURE_NOT_CLOSED_SOURCE')
    raw=capture['raw'];require(hashlib.sha256(raw.encode()).hexdigest()==capture['sha256'],'CANDLE_RAW_PIN_CONFLICT')
    response=json.loads(raw);require(response['retCode']==0,'CANDLE_GET_FAILED')
    rows=response['result']['list'];opens=[int(r[0]) for r in rows]
    require(len(set(opens))==len(opens) and all(t%DAY==0 and t+DAY<=start for t in opens),'CANDLE_CLOSED_IDENTITY')
    return len(opens)>=60 and max(opens,default=-1)==start-DAY


def taker_share(row,symbol,start):
    p=verified_path(row);require(p.suffix=='.gz' and p.stat().st_size<=MAX_COMPRESSED,'ARCHIVE_RESOURCE_BOUND')
    before=p.stat();buy=sell=0.;count=0
    with p.open('rb') as compressed:
        with gzip.GzipFile(fileobj=compressed) as stream:
            text=io.TextIOWrapper(stream,encoding='utf-8');reader=csv.DictReader(text)
            require({'side','size','price'}.issubset(reader.fieldnames or []),'TRADE_COLUMNS_REQUIRED')
            for trade in reader:
                count+=1;require(stream.tell()<=MAX_UNCOMPRESSED,'ARCHIVE_RESOURCE_BOUND')
                require(trade['side'] in {'Buy','Sell'},'TRADE_SIDE_UNKNOWN')
                if 'symbol' in trade:require(trade['symbol']==symbol,'TRADE_SYMBOL_CONFLICT')
                if 'timestamp' in trade:
                    t=finite(trade['timestamp'],'TRADE_TIME_INVALID')*1000
                    require(start-DAY<=t<start,'TRADE_DAY_CONFLICT')
                v=finite(trade.get('foreignNotional') or 0,'TRADE_VALUE_INVALID')
                if not v:v=finite(trade['size'],'TRADE_VALUE_INVALID')*finite(trade['price'],'TRADE_VALUE_INVALID')
                require(math.isfinite(v),'TRADE_VALUE_INVALID')
                if trade['side']=='Buy':buy+=v
                else:sell+=v
    after=p.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'ARCHIVE_CHANGED_DURING_READ')
    require(count>0 and math.isfinite(buy+sell) and buy+sell>0,'ARCHIVE_TOTAL_INVALID')
    return buy/(buy+sell)


def reconstruct(bundle,*,now_ms):
    try:
        require(bundle['schema']=='KITY_BYBIT_C2_INPUT_V1' and bundle['research_ref']==RESEARCH_REF,'FROZEN_RESEARCH_IDENTITY')
        day=bundle['day'];start=timestamp(day+'T00:00:00Z')
        require(start<=now_ms,'DECISION_DAY_FUTURE')
        snapshot=read_json(str(verified_path(bundle['snapshot'])))
        stamp=timestamp(snapshot['vremya'])
        # Bybit-native prereg allows23:50–23:59; M3's exact23:55 is a different version.
        require(start-600000<=stamp<start and stamp<=now_ms,'FROZEN_SNAPSHOT_WINDOW')
        oi=snapshot['oi_usd'];require(bool(oi),'SNAPSHOT_EMPTY')
        for s,v in oi.items():
            require(s in snapshot['instrumenty'],'SNAPSHOT_INSTRUMENT_REQUIRED');finite(v,'OI_VALUE_INVALID')
        top=sorted(oi,key=lambda s:-float(oi[s]))[:50]  # Stable order from the frozen snapshot.
        features={};hashes={};sources=[bundle['snapshot']];ineligible=[]
        for s in top:
            require(s in bundle['candles'],'CANDLES_REQUIRED')
            sources.append(bundle['candles'][s])
            if not candle_eligible(bundle['candles'][s],s,start,now_ms):ineligible.append(s);continue
            require(s in bundle['archives'],'ARCHIVE_REQUIRED')
            features[s]=taker_share(bundle['archives'][s],s,start)
            hashes[s]=bundle['archives'][s]['sha256'];sources.append(bundle['archives'][s])
        require(len(features)>=30,'FROZEN_MINIMUM_30_NOT_MET')
        ranked=sorted(features,key=lambda s:(features[s],s));k=len(ranked)//10
        out=dict(schema='KITY_BYBIT_C2_RECONSTRUCTION_V1',status='C2_RECONSTRUCTED_ORDERS_OFF',
            d=day,research_ref=RESEARCH_REF,vse_priznaki=features,long=ranked[-k:],short=ranked[:k],
            arhiv_sha256=hashes,top=top,feature_ineligible=ineligible,source_bundle=json.loads(canonical(bundle)),source_files=sources,
            source_manifest_sha256=digest(sources),observed_ms=now_ms,
            orders_allowed=False,money_ready=False,evidence_kind='LOCAL_RAW_RECONSTRUCTION_NOT_C1_OR_ACCOUNT_PASS')
        out['receipt_sha256']=digest(out);return out
    except (ValueError,KeyError,TypeError,OSError,EOFError,ArithmeticError,csv.Error) as exc:
        return dict(status='BLOCKED_DATA',reason=str(exc),orders_allowed=False,money_ready=False)


def compare(codex,signal,flow):
    problems=[]
    try:
        require(codex.get('status')=='C2_RECONSTRUCTED_ORDERS_OFF','INDEPENDENT_RECONSTRUCTION_REQUIRED')
        require(codex['receipt_sha256']==digest({k:v for k,v in codex.items() if k!='receipt_sha256'}),'INDEPENDENT_RECEIPT_PIN_CONFLICT')
        require(reconstruct(codex['source_bundle'],now_ms=codex['observed_ms'])==codex,'INDEPENDENT_RAW_REPLAY_CONFLICT')
        require(codex['d']==signal['d'],'DECISION_DAY_MISMATCH')
        a=codex['vse_priznaki'];b=signal['vse_priznaki']
        require(set(a)==set(b),'FEATURE_POPULATION_MISMATCH')
        require(set(codex['arhiv_sha256'])==set(a),'EXACT_ARCHIVE_HASH_COVERAGE_REQUIRED')
        for s,v in a.items():
            require(s in flow and isinstance(flow[s],dict) and flow[s]['sha256']==codex['arhiv_sha256'][s],'ARCHIVE_HASH_MISMATCH:'+s)
            other=finite(b[s],'FEATURE_NONFINITE');require(0<=v<=1 and other<=1,'FEATURE_RANGE')
            if abs(v-other)>=1e-6:problems.append('FEATURE_TOLERANCE:'+s)
        for side in ('long','short'):
            names=[n['s'] for n in signal[side]]
            if len(names)!=len(set(names)) or set(codex[side])!=set(names):problems.append('BASKET_MISMATCH:'+side)
    except (ValueError,KeyError,TypeError,ArithmeticError) as exc:problems.append(str(exc))
    return dict(status='C2_FAIL' if problems else 'C2_PASS_MATCH_ONLY',d=codex.get('d'),problems=problems,
        orders_allowed=False,money_ready=False,independent_reconstruction_sha256=codex.get('receipt_sha256'),
        limitation='Signal/raw-feature parity only; C1/C3/account execution and owner GO remain separate')
