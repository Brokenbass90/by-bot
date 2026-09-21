import json
from datetime import datetime, timezone

import pytest
from scripts import equities_alpaca_paper_bridge as bridge
from scripts import alpaca_protective_exit_manager as manager


def _state():
    return {'SCHW': {'entry_order_id': 'entry-1', 'accepted_order_id': 'stop-2',
        'account_id': 'paper-1', 'strategy_id': bridge._INTENDED_PAPER_STRATEGY_ID,
        'entry_price': 100, 'qty': .4, 'hwm': 110, 'accepted_stop_floor': 106,
        'lifecycle_first_seen_at_utc': '2026-09-18T13:31:00Z'}}


class Broker:
    def __init__(self, **changes):
        self.order = {'id':'stop-2','symbol':'SCHW','side':'sell','type':'stop',
            'status':'filled','filled_qty':'.4','filled_avg_price':'105.98',
            'filled_at':'2026-09-21T14:00:00Z', **changes}
    def get_order(self, order_id):
        assert order_id == 'stop-2'
        return dict(self.order)
    def list_positions(self):
        return []


def _run(tmp_path, broker=None):
    ledger=tmp_path/'floor.json'; blocks=tmp_path/'blocks.json'
    if not ledger.exists(): ledger.write_text(json.dumps(_state()))
    state=json.loads(ledger.read_text())
    return bridge._reconcile_intended_stop_exits(client=broker or Broker(),
        state=state,state_path=ledger,reentry_path=blocks,positions={},open_orders=[],
        account_id='paper-1',state_dir=tmp_path, now=datetime(2026,9,21,15,tzinfo=timezone.utc))


def test_actual_stop_fill_creates_21_day_lock_before_retirement_and_never_extends(tmp_path):
    assert _run(tmp_path)=={'SCHW'}
    raw=(tmp_path/'blocks.json').read_bytes()
    rec=json.loads(raw)['symbols']['SCHW']
    assert rec['blocked_until']=='2026-10-12T14:00:00Z'
    assert rec['exit_order_id']=='stop-2'
    assert rec['entry_order_id']=='entry-1'
    assert json.loads((tmp_path/'floor.json').read_text())=={}
    assert _run(tmp_path)==set()
    assert (tmp_path/'blocks.json').read_bytes()==raw


@pytest.mark.parametrize('change', [
    {'status':'canceled'}, {'id':'wrong'}, {'filled_qty':'.1'},
    {'filled_avg_price':'NaN'}, {'filled_at':'2026-09-01T14:00:00Z'},
])
def test_unconfirmed_exit_preserves_lifecycle_and_halts_new_entries(tmp_path, change):
    with pytest.raises(bridge.IntendedPaperProtectionError): _run(tmp_path,Broker(**change))
    assert json.loads((tmp_path/'floor.json').read_text())==_state()
    assert json.loads((tmp_path/'.paper-entry-halt.json').read_text())['halted']


def test_previous_exit_block_cannot_mask_new_stop_exit(tmp_path):
    (tmp_path/'blocks.json').write_text(json.dumps({'symbols':{'SCHW':{
        'created_at':'2026-08-01T14:00:00Z','blocked_until':'2026-08-22T14:00:00Z',
        'exit_order_id':'old-stop'}}}))
    _run(tmp_path)
    rec=json.loads((tmp_path/'blocks.json').read_text())['symbols']['SCHW']
    assert rec['exit_order_id']=='stop-2'
    assert rec['blocked_until']=='2026-10-12T14:00:00Z'


def test_crash_after_block_before_ledger_write_recovers_without_extending(tmp_path, monkeypatch):
    original=bridge._atomic_write_json
    def fail_ledger(path, value):
        if path.name=='floor.json': raise OSError('fixture crash')
        return original(path,value)
    monkeypatch.setattr(bridge,'_atomic_write_json',fail_ledger)
    with pytest.raises(OSError): _run(tmp_path)
    assert json.loads((tmp_path/'floor.json').read_text())==_state()
    saved=(tmp_path/'blocks.json').read_bytes()
    monkeypatch.setattr(bridge,'_atomic_write_json',original)
    _run(tmp_path)
    assert (tmp_path/'blocks.json').read_bytes()==saved
    assert json.loads((tmp_path/'floor.json').read_text())=={}


def test_malformed_block_cannot_silently_disappear(tmp_path):
    (tmp_path/'blocks.json').write_text(json.dumps({'symbols':{'AMZN':'corrupt'}}))
    with pytest.raises(bridge.IntendedPaperProtectionError): _run(tmp_path)
    assert json.loads((tmp_path/'floor.json').read_text())==_state()


def test_day_rearm_confirms_new_id_and_never_lowers_floor(tmp_path):
    class RearmBroker:
        sent=[]
        def submit_stop_sell(self,symbol,**kwargs):
            self.sent.append((symbol,kwargs))
            return {'id':'new-stop'}
        def get_order(self,order_id):
            return {'id':order_id,'symbol':'SCHW','side':'sell','type':'stop','status':'new',
                    'qty':'.4','filled_qty':'0','stop_price':'106','time_in_force':'day'}
    state=_state(); path=tmp_path/'floor.json';path.write_text(json.dumps(state))
    broker=RearmBroker()
    bridge._rearm_intended_position(client=broker, symbol='SCHW',
        position={'qty':'.4','avg_entry_price':'100','current_price':'109','side':'long'},
        existing_stops=[], state=state,state_path=path,account_id='paper-1')
    assert broker.sent==[('SCHW',{'qty':.4,'stop_price':106.0,'time_in_force':'day'})]
    row=json.loads(path.read_text())['SCHW']
    assert row['accepted_order_id']=='new-stop' and row['hwm']==110
    assert row['accepted_stop_floor']==106


def test_manager_preserves_disappeared_position_until_bridge_confirms_exit(tmp_path,monkeypatch):
    import sys
    state=_state();path=tmp_path/'floor.json';path.write_text(json.dumps(state))
    class Client:
        def __init__(self,*args): pass
        def get_account(self): return {'id':'paper-1'}
        def get_clock(self): return {'is_open':True}
        def list_positions(self): return []
        def list_orders(self,**kwargs): return []
    for key,value in {'ALPACA_BASE_URL':bridge._PAPER_API_URL,'ALPACA_API_KEY_ID':'fixture',
        'ALPACA_API_SECRET_KEY':'fixture','ALPACA_INTENDED_PAPER':'1',
        'ALPACA_PROTECTIVE_EXIT_HWM_PATH':str(path),'ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR':str(tmp_path),
        'ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH':str(tmp_path/'receipt.json'),
        'ALPACA_PROTECTIVE_EXIT_APPLY':'0'}.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(manager,'AlpacaClient',Client)
    monkeypatch.setattr(sys,'argv',['manager'])
    assert manager._main_unlocked()==0
    assert json.loads(path.read_text())==state
