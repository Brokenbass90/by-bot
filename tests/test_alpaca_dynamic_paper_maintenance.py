"""Catch stranded DAY protection and incorrect emergency/duplicate ownership."""
import copy,json
from decimal import Decimal
from datetime import datetime,timezone
from pathlib import Path
import pytest
from test_alpaca_dynamic_paper import Broker,policy,plan,NOW
from research_lab.alpaca_dynamic_paper import execute_paper
from research_lab import alpaca_dynamic_paper_maintenance as maintenance

class DayBroker(Broker):
    def __init__(self):
        super().__init__();self.fill_qty='.4';self.rearm_422=False;self.uncertain=False
    def get_clock(self):return {'is_open':True,'timestamp':'2026-10-08T13:30:02Z'}
    def submit_stop_sell(self,symbol,**kw):
        if kw['client_order_id'] not in self.orders and any(o['type']=='stop' for o in self.orders.values()):
            if self.rearm_422:raise RuntimeError('422 stop must be less than market')
            o=super().submit_stop_sell(symbol,**kw);o['id']='new-day-stop';self.orders[kw['client_order_id']]=o
            if self.uncertain:raise TimeoutError('response lost after POST')
            return copy.deepcopy(o)
        return super().submit_stop_sell(symbol,**kw)
    def list_orders(self,**kw):
        rows=list(self.orders.values())
        if kw.get('symbols'):rows=[o for o in rows if o['symbol'] in kw['symbols']]
        if kw.get('status')=='open':rows=[o for o in rows if o['status']=='new']
        return copy.deepcopy(rows)
    def close_position(self,symbol):
        assert symbol=='NET'
        self.writes.append({'close':symbol})
        self.positions=[p for p in self.positions if p['symbol']!=symbol]
        row={'id':'emergency','symbol':symbol,'type':'market','side':'sell','status':'filled',
             'qty':'.4','filled_qty':'.4','filled_avg_price':'95','filled_at':'2026-10-08T13:30:03Z'}
        self.orders['emergency']=row
        return copy.deepcopy(row)

def setup_intent(plan,policy,tmp_path):
    b=DayBroker();b.get_clock=lambda:{'is_open':True,'timestamp':'2026-10-07T13:30:01Z'}
    r=execute_paper(plan,policy,b,b.account_id,tmp_path,NOW,send=True)
    assert r['status']=='PAPER_PROTECTED'
    b.get_clock=lambda:{'is_open':True,'timestamp':'2026-10-08T13:30:02Z'}
    for p in b.positions:
        if p['symbol']=='NET':p['current_price']='102'
    next(o for o in b.orders.values() if o['type']=='stop')['status']='expired'
    return b

def call(b,plan,policy,tmp_path,send=True):
    return maintenance.maintain_paper(plan=plan,policy=policy,client=b,
        expected_paper_id=b.account_id,runtime=tmp_path,now_ms=1791466202000,send=send)

def test_expired_day_rearms_exact_floor_and_restart_has_no_second_sell(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_PROTECTED' and r['stop_order_id']=='new-day-stop'
    assert b.writes[-1]['qty']=='0.4' and b.writes[-1]['stop_price']=='96.0'
    first=copy.deepcopy(b.writes);r2=call(b,plan,policy,tmp_path)
    assert r2['status']=='PAPER_PROTECTED' and b.writes==first
    ledger=json.loads((tmp_path/'protective_exit_hwm.json').read_text())
    assert ledger['NET']['accepted_stop_floor']==96 and ledger['NET']['accepted_order_id']=='new-day-stop'
    assert b.positions[0]['symbol']=='OLD'

def test_422_unwinds_only_actual_paper_owned_symbol(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);b.rearm_422=True
    r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_EMERGENCY_EXIT_PENDING_FINALITY'
    assert b.positions==[{'symbol':'OLD','qty':'2','avg_entry_price':'50'}]
    assert b.writes[-1]=={'close':'NET'}
    assert r['kill_receipt']['status']=='confirmed_flat'
    assert r['exit_kind']=='EMERGENCY_MARKET' and r['net_pnl_status']=='NOT_PROVEN'

def test_lost_response_recovers_existing_stop_and_never_resends(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);b.uncertain=True
    # Current readback proves protection after the ambiguous response.
    r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_PROTECTED'
    writes=copy.deepcopy(b.writes)
    assert call(b,plan,policy,tmp_path)['status']=='PAPER_PROTECTED' and b.writes==writes

def test_missing_uncertain_rearm_never_resends_after_restart(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path)
    def missing(*a,**kw):raise TimeoutError('uncertain never accepted')
    b.submit_stop_sell=missing
    # Flat exit is not fabricated when broker cannot establish kill ownership.
    b.close_position=lambda symbol:(_ for _ in ()).throw(TimeoutError('close uncertain'))
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    count=len(b.writes)
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    assert len(b.writes)==count

@pytest.mark.parametrize('kind',['live','different_qty','foreign_buy','no_intent'])
def test_no_ownership_means_no_protection_or_close(plan,policy,tmp_path,kind):
    b=setup_intent(plan,policy,tmp_path)
    if kind=='live':b.base_url='https://api.alpaca.markets'
    if kind=='different_qty':b.positions[-1]['qty']='.5'
    if kind=='foreign_buy':b.orders['foreign']={'id':'foreign','symbol':'NET','side':'buy','type':'limit','status':'new','qty':'.2'}
    if kind=='no_intent':(tmp_path/'paper.sqlite').unlink()
    before=copy.deepcopy(b.writes)
    assert call(b,plan,policy,tmp_path)['status'].startswith('BLOCKED')
    assert b.writes==before and b.positions[0]['symbol']=='OLD'

def test_read_only_missing_stop_never_posts_or_closes(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);before=copy.deepcopy(b.writes)
    assert call(b,plan,policy,tmp_path,False)['status']=='PAPER_MAINTENANCE_REQUIRED'
    assert b.writes==before

def test_closed_stop_terminal_replays_without_retiring_or_recreating_again(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path)
    b.positions=[p for p in b.positions if p['symbol']!='NET']
    stop=next(o for o in b.orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.4',filled_avg_price='96',filled_at='2026-10-08T13:30:02Z')
    first=call(b,plan,policy,tmp_path)
    assert first['status']=='PAPER_STOP_EXIT_PENDING_FINALITY'
    writes=copy.deepcopy(b.writes)
    assert call(b,plan,policy,tmp_path)==first and b.writes==writes

def test_later_foreign_filled_buy_cannot_be_adopted_as_old_position(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path)
    b.orders['later-buy']={'id':'later-buy','symbol':'NET','side':'buy','type':'market',
        'status':'filled','filled_qty':'.4','filled_avg_price':'100','filled_at':'2026-10-08T13:30:01Z'}
    before=copy.deepcopy(b.writes)
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION' and b.writes==before

def test_real_client_does_not_gain_generic_market_or_position_flatten_authority():
    from scripts.run_alpaca_dynamic_paper import PaperClient
    c=PaperClient('test-key','test-secret',['owned'])
    with pytest.raises(ValueError):c._request('POST','/v2/orders',{'symbol':'OLD','client_order_id':'owned',
        'side':'sell','type':'market','qty':'1','time_in_force':'day'})
    with pytest.raises(ValueError):c.close_position('OLD')

def test_accepted_rearm_then_ledger_write_crash_recovers_same_cid(plan,policy,tmp_path,monkeypatch):
    from scripts import equities_alpaca_paper_bridge as bridge
    b=setup_intent(plan,policy,tmp_path);write=bridge._atomic_write_json
    def fail(path,value):
        if Path(path).name=='protective_exit_hwm.json' and value['NET']['accepted_order_id']=='new-day-stop':raise OSError('crash after accept')
        return write(path,value)
    monkeypatch.setattr(bridge,'_atomic_write_json',fail)
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    writes=copy.deepcopy(b.writes);monkeypatch.setattr(bridge,'_atomic_write_json',write)
    assert call(b,plan,policy,tmp_path)['status']=='PAPER_PROTECTED' and b.writes==writes

def test_stop_retirement_crash_recovers_terminal_preparation(plan,policy,tmp_path,monkeypatch):
    b=setup_intent(plan,policy,tmp_path)
    b.positions=[p for p in b.positions if p['symbol']!='NET']
    stop=next(o for o in b.orders.values() if o['type']=='stop')
    stop.update(status='filled',filled_qty='.4',filled_avg_price='96',filled_at='2026-10-08T13:30:02Z')
    save=maintenance._save
    def fail(db,item):
        if item.get('terminal'):raise OSError('crash after native retirement')
        return save(db,item)
    monkeypatch.setattr(maintenance,'_save',fail)
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    monkeypatch.setattr(maintenance,'_save',save)
    assert call(b,plan,policy,tmp_path)['status']=='PAPER_STOP_EXIT_PENDING_FINALITY'

def test_native_stop_fill_during_unwind_is_classified_from_order_not_flatness(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path)
    stop=next(o for o in b.orders.values() if o['type']=='stop');stop['status']='new'
    def fill_during_cancel(oid):
        stop.update(status='filled',filled_qty='.4',filled_avg_price='96',filled_at='2026-10-08T13:30:02Z')
        b.positions=[p for p in b.positions if p['symbol']!='NET'];return copy.deepcopy(stop)
    b.cancel_order=fill_during_cancel
    r=maintenance.maintain_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,
        runtime=tmp_path,now_ms=1791466202000,send=True,unwind=True)
    assert r['exit_kind']=='NATIVE_STOP' and not any(x.get('close') for x in b.writes)

def test_delayed_market_exit_recovers_pending_partial_then_full_without_resend(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);b.rearm_422=True
    cid=maintenance.unwind_cid(plan['receipt_id'],b.account_id)
    def pending(symbol):
        b.writes.append({'close':symbol})
        o={'id':'pending-exit','client_order_id':cid,'symbol':'NET','type':'market','side':'sell','status':'new',
           'qty':'.4','filled_qty':'0','filled_avg_price':None,'filled_at':None}
        b.orders[cid]=o;return copy.deepcopy(o)
    b.close_position=pending
    r=call(b,plan,policy,tmp_path);assert r['status']=='PAPER_UNWIND_PENDING'
    before=copy.deepcopy(b.writes);o=b.orders[cid]
    o.update(status='partially_filled',filled_qty='.2',filled_avg_price='95',filled_at='2026-10-08T13:30:02Z')
    b.positions[-1]['qty']='.2'
    assert call(b,plan,policy,tmp_path)['status']=='PAPER_UNWIND_PENDING'
    o.update(status='filled',filled_qty='.4');b.positions=[p for p in b.positions if p['symbol']!='NET']
    r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_EMERGENCY_EXIT_PENDING_FINALITY' and r['exit_kind']=='EMERGENCY_MARKET'
    assert b.writes==before and call(b,plan,policy,tmp_path)==r

def test_lost_market_response_is_looked_up_and_never_resent(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path);b.rearm_422=True
    cid=maintenance.unwind_cid(plan['receipt_id'],b.account_id)
    def lost(symbol):
        b.writes.append({'close':symbol});b.positions=[p for p in b.positions if p['symbol']!=symbol]
        b.orders[cid]={'id':'lost-exit','client_order_id':cid,'symbol':symbol,'type':'market','side':'sell','status':'filled',
                      'qty':'.4','filled_qty':'.4','filled_avg_price':'95','filled_at':'2026-10-08T13:30:02Z'}
        raise TimeoutError('close accepted, response lost')
    b.close_position=lost
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    before=copy.deepcopy(b.writes)
    r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_EMERGENCY_EXIT_PENDING_FINALITY' and b.writes==before

def test_mixed_native_partial_stop_and_market_fill_keep_both_sources(plan,policy,tmp_path):
    b=setup_intent(plan,policy,tmp_path)
    stop=next(o for o in b.orders.values() if o['type']=='stop');stop['status']='new'
    def partial_cancel(oid):
        stop.update(status='canceled',filled_qty='.2',filled_avg_price='96',filled_at='2026-10-08T13:30:02Z')
        b.positions[-1]['qty']='.2';return copy.deepcopy(stop)
    b.cancel_order=partial_cancel
    def close_remaining(symbol):
        b.writes.append({'close':symbol});b.positions=[p for p in b.positions if p['symbol']!=symbol]
        o={'id':'rest','symbol':symbol,'type':'market','side':'sell','status':'filled','qty':'.2',
           'filled_qty':'.2','filled_avg_price':'95','filled_at':'2026-10-08T13:30:02Z'}
        b.orders['rest']=o;return copy.deepcopy(o)
    b.close_position=close_remaining
    r=maintenance.maintain_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,
        runtime=tmp_path,now_ms=1791466202000,send=True,unwind=True)
    assert r['exit_kind']=='MIXED_NATIVE_STOP_EMERGENCY' and len(r['exit_orders'])==2
    assert Decimal(r['gross_before_fees'])==Decimal('-1.8') and r['net_pnl_status']=='NOT_PROVEN'

def test_accepted_rearm_fills_before_crash_recovery_uses_proven_new_stop(plan,policy,tmp_path,monkeypatch):
    from scripts import equities_alpaca_paper_bridge as bridge
    b=setup_intent(plan,policy,tmp_path);write=bridge._atomic_write_json
    def fail(path,value):
        if Path(path).name=='protective_exit_hwm.json' and value['NET']['accepted_order_id']=='new-day-stop':raise OSError('lost native ledger')
        return write(path,value)
    monkeypatch.setattr(bridge,'_atomic_write_json',fail)
    assert call(b,plan,policy,tmp_path)['status']=='BLOCKED_EXECUTION'
    monkeypatch.setattr(bridge,'_atomic_write_json',write)
    stop=next(o for o in b.orders.values() if o['id']=='new-day-stop')
    stop.update(status='filled',filled_qty='.4',filled_avg_price='96',filled_at='2026-10-08T13:30:02Z')
    b.positions=[p for p in b.positions if p['symbol']!='NET'];writes=copy.deepcopy(b.writes)
    r=call(b,plan,policy,tmp_path)
    assert r['status']=='PAPER_STOP_EXIT_PENDING_FINALITY' and r['exit_orders'][0]['id']=='new-day-stop'
    assert call(b,plan,policy,tmp_path)==r and b.writes==writes
    blocks=json.loads((tmp_path/'reentry.json').read_text())['symbols']['NET']
    assert blocks['exit_order_id']=='new-day-stop'
