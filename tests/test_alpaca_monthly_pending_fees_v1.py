"""Incomplete-day fee estimates are admission evidence, never final PnL."""
import copy
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research_lab import alpaca_monthly_cost_source_v1 as costs
from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source
from test_alpaca_monthly_cost_source_v1 import case, ms
from test_alpaca_monthly_native_binding_v1 import setup


def pending_inputs(case):
    c=copy.deepcopy(case)
    c['observed']=ms('2026-10-02T14:01:00Z')
    c['fees']=c['fees'][:1]
    c['cash']='61.99'
    return c


def inputs(c):
    account=dict(id='fixture',currency='USD',cash=c['cash'],
        accrued_fees=c.get('pending','0'),pending_reg_taf_fees='0')
    def get(route,query):
        return dict(http_status=200,started_ms=c['observed']-100,
            received_ms=c['observed']-100,
            raw=json.dumps(account if route=='/v2/account' else c['fills']+c['fees']))
    until='2026-10-02T14:00:59Z' if c['observed']==ms('2026-10-02T14:01:00Z') else '2026-10-03T06:00:00Z'
    source=collect_account_cost_source(get,account_id='fixture',
        after='2026-10-01T00:00:00Z',until=until,now_ms=c['observed'])
    return dict(source=source,protocol=c['protocol'],calendar=c['calendar'],
        assets=c['assets'],anchor=c['anchor'],positions=c['positions'],
        exits=c['exits'],entry_id='buy-a')


def test_partial_day_estimate_uses_fills_not_missing_fee_as_zero(case):
    args=inputs(pending_inputs(case))
    with pytest.raises(ValueError,match='DAY_COVERAGE_OR_SESSION_NOT_CLOSED'):
        costs.derive_owned_exit_cost(**args)
    estimate=costs.derive_owned_exit_cost(**args,pending=True)
    assert estimate['schema']=='ALPACA_MONTHLY_PENDING_FEE_ESTIMATE_V1'
    assert estimate['closure_status']=='PENDING_NOT_FINAL'
    assert estimate['unposted_account_fees_usd']=='0.02'
    assert Decimal(estimate['known_net_before_pending_account_fees_usd'])==2
    assert Decimal(estimate['regulatory_fees_usd'])==0
    assert estimate['terminal_cost_finality_proven'] is False
    assert 'net_usd_exact' not in estimate


def test_posted_account_cents_are_not_reserved_again(case):
    c=pending_inputs(case)
    c['fees'].append(dict(id='fee2',activity_type='FEE',activity_sub_type='CAT',
        date='2026-10-02',created_at='2026-10-02T14:00:30Z',
        status='executed',currency='USD',net_amount='-.01'))
    c['cash']='61.98'
    estimate=costs.derive_owned_exit_cost(**inputs(c),pending=True)
    assert estimate['unposted_account_fees_usd']=='0.01'
    assert estimate['known_net_before_pending_account_fees_usd']=='1.99'


@pytest.mark.parametrize('fault',['unknown_fee','excess_fee','fraction_cent','foreign_fill','cash','liability'])
def test_unknown_or_conflicting_costs_cannot_be_estimated(case,fault):
    c=pending_inputs(case)
    if fault in {'unknown_fee','excess_fee','fraction_cent'}:
        c['fees'].append(dict(id='unexpected',activity_type='FEE',
            activity_sub_type='ADR' if fault=='unknown_fee' else 'CAT',
            date='2026-10-02',created_at='2026-10-02T14:00:30Z',status='executed',currency='USD',
            net_amount='-.005' if fault=='fraction_cent' else '-1'))
    if fault=='foreign_fill':c['fills'][0]['order_id']='foreign'
    if fault=='cash':c['cash']='62.99'
    if fault=='liability':c['pending']='1'
    with pytest.raises(ValueError):costs.derive_owned_exit_cost(**inputs(c),pending=True)


def test_late_fees_can_finalize_without_rewriting_prior_estimate(case):
    old=costs.derive_owned_exit_cost(**inputs(pending_inputs(case)),pending=True)
    saved=copy.deepcopy(old)
    final=costs.derive_owned_exit_cost(**inputs(case))
    assert final['closure_status']=='ACCOUNT_DAY_FEES_RECONCILED'
    assert final['regulatory_fees_usd']=='0.02'
    assert old==saved and old['closure_status']=='PENDING_NOT_FINAL'


def producer_fixture(c,tmp_path):
    from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
    from research_lab.alpaca_monthly_binding_v1 import CONTRACT
    from research_lab.alpaca_dynamic_v1 import canonical
    for p in c['positions']+[e['retired_position'] for e in c['exits']]:
        p['raw_entry'].update(type='market',status='filled',qty=p['raw_entry']['filled_qty'])
    for e in c['exits']:
        e['symbol']=e['retired_position']['symbol']
        for o in e['orders']:o['qty']=o['filled_qty']
    args=inputs(c)
    class Book:
        contract=CONTRACT
        path=tmp_path/'book.sqlite'
        def rows(self,table):return copy.deepcopy(c[table])
    orders={p['entry_id']:p['raw_entry'] for p in c['positions']+[e['retired_position'] for e in c['exits']]}
    orders.update({o['id']:o for e in c['exits'] for o in e['orders']})
    client=SimpleNamespace(get_order=lambda oid:copy.deepcopy(orders[oid]))
    native=MonthlyNativeBinding(Book(),client=client,base_url='https://paper-api.alpaca.markets',
        account_id='fixture',capital='100',runtime=tmp_path/'native',lock_path=tmp_path/'account.lock',
        entry_halt_path=tmp_path/'halt',liability_reserve_usd='.03',pending_fee_admission=True)
    root=tmp_path/'inputs';root.mkdir()
    paths={}
    for key in ('source','protocol','calendar','assets'):
        p=root/(key+'.json');p.write_bytes(canonical(args[key]));paths[key+'_path']=str(p)
    anchors=native.runtime/'cash-anchors';anchors.mkdir(parents=True)
    (anchors/(c['anchor']['client_order_id']+'.json')).write_bytes(canonical(c['anchor']))
    return native,paths,args['source']


def test_pending_producer_replays_on_restart_and_uses_one_reserve(case,tmp_path):
    c=pending_inputs(case);native,paths,source=producer_fixture(c,tmp_path)
    sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True)
    native.pending_fee_sources=sources
    lower,proof=native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert lower==Decimal('1.98')
    assert proof['unposted_account_fees_usd']=='0.02'
    assert proof['cash_reserve_usd']=='0.03'
    with pytest.raises(ValueError,match='MONTHLY_ACCOUNTING_PENDING'):native._require_exit_accounting()
    metadata={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in native.runtime.rglob('*') if p.is_file()}
    assert costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True)==sources
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==v for p,v in metadata.items())
    native.pending_fee_admission=False
    with pytest.raises(ValueError,match='MONTHLY_ACCOUNTING_PENDING'):
        native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


@pytest.mark.parametrize('fault',['stale','cash','reserve','source','book','forged_net'])
def test_admission_estimate_cannot_bypass_reconciliation(case,tmp_path,fault):
    c=pending_inputs(case);native,paths,source=producer_fixture(c,tmp_path)
    native.pending_fee_sources=costs.produce_cost_sources(native,**paths,now_ms=c['observed'],allow_pending=True)
    account=copy.deepcopy(source['account_after']);now=c['observed']
    if fault=='stale':now+=6000
    if fault=='cash':account['cash']='999'
    if fault=='reserve':native.liability=Decimal('.01')
    if fault=='source':
        from pathlib import Path
        Path(paths['source_path']).write_text('{}')
    if fault=='book':c['exits'][0]['reason']='different'
    if fault=='forged_net':
        from pathlib import Path
        p=Path(next(iter(native.pending_fee_sources.values())))
        doc=json.loads(p.read_bytes());doc['known_net_before_pending_account_fees_usd']='10000'
        p.write_text(json.dumps(doc))
    with pytest.raises(ValueError):native._accounting_for_admission(account=account,now_ms=now)


def test_admission_uses_pending_loss_lower_bound_and_existing_cash_reserve(case,tmp_path):
    c=pending_inputs(case);c['positions']=[];c['fills']=[f for f in c['fills'] if f['order_id']!='buy-b']
    c['cash']='97.99';c['fills'][-1]['price']='8'
    c['exits'][0]['orders'][0]['filled_avg_price']='8'
    n,paths,source=producer_fixture(c,tmp_path)
    n.pending_fee_sources=costs.produce_cost_sources(n,**paths,now_ms=c['observed'],allow_pending=True)
    account=dict(source['account_after'],non_marginable_buying_power=c['cash'],equity='100',
        trading_blocked=False,account_blocked=False)
    n.client.get_account=lambda:copy.deepcopy(account)
    n.client.get_clock=lambda:dict(is_open=True,timestamp='2026-10-02T14:01:00Z')
    n.client.list_positions=lambda:[];n.client.list_orders=lambda **kw:[]
    n.client.get_asset=lambda s:dict(symbol=s,status='active',tradable=True,fractionable=True)
    n.client.latest_quote=lambda s:dict(ap='10',t='2026-10-02T14:01:00Z')
    t=dict(symbol='NET',client_order_id='fixture-next',notional='20',entry_gate={'weight':'.6'})
    anchor=n._admit_new_entry(t,c['observed'])
    proof=anchor['pending_fee_admission']
    assert Decimal(proof['conservative_realized_net_usd'])==Decimal('-2.03')
    with pytest.raises(ValueError,match='LOSS_ADMISSION_STOP'):
        n._check_standing_loss({'max_cumulative_net_loss_usd':'2.02'},Decimal('-2.03'),[])
    account['cash']=account['non_marginable_buying_power']='20.02'
    # A fresh proof matching low cash still cannot spend the existing reserve.
    # The real-source mismatch is independently rejected before the cash test.
    with pytest.raises(ValueError):n._admit_new_entry(t,c['observed'])


def test_old_live_scope_cannot_enable_pending_fee_admission(setup,monkeypatch):
    from test_alpaca_monthly_account_transport_v1 import connect_wire
    from test_alpaca_monthly_standing_v1 import standing,resign
    from research_lab.alpaca_monthly_native_binding_v1 import PENDING_FEE_POLICY
    b,s,n,io,now=setup;connect_wire(setup,monkeypatch)
    scope=standing(n,now);n.pending_fee_admission=True;n.liability=Decimal('.03')
    scope['liability_reserve_usd']='0.03';resign(n,scope)
    with pytest.raises(ValueError,match='PENDING_FEE_SCOPE_REQUIRED'):n._live_custody()
    scope['pending_fee_admission']=PENDING_FEE_POLICY;resign(n,scope)
    with pytest.raises(ValueError,match='PENDING_FEE_PROTOCOL_REQUIRED'):n._live_custody()
    scope['pending_fee_protocol_sha256']='a'*64;resign(n,scope)
    assert n._live_custody()['pending_fee_admission']==PENDING_FEE_POLICY


def test_single_manager_refreshes_costs_after_rotation_before_entry(setup,tmp_path):
    from test_alpaca_monthly_cycle_custody_v1 import wired
    m,n,s,io,now=wired(setup,tmp_path);events=[]
    rotate=n.rotate;enter=n.enter
    def rotation(*a,**kw):events.append('rotation');return rotate(*a,**kw)
    def entry(*a,**kw):events.append('entry');return enter(*a,**kw)
    n.rotate=rotation;n.enter=entry
    out=m.opening(n,{},s['selection_id'],quotes={'NET':dict(ask=311.,quote_ts=now,
        received_ms=now,source='fixture')},now_ms=now,apply=True,
        before_entry=lambda:events.append('cost_refresh'))
    assert events==['rotation','cost_refresh','entry']
    assert out['results'][0]['status']=='MONTHLY_NATIVE_PROTECTED'


@pytest.mark.parametrize('state',['no_exits','all_final'])
@pytest.mark.parametrize('fault',['positive','missing','negative','nonfinite','currency'])
def test_completed_accounting_does_not_waive_unknown_current_liability(case,tmp_path,state,fault):
    c=pending_inputs(case);n,paths,source=producer_fixture(c,tmp_path)
    if state=='no_exits':c['exits']=[]
    else:n._accounting_net=lambda **kw:Decimal('1')
    account=copy.deepcopy(source['account_after'])
    if fault=='positive':account['accrued_fees']='1000'
    if fault=='missing':account.pop('pending_reg_taf_fees')
    if fault=='negative':account['pending_reg_taf_fees']='-.01'
    if fault=='nonfinite':account['accrued_fees']='NaN'
    if fault=='currency':account['currency']='EUR'
    with pytest.raises(ValueError):n._accounting_for_admission(account=account,now_ms=c['observed'])


def test_live_pending_proof_must_use_owner_pinned_tariff(case,tmp_path):
    c=pending_inputs(case);n,paths,source=producer_fixture(c,tmp_path)
    n.pending_fee_sources=costs.produce_cost_sources(n,**paths,now_ms=c['observed'],allow_pending=True)
    n.base_url='https://api.alpaca.markets'
    n._live_custody=lambda:{'pending_fee_protocol_sha256':'f'*64}
    with pytest.raises(ValueError,match='PROTOCOL'):
        n._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


def test_source_aging_during_replay_blocks_admission(case,tmp_path,monkeypatch):
    c=pending_inputs(case);n,paths,source=producer_fixture(c,tmp_path)
    n.pending_fee_sources=costs.produce_cost_sources(n,**paths,now_ms=c['observed'],allow_pending=True)
    elapsed=[0.];original=costs._document
    monkeypatch.setattr(costs,'time',SimpleNamespace(monotonic=lambda:elapsed[0]),raising=False)
    def delayed(*a,**kw):
        out=original(*a,**kw);elapsed[0]+=6.;return out
    monkeypatch.setattr(costs,'_document',delayed)
    with pytest.raises(ValueError,match='STALE_SOURCE'):
        n._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])


@pytest.mark.parametrize('representation',['access_key','microsecond'])
def test_supported_broker_representations_preserve_exact_book_identity(case,tmp_path,representation):
    c=pending_inputs(case)
    if representation=='microsecond':
        for p in c['positions']+[e['retired_position'] for e in c['exits']]:
            p['raw_entry']['filled_at']=p['raw_entry']['filled_at'].replace('Z','.000000123Z')
    n,paths,source=producer_fixture(c,tmp_path);original=n.client.get_order
    def get(oid):
        out=original(oid)
        if representation=='access_key':out['source']='access_key'
        else:out['filled_at']=out['filled_at'].replace('.000000123Z','.000000Z')
        return out
    n.client.get_order=get
    n.pending_fee_sources=costs.produce_cost_sources(n,**paths,now_ms=c['observed'],allow_pending=True)
    lower,proof=n._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert lower==Decimal('1.98')


def test_final_clock_delay_cannot_dispatch_with_old_pending_proof(setup,monkeypatch):
    from test_alpaca_monthly_native_binding_v1 import ticket
    from research_lab import alpaca_monthly_native_binding_v1 as mod
    from datetime import datetime,timezone
    b,s,n,io,now=setup;n.pending_fee_admission=True;n.liability=Decimal('.03')
    elapsed=[0.];reads=[0]
    monkeypatch.setattr(mod.time,'monotonic',lambda:elapsed[0])
    def verified(**kw):
        reads[0]+=1
        return Decimal(0),dict(source_observed_ms=now,source_coverage_end_ms=now)
    n._accounting_for_admission=verified
    def clock():
        if reads[0]>=2:elapsed[0]=6.
        return dict(is_open=True,timestamp=datetime.fromtimestamp((now+int(elapsed[0]*1000))/1000,timezone.utc).isoformat())
    io.get_clock=clock
    with pytest.raises(ValueError,match='STALE_SOURCE'):n.enter(ticket(setup),now_ms=now,apply=True)
    assert io.sent==[] and n.reentry.exists()


def test_full_frozen_source_rotation_reenters_with_pending_fees_and_restart(tmp_path):
    from scripts.rehearse_alpaca_monthly_cycle_v1 import run_pending_rotation
    out=run_pending_rotation(tmp_path/'pending-rotation')
    assert out['status']=='MONTHLY_PENDING_FEE_ROTATION_ORDERS_OFF_E2E_PASS'
    assert out['selector_monkeypatched'] is False and out['source_symbols']==58
    assert out['rotation_exits']==1 and out['simulated_entries']==2
    assert out['owned_positions']==1 and out['response_loss_recovered']
    assert out['old_exit_pending_during_new_entries'] and out['old_exit_finalized_after_posting']
    assert out['duplicate_entries']==0 and out['real_broker_writes']==0
