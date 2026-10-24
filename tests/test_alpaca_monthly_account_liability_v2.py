"""Owner opt-in: reported liabilities reserved, never erased or final PnL."""
import copy,json,hashlib
from decimal import Decimal as D
from pathlib import Path
import pytest
from test_alpaca_monthly_cost_source_v1 import case
from test_alpaca_monthly_legacy_cost_transition_v1 import legacy_case
from test_alpaca_monthly_pending_fees_v1 import producer_fixture
from research_lab import alpaca_monthly_cost_source_v1 as costs

POLICY=dict(schema='ALPACA_MONTHLY_PENDING_ACCOUNT_RESERVE_V1',reserve_usd='40',
 loss_metric='CONSERVATIVE_MONTHLY_LOWER_BOUND',terminal_cost_finality_proven=False)


def prepared(case,tmp_path):
 c,seal=legacy_case(case);c['pending']='.02'
 from test_alpaca_monthly_cost_source_v1 import ms
 c['observed']=ms('2026-10-03T06:00:01Z')
 native,paths,source=producer_fixture(c,tmp_path);native.liability=D('40')
 path=tmp_path/'legacy-seal.json';path.write_text(json.dumps(seal));pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 return c,seal,native,paths,source,pin


def test_reported_pending_is_retained_after_all_model_fees_are_posted(case,tmp_path):
 c,seal,native,paths,source,pin=prepared(case,tmp_path)
 try:
  native.pending_fee_sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 except TypeError:pytest.fail('Explicit owner reserve policy missing: settled-activity/pending-account mismatch still blocks')
 lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
 assert proof['unposted_account_fees_usd']=='0.02'
 assert proof['reported_pending_liability_reserve_usd']=='0.02'
 assert D(proof['modelled_unposted_fees_usd'])==0
 assert lower==D('1.95') and proof['terminal_cost_finality_proven'] is False
 assert native._accounting_net(pending={'buy-a':'1.98'})==D('1.98')
 before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in native.runtime.rglob('*') if p.is_file()}
 costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 assert all((p.read_bytes(),p.stat().st_mtime_ns)==v for p,v in before.items())


def test_old_scope_and_foreign_fills_remain_fail_closed(case,tmp_path):
 c,seal,native,paths,source,pin=prepared(case,tmp_path)
 with pytest.raises(ValueError,match='LIABILITY_UNCLASSIFIED'):
  costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin)
 c['fills'][0]['order_id']='foreign'
 from test_alpaca_monthly_pending_fees_v1 import inputs
 bad=inputs(c)['source']
 with pytest.raises(ValueError,match='FOREIGN_FILL'):
  costs._account_day_context(source=bad,protocol=c['protocol'],calendar=c['calendar'],assets=c['assets'],positions=c['positions'],exits=c['exits'],legacy_transition=seal,pending=True,liability_policy=POLICY)


def test_model_and_reported_obligations_are_not_assumed_to_overlap(case,tmp_path):
 c,seal,native,paths,source,pin=prepared(case,tmp_path)
 # Rebuild a real raw capture with a missing assessment and reported liability.
 c['fees']=[r for r in c['fees'] if r['id']!='legacy-reg']
 c['cash']='61.97'
 from test_alpaca_monthly_pending_fees_v1 import inputs
 source=inputs(c)['source'];Path(paths['source_path']).write_text(json.dumps(source))
 native.pending_fee_sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 lower,p=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
 assert p['modelled_unposted_fees_usd']=='0.01' and p['reported_pending_liability_reserve_usd']=='0.02'
 assert p['unposted_account_fees_usd']=='0.03' and p['cash_reserve_usd']=='40'
 assert lower==D('1.95')
 native.liability=D('.02')
 with pytest.raises(ValueError,match='RESERVE'):
  native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


def test_pending_buffer_can_only_reduce_loss_admission(case,tmp_path):
 c,seal,native,paths,source,pin=prepared(case,tmp_path)
 native.pending_fee_sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 lower,p=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
 with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
  native._check_standing_loss({'max_cumulative_net_loss_usd':'8'},lower,[dict(qty='1',avg_entry_price='20',current_price='10.04')])


@pytest.mark.parametrize('authorized',[False,True])
def test_live_admission_cannot_use_policy_outside_owner_scope(case,tmp_path,authorized):
 c,seal,native,paths,source,pin=prepared(case,tmp_path)
 native.pending_fee_sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 native.base_url='https://api.alpaca.markets'
 rows={k:dict(path=paths[k+'_path'],sha256=hashlib.sha256(Path(paths[k+'_path']).read_bytes()).hexdigest()) for k in ('protocol','calendar','assets')}
 scope=dict(pending_fee_protocol_sha256=rows['protocol']['sha256'],legacy_cost_transition=pin,legacy_pending_cost_inputs=dict(after=source['coverage']['after'],**rows))
 if authorized:scope['account_liability_reserve_policy']=POLICY
 call=lambda:costs.pending_admission_net(native,account=source['account_after'],now_ms=c['observed'],owner_scope=scope)
 if authorized:assert call()[0]==D('1.95')
 else:
  with pytest.raises(ValueError,match='ACCOUNT_LIABILITY_SCOPE_CONFLICT'):call()


def test_first_buy_and_later_zero_field_never_claim_finality(case,tmp_path):
 c,seal=legacy_case(case)
 from test_alpaca_monthly_cost_source_v1 import ms
 from test_alpaca_monthly_pending_fees_v1 import inputs
 c.update(observed=ms('2026-10-03T06:00:01Z'),positions=[],exits=[],fees=[],cash='100',pending='.02')
 c['fills']=c['fills'][:1]
 native,paths,source=producer_fixture(c,tmp_path);native.liability=D('40')
 path=tmp_path/'seal.json';path.write_text(json.dumps(seal));pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 assert costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)=={}
 lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
 assert lower==D('-.02') and D(proof['unposted_account_fees_usd'])==D('.04')
 old=Path(native.pending_account_fee_source);before=old.read_bytes()
 c['pending']='0';source=inputs(c)['source'];Path(paths['source_path']).write_text(json.dumps(source))
 costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
 lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
 assert lower==0 and D(proof['unposted_account_fees_usd'])==D('.02')
 assert proof['terminal_cost_finality_proven'] is False and old.read_bytes()==before


@pytest.mark.parametrize('value',['-1','41'])
def test_negative_and_over_reserve_reported_obligations_block(case,tmp_path,value):
 c,seal,native,paths,source,pin=prepared(case,tmp_path);c['pending']=value
 from test_alpaca_monthly_pending_fees_v1 import inputs
 if value=='-1':
  with pytest.raises(ValueError,match='ACCOUNT_NUMBER'):inputs(c)
  return
 source=inputs(c)['source'];Path(paths['source_path']).write_text(json.dumps(source))
 with pytest.raises(ValueError,match='LIABILITY|RESERVE'):
  costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True,legacy_transition=pin,liability_policy=POLICY)
