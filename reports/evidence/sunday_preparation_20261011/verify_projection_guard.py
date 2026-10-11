"""Offline regression: a source draft must fail the real protocol consumer.

Synthetic GET fixtures only; no client, credentials, network, book or orders.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from research_lab.alpaca_open_dispatch_v2 import PreloadedSourcePublisher

class FixtureLive:
    base_url='https://api.alpaca.markets'
    def get_account(self):
        return {'id':'afd9ffea-e99d-4d2a-b64a-f07fb0f295c6','status':'ACTIVE',
                'trading_blocked':False,'account_blocked':False,'pending_reg_taf_fees':'0',
                'accrued_fees':'0','cash':'496.12','non_marginable_buying_power':'496.12'}
    def list_positions(self):return []
    def list_orders(self,**_):return []
    def _request(self,method,path):
        assert method=='GET' and path=='/v2/assets/NET'
        return {'symbol':'NET','status':'active','tradable':True,'fractionable':True}

class FixtureClock:
    def wall_ms(self):return 1791811801000

policy=json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_bytes())
template={'positions':[],'single_owner_verified':True,'cash_finality_verified':True,
          'quotes':{'NET':{'risk_distance':'33.54'}},
          'gates':{'NET':{'earnings':True,'concentration':True}}}
protocol=json.loads(Path(__file__).with_name('net_protocol_projection.json').read_bytes())
calls=[]
def quote(_):
    calls.append('fixture_quote')
    return {'quote':{'t':'2026-10-12T13:30:01Z','ap':360},'received_ms':1791811801000}

def rejected(value):
    try:
        PreloadedSourcePublisher(policy,template,value,'NET',FixtureLive(),quote,FixtureClock()).capture()
    except ValueError as e:
        assert str(e)=='PROTECTION_PROTOCOL_MAPPING_UNCONFIRMED'
        return True
    return False

legacy=deepcopy(protocol)
legacy.update(schema=legacy['parent_contract_schema'],status=legacy['parent_contract_status'])
assert not rejected(legacy), 'REGRESSION_FIXTURE_DID_NOT_REPRODUCE_OLD_CONSUMER_ACCEPTANCE'
calls.clear()
assert rejected(protocol), 'SOURCE_ONLY_PROJECTION_ACCEPTED_BY_RUNNER'
assert calls==[], 'DRAFT_REACHED_QUOTE_OR_SIZING'
print(json.dumps({'kind':'SYNTHETIC_PROTOCOL_CONSUMER_REGRESSION',
                  'old_projection_protocol_gate_accepted':True,
                  'fixed_projection_blocked_before_quote':True,'broker_calls':0,'orders':0}))
