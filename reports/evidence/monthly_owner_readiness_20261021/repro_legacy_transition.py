"""Synthetic handoff source diagnostic, no broker or real account state."""
import copy,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path[:0]=[str(root),str(root/'tests')]
from test_alpaca_monthly_cost_source_v1 import case,derive,ms
c=case.__wrapped__();assert derive(copy.deepcopy(c))['closure_status']=='ACCOUNT_DAY_FEES_RECONCILED'
c['anchor']['observed_ms']=ms('2026-10-01T14:00:00Z')
c['exits'][0]['retired_position']['raw_entry']['filled_at']='2026-10-01T14:02:00Z'
c['positions'][0]['raw_entry']['filled_at']='2026-10-01T14:03:00Z'
for row,at in zip(c['fills'][:3],['14:01:00','14:02:00','14:03:00']):row['transaction_time']='2026-10-01T'+at+'Z'
assert derive(copy.deepcopy(c))['closure_status']=='ACCOUNT_DAY_FEES_RECONCILED'
c['fills'].insert(0,dict(id='fixture-legacy-fill',activity_type='FILL',order_id='fixture-legacy-sell',symbol='LEGACY',side='sell',qty='1',price='5',transaction_time='2026-10-01T13:59:00Z'))
c['assets'].append(dict(id='LEGACY',symbol='LEGACY',asset_class='us_equity',exchange='NASDAQ'))
c['fees'].append(dict(id='fixture-legacy-reg',activity_type='FEE',activity_sub_type='REG',date='2026-10-01',created_at='2026-10-02T00:17:00Z',status='executed',currency='USD',net_amount='-.01'));c['cash']='61.96'
try:derive(c);raise AssertionError('Unbound legacy fill unexpectedly admitted')
except ValueError as exc:reason=str(exc)
assert reason=='MONTHLY_COST_FOREIGN_FILL',reason
print(json.dumps(dict(status='REPRODUCED_BLOCKER',observed_rejection=reason,fixture_only=True,broker_requests=0,broker_writes=0)))
