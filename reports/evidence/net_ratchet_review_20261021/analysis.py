"""Deterministic rule review only; no historical simulator or broker execution."""
import hashlib,json,socket,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
source=root/'scripts/alpaca_protective_exit_manager.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='2d5243ee52d3857c14fd564cea671f8938dd1cdc7623f360293154c8bce5eea1'
def denied(*a,**k):raise AssertionError('READ_ONLY_ANALYSIS_NETWORK_FORBIDDEN')
class NoNetwork(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=NoNetwork;socket.create_connection=denied
from scripts import alpaca_protective_exit_manager as ratchet
ratchet.AlpacaClient=denied
settings=dict(trail_pct=3.5,min_lock_gain_pct=.5,min_raise_bps=10.,market_gap_bps=10.)
# Normalized units; no private account amount/order/position is published.
order=dict(id='synthetic-owned-stop',symbol='NET',side='sell',type='stop',status='new',
    qty='1',filled_qty='0',stop_price='89.23',time_in_force='day')
def plan(activation,mark,hwm):
 rows,_=ratchet.build_ratchet_plan([dict(symbol='NET',qty='1',avg_entry_price='100',current_price=str(mark))],
  [order],dict(NET=dict(entry_price=100.,hwm=hwm,accepted_stop_floor=89.23)),
  activate_gain_pct=activation,**settings)
 assert len(rows)==1
 return rows[0]
rows=[]
for threshold in [1.,2.,3.5]:
 mark=100+threshold;r=plan(threshold,mark,mark)
 assert r['action']=='replace_stop' and r['target_stop']==100.49
 rows.append(dict(activation_gain_pct=threshold,first_observed_price=mark,
  proposed_stop=r['target_stop'],gross_gain_at_stop_pct=r['locked_gain_pct_at_stop'],
  effective_gap_from_mark_pct=(1-r['target_stop']/mark)*100))
late=plan(1.,99.45,101.38)
assert late['target_stop']<100  # min-lock is capped by current mark; no guaranteed profit.
# Sensitivity defined as total round-trip cost divided by reference entry capital.
gross=rows[0]['gross_gain_at_stop_pct']
costs=[dict(total_round_trip_cost_bps=bps,gross_gain_pct=gross,model_net_gain_pct=gross-bps/100)
 for bps in [10,20,40,60]]
data=root/'research_lab/data/alpaca_pit_daily_v1/bars/NET.json';raw=data.read_bytes();d=json.loads(raw)
bars=d['records'];timestamps=[b['t'] for b in bars]
assert len(timestamps)==len(set(timestamps)) and timestamps==sorted(timestamps)
assert all(0<b['l']<=min(b['o'],b['c'])<=max(b['o'],b['c'])<=b['h'] for b in bars)
out=dict(schema='NET_RATCHET_RULE_REVIEW_V1',status='RULE_REPRODUCTION_PASS_HISTORICAL_COMPARISON_BLOCKED_DATA',
 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),settings=settings,
 assumptions='Normalized entry100, first threshold sampled exactly, mark=HWM, original stop89.23; no fill or fee guarantee',
 threshold_cases=rows,late_observation_case=dict(activation_pct=1.,mark=99.45,hwm=101.38,proposed_stop=late['target_stop']),
 cost_sensitivity=costs,cost_model='Hypothetical total entry+exit fees/spread/slippage in bps of entry capital, not actual broker charges; no gap model',
 inspected_daily_source=dict(path=str(data.relative_to(root)),sha256=hashlib.sha256(raw).hexdigest(),rows=len(bars),
  first_utc=datetime.fromtimestamp(min(timestamps)/1000,timezone.utc).isoformat(),
  last_utc=datetime.fromtimestamp(max(timestamps)/1000,timezone.utc).isoformat(),
  duplicate_timestamps=0,ohlc_valid=True,grain='DAILY_NOT_5MIN_QUOTE_MARKS'),
 historical_metrics=dict(threshold_reach_counts=None,mean_net_pnl=None,max_drawdown=None,premature_exit_frequency=None),
 blocker='No verified same-entry historical NET lifecycle set paired with 5min broker marks, DAY rearm/replace timing and actual fills/costs in inspected inputs; H6 aggregates are Monthly, not legacy NET',
 research_judges_run=False,strategy_code_changed=False,live_changed=False,broker_requests=0,broker_writes=0,money_authority=False)
assert hashlib.sha256(source.read_bytes()).hexdigest()==out['source_sha256']
assert hashlib.sha256(data.read_bytes()).hexdigest()==out['inspected_daily_source']['sha256']
dest=Path(sys.argv[1]);assert not dest.exists()
with dest.open('x') as f:f.write(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(status=out['status'],cases=rows,daily_rows=len(bars),late_proposed_stop=late['target_stop'],broker_writes=0)))
