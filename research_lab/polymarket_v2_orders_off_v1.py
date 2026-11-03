"""File-only signal/quote measurement; never an execution transport or money grant.

The caller supplies a versioned signal. Its trading rule is NOT re-evaluated or
promoted here. Displayed depth, model fills/fees and later outcomes remain
counterfactual estimates. No wallet, network, broker, supervisor or account import.
"""
from __future__ import annotations
import argparse
from decimal import Decimal,InvalidOperation,localcontext,ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import time

LIMIT=Decimal('0.985')
MODEL_BUDGET=Decimal('100')

def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(x):return hashlib.sha256(encoded(x)).hexdigest()
def _pin(x):return isinstance(x,str) and len(x)==64 and all(c in '0123456789abcdef' for c in x)
def _ms(x):return type(x) is int and x>=0
def _token(x):return isinstance(x,str) and 1<=len(x)<=100 and x.strip()==x and not any(c.isspace() for c in x)

def _number(x):
 if isinstance(x,bool) or x is None:raise ValueError('NUMBER_REQUIRED')
 try:d=Decimal(str(x))
 except (InvalidOperation,ValueError):raise ValueError('NUMBER_REQUIRED') from None
 if not d.is_finite():raise ValueError('NONFINITE_NUMBER')
 return d

def _levels(rows):
 if not isinstance(rows,list):raise ValueError('LADDER_REQUIRED')
 out=[];seen=set()
 for row in rows:
  if not isinstance(row,dict):raise ValueError('LEVEL_OBJECT_REQUIRED')
  price,size=_number(row.get('price')),_number(row.get('size'))
  if not 0<price<1 or size<=0 or price in seen:raise ValueError('INVALID_OR_DUPLICATE_LEVEL')
  seen.add(price);out.append((price,size))
 return out

def measure(signal,book,market,*,decision_ms):
 """Assess actual token asks using captured metadata; return no order or fill."""
 if not all(isinstance(x,dict) for x in (signal,book,market)) or not _ms(decision_ms):raise ValueError('INPUT_SCHEMA')
 issues=[];fatal=[]
 def problem(name,blocks=True):
  issues.append(name)
  if blocks:fatal.append(name)
 out=dict(schema='POLY_V2_READ_ONLY_MEASUREMENT_V1',decision_ms=decision_ms,
  market_id=signal.get('market_id'),token_id=signal.get('token_id'),policy_sha256=signal.get('policy_sha256'),
  capture_mode='CALLER_SUPPLIED_DECISION_TIME_NO_WITNESS',
  market_tokens=market.get('tokens'),fee_source_sha256=market.get('fee_source_sha256'),captured_fee_rate=None,book_source_sha256=book.get('source_sha256'),market_source_sha256=market.get('source_sha256'),
  orders_allowed=False,money_authority=False,real_fill=False,actual_fees=None,actual_net_pnl=None,
  signal_rule_verified=False,prospective_durability_witness=False,
  capital_available_again_ms=None,quote_currency='MODEL_QUOTE_UNITS',
  model_gross=None,model_shares=None,observed_vwap=None,best_ask=None,depth_to_limit=None,
  estimated_fee=None,estimated_win_net=None,estimated_loss_net=None,vwap_minus_model_price=None,
  book_age_ms=None,signal_to_decision_ms=None,depth_sufficient_for_model_100=None,
  model_price=signal.get('model_price'),limit_price=str(LIMIT),model_budget=str(MODEL_BUDGET),
  assumption='DISPLAYED_LEVELS_ONLY_NOT_FILL_OR_QUEUE_PROOF')
 tokens=market.get('tokens')
 if not _token(signal.get('token_id')) or not _token(book.get('asset_id')) or not isinstance(tokens,list) or len(tokens)!=2 or not all(_token(t) for t in tokens) or len(set(tokens))!=2 or signal.get('token_id') not in tokens or book.get('asset_id')!=signal.get('token_id'):problem('TOKEN_MISMATCH')
 if not isinstance(signal.get('market_id'),str) or not signal['market_id'] or signal['market_id']!=market.get('market_id'):problem('MARKET_MISMATCH')
 if not _pin(signal.get('policy_sha256')):problem('POLICY_VERSION_MISSING')
 if not _pin(book.get('source_sha256')) or not _pin(market.get('source_sha256')):problem('SOURCE_HASH_MISSING')
 for obj in (signal,book,market):
  t=obj.get('received_ms')
  if not _ms(t):problem('RECEIVE_TIMESTAMP_MISSING')
  elif t>decision_ms:problem('FUTURE_SOURCE')
 if _ms(book.get('received_ms')):out['book_age_ms']=decision_ms-book['received_ms']
 if _ms(signal.get('received_ms')):out['signal_to_decision_ms']=decision_ms-signal['received_ms']
 if book.get('time_origin') not in {'RESPONSE_RECEIVED','VPS_WS_RECEIVED'}:problem('RECEIVE_TIME_UNPROVEN')
 if book.get('continuity')!='VERIFIED':problem('BOOK_CONTINUITY_UNKNOWN')
 if market.get('accepting_orders') is False:problem('MARKET_NOT_ACCEPTING')
 elif market.get('accepting_orders') is not True:problem('ACCEPTING_STATUS_UNKNOWN')
 try:
  asks=sorted(_levels(book.get('asks')));bids=_levels(book.get('bids'))
  if asks and bids and max(p for p,_ in bids)>=asks[0][0]:raise ValueError('CROSSED_BOOK')
 except ValueError as e:problem(str(e));asks=[]
 fee_rate=None
 if not _pin(market.get('fee_source_sha256')):problem('FEE_SCHEDULE_UNKNOWN',False)
 else:
  try:
   rate=_number(market.get('fee_rate'))
   if not 0<=rate<=1:raise ValueError('FEE_RATE_RANGE')
   fee_rate=rate;out['captured_fee_rate']=str(rate)
  except ValueError:problem('FEE_SCHEDULE_UNKNOWN',False)
 if not set(fatal)-{'MARKET_NOT_ACCEPTING','ACCEPTING_STATUS_UNKNOWN'}:
  with localcontext() as ctx:
   ctx.prec=40
   eligible=[(p,s) for p,s in asks if p<=LIMIT];depth=sum((p*s for p,s in eligible),Decimal(0))
   out.update(best_ask=str(asks[0][0]) if asks else None,depth_to_limit=str(depth),depth_sufficient_for_model_100=depth>=MODEL_BUDGET)
   if not fatal:
    remaining=min(MODEL_BUDGET,depth);gross=remaining;quantity=Decimal(0);fee=Decimal(0)
    for price,size in eligible:
     spent=min(remaining,price*size);shares=spent/price;quantity+=shares;remaining-=spent
     if fee_rate is not None:fee+=(shares*fee_rate*price*(1-price)).quantize(Decimal('.00001'),rounding=ROUND_HALF_UP)
     if remaining==0:break
    if gross<=0:problem('NO_ASK_AT_LIMIT')
    else:
     vwap=gross/quantity;out.update(model_gross=str(gross),model_shares=str(quantity),observed_vwap=str(vwap))
     try:out['vwap_minus_model_price']=str(vwap-_number(signal.get('model_price')))
     except ValueError:pass
     if fee_rate is not None:out.update(estimated_fee=str(fee),estimated_win_net=str(quantity-gross-fee),estimated_loss_net=str(-gross-fee))
 out.update(status='UNKNOWN' if issues else 'MEASURED_ORDERS_OFF',issues=sorted(set(issues)),fee_estimate_assumption='CAPTURED_RATE_C_P_ONE_MINUS_P_ROUNDED_PER_DISPLAYED_LEVEL_NOT_ACTUAL_MATCHES')
 out['measurement_id']=sha(out)
 return out

def join_outcome(receipt,winning_token,*,resolved_ms,joined_ms):
 """Append a model outcome reference; resolution never proves available funds."""
 if receipt.get('schema')!='POLY_V2_READ_ONLY_MEASUREMENT_V1' or not all(_ms(x) for x in (resolved_ms,joined_ms)) or not receipt['decision_ms']<=resolved_ms<=joined_ms:raise ValueError('OUTCOME_TIME')
 if not _token(winning_token) or winning_token not in (receipt.get('market_tokens') or []):raise ValueError('OUTCOME_TOKEN')
 if receipt.get('measurement_id')!=sha({k:v for k,v in receipt.items() if k!='measurement_id'}):raise ValueError('RECEIPT_IDENTITY')
 won=winning_token==receipt['token_id']
 return dict(schema='POLY_V2_MODEL_OUTCOME_JOIN_V1',parent_receipt_sha256=sha(receipt),
  joined_ms=joined_ms,resolution_received_ms=resolved_ms,won=won,
  model_net=receipt['estimated_win_net' if won else 'estimated_loss_net'] if receipt['status']=='MEASURED_ORDERS_OFF' else None,
  model_hold_ms=resolved_ms-receipt['decision_ms'],capital_available_again_ms=None,
  actual_fees=None,actual_net_pnl=None,real_fill=False,money_authority=False,orders_allowed=False)

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ('signal','book','market','destination'):ap.add_argument('--'+n,type=Path,required=True)
 ap.add_argument('--replay-decision-ms',type=int)
 a=ap.parse_args(argv);values=[json.loads(p.read_bytes()) for p in (a.signal,a.book,a.market)]
 r=measure(*values,decision_ms=a.replay_decision_ms if a.replay_decision_ms is not None else time.time_ns()//1000000)
 r['capture_mode']='HISTORICAL_REPLAY' if a.replay_decision_ms is not None else 'READ_ONLY_CURRENT_MEASUREMENT'
 r['measurement_id']=sha({k:v for k,v in r.items() if k!='measurement_id'})
 raw=encoded(r)+b'\n';fd=os.open(a.destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 parent=os.open(a.destination.parent,os.O_RDONLY)
 try:os.fsync(parent)
 finally:os.close(parent)
 print(json.dumps({'status':r['status'],'receipt':str(a.destination),'receipt_sha256':hashlib.sha256(raw).hexdigest(),'actual_saved_ms':time.time_ns()//1000000,'orders_allowed':False}))
 return 0
if __name__=='__main__':raise SystemExit(main())
