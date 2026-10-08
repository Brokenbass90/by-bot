"""Execution safety of prospective Alpaca PAPER adaptation; synthetic broker only."""
import importlib,json,copy
from pathlib import Path
from decimal import Decimal
import pytest

ROOT=Path(__file__).resolve().parents[1]
NOW=1791379801000
PAPER='https://paper-api.alpaca.markets'

@pytest.fixture
def api():
    try:return importlib.import_module('research_lab.alpaca_dynamic_paper')
    except ImportError:return None

@pytest.fixture
def policy():return json.loads((ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_text())

@pytest.fixture
def plan(policy):
    from research_lab.alpaca_dynamic_v1 import digest
    slot=next(s for s in policy['inherited_slots'] if s['symbol']=='AMD')
    core={'epoch_sha256':digest(policy),'slot_entry_order_id':slot['entry_order_id'],'symbol':'NET','qty':'1',
          'reference_ask':'100','stop_price':'96','risk_distance':'4','notional_usd':'100','modeled_stop_risk_usd':'4',
          'notional_limit_usd':'100','funding_limit_usd':'100.10','fee_rate':'.001','protection_qty':'1',
          'protection_tif':'gtc','ranking_sha256':'b'*64,'snapshot_sha256':'c'*64,'source_sha256':'d'*64,
          'session':'2026-10-07','prepared_ms':NOW}
    return {**core,'receipt_id':digest(core),'client_order_id':'dyn1-'+digest(core)[:32],
            'status':'RESERVED_ORDERS_OFF','money_authority':False,'orders_allowed':False,'evidence_kind':'INPUT_PROVIDED_ORDERS_OFF'}

class Broker:
    base_url=PAPER
    account_id='paper-distinct-account'
    def __init__(self):self.orders={};self.writes=[];self.positions=[{'symbol':'OLD','qty':'2','avg_entry_price':'50'}];self.fill_qty='1';self.fail_post=False
    def get_account(self):return {'id':self.account_id,'cash':'1000','trading_blocked':False,'account_blocked':False}
    def get_clock(self):return {'is_open':True,'timestamp':'2026-10-07T13:30:01Z'}
    def list_positions(self):return copy.deepcopy(self.positions)
    def list_orders(self,**kwargs):return [copy.deepcopy(o) for o in self.orders.values() if o['status']=='new']
    def get_order_by_client_id(self,cid):return copy.deepcopy(self.orders.get(cid))
    def get_order(self,oid):return next(copy.deepcopy(o) for o in self.orders.values() if o['id']==oid)
    def _request(self,method,path,payload):
        assert method=='POST' and path=='/v2/orders';self.writes.append(copy.deepcopy(payload))
        if self.fail_post:raise TimeoutError('uncertain dispatch')
        o={**payload,'id':'entry-id','status':'filled','filled_qty':self.fill_qty,'filled_avg_price':payload['limit_price'],'filled_at':'2026-10-07T13:30:02Z'}
        self.orders[payload['client_order_id']]=o
        self.positions.append({'symbol':o['symbol'],'qty':self.fill_qty,'avg_entry_price':o['filled_avg_price']})
        return copy.deepcopy(o)
    def submit_stop_sell(self,symbol,**kwargs):
        o={'id':'stop-id','symbol':symbol,'qty':str(kwargs['qty']),'stop_price':str(kwargs['stop_price']),
           'side':'sell','type':'stop','status':'new','filled_qty':'0','time_in_force':kwargs['time_in_force'],
           'client_order_id':kwargs['client_order_id']};self.orders[o['client_order_id']]=o;self.writes.append(copy.deepcopy(o));return o
    def cancel_order(self,oid):
        o=next(o for o in self.orders.values() if o['id']==oid);o['status']='canceled';self.writes.append({'cancel':oid});return copy.deepcopy(o)


def test_paper_entry_uses_exact_quantity_capped_limit_and_existing_full_stop_readback(api,policy,plan,tmp_path):
    assert api is not None,'PAPER integration is missing'
    broker=Broker();r=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert r['status']=='PAPER_PROTECTED' and r['money_authority'] is False
    assert broker.writes[0]['type']=='limit' and broker.writes[0]['qty']=='1' and broker.writes[0]['limit_price']=='100.00'
    assert broker.writes[1]['qty']=='1.0' and Decimal(broker.writes[1]['stop_price'])>=96
    assert broker.positions[0]['symbol']=='OLD'  # no authority over legacy PAPER positions


def test_restart_receipt_is_identical_and_cannot_submit_twice(api,policy,plan,tmp_path):
    assert api is not None
    broker=Broker();first=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    second=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)
    assert second==first and len(broker.writes)==2


@pytest.mark.parametrize('base,account', [('https://api.alpaca.markets','paper-distinct-account'),(PAPER,'wrong-paper-id')])
def test_live_endpoint_or_wrong_paper_identity_never_gets_a_write(api,policy,plan,tmp_path,base,account):
    assert api is not None
    broker=Broker();broker.base_url=base
    assert api.execute_paper(plan,policy,broker,account,tmp_path,NOW,send=True)['status']=='BLOCKED_DATA'
    assert broker.writes==[]


def test_dryrun_never_submits_and_future_or_changed_plan_fails_closed(api,policy,plan,tmp_path):
    assert api is not None
    broker=Broker();assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=False)['status']=='PAPER_READ_ONLY_READY'
    plan['qty']='2';assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_DATA'
    assert broker.writes==[]


def test_uncertain_post_is_not_retried_after_restart(api,policy,plan,tmp_path):
    assert api is not None
    broker=Broker();broker.fail_post=True
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    broker.fail_post=False
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)['status']=='BLOCKED_EXECUTION'
    assert len(broker.writes)==1


def test_selected_symbol_foreign_position_refuses_adoption(api,policy,plan,tmp_path):
    assert api is not None
    broker=Broker();broker.positions.append({'symbol':'NET','qty':'1','avg_entry_price':'100'})
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    assert broker.writes==[]


def test_earnings_unknown_is_not_relabelled_safe(api):
    assert api is not None
    assert api.earnings_check([], '2026-10-07')['safe'] is False
    assert api.earnings_check(['2026-10-10'],'2026-10-07')['safe'] is False
    assert api.earnings_check(['2026-11-10'],'2026-10-07')['safe'] is True


def test_partial_terminal_fill_gets_exact_full_protection(api,policy,plan,tmp_path):
    broker=Broker();broker.fill_qty='0.4'
    r=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert r['status']=='PAPER_PROTECTED' and r['filled_qty']=='0.4'
    assert broker.writes[-1]['qty']=='0.4' and broker.writes[-1]['time_in_force']=='day'


def test_uncertain_stop_recovers_existing_id_but_never_resends_missing_one(api,policy,plan,tmp_path):
    broker=Broker();original=broker.submit_stop_sell
    def uncertain(*a,**k):
        original(*a,**k);raise TimeoutError('stop response lost')
    broker.submit_stop_sell=uncertain
    first=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert first['status']=='BLOCKED_EXECUTION'
    broker.submit_stop_sell=original
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)['status']=='PAPER_PROTECTED'
    assert len(broker.writes)==2


def test_expired_plan_cannot_buy_and_missing_stop_invalidates_receipt(api,policy,plan,tmp_path):
    broker=Broker()
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+300000,send=True)['status']=='BLOCKED_DATA'
    assert not broker.writes
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='PAPER_PROTECTED'
    broker.orders={k:v for k,v in broker.orders.items() if v['side']=='buy'}
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)['status']!='PAPER_PROTECTED'
    assert len(broker.writes)==2


def test_real_paper_client_has_no_account_flatten_or_live_url(monkeypatch):
    import importlib
    try:module=importlib.import_module('scripts.run_alpaca_dynamic_paper')
    except ImportError:module=None
    assert module is not None,'bounded PAPER CLI is missing'
    client=module.PaperClient('test-key','test-secret')
    with pytest.raises(ValueError):client._request('DELETE','/v2/positions/OLD')
    client.base_url='https://api.alpaca.markets'
    with pytest.raises(ValueError):client.get_account()


def test_filtered_open_orders_prevent_adoption_beyond_first_default_page(api,policy,plan,tmp_path):
    broker=Broker();calls=[]
    def orders(**kw):
        calls.append(kw)
        return [{'symbol':'NET','side':'buy','status':'new'}] if kw.get('symbols')==['NET'] else [{'symbol':'OTHER','status':'new'}]*100
    broker.list_orders=orders
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    assert calls[-1]['symbols']==['NET'] and not broker.writes


def test_clock_crossing_window_during_preflight_prevents_dispatch(api,policy,plan,tmp_path):
    broker=Broker();clocks=iter([{'is_open':True,'timestamp':'2026-10-07T13:30:01Z'},
                               {'is_open':True,'timestamp':'2026-10-07T13:35:01Z'}])
    broker.get_clock=lambda:next(clocks)
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_DATA'
    assert not broker.writes


def test_cancellation_cannot_touch_foreign_readback_with_same_order_id(api,policy,plan,tmp_path):
    broker=Broker();actual=broker.get_order
    def changed(oid):
        o=actual(oid);o.update(client_order_id='foreign',status='new');return o
    broker.get_order=changed
    r=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert r['status']=='BLOCKED_EXECUTION' and len(broker.writes)==1


def test_packaged_cli_uses_original_broker_lock_not_its_own_root():
    from scripts.run_alpaca_dynamic_paper import shared_lock_path
    from scripts.equities_alpaca_paper_bridge import _alpaca_account_lock_path
    expected=_alpaca_account_lock_path(PAPER,'test-key').name
    p=shared_lock_path(Path('/root/by-bot/configs/alpaca_paper_local.env'),{},'test-key')
    assert p==Path('/root/by-bot/runtime/locks')/expected


def test_oct8_wide_quote_price_improvement_keeps_actual_fill_relative_full_stop(api,policy,plan,tmp_path):
    """Captured IEX ask169/bid158.36; broker fills below ask, not a real PAPER fill."""
    from research_lab.alpaca_dynamic_v1 import digest
    core={k:v for k,v in plan.items() if k not in {'receipt_id','client_order_id','status','money_authority','orders_allowed','evidence_kind'}}
    core.update(symbol='XOM',qty='.6',reference_ask='169',stop_price='161.69',
                risk_distance='7.31',notional_usd='101.4',modeled_stop_risk_usd='4.386',
                notional_limit_usd='101.4',funding_limit_usd='101.5014',protection_qty='.6',protection_tif='day')
    plan.update(core,receipt_id=digest(core),client_order_id='dyn1-'+digest(core)[:32])
    broker=Broker();submit=broker._request
    def improved(method,path,payload):
        order=submit(method,path,payload)
        order['filled_avg_price']='158.36'
        broker.orders[payload['client_order_id']]['filled_avg_price']='158.36'
        broker.positions[-1]['avg_entry_price']='158.36'
        return order
    broker._request=improved;broker.fill_qty='.6'
    receipt=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert receipt['status']=='PAPER_PROTECTED'
    assert receipt['stop_price']=='151.05' and Decimal(receipt['stop_price'])<Decimal('158.36')
    assert broker.writes[-1]['qty']=='0.6' and broker.writes[-1]['time_in_force']=='day'
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)==receipt
    assert len(broker.writes)==2 and broker.positions[0]['symbol']=='OLD'


def test_accepted_entry_with_lost_response_recovers_same_fill_without_second_buy(api,policy,plan,tmp_path):
    broker=Broker();submit=broker._request
    def accepted_but_lost(method,path,payload):
        submit(method,path,payload)
        raise TimeoutError('entry accepted, response lost')
    broker._request=accepted_but_lost
    first=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW,send=True)
    assert first['status']=='BLOCKED_EXECUTION' and len(broker.writes)==1
    broker._request=submit
    recovered=api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+1000,send=True)
    assert recovered['status']=='PAPER_PROTECTED' and len(broker.writes)==2
    assert [o['side'] for o in broker.writes]==['buy','sell']
    assert api.execute_paper(plan,policy,broker,broker.account_id,tmp_path,NOW+2000,send=True)==recovered
    assert len(broker.writes)==2
