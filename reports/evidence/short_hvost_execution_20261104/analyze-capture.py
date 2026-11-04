"""Offline measurement from immutable public GET captures; no strategy/judge/import of money code."""
import json,hashlib,math,sys
from pathlib import Path
from decimal import Decimal as D,ROUND_FLOOR,ROUND_CEILING

def sha(b):return hashlib.sha256(b).hexdigest()
def analyse(p):
 raw=Path(p).read_bytes();capture=json.loads(raw);out=[];bad=[]
 for r in capture['rows']:
  if 'raw' not in r:bad.append(r);continue
  assert sha(r['raw'].encode())==r['raw_sha256'];body=json.loads(r['raw']);assert body['retCode']==0
 def one(symbol,endpoint):
  rows=[r for r in capture['rows'] if r['symbol']==symbol and r['endpoint']==endpoint];assert len(rows)==1
  return json.loads(rows[0]['raw'])['result']['list']
 def vwap(levels,q):
  left=q;value=D(0)
  for price,size in levels:
   used=min(left,D(size));value+=used*D(price);left-=used
   if left==0:break
  assert left==0,'INSUFFICIENT_DISPLAYED_DEPTH'
  return value/q
 funding_cap=D(0)
 for symbol in capture['symbols']:
  i=one(symbol,'/v5/market/instruments-info')[0];t=one(symbol,'/v5/market/tickers')[0];risk=one(symbol,'/v5/market/risk-limit');history=one(symbol,'/v5/market/funding/history')
  assert i['symbol']==t['symbol']==symbol and i['status']=='Trading' and i['quoteCoin']=='USDT' and i['contractType']=='LinearPerpetual'
  tiers=[z for z in risk if z['symbol']==symbol and z['isLowestRisk']==1];assert len(tiers)==1;mm=D(str(tiers[0]['maintenanceMargin']))
  step=D(i['lotSizeFilter']['qtyStep']);minimum=D(i['lotSizeFilter']['minOrderQty']);minN=D(i['lotSizeFilter']['minNotionalValue']);ask=D(t['ask1Price']);minqty=max(minimum,(minN/ask/step).to_integral_value(rounding=ROUND_CEILING)*step)
  samples=[]
  for row in capture['rows']:
   if row['symbol']!=symbol or not row['endpoint'].endswith('orderbook'):continue
   b=json.loads(row['raw'])['result'];assert b['s']==symbol
   asks=sorted(b['a'],key=lambda z:D(z[0]));bids=sorted(b['b'],key=lambda z:-D(z[0]));mid=(D(asks[0][0])+D(bids[0][0]))/2
   q=(D(50)/mid/step).to_integral_value(rounding=ROUND_FLOOR)*step
   legal=q>=minimum and q*mid>=minN
   # Tiny budget can be below min BTC lot; measure legal minimum as a separate sample.
   measured=q if legal else minqty
   buy=vwap(asks,measured);sell=vwap(bids,measured)
   samples.append(dict(sample=row['sample'],request_ms=row['request_ms'],received_ms=row['received_ms'],venue_ms=b['ts'],quote_to_receive_ms=row['received_ms']-b['ts'],quantity=str(measured),at_50_usd_legal=legal,spread_bps=str((D(asks[0][0])-D(bids[0][0]))/mid*10000),displayed_roundtrip_bps=str((buy-sell)/mid*10000),buy_vwap=str(buy),sell_vwap=str(sell)))
  assert len(samples)==10
  values=sorted(D(z['displayed_roundtrip_bps']) for z in samples);p90=values[math.ceil(.9*len(values))-1]
  rate=D(i['upperFundingRate']) if symbol=='BTCUSDT' else -D(i['lowerFundingRate']);n=math.ceil(16*60/i['fundingInterval']);N=D(150) if symbol=='BTCUSDT' else D(50);funding_cap+=N*rate*n
  out.append(dict(symbol=symbol,min_qty=str(minqty),qty_step=str(step),min_trade_notional_at_ask=str(minqty*ask),minimum_notional_filter=str(minN),mark=t['markPrice'],bid=t['bid1Price'],ask=t['ask1Price'],maintenance_margin=str(mm),short_1x_liquidation_ratio_ignoring_fee_extra_margin=str(2/(1+mm)),stop80_buffer_entry_percentage_points=str((2/(1+mm)-D('1.8'))*100),min_leverage=i['leverageFilter']['minLeverage'],funding_interval_minutes=i['fundingInterval'],current_predicted_funding_rate=t['fundingRate'],history_last8=[{k:z[k] for k in ['fundingRate','fundingRateTimestamp']} for z in history],sixteen_hour_current_cap_constant_notional_reserve=str(N*rate*n),samples=samples,short_window_p90_roundtrip_spread_depth_bps=str(p90),signal_time_p90_qualified=False,actual_account_fee_rate=None))
 btc=out[-1];ask=D(btc['ask']);step=D(btc['qty_step']);hedges=[]
 for N in (50,100,150):
  down=(D(N)/ask/step).to_integral_value(rounding=ROUND_FLOOR)*step;up=(D(N)/ask/step).to_integral_value(rounding=ROUND_CEILING)*step
  hedges.append(dict(target_hedge_notional=N,floor_qty=str(down),floor_notional=str(down*ask),ceil_qty=str(up),ceil_notional=str(up*ask),floor_legal=down>=D(btc['min_qty']),exact_nominal_possible=down*ask==D(N),ceil_exceeds_target=up*ask>D(N)))
 return dict(schema='SHORT_HVOST_EXECUTION_RECON_RESULT_V1',observed_ms=capture['observed_ms'],capture_sha256=sha(raw),public_get_requests=len(capture['rows']),errors=bad,symbols=out,hedge_rounding=hedges,margin_only_three_pairs_1x_1x='300',margin_only_three_pairs_alt1x_btc3x='200',illustrative_fee_rate_per_side='.00055',actual_account_fee_known=False,three_pair_roundtrip_fees_constant_notional_scenario='.33',sixteen_hour_current_cap_constant_notional_funding_reserve=str(funding_cap),illustrative_1x_capital_with_scenario_fees_and_funding=str(D(300)+D('.33')+funding_cap),finite_safe_minimum_capital_proven=False,exact_50usd_pairs_executable=False,verdict='BLOCKED',economic_pass=False,order_posts=0,account_mutations=0)
if __name__=='__main__':print(json.dumps(analyse(sys.argv[1]),sort_keys=True,indent=2))
