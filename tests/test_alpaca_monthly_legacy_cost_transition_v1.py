"""A pinned, already closed NET handoff is cash provenance, never Monthly PnL."""
import copy
import hashlib
import json
from decimal import Decimal

import pytest
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source
from research_lab import alpaca_monthly_cost_source_v1 as costs
from test_alpaca_monthly_cost_source_v1 import case, ms
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire
from test_alpaca_monthly_standing_v1 import standing,resign


def legacy_case(c):
    c=copy.deepcopy(c)
    c['anchor']['observed_ms']=ms('2026-10-01T14:00:00Z')
    for row,at in zip(c['fills'][:3],['14:01:00','14:02:00','14:03:00']):
        row['transaction_time']='2026-10-01T'+at+'Z'
    c['exits'][0]['retired_position']['raw_entry']['filled_at']='2026-10-01T14:02:00Z'
    c['positions'][0]['raw_entry']['filled_at']='2026-10-01T14:03:00Z'
    sell=dict(id='legacy-sell',symbol='NET',side='sell',status='filled',qty='1',filled_qty='1',
        filled_avg_price='5',filled_at='2026-10-01T13:59:00Z',client_order_id='legacy-owned-exit')
    entry=dict(id='legacy-buy',symbol='NET',side='buy',status='filled',qty='1',filled_qty='1',
        filled_avg_price='6',filled_at='2026-09-15T14:00:00Z',client_order_id='legacy-owned-entry')
    seal=dict(schema='ALPACA_MONTHLY_LEGACY_TERMINAL_COST_TRANSITION_V1',account_id='fixture',
        classification='OFF_PROTOCOL',sealed_ms=ms('2026-10-01T13:59:30Z'),entry=entry,exits=[sell])
    c['fills'].insert(0,dict(id='legacy-f1',activity_type='FILL',order_id='legacy-sell',symbol='NET',
        side='sell',qty='1',price='5',transaction_time=sell['filled_at']))
    c['assets'].append(dict(id='NET',symbol='NET',asset_class='us_equity',exchange='NASDAQ'))
    c['fees'].append(dict(id='legacy-reg',activity_type='FEE',activity_sub_type='REG',date='2026-10-01',
        created_at='2026-10-02T00:17:00Z',status='executed',currency='USD',net_amount='-.01'))
    c['cash']='61.96'
    c['anchor']['legacy_transition_sha256']=digest(seal)
    return c,seal


def derive(c,seal):
    account=dict(id='fixture',currency='USD',cash=c['cash'],accrued_fees='0',pending_reg_taf_fees='0')
    def get(route,params):
        return dict(http_status=200,started_ms=c['observed']-100,received_ms=c['observed']-100,
            raw=json.dumps(account if route=='/v2/account' else c['fills']+c['fees']))
    source=collect_account_cost_source(get,account_id='fixture',after='2026-10-01T00:00:00Z',
        until='2026-10-03T06:00:00Z',now_ms=c['observed'])
    return costs.derive_owned_exit_cost(source=source,protocol=c['protocol'],calendar=c['calendar'],
        assets=c['assets'],anchor=c['anchor'],positions=c['positions'],exits=c['exits'],entry_id='buy-a',
        legacy_transition=seal)


def test_late_legacy_fee_is_cash_but_not_monthly_pnl(case):
    c,seal=legacy_case(case);result=derive(c,seal)
    assert result['regulatory_fees_usd']=='0.02'
    assert result['legacy_regulatory_fees_usd']=='0.01'
    assert result['gross_before_fees']=='2'
    assert result['other_cash_net_usd']=='-40.02'
    assert result['cash_after_exit']=='61.96'
    assert result['legacy_transition_sha256']==digest(seal)
    assert derive(c,seal)==result
    c['fills'].reverse();c['fees'].reverse()
    again=derive(c,seal)
    assert again['account_day_allocations']==result['account_day_allocations']


@pytest.mark.parametrize('fault',['unbound','pin','account','open','late','quantity','not_net','foreign','cash','price'])
def test_legacy_uncertainty_still_blocks(case,fault):
    c,seal=legacy_case(case)
    if fault=='unbound':c['anchor'].pop('legacy_transition_sha256')
    elif fault=='pin':c['anchor']['legacy_transition_sha256']='f'*64
    elif fault=='account':seal['account_id']='other'
    elif fault=='open':seal['exits'][0]['status']='partially_filled'
    elif fault=='late':seal['sealed_ms']=c['anchor']['observed_ms']+1
    elif fault=='quantity':seal['exits'][0]['filled_qty']='.9'
    elif fault=='not_net':seal['entry']['symbol']='OTHER'
    elif fault=='foreign':c['fills'][0]['order_id']='unowned-sell'
    elif fault=='cash':c['cash']='62.96'
    elif fault=='price':c['fills'][0]['price']='6'
    if fault not in {'unbound','pin'}:c['anchor']['legacy_transition_sha256']=digest(seal)
    with pytest.raises(ValueError):derive(c,seal)


def test_two_partial_legacy_exits_reconcile_total_and_all_charged_cents(case):
    c,seal=legacy_case(case);sell=seal['exits'][0]
    sell['qty']=sell['filled_qty']='.4'
    other=dict(sell,id='legacy-sell-2',qty='.6',filled_qty='.6',client_order_id='legacy-owned-exit-2')
    seal['exits'].append(other)
    c['fills'][0]['qty']='.4'
    c['fills'].append(dict(c['fills'][0],id='legacy-f2',order_id=other['id'],qty='.6'))
    c['anchor']['legacy_transition_sha256']=digest(seal)
    result=derive(c,seal)
    allocated=sum((Decimal(v) for day in result['account_day_allocations'].values()
        for parts in day.values() for v in parts.values()),Decimal(0))
    assert allocated==Decimal('.04')
    assert result['legacy_regulatory_fees_usd']=='0.01'


def test_existing_producer_replays_transition_inputs_without_duplicates(case,tmp_path):
    from test_alpaca_monthly_pending_fees_v1 import producer_fixture
    c,seal=legacy_case(case);native,paths,source=producer_fixture(c,tmp_path)
    path=tmp_path/'terminal-seal.json';path.write_text(json.dumps(seal))
    pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    result=costs.produce_cost_sources(native,**paths,legacy_transition=pin,now_ms=c['observed'])
    document_path=__import__('pathlib').Path(result['buy-a'])
    raw=document_path.read_bytes();mtime=document_path.stat().st_mtime_ns
    document=json.loads(raw);costs.verify_generated_source(document)
    assert document['legacy_regulatory_fees_usd']=='0.01'
    assert costs.produce_cost_sources(native,**paths,legacy_transition=pin,now_ms=c['observed'])==result
    assert document_path.read_bytes()==raw and document_path.stat().st_mtime_ns==mtime
    path.write_text(json.dumps(dict(seal,account_id='changed')))
    with pytest.raises(ValueError,match='LEGACY_TRANSITION_PIN'):
        costs.produce_cost_sources(native,**paths,legacy_transition=pin,now_ms=c['observed'])


def test_unattributed_legacy_pending_fee_never_becomes_monthly_loss_pnl(case,tmp_path):
    from test_alpaca_monthly_pending_fees_v1 import producer_fixture
    c,seal=legacy_case(case)
    c['fees']=[r for r in c['fees'] if r['id']!='legacy-reg']
    c['cash']='61.97';c['observed']=ms('2026-10-03T06:00:01Z')
    native,paths,source=producer_fixture(c,tmp_path)
    path=tmp_path/'terminal-seal.json';path.write_text(json.dumps(seal))
    pin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    native.pending_fee_sources=costs.produce_cost_sources(native,**paths,legacy_transition=pin,
        now_ms=c['observed'],allow_pending=True)
    # A target estimate alone is insufficient. The new classifier's complete
    # same-account context must also be replayed before admitting pending costs.
    native.pending_account_fee_source=None
    with pytest.raises(ValueError,match='LEGACY_ATTRIBUTION_UNRESOLVED'):
        native._accounting_for_admission(account=source['account_after'],now_ms=c['observed'])
    assert not (native.runtime/'standing-loss-observation.json').exists()
    assert not (native.runtime/'standing-loss-stop.json').exists()


@pytest.mark.parametrize('changed_after_reservation',[False,True])
def test_entry_anchor_and_final_dispatch_bind_same_owner_pinned_seal(setup,case,tmp_path,monkeypatch,changed_after_reservation):
    b,s,n,io,now=setup;client,writes,lose=connect_wire(setup,monkeypatch);scope=standing(n,now)
    c,seal=legacy_case(case);path=tmp_path/'terminal-seal.json';path.write_text(json.dumps(seal))
    scope['legacy_cost_transition']=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    resign(n,scope);saved=ticket(setup)
    if changed_after_reservation:
        clock=client.get_clock
        def changed():
            if n.reentry.exists():path.write_text('{}')
            return clock()
        client.get_clock=changed
        with pytest.raises(ValueError,match='LEGACY_TRANSITION_PIN'):n.enter(saved,now_ms=now,apply=True)
        assert writes==[]
    else:
        assert n.enter(saved,now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
        anchor=json.loads((n.runtime/'cash-anchors'/(saved['client_order_id']+'.json')).read_bytes())
        assert anchor['legacy_transition_sha256']==digest(seal) and len(writes)==2
