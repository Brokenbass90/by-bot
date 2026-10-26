"""Offline exact84+open1 signal/init parity and cost arithmetic; no evaluator."""
from pathlib import Path
import sys,json,gzip,hashlib,dataclasses,statistics
from decimal import Decimal as D
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parents[2]));H=3600000
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_execution_plan_v1 import frozen_sources
from research_lab.att1_lifecycle_journal import SCHEMA
from strategies.pump_fade_v4r import PumpFadeV4RStrategy
frozen_sources();m=json.loads((P/'signal-inputs-manifest.json').read_bytes());raw=(P/'signal-inputs.json.gz').read_bytes();assert hashlib.sha256(raw).hexdigest()==m['sha256'];raw=gzip.decompress(raw);assert hashlib.sha256(raw).hexdigest()==m['decoded_sha256'];d=json.loads(raw)
saved=json.loads((P/'parity.json').read_bytes());expect={(x['sym'],x['ts']):x for x in saved['rows']};closed=0;opened=0
for sym,bars in d['bars'].items():
    s=PumpFadeV4RStrategy();signals={}
    for b in bars:
        before=s._cooldown;v=s.maybe_signal(sym,*b)
        if v is not None:signals[b[0]]=dict(signal=dataclasses.asdict(v),cooldown_before=before,cooldown_after=s._cooldown,buffer_bars=len(s._closes))
    intake=Pump4Intake(P/'NEVER_CREATED'/sym,sym);ctx=intake._context();seed=bars[:1000]
    events=[dict(schema_id=SCHEMA,event_id='pump4:'+sym+':seed',**ctx,kind='HISTORICAL_SEED',bars=seed,available_ms=seed[-1][0]+H,observed_ms=seed[-1][0]+H)]
    events += [dict(schema_id=SCHEMA,event_id='pump4:'+sym+':'+str(b[0]),**ctx,kind='CLOSED_BAR',bar=b,available_ms=b[0]+H,observed_ms=b[0]+H) for b in bars[1000:]]
    decisions={x['bar_open_ms']:x for x in intake._replay(events)['decisions']}
    for (symbol,ts),row in expect.items():
        if symbol!=sym:continue
        assert signals[ts]==row['research_schedule']
        assert decisions[ts]==row['intake_decision']
        assert signals[ts]['signal']==decisions[ts]['signal']
        assert signals[ts]['cooldown_after']==decisions[ts]['cooldown_remaining']==24
        if row['cohort']=='CLOSED84':closed+=1
        else:opened+=1
assert (closed,opened)==(84,1)
c=json.loads((P/'cost-lot.json').read_bytes());meta=json.loads((P/'cost-lot-source-summary.json').read_bytes());plans={(x['sym'],x['ts']):x['plan'] for x in c['plans']};values=[];tick_ok=0
for row in c['rows']:
    plan=plans[row['sym'],row['ts']];width=abs(plan['stop']-plan['entry'])/plan['entry'];fee=float(meta['fees'][row['sym']]['takerFeeRate']);slip=float(meta['policy']['slippage_bps'])/10000
    value=row['reported_R']+row['reported_model_fee_R']-2*(fee+slip)/width;assert abs(value-row['after_fee_and_slippage_before_funding_R'])<1e-12;values.append(value)
    tick=D(meta['instruments'][row['sym']]['priceFilter']['tickSize']);tick_ok+=D(str(plan['stop']))%tick==0
assert tick_ok==0 and abs(statistics.mean(values)-c['summary']['after_observed_fee_and_10bps_slippage_before_funding_mean_R'])<1e-12
print(json.dumps(dict(status='PASS',closed_signal_init_parity=closed,open_signal_init_parity=opened,native_stops_exactly_representable=tick_ok,after_fee_slip_before_funding_R=statistics.mean(values),economic_verdict='INCONCLUSIVE',PnL_evaluator_calls=0,broker_requests=0,financial_authority=False)))
