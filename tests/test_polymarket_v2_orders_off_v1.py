import copy,json,subprocess,sys
from decimal import Decimal,localcontext
from pathlib import Path
import pytest
from research_lab import polymarket_v2_orders_off_v1 as p
PIN='a'*64

def inputs():
 return ({'market_id':'m','token_id':'B','policy_sha256':PIN,'received_ms':1000,'model_price':'0.97'},
 {'asset_id':'B','bids':[{'price':'0.965','size':'200'}],'asks':[{'price':'0.97','size':'50'},{'price':'0.98','size':'100'},{'price':'0.99','size':'1000'}],'received_ms':1001,'time_origin':'RESPONSE_RECEIVED','continuity':'VERIFIED','source_sha256':PIN},
 {'market_id':'m','tokens':['A','B'],'accepting_orders':True,'received_ms':999,'source_sha256':PIN,'fee_rate':'0.05','fee_source_sha256':PIN})

def test_selected_no_token_walks_its_own_asks_and_never_synthesizes():
 r=p.measure(*inputs(),decision_ms=1010)
 assert r['status']=='MEASURED_ORDERS_OFF'
 assert Decimal(r['model_gross'])==100
 with localcontext() as ctx:
  ctx.prec=40
  assert Decimal(r['model_shares'])==50+Decimal('51.5')/Decimal('.98')
 assert Decimal(r['observed_vwap'])>Decimal('.97')
 assert r['best_ask']=='0.97' and r['orders_allowed'] is False and r['real_fill'] is False
 assert r['book_age_ms']==9 and r['signal_to_decision_ms']==10

def test_ladder_depth_excludes_levels_above_limit():
 s,b,m=inputs();b['asks']=[{'price':'0.98','size':'20'},{'price':'0.99','size':'99999'}]
 r=p.measure(s,b,m,decision_ms=1010)
 assert Decimal(r['depth_to_limit'])==Decimal('19.6')
 assert Decimal(r['model_gross'])==Decimal('19.6') and not r['depth_sufficient_for_model_100']

def test_wrong_token_is_unknown_with_no_counterfactual_fill():
 s,b,m=inputs();b['asset_id']='A';r=p.measure(s,b,m,decision_ms=1010)
 assert r['status']=='UNKNOWN' and 'TOKEN_MISMATCH' in r['issues'] and r['model_gross'] is None

@pytest.mark.parametrize('field',['received_ms','source_sha256'])
def test_missing_book_timestamp_or_hash_never_qualified(field):
 s,b,m=inputs();del b[field];assert p.measure(s,b,m,decision_ms=1010)['status']=='UNKNOWN'

def test_request_start_timestamp_is_not_response_availability():
 s,b,m=inputs();b['time_origin']='MONITOR_LOOP_START';r=p.measure(s,b,m,decision_ms=1010)
 assert 'RECEIVE_TIME_UNPROVEN' in r['issues']

def test_future_quote_is_not_used():
 s,b,m=inputs();b['received_ms']=1011;r=p.measure(s,b,m,decision_ms=1010)
 assert 'FUTURE_SOURCE' in r['issues'] and r['model_shares'] is None

def test_missing_fee_is_unknown_not_zero_or_positive_net():
 s,b,m=inputs();del m['fee_rate'];r=p.measure(s,b,m,decision_ms=1010)
 assert r['status']=='UNKNOWN' and r['estimated_fee'] is None and r['estimated_win_net'] is None
 assert Decimal(r['model_gross'])==100

def test_market_not_accepting_orders_is_not_an_executable_signal():
 s,b,m=inputs();m['accepting_orders']=False;r=p.measure(s,b,m,decision_ms=1010)
 assert 'MARKET_NOT_ACCEPTING' in r['issues'] and r['model_gross'] is None

def test_disconnected_book_has_unknown_depth():
 s,b,m=inputs();b['continuity']='GAP';r=p.measure(s,b,m,decision_ms=1010)
 assert 'BOOK_CONTINUITY_UNKNOWN' in r['issues'] and r['depth_to_limit'] is None

@pytest.mark.parametrize('asks',[[{'price':'NaN','size':'5'}],[{'price':'0.97','size':'-1'}],[{'price':'0.97','size':'5'},{'price':'0.97','size':'5'}]])
def test_malformed_or_duplicate_depth_is_rejected(asks):
 s,b,m=inputs();b['asks']=asks;assert p.measure(s,b,m,decision_ms=1010)['status']=='UNKNOWN'

def test_fee_and_win_loss_are_estimates_not_real_pnl():
 s,b,m=inputs();b['asks']=[{'price':'0.97','size':'100'}];r=p.measure(s,b,m,decision_ms=1010)
 assert Decimal(r['estimated_fee'])==Decimal('.14550')
 assert Decimal(r['estimated_win_net'])==Decimal('2.85450')
 assert Decimal(r['estimated_loss_net'])==Decimal('-97.14550')
 assert r['actual_fees'] is None and r['actual_net_pnl'] is None

def test_join_preserves_original_and_never_infers_funds_release():
 r=p.measure(*inputs(),decision_ms=1010);before=copy.deepcopy(r);j=p.join_outcome(r,'B',resolved_ms=2000,joined_ms=2001)
 assert r==before and j['parent_receipt_sha256']==p.sha(r)
 assert j['won'] and j['model_net']==r['estimated_win_net']
 assert j['capital_available_again_ms'] is None and j['actual_net_pnl'] is None
 with pytest.raises(ValueError):p.join_outcome(r,'B',resolved_ms=1000,joined_ms=2001)

def test_module_has_no_network_wallet_or_order_transport():
 import ast
 tree=ast.parse(Path(p.__file__).read_text())
 names={n.names[0].name.split('.')[0] if isinstance(n,ast.Import) else (n.module or '').split('.')[0] for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))}
 assert names <= {'__future__','argparse','datetime','decimal','hashlib','json','os','pathlib','time'}


def test_changed_measurement_cannot_join_as_the_original_receipt():
 r=p.measure(*inputs(),decision_ms=1010);r['estimated_win_net']='999'
 with pytest.raises(ValueError,match='RECEIPT_IDENTITY'):p.join_outcome(r,'B',resolved_ms=2000,joined_ms=2001)

def test_file_only_cli_is_create_exclusive_and_has_no_apply_mode(tmp_path,capsys):
 paths=[]
 for n,x in zip(('signal','book','market'),inputs()):
  q=tmp_path/(n+'.json');q.write_text(json.dumps(x));paths.append(str(q))
 dest=tmp_path/'receipt.json';args=['--signal',paths[0],'--book',paths[1],'--market',paths[2],'--destination',str(dest),'--replay-decision-ms','1010']
 assert p.main(args)==0
 raw=dest.read_bytes();r=json.loads(raw);assert r['capture_mode']=='HISTORICAL_REPLAY' and r['money_authority'] is False
 assert r['measurement_id']==p.sha({k:v for k,v in r.items() if k!='measurement_id'})
 assert dest.stat().st_mode&0o777==0o600
 with pytest.raises(FileExistsError):p.main(args)
 assert dest.read_bytes()==raw
 with pytest.raises(SystemExit):p.main(args+['--apply-once'])

@pytest.mark.parametrize('token',[None,'',' B '])
def test_missing_or_invalid_token_cannot_be_measured_or_joined(token):
 s,b,m=inputs();s['token_id']=token;b['asset_id']=token;m['tokens']=['A',token]
 r=p.measure(s,b,m,decision_ms=1010)
 assert r['status']=='UNKNOWN' and 'TOKEN_MISMATCH' in r['issues']
 with pytest.raises(ValueError):p.join_outcome(r,token,resolved_ms=2000,joined_ms=2001)

def test_fee_capture_lineage_and_rate_are_bound_by_receipt_identity():
 s,b,m=inputs();r=p.measure(s,b,m,decision_ms=1010)
 assert r['fee_source_sha256']==PIN and Decimal(r['captured_fee_rate'])==Decimal('.05')
 m['fee_source_sha256']='b'*64;r2=p.measure(s,b,m,decision_ms=1010)
 assert r2['measurement_id']!=r['measurement_id']

def test_missing_acceptance_is_unknown_but_observed_depth_is_preserved():
 s,b,m=inputs();del m['accepting_orders'];r=p.measure(s,b,m,decision_ms=1010)
 assert r['status']=='UNKNOWN' and 'ACCEPTING_STATUS_UNKNOWN' in r['issues']
 assert r['best_ask']=='0.97' and Decimal(r['depth_to_limit'])==Decimal('146.5')
 assert r['model_gross'] is None
