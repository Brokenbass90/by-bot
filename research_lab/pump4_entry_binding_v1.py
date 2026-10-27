"""Explicit <=60s entry contract; no clock rebasing or implicit money authority.

Reference-open drift and execution-impact slippage are different quantities.
The numeric drift proposal requires a new exact owner scope/GO before money.
"""
import copy,sys,base64,zlib,json
from pathlib import Path
from decimal import Decimal as D
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.pump4_bybit_sources_v1 import checked,number,H
from research_lab.pump4_native_stop_v1 import SCHEMA as MAPPER_SCHEMA

POLICY='PUMP4_EXPLICIT_ENTRY_EXECUTION_POLICY_V1'
BINDING='PUMP4_CAUSAL_DELAYED_ENTRY_BINDING_V1'
def need(ok,why):
    if not ok:raise ValueError('PUMP4_ENTRY_'+why)

def pack_quote(cap):
    value=dict(schema='PUMP4_COMPRESSED_PUBLIC_QUOTE_V1',metadata={k:copy.deepcopy(v) for k,v in cap.items() if k not in ('raw','body')},
        raw_zlib_b64=base64.b64encode(zlib.compress(cap['raw'].encode())).decode())
    need(len(json.dumps(value).encode())<=262144,'QUOTE_EVIDENCE_BOUND');return value

def unpack_quote(value):
    need(value.get('schema')=='PUMP4_COMPRESSED_PUBLIC_QUOTE_V1' and len(value['raw_zlib_b64'])<=262144,'QUOTE_EVIDENCE_SCHEMA')
    try:
        z=zlib.decompressobj();raw=z.decompress(base64.b64decode(value['raw_zlib_b64'],validate=True),5000001)
        need(len(raw)<=5000000 and z.eof and not z.unused_data and not z.unconsumed_tail,'QUOTE_EVIDENCE_BOUND')
        text=raw.decode();return dict(value['metadata'],raw=text,body=json.loads(text))
    except (ValueError,TypeError,zlib.error,UnicodeError) as exc:raise ValueError('PUMP4_ENTRY_QUOTE_EVIDENCE') from exc

def execution_policy(risk_policy,*,max_reference_drift_bps,max_delay_ms=60000):
    from research_lab.pump4_selected_runner_v1 import source_pins
    return dict(schema=POLICY,max_delay_ms=max_delay_ms,max_reference_drift_bps=str(max_reference_drift_bps),
        native_stop_schema=MAPPER_SCHEMA,source_manifest_sha256=digest(source_pins()),risk_policy_sha256=digest(risk_policy),
        quote_convention='LAST_PRICE_GEOMETRY_BID_ASK_EXECUTION',interval_policy='REJECT_PRIOR_NATIVE_STOP_OR_TP1_TOUCH')

def verify_policy(policy,risk_policy=None,*,verify_sources=True):
    need(isinstance(policy,dict) and set(policy)=={'schema','max_delay_ms','max_reference_drift_bps','native_stop_schema','source_manifest_sha256','risk_policy_sha256','quote_convention','interval_policy'},'POLICY_SCHEMA')
    need(policy['schema']==POLICY and type(policy['max_delay_ms']) is int and 0<policy['max_delay_ms']<=60000,'POLICY_DELAY')
    drift=number(policy['max_reference_drift_bps'],zero=True);need(drift<10000,'POLICY_DRIFT')
    need(policy['native_stop_schema']==MAPPER_SCHEMA and policy['quote_convention']=='LAST_PRICE_GEOMETRY_BID_ASK_EXECUTION'
        and policy['interval_policy']=='REJECT_PRIOR_NATIVE_STOP_OR_TP1_TOUCH','POLICY_CONVENTION')
    need(all(type(policy[k]) is str and len(policy[k])==64 and all(c in '0123456789abcdef' for c in policy[k])
        for k in ('source_manifest_sha256','risk_policy_sha256')),'POLICY_HASH')
    if risk_policy is not None:need(policy['risk_policy_sha256']==digest(risk_policy),'RISK_POLICY_CHANGED')
    if verify_sources:
        from research_lab.pump4_selected_runner_v1 import source_pins
        need(policy['source_manifest_sha256']==digest(source_pins()),'SOURCE_MANIFEST_CHANGED')
        root=Path(__file__).absolute().parents[1]
        for name in ('pump4_entry_binding_v1','pump4_native_stop_v1','pump4_account_owner_v1','pump4_account_adapter_v1','pump4_execution_lifecycle_v1','pump4_selected_runner_v1','pump4_runtime_sources_v1'):
            module=sys.modules.get('research_lab.'+name)
            if module is not None:need(Path(module.__file__).absolute()==root/'research_lab'/(name+'.py'),'LOADED_SOURCE_ORIGIN')
    return policy

def _bind(plan,policy,public,native_stop,now,*,verify_sources):
    verify_policy(policy,verify_sources=verify_sources)
    need(plan['plan_sha256']==digest({k:v for k,v in plan.items() if k!='plan_sha256'}),'PLAN_HASH')
    entry_ms=plan['entry_bar_open_ms'];need(type(now) is int and 0<=now-entry_ms<=policy['max_delay_ms'],'DEADLINE')
    quote=public['quote'];path=public['entry_interval'];symbol=plan['symbol'];short=plan['side']=='short'
    need(plan['side'] in ('short','long') and quote['params']==dict(category='linear'),'QUOTE_SCOPE')
    ticks=checked(quote,'/v5/market/tickers',now_ms=now,private=False)['list'];rows=[r for r in ticks if r['symbol']==symbol];need(len(rows)==1,'QUOTE_IDENTITY');ticker=rows[0]
    body=checked(path,'/v5/market/kline',now_ms=now,private=False)
    need(len(path['raw'].encode())<=65536,'INTERVAL_EVIDENCE_BOUND')
    need(path['params']==dict(category='linear',symbol=symbol,interval='60',start=entry_ms,end=entry_ms+H-1,limit=1)
        and body.get('symbol')==symbol and body.get('category')=='linear' and len(body['list'])==1,'INTERVAL_SCOPE')
    need(all(0<=now-c['request_ms']<=5000 and 0<=now-c['body']['time']<=5000 for c in (quote,path)),'SOURCE_STALE')
    need(path['body']['time']>=quote['body']['time']>=entry_ms,'INTERVAL_ASOF')
    raw=body['list'][0];need(isinstance(raw,list) and len(raw)==7 and int(raw[0])==entry_ms,'INTERVAL_BAR')
    number(raw[5],zero=True);number(raw[6],zero=True)
    o,h,l,c=map(number,raw[1:5]);entry=number(plan['entry']);native=number(native_stop);target=number(plan['targets'][0]);last=number(ticker['lastPrice']);executable=number(ticker['bid1Price'] if short else ticker['ask1Price'])
    need(o==entry and l<=min(o,c)<=max(o,c)<=h and l<=last<=h,'INTERVAL_OHLC')
    need((entry<native<=number(plan['stop']) and target<executable<native and target<last<native
          and h<native and l>target) if short else
         (number(plan['stop'])<=native<entry and native<executable<target and native<last<target
          and l>native and h<target),'PRIOR_STOP_OR_TARGET_TOUCH')
    drift=abs(executable-entry)/entry*10000;need(drift<=number(policy['max_reference_drift_bps'],zero=True),'REFERENCE_DRIFT')
    return dict(schema=BINDING,plan_sha256=plan['plan_sha256'],policy=copy.deepcopy(policy),policy_sha256=digest(policy),
        max_delay_ms=policy['max_delay_ms'],valid_until_ms=entry_ms+policy['max_delay_ms'],observed_ms=now,
        reference_entry=str(plan['entry']),native_stop=str(native),execution_quote_price=str(executable),
        last_price=str(last),reference_drift_bps=str(drift),quote_capture=pack_quote(quote),entry_interval_capture=copy.deepcopy(path),
        source_ms=min(quote['request_ms'],quote['body']['time'],path['request_ms'],path['body']['time']),
        orders_allowed=False,money_authority=False)

def bind_entry(plan,policy,public,native_stop,*,now_ms):
    return _bind(plan,policy,public,native_stop,now_ms,verify_sources=True)

def verify_binding(plan,binding,*,now_ms):
    need(isinstance(binding,dict) and binding.get('schema')==BINDING and binding['observed_ms']<=now_ms,'BINDING_SCHEMA_OR_CLOCK')
    public=dict(quote=unpack_quote(binding['quote_capture']),entry_interval=binding['entry_interval_capture'])
    original=_bind(plan,binding['policy'],public,binding['native_stop'],binding['observed_ms'],verify_sources=False)
    need(original==binding,'BINDING_CHANGED')
    _bind(plan,binding['policy'],public,binding['native_stop'],now_ms,verify_sources=False)
    return binding
