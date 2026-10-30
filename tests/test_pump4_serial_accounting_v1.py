import copy,json,hashlib
from decimal import Decimal as D
import pytest
from research_lab import pump4_serial_accounting_v1 as S
from test_pump4_account_owner_v1 import inputs,FP
from test_pump4_bybit_sources_v1 import NOW,H
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit

def sync(bundle):
 caps=list(bundle['captures'].values())+[v for w in bundle['history_windows'] for v in w['groups'].values()]
 for v in caps:
  for c in v.get('pages',[v]):c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
 return bundle

def case(tmp_path):
 ex=MemoryBybit(tmp_path/'wire.json','normal');b,p=inputs(ex,now=NOW+4000)
 requests=[];history=[];fills=[];slots=[]
 for j,qty,exitprice in [(1,'.2','98'),(2,'.1','99')]:
  reqs=[]
  for n,side,price in [(1,'Sell','100'),(2,'Buy',exitprice)]:
   cid=f'serial-{j}-{n}';oid=f'order-{j}-{n}';t=NOW+j*1000+n*100
   req=dict(category='linear',symbol='ZROUSDT',positionIdx=0,side=side,qty=qty,reduceOnly=n==2,orderLinkId=cid)
   reqs.append(req);history.append(dict(req,orderId=oid,orderStatus='Filled',cumExecQty=qty,updatedTime=str(t)))
   fills.append(dict(execId='exec-'+cid,orderId=oid,orderLinkId=cid,symbol='ZROUSDT',side=side,execQty=qty,execPrice=price,execTime=str(t),execType='Trade',execFee='.01',feeCurrency='USDT'))
  slots.append(dict(ordinal=j,symbol='ZROUSDT',side='short',first_send_ms=NOW+j*1000,closed_ms=NOW+j*1000+300,requests=reqs,verified_native_ids=[]))
 groups=b['history_windows'][0]['groups']
 for key,rows in [('history',history),('executions',fills),('transactions',[])]:groups[key]['pages'][0]['body']['result']['list']=rows
 return sync(b),slots

def rows(b,key):return b['history_windows'][0]['groups'][key]['pages'][0]['body']['result']['list']
def view(b,s):return S.source_view(b,s,expected_fingerprint=FP,now_ms=NOW+4000)

def test_two_cycles_use_real_capture_contract_and_sum_once(tmp_path):
 b,s=case(tmp_path);v=view(b,s)
 assert D(v['known_net_usdt'])==D('.46');assert D(v['posted_trade_fees_usdt'])==D('.04')
 assert len(v['slots'])==2 and v['account_exposure_matches'] is True
 assert v['cost_finality_proven'] is False and v['unposted_costs_usdt']=='UNKNOWN'
 assert v['release_next_entry_allowed'] is False

def test_late_funding_attributed_to_first_cycle_after_second_is_closed(tmp_path):
 b,s=case(tmp_path);rows(b,'transactions').append(dict(id='fund1',symbol='ZROUSDT',type='SETTLEMENT',category='linear',currency='USDT',transactionTime=str(NOW+1150),funding='-.05'))
 v=view(sync(b),s);assert D(v['known_net_usdt'])==D('.41')
 assert D(v['slots'][0]['posted_funding_usdt'])==D('-.05') and D(v['slots'][1]['posted_funding_usdt'])==0

def test_transaction_trade_fee_is_not_charged_twice(tmp_path):
 b,s=case(tmp_path);rows(b,'transactions').append(dict(id='trade1',symbol='ZROUSDT',type='TRADE',category='linear',currency='USDT',transactionTime=str(NOW+1100),fee='.01'))
 assert D(view(sync(b),s)['known_net_usdt'])==D('.46')

def test_explicit_zero_fee_is_known_but_missing_fee_is_not_zero(tmp_path):
 b,s=case(tmp_path);rows(b,'executions')[0]['execFee']='0'
 assert D(view(sync(b),s)['posted_trade_fees_usdt'])==D('.03')
 del rows(b,'executions')[0]['execFee']
 with pytest.raises(ValueError):view(sync(b),s)

def test_page_duplicate_deduplicated_conflicting_duplicate_blocks(tmp_path):
 b,s=case(tmp_path);rows(b,'executions').append(copy.deepcopy(rows(b,'executions')[0]));assert D(view(sync(b),s)['known_net_usdt'])==D('.46')
 rows(b,'executions')[-1]['execFee']='.02'
 with pytest.raises(ValueError,match='DUPLICATE'):view(sync(b),s)

def test_missing_execution_against_terminal_history_blocks(tmp_path):
 b,s=case(tmp_path);rows(b,'executions').pop()
 with pytest.raises(ValueError,match='EXECUTION_QUANTITY'):view(sync(b),s)

def test_foreign_execution_not_hidden_in_strategy_net(tmp_path):
 b,s=case(tmp_path);x=copy.deepcopy(rows(b,'executions')[0]);x.update(execId='foreign',orderId='foreign-order',orderLinkId='foreign-cid');rows(b,'executions').append(x)
 v=view(sync(b),s);assert v['unclassified_activity'] and v['entry_inputs_complete'] is False
 assert D(v['known_net_usdt'])==D('.46')

def test_funding_without_unique_holding_interval_stays_unclassified(tmp_path):
 b,s=case(tmp_path);rows(b,'transactions').append(dict(id='fund-gap',symbol='ZROUSDT',type='SETTLEMENT',category='linear',currency='USDT',transactionTime=str(NOW+1500),funding='-.1'))
 v=view(sync(b),s);assert v['entry_inputs_complete'] is False
 assert v['unclassified_activity'][0]['reason']=='FUNDING_OWNERSHIP_UNKNOWN'

def test_registry_overlap_or_duplicate_request_is_rejected(tmp_path):
 b,s=case(tmp_path);s[1]['first_send_ms']=NOW+1000
 with pytest.raises(ValueError,match='INTERVAL'):view(b,s)

def test_root_journal_preserves_late_fee_revision_and_lifetime_latch(tmp_path):
 b,s=case(tmp_path);ledger=S.SeriesAccounting(tmp_path/'ledger',FP,dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3'))
 one=ledger.record(view(b,s));old=(tmp_path/'ledger/source-risk.jsonl').read_bytes()
 rows(b,'executions')[0]['execFee']='4';two=ledger.record(view(sync(b),s))
 assert D(two['known_net_usdt'])==D('-3.53') and 'LIFETIME' in two['loss_reasons']
 assert two['cost_revisions'] and (tmp_path/'ledger/source-risk.jsonl').read_bytes().startswith(old)
 reopened=S.SeriesAccounting(tmp_path/'ledger',FP,ledger.policy)
 assert reopened.summary()['entry_loss_latched'] is True

def test_source_history_cannot_shrink_on_restart(tmp_path):
 b,s=case(tmp_path);ledger=S.SeriesAccounting(tmp_path/'ledger',FP,dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3'));ledger.record(view(b,s))
 rows(b,'history').pop();rows(b,'executions').pop()
 with pytest.raises(ValueError):ledger.record(view(sync(b),s))

def test_source_binding_policy_and_replay_are_durable(tmp_path):
 b,s=case(tmp_path);p=dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3');o=S.SeriesAccounting(tmp_path/'ledger',FP,p);v=view(b,s);a=o.record(v)
 assert o.record(v)==a and o.summary()['source_observations']==1
 with pytest.raises(ValueError):S.SeriesAccounting(tmp_path/'ledger','0'*64,p)
 with pytest.raises(ValueError):S.SeriesAccounting(tmp_path/'ledger',FP,dict(p,lifetime_loss_usdt='4'))

def test_stale_or_foreign_capture_rejected(tmp_path):
 b,s=case(tmp_path)
 with pytest.raises(ValueError):S.source_view(b,s,expected_fingerprint='0'*64,now_ms=NOW+4000)
 with pytest.raises(ValueError):S.source_view(b,s,expected_fingerprint=FP,now_ms=NOW+10000)

def test_late_fee_arriving_after_utc_day_week_rollover_keeps_lifetime(tmp_path):
 b,s=case(tmp_path);p=dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3')
 ledger=S.SeriesAccounting(tmp_path/'ledger',FP,p);v=view(b,s);ledger.record(v)
 # Recognition is at observation time; the original trade/funding clocks stay.
 later=copy.deepcopy(v);later['observed_ms']+=8*24*H
 later['history_end_ms']=later['observed_ms'];later['source_records']['executions'][next(iter(later['source_records']['executions']))]['execFee']='4'
 later['known_net_usdt']='-3.53';later['posted_trade_fees_usdt']='4.03'
 later['view_sha256']=S.digest({k:x for k,x in later.items() if k!='view_sha256'})
 row=ledger.record(later)
 assert 'LIFETIME' in row['loss_reasons'] and D(row['day_baseline_usdt'])==D('.46')
 assert 'DAY' in row['loss_reasons'] and 'WEEK' in row['loss_reasons']
 assert S.SeriesAccounting(tmp_path/'ledger',FP,p).summary()['entry_loss_latched'] is True

def test_partial_journal_is_never_repaired_or_reset(tmp_path):
 b,s=case(tmp_path);p=dict(day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',lifetime_loss_usdt='3')
 ledger=S.SeriesAccounting(tmp_path/'ledger',FP,p);ledger.record(view(b,s));target=tmp_path/'ledger/source-risk.jsonl'
 with target.open('ab') as f:f.write(b'{"incomplete":')
 before=target.read_bytes()
 with pytest.raises(ValueError):S.SeriesAccounting(tmp_path/'ledger',FP,p)
 assert target.read_bytes()==before

def test_funding_exact_fill_boundary_is_uncertain_not_assigned_by_sort(tmp_path):
 b,s=case(tmp_path);rows(b,'transactions').append(dict(id='fund-edge',symbol='ZROUSDT',type='SETTLEMENT',category='linear',currency='USDT',transactionTime=str(NOW+1100),funding='-.05'))
 v=view(sync(b),s)
 assert v['entry_inputs_complete'] is False and D(v['posted_funding_usdt'])==0
 assert v['unclassified_activity'][0]['reason']=='FUNDING_OWNERSHIP_UNKNOWN'

def test_rebate_is_signed_and_non_usdt_fee_blocks(tmp_path):
 b,s=case(tmp_path);rows(b,'executions')[0]['execFee']='-.02'
 assert D(view(sync(b),s)['posted_trade_fees_usdt'])==D('.01')
 rows(b,'executions')[0]['feeCurrency']='BTC'
 with pytest.raises(ValueError):view(sync(b),s)
