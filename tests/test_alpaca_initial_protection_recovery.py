"""Initial stop failure/early fills cannot strand or invent a protected lifecycle."""
import copy,json
from pathlib import Path
import pytest
from test_alpaca_dynamic_paper import policy,plan,NOW
from test_alpaca_dynamic_paper_maintenance import DayBroker
from research_lab.alpaca_dynamic_paper import execute_paper
from research_lab import alpaca_dynamic_paper_maintenance as maintenance
from scripts.equities_alpaca_paper_bridge import AlpacaAPIError


class InitialBroker(DayBroker):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.clock='2026-10-07T13:30:01Z'
    def get_clock(self):return {'is_open':True,'timestamp':self.clock}
    def submit_stop_sell(self,symbol,**kw):
        if self.kind=='reject':raise AlpacaAPIError(422,'PAPER_HTTP_422')
        if self.kind=='missing':raise TimeoutError('unknown stop')
        order=super().submit_stop_sell(symbol,**kw)
        stored=self.orders[kw['client_order_id']]
        stored.update(status='filled',filled_qty='.4',filled_avg_price='96',filled_at='2026-10-07T13:30:03Z')
        self.positions=[p for p in self.positions if p['symbol']!=symbol]
        raise TimeoutError('stop filled before response')
    def close_position(self,symbol):
        receipt=super().close_position(symbol)
        self.orders['emergency'].update(client_order_id=maintenance.unwind_cid(self.parent,self.account_id),filled_at='2026-10-07T13:30:04Z')
        return copy.deepcopy(self.orders['emergency'])


def test_confirmed_initial_422_unwinds_owned_fill_and_restart_never_resends(plan,policy,tmp_path):
    b=InitialBroker('reject');b.parent=plan['receipt_id']
    r=execute_paper(plan,policy,b,b.account_id,tmp_path,NOW,send=True)
    assert r['status']=='BLOCKED_EXECUTION'
    assert b.positions==[{'symbol':'OLD','qty':'2','avg_entry_price':'50'}]
    first=copy.deepcopy(b.writes)
    replay=maintenance.recover_initial_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,runtime=tmp_path,now_ms=NOW+5000)
    assert replay['status']=='PAPER_INITIAL_EXIT_PENDING_FINALITY'
    assert replay['exit_kind']=='EMERGENCY_MARKET' and replay['initial_full_protection_proven'] is False
    assert b.writes==first


def test_lost_stop_response_then_full_stop_fill_is_real_terminal_not_position_mismatch(plan,policy,tmp_path):
    b=InitialBroker('filled');b.parent=plan['receipt_id']
    assert execute_paper(plan,policy,b,b.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    first=copy.deepcopy(b.writes)
    r=maintenance.recover_initial_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,runtime=tmp_path,now_ms=NOW+5000)
    assert r['status']=='PAPER_INITIAL_EXIT_PENDING_FINALITY' and r['exit_kind']=='NATIVE_STOP'
    assert r['initial_full_protection_proven'] is False and b.writes==first


def test_unknown_missing_stop_is_owner_action_without_blind_sell_or_stop_resend(plan,policy,tmp_path):
    b=InitialBroker('missing');b.parent=plan['receipt_id']
    assert execute_paper(plan,policy,b,b.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    first=copy.deepcopy(b.writes)
    r=maintenance.recover_initial_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,runtime=tmp_path,now_ms=NOW+5000)
    assert r['status']=='BLOCKED_EXECUTION' and r['reason']=='UNKNOWN_INITIAL_STOP_OWNER_ACTION_REQUIRED'
    assert b.writes==first and any(p['symbol']=='NET' for p in b.positions)


def test_initial_partial_stop_and_delayed_unwind_keep_mixed_sources_without_resend(plan,policy,tmp_path):
    class PartialBroker(InitialBroker):
        def submit_stop_sell(self,symbol,**kw):
            order=DayBroker.submit_stop_sell(self,symbol,**kw)
            self.orders[kw['client_order_id']].update(status='partially_filled',filled_qty='.2',filled_avg_price='96',filled_at='2026-10-07T13:30:03Z')
            next(p for p in self.positions if p['symbol']==symbol)['qty']='.2'
            raise TimeoutError('initial partial stop response lost')
        def cancel_order(self,oid):
            row=next(o for o in self.orders.values() if o['id']==oid)
            row['status']='canceled';self.writes.append({'cancel':oid});return copy.deepcopy(row)
        def close_position(self,symbol):
            self.writes.append({'close':symbol})
            cid=maintenance.unwind_cid(self.parent,self.account_id)
            self.orders[cid]={'id':'market','client_order_id':cid,'symbol':symbol,'side':'sell','type':'market',
                'qty':'.2','status':'new','filled_qty':'0','filled_avg_price':None,'filled_at':None}
            return copy.deepcopy(self.orders[cid])
    b=PartialBroker('partial');b.parent=plan['receipt_id']
    assert execute_paper(plan,policy,b,b.account_id,tmp_path,NOW,send=True)['status']=='BLOCKED_EXECUTION'
    assert maintenance.recover_initial_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,runtime=tmp_path,now_ms=NOW+5000)['status']=='PAPER_UNWIND_PENDING'
    writes=copy.deepcopy(b.writes)
    cid=maintenance.unwind_cid(plan['receipt_id'],b.account_id)
    b.orders[cid].update(status='filled',filled_qty='.2',filled_avg_price='95',filled_at='2026-10-07T13:30:07Z')
    b.positions=[p for p in b.positions if p['symbol']!='NET']
    r=maintenance.recover_initial_paper(plan=plan,policy=policy,client=b,expected_paper_id=b.account_id,runtime=tmp_path,now_ms=NOW+10000)
    assert r['status']=='PAPER_INITIAL_EXIT_PENDING_FINALITY' and r['exit_kind']=='MIXED_NATIVE_STOP_EMERGENCY'
    assert {o['type'] for o in r['exit_orders']}=={'stop','market'} and b.writes==writes
