import contextlib
import io
import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from scripts import alpaca_adaptive_paper as driver
from scripts import alpaca_protective_exit_manager as manager
from scripts import equities_alpaca_paper_bridge as bridge
from test_alpaca_intended_rotation import Broker, record, NOW


@pytest.mark.parametrize('live', [False, True])
@pytest.mark.parametrize('crash_after_buy', [False, True])
def test_month_turn_real_driver_closes_stale_retains_floor_and_buys_once(tmp_path, monkeypatch, live, crash_after_buy):
    class Frozen(datetime):
        current = NOW
        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
    for module in [driver, bridge, manager]: monkeypatch.setattr(module, 'datetime', Frozen)
    class Exchange(Broker):
        def __init__(self):
            super().__init__(); self.buys=[]; self.crash_after_buy=crash_after_buy
            self.positions.pop('FOREIGN'); self.orders.pop('entry-FOREIGN'); self.orders.pop('stop-FOREIGN')
            for p in self.positions.values(): p['current_price']='109'
            self.orders['stop-KEEP']['stop_price']='106.14'
        def get_account(self): return {'id':'fixture','status':'ACTIVE','currency':'USD','cash':'487.42','equity':'487.42','buying_power':'487.42'}
        def _request(self, method, path):
            assert method=='GET'
            return [{'date':'2026-09-30','open':'09:30','close':'16:00'},{'date':'2026-10-01','open':'09:30','close':'16:00'}]
        def submit_market_buy(self,symbol,notional,*,client_order_id):
            self.buys.append((symbol,notional));qty=notional/100
            entry={'id':'entry-'+symbol,'client_order_id':client_order_id,'symbol':symbol,'side':'buy','type':'market','status':'filled','notional':str(notional),'time_in_force':'day','filled_qty':str(qty),'filled_avg_price':'100','filled_at':NOW.isoformat()}
            self.orders[entry['id']]=entry
            self.positions[symbol]={'symbol':symbol,'side':'long','qty':str(qty),'avg_entry_price':'100','current_price':'100'}
            if self.crash_after_buy:
                raise OSError('response lost after accepted entry')
            return dict(entry)
        def submit_stop_sell(self,symbol,**kwargs):
            key='stop-new-'+str(len(self.orders))
            order={'id':key,'client_order_id':kwargs.get('client_order_id'),'symbol':symbol,'side':'sell','type':'stop','status':'new','qty':str(kwargs['qty']),'filled_qty':'0','stop_price':str(kwargs['stop_price']),'time_in_force':'day'}
            self.orders[key]=order
            return dict(order)
        def replace_order(self,key,payload):
            old=self.orders[key];old['status']='replaced'
            return self.submit_stop_sell(old['symbol'],qty=float(old['qty']),stop_price=float(payload['stop_price']),time_in_force='day')
        def get_order_by_client_id(self, client_order_id):
            return next((dict(order) for order in self.orders.values() if order.get('client_order_id') == client_order_id), None)
    exchange=Exchange()
    for module in [bridge,manager]:monkeypatch.setattr(module,'AlpacaClient',lambda *args:exchange)
    for k,v in {'ALPACA_API_KEY_ID':'fixture','ALPACA_API_SECRET_KEY':'fixture','ALPACA_BRIDGE_LOCK_PATH':str(tmp_path/'account.lock'),'ALPACA_BASE_URL':'https://api.alpaca.markets' if live else bridge._PAPER_API_URL}.items():monkeypatch.setenv(k,v)
    if live:
        cfg={'schema_version':1,'endpoint':'https://api.alpaca.markets','strategy_id':bridge._INTENDED_PAPER_STRATEGY_ID,'account_id':'fixture','enabled':True,'capital_usd':487.42,'max_positions':4,'gross_exposure':.7,'maximum_weight':.6,'selector_source_hashes':driver._frozen_source_hashes(),'runtime_dir':str(tmp_path.resolve()),'account_lock_path':str(tmp_path/'account.lock')}
        (tmp_path/'binding.json').write_text(json.dumps(cfg))
        for k,v in {'ALPACA_INTENDED_LIVE_BINDING_PATH':str(tmp_path/'binding.json'),'ALPACA_INTENDED_LIVE_ACK':'INTENDED_LIVE_CANARY','ALPACA_LIVE_ACCOUNT_ROLE':'monthly_v38','ALPACA_LIVE_CONFIRM':'MONTHLY_V38_LIVE','ALPACA_LIVE_MAX_CAPITAL_USD':'487.42'}.items():monkeypatch.setenv(k,v)
    (tmp_path/'foreign_owners.json').write_text(json.dumps({'account_id':'fixture','owners':{}}))
    ledger=tmp_path/'protective_exit/protective_exit_hwm.json';ledger.parent.mkdir()
    keep=record('KEEP');keep['accepted_stop_floor']=106.14
    ledger.write_text(json.dumps({'OLD':record('OLD'),'KEEP':keep}))
    picks = [('KEEP',.6),('NEW',.4)] if not crash_after_buy else [('KEEP',.6),('NEW',.25),('OTHER',.15)]
    selection={'mode':'intended_prepare_only','signal_session':'2026-09-30','entry_session':'2026-10-01','max_positions':4,'target_gross_exposure':.7,'maximum_weight':.6,'capital_usd':487.42,'selector_source_hashes':driver._frozen_source_hashes(),'picks':[{'symbol':s,'weight':w,'rawscore':1,'atr20_pct':3,'signal_close':100.,'stop_price':94.} for s,w in picks]}
    monkeypatch.setattr(driver,'_load_intended_hourly_history',lambda _: {})
    monkeypatch.setattr(driver,'prepare_intended_report',lambda *args,**kwargs:dict(selection))
    def dispatch(command,**kwargs):
        with monkeypatch.context() as context:
            for k,v in kwargs['env'].items():context.setenv(k,v)
            context.setattr(sys,'argv',command[1:])
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                code=bridge._main_unlocked() if 'equities_alpaca_paper_bridge.py' in command[1] else manager._main_unlocked()
            return subprocess.CompletedProcess(command,code,out.getvalue(),err.getvalue())
    monkeypatch.setattr(driver.subprocess,'run',dispatch)
    if crash_after_buy:
        assert driver.run_intended_cycle(tmp_path,capital=487.42,send_orders=True,client=exchange,live=live,monthly=True,cache_dir=tmp_path)==9
        exchange.crash_after_buy=False
    for _ in range(2):
        assert driver.run_intended_cycle(tmp_path,capital=487.42,send_orders=True,client=exchange,live=live,monthly=True,cache_dir=tmp_path)==0, (tmp_path/'latest_intended_run.json').read_text()
    assert [s[0] for s in exchange.sent]==['OLD']
    expected_notional = 85.29 if crash_after_buy else 136.47
    assert exchange.buys==[('NEW',expected_notional)]
    state=json.loads(ledger.read_text())
    assert {key:state['KEEP'][key] for key in keep}==keep
    assert set(state)=={'KEEP','NEW'}
    assert len([order for order in exchange.orders.values() if order.get('symbol') == 'NEW' and order.get('type') == 'stop']) == 1
    assert not any(order.get('symbol') == 'OTHER' and order.get('side') == 'buy' for order in exchange.orders.values())
    exchange.orders[state['NEW']['accepted_order_id']]['status'] = 'expired'
    Frozen.current = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
    prior_buys = list(exchange.buys)
    assert driver.run_intended_cycle(tmp_path,capital=487.42,send_orders=True,client=exchange,live=live,monthly=True,cache_dir=tmp_path)==0
    rearmed = json.loads(ledger.read_text())['NEW']
    assert rearmed['accepted_order_id'] != state['NEW']['accepted_order_id']
    assert exchange.buys == prior_buys
    exits=json.loads((tmp_path/'monthly_reentry_block.json').read_text())
    assert len(exits['rotation_exits'])==1 and exits['symbols']=={}
