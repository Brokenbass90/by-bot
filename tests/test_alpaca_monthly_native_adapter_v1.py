"""Use the existing native unknown-send journal; no network in these tests."""
import copy
import json
from types import SimpleNamespace
import pytest
from scripts import equities_alpaca_paper_bridge as native


class Broker:
    def __init__(self):self.orders={};self.sent=[];self.positions=[];self.lose_once=False
    def get_account(self):return {'id':'fixture'}
    def get_order(self,id):return copy.deepcopy(self.orders[id])
    def get_order_by_client_id(self,cid):return next((copy.deepcopy(o) for o in self.orders.values() if o['client_order_id']==cid),None)
    def list_positions(self):return copy.deepcopy(self.positions)
    def list_orders(self,**kw):return [copy.deepcopy(o) for o in self.orders.values()
        if (kw.get('status')=='all' or o['status'] in {'new','partially_filled'})
        and (not kw.get('symbols') or o['symbol'] in kw['symbols'])]
    def submit_market_buy(self,symbol,notional,*,client_order_id):
        self.sent.append('buy')
        o=dict(id='entry',client_order_id=client_order_id,symbol=symbol,side='buy',type='market',
            time_in_force='day',notional=str(notional),qty='.3',status='filled',filled_qty='.3',
            filled_avg_price='311.222',filled_at='2026-11-02T14:30:01Z')
        self.orders['entry']=o;self.positions=[dict(symbol=symbol,qty='.3',avg_entry_price='311.222',side='long')]
        if self.lose_once:self.lose_once=False;raise OSError('response lost after accepted')
        return copy.deepcopy(o)
    def submit_stop_sell(self,symbol,*,qty,stop_price,time_in_force,client_order_id):
        self.sent.append('stop');o=dict(id='stop',client_order_id=client_order_id,symbol=symbol,
            side='sell',type='stop',status='new',qty=str(qty),filled_qty='0',stop_price=str(stop_price),time_in_force=time_in_force)
        self.orders['stop']=o;return copy.deepcopy(o)


def test_monthly_raw_atr_adapter_uses_existing_dispatch_and_recovers_without_duplicate(tmp_path,monkeypatch):
    monkeypatch.setenv('ALPACA_INTENDED_PAPER','1');monkeypatch.setenv('ALPACA_INTENDED_LIVE','0')
    broker=Broker();broker.lose_once=True
    kwargs=dict(client=broker,base_url=native._PAPER_API_URL,account_id='fixture',capital=487.42,
        reentry_path=tmp_path/'reentry.json',state_path=tmp_path/'floor.json',state_dir=tmp_path/'halt',
        pick=SimpleNamespace(ticker='NET',entry_day='2026-11-02',entry_price=360.9299926758,
            stop_price=327.38757934571),notional=100.,timeout_sec=0,
        baseline_atr20=16.771206665045003,baseline_signal_session='2026-10-30',
        baseline_selection_sha256='a'*64)
    with pytest.raises(OSError):native._submit_intended_reserved_entry(**kwargs)
    native._recover_intended_entry_intents(client=broker,base_url=native._PAPER_API_URL,account_id='fixture',capital=487.42,
        reentry_path=tmp_path/'reentry.json',state_path=tmp_path/'floor.json',state_dir=tmp_path/'halt')
    assert broker.sent==['buy','stop']
    assert broker.orders['stop']['stop_price']=='277.67'
    state=json.loads((tmp_path/'floor.json').read_text())['NET']
    assert state['accepted_stop_floor']==277.67 and state['hwm']==311.222
    assert state['entry_selection_policy']=='ALPACA_BASELINE_MONTHLY_DAILY_V1'
    assert state['atr20']==16.771206665045003
    assert state['signal_session']=='2026-10-30'


def test_baseline_metadata_cannot_be_partial_or_invalid_before_any_post(tmp_path,monkeypatch):
    monkeypatch.setenv('ALPACA_INTENDED_PAPER','1');monkeypatch.setenv('ALPACA_INTENDED_LIVE','0')
    broker=Broker()
    with pytest.raises((ValueError,native.IntendedPaperProtectionError)):
        native._submit_intended_reserved_entry(client=broker,base_url=native._PAPER_API_URL,
            account_id='fixture',capital=487.42,reentry_path=tmp_path/'reentry.json',state_path=tmp_path/'floor.json',state_dir=tmp_path/'halt',
            pick=SimpleNamespace(ticker='NET',entry_day='2026-11-02',entry_price=100.,stop_price=94.),
            notional=100.,timeout_sec=0,baseline_atr20=True,
            baseline_signal_session='2026-10-30',baseline_selection_sha256='a'*64)
    assert not broker.sent
