import json
from pathlib import Path
import pytest
from scripts import alpaca_adaptive_paper as driver


class Broker:
    def get_account(self): return {'id':'paper-1','status':'ACTIVE','trading_blocked':False}
    def get_clock(self): return {'is_open':False,'timestamp':'2026-09-20T15:00:00Z','next_open':'2026-09-21T13:30:00Z'}
    def list_positions(self): return [{'symbol':'AMZN','qty':'.591'}]
    def list_orders(self,**kwargs): return []


def setup(tmp_path,monkeypatch):
    (tmp_path/'latest_selection.json').write_text(json.dumps({'entry_session':'2026-09-21',
        'signal_session':'2026-09-18','paper_capital_usd':1000,'mode':'intended_prepare_only',
        'target_gross_exposure':.7,'maximum_weight':.6,'max_positions':4,
        'picks':[], 'selector_source_hashes':driver._frozen_source_hashes()}))
    driver.write_intended_bridge_picks_csv({'entry_session':'2026-09-21','picks':[]},tmp_path/'current_cycle_picks.csv')
    (tmp_path/'foreign_owners.json').write_text(json.dumps({'account_id':'paper-1','owners':{'AMZN':'intraday'}}))
    monkeypatch.setenv('ALPACA_BASE_URL','https://paper-api.alpaca.markets')
    monkeypatch.setenv('ALPACA_API_KEY_ID','fixture')
    monkeypatch.setenv('ALPACA_API_SECRET_KEY','fixture')
    monkeypatch.setenv('ALPACA_BRIDGE_LOCK_PATH',str(tmp_path/'account.lock'))


def test_closed_market_arms_without_orders_and_preserves_foreign_position(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    monkeypatch.setattr(driver.subprocess,'run',lambda *a,**k:pytest.fail('closed market broker write'))
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=Broker())==0
    receipt=json.loads((tmp_path/'latest_intended_run.json').read_text())
    assert receipt['status']=='WAITING_FOR_REGULAR_SESSION'
    assert receipt['foreign_positions']==['AMZN']
    assert receipt['money_authority'] is False


def test_unknown_position_halts_before_execution(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    class Unknown(Broker):
        def list_positions(self):return [{'symbol':'UNPROVEN','qty':'1'}]
    monkeypatch.setattr(driver.subprocess,'run',lambda *a,**k:pytest.fail('unproven ownership'))
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=Unknown())==9
    receipt=json.loads((tmp_path/'latest_intended_run.json').read_text())
    assert receipt['status']=='HALTED' and 'unknown_position' in receipt['error']


def test_wrong_account_and_capital_cannot_activate(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    class Wrong(Broker):
        def get_account(self):return {'id':'other'}
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=Wrong())==9
    assert driver.run_intended_cycle(tmp_path,capital=1001,send_orders=True,client=Broker())==9


def test_failed_protection_invokes_scoped_paper_emergency(tmp_path,monkeypatch):
    import subprocess
    setup(tmp_path,monkeypatch)
    state=tmp_path/'protective_exit/protective_exit_hwm.json';state.parent.mkdir()
    state.write_text(json.dumps({'CRM':{'entry_order_id':'own-entry','account_id':'paper-1',
        'strategy_id':'ALPACA-BASELINE-26f7ff663dc98e87','entry_price':100,'qty':.5,
        'hwm':100,'accepted_stop_floor':0,'protection_pending':True,
        'lifecycle_first_seen_at_utc':'2026-09-21T13:30:01Z'}}))
    class Open(Broker):
        def get_clock(self):return {'is_open':True,'timestamp':'2026-09-21T13:31:00Z'}
        def list_positions(self):return [{'symbol':'CRM','qty':'.5','avg_entry_price':'100'}]
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs['env']))
        if '--apply-kill' in command:
            proof=json.loads(Path(command[command.index('--paper-kill-owned')+1]).read_text())
            assert [p['symbol'] for p in proof['positions']]==['CRM']
            return subprocess.CompletedProcess(command,0,'{"status":"confirmed_flat"}','')
        return subprocess.CompletedProcess(command,9,'protection failure','')
    monkeypatch.setattr(driver.subprocess,'run',run)
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=Open())==9
    assert len(calls)==2 and '--apply-kill' in calls[1][0]
    assert calls[1][1]['ALPACA_ALLOW_NEW_ENTRIES']=='0'
    assert calls[1][1]['ALPACA_PAPER_KILL_ACK']=='PAPER_OWNED_EXITS_ONLY'


def test_full_missed_session_uses_broker_calendar_not_weekdays():
    from datetime import datetime,timezone
    class Calendar:
        def _request(self,method,path):
            assert method=='GET' and path.startswith('/v2/calendar?')
            return [{'date':'2026-09-18','open':'09:30','close':'16:00'},
                    {'date':'2026-09-21','open':'09:30','close':'16:00'}]
    utc=timezone.utc
    last=datetime(2026,9,18,19,tzinfo=utc)
    assert not driver._intended_missed_session(Calendar(),last,datetime(2026,9,21,14,tzinfo=utc))
    assert driver._intended_missed_session(Calendar(),last,datetime(2026,9,22,14,tzinfo=utc))


@pytest.mark.parametrize("live", [False, True])
def test_real_driver_bridge_ratchet_rearm_and_stop_exit_without_broker_network(tmp_path,monkeypatch,live):
    import io,contextlib,subprocess,sys
    from datetime import datetime,timedelta,timezone
    from scripts import equities_alpaca_paper_bridge as bridge
    from scripts import alpaca_protective_exit_manager as manager
    setup(tmp_path,monkeypatch)
    if live:
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                value=cls(2026,10,1,14,0,tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        datetime=FrozenDatetime
        for module in [driver,bridge,manager]:monkeypatch.setattr(module,'datetime',FrozenDatetime)
        cfg={'schema_version':1,'strategy_id':bridge._INTENDED_PAPER_STRATEGY_ID,
             'endpoint':'https://api.alpaca.markets','account_id':'paper-1','enabled':True,
             'capital_usd':1000,'max_positions':4,'gross_exposure':.70,'maximum_weight':.60,
             'selector_source_hashes':driver._frozen_source_hashes()}
        (tmp_path/'live_binding.json').write_text(json.dumps(cfg))
        for k,v in {'ALPACA_BASE_URL':'https://api.alpaca.markets',
          'ALPACA_INTENDED_LIVE_BINDING_PATH':str(tmp_path/'live_binding.json'),
          'ALPACA_INTENDED_LIVE_ACK':'INTENDED_LIVE_CANARY','ALPACA_LIVE_ACCOUNT_ROLE':'monthly_v38',
          'ALPACA_LIVE_CONFIRM':'MONTHLY_V38_LIVE','ALPACA_LIVE_MAX_CAPITAL_USD':'1000'}.items():monkeypatch.setenv(k,v)
    now=datetime.now(timezone.utc)
    report=json.loads((tmp_path/'latest_selection.json').read_text())
    if live:report.update(signal_session='2026-09-30',capital_usd=1000)

    report['entry_session']=now.date().isoformat()
    report['picks']=[{'symbol':'CRM','weight':.6,'signal_close':100.,'stop_price':94.,'rawscore':1.,'atr20_pct':3.}]
    (tmp_path/'latest_selection.json').write_text(json.dumps(report))
    driver.write_intended_bridge_picks_csv(report,tmp_path/'current_cycle_picks.csv')
    class Exchange:
        buys=0
        position=None
        orders={}
        def get_account(self):return {'id':'paper-1','status':'ACTIVE','cash':'10000','buying_power':'10000'}
        def get_clock(self):return {'is_open':True,'timestamp':datetime.now(timezone.utc).isoformat()}
        def list_positions(self):return [dict(self.position)] if self.position else []
        def list_orders(self,**kwargs):return [dict(v) for v in self.orders.values() if v['status']=='new']
        def get_order(self,key):return dict(self.orders[key])
        def submit_market_buy(self,symbol,notional):
            assert notional == 420.0
            qty = notional / 101.0
            self.buys+=1
            row={'id':'entry','symbol':symbol,'side':'buy','type':'market','status':'filled',
                 'filled_qty':str(qty),'filled_avg_price':'101','filled_at':datetime.now(timezone.utc).isoformat()}
            self.orders['entry']=row
            self.position={'symbol':symbol,'qty':str(qty),'avg_entry_price':'101','current_price':'110','side':'long'}
            return dict(row)
        def submit_stop_sell(self,symbol,**kwargs):
            key='stop-'+str(len(self.orders))
            self.orders[key]={'id':key,'symbol':symbol,'side':'sell','type':'stop','status':'new',
                'qty':str(kwargs['qty']),'filled_qty':'0','stop_price':str(kwargs['stop_price']),
                'time_in_force':kwargs['time_in_force']}
            return dict(self.orders[key])
        def replace_order(self,key,payload):
            old=self.orders[key];old['status']='replaced'
            return self.submit_stop_sell(old['symbol'],qty=float(old['qty']),stop_price=float(payload['stop_price']),time_in_force=old['time_in_force'])
        def _request(self,*args):return [{"date":"2026-09-30"},{"date":"2026-10-01"}] if live else []
    broker=Exchange()
    monkeypatch.setattr(bridge,'AlpacaClient',lambda *args:broker)
    monkeypatch.setattr(manager,'AlpacaClient',lambda *args:broker)
    def run(command,**kwargs):
        with monkeypatch.context() as context:
            for k,v in kwargs['env'].items():context.setenv(k,v)
            context.setattr(sys,'argv',command[1:])
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                if 'equities_alpaca_paper_bridge.py' in command[1]:rc=bridge._main_unlocked()
                else:rc=manager._main_unlocked()
            return subprocess.CompletedProcess(command,rc,out.getvalue(),err.getvalue())
    monkeypatch.setattr(driver.subprocess,'run',run)
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=broker,live=live)==0
    state_path=tmp_path/'protective_exit/protective_exit_hwm.json'
    first=json.loads(state_path.read_text())['CRM']
    assert first['hwm']==110 and first['accepted_stop_floor']>101
    broker.orders[first['accepted_order_id']]['status']='expired'
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=broker,live=live)==0
    after=json.loads(state_path.read_text())['CRM']
    assert after['accepted_order_id']!=first['accepted_order_id']
    assert after['accepted_stop_floor']==first['accepted_stop_floor'] and after['hwm']==110
    closed=broker.orders[after['accepted_order_id']]
    closed.update(status='filled',filled_qty=closed['qty'],filled_avg_price='106',filled_at=datetime.now(timezone.utc).isoformat())
    broker.position=None
    assert driver.run_intended_cycle(tmp_path,capital=1000,send_orders=True,client=broker,live=live)==0
    assert broker.buys==1 and json.loads(state_path.read_text())=={}
    block=json.loads((tmp_path/'monthly_reentry_block.json').read_text())['symbols']['CRM']
    assert block['exit_order_id']==closed['id']
    assert datetime.fromisoformat(block['blocked_until'].replace('Z','+00:00'))-datetime.fromisoformat(block['created_at']) > timedelta(days=20,hours=23)
