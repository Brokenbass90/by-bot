import json
import sys
import pytest
from scripts import alpaca_adaptive_paper as driver


class ReadOnlyBroker:
    def get_account(self):
        return {'id':'live-fixture','status':'ACTIVE','currency':'USD','cash':'487.42','equity':'487.42','trading_blocked':False,'account_blocked':False}
    def get_clock(self):return {'is_open':False,'next_open':'2026-10-01T09:30:00-04:00'}
    def list_positions(self):return []
    def list_orders(self, **kwargs):return []


def bind(tmp_path, monkeypatch, **changes):
    value={'schema_version':1,'strategy_id':'ALPACA-BASELINE-26f7ff663dc98e87',
           'endpoint':'https://api.alpaca.markets','account_id':'live-fixture','enabled':False,
           'capital_usd':None,'max_positions':4,'gross_exposure':.70,'maximum_weight':.60,
           'selector_source_hashes':driver._frozen_source_hashes()}
    value.update(changes)
    path=tmp_path/'binding.json';path.write_text(json.dumps(value))
    monkeypatch.setenv('ALPACA_INTENDED_LIVE_BINDING_PATH',str(path))
    monkeypatch.setenv('ALPACA_BASE_URL','https://api.alpaca.markets')
    monkeypatch.setenv('ALPACA_API_KEY_ID','fixture')
    monkeypatch.setenv('ALPACA_API_SECRET_KEY','fixture')
    monkeypatch.setattr(driver.subprocess,'run',lambda *a,**kw:pytest.fail('preflight must never dispatch broker writer'))


def test_disabled_unallocated_live_binding_reads_real_identity_without_order_dispatch(tmp_path,monkeypatch):
    bind(tmp_path,monkeypatch)
    assert driver.preflight_intended_live(tmp_path,client=ReadOnlyBroker())==0
    r=json.loads((tmp_path/'live_binding_preflight.json').read_text())
    assert r['status']=='LIVE_ACCOUNT_BOUND_READ_ONLY'
    assert r['broker_writes']==0 and r['money_authority'] is False
    assert r['capital_usd'] is None and r['activation_ready'] is False
    assert r['positions_count']==0 and r['open_orders_count']==0


@pytest.mark.parametrize('fault',['account','source','position','order','paper'])
def test_preflight_cannot_validate_mismatched_or_occupied_scope(tmp_path,monkeypatch,fault):
    changes={'account_id':'wrong'} if fault=='account' else {'selector_source_hashes':{}} if fault=='source' else {}
    bind(tmp_path,monkeypatch,**changes)
    client=ReadOnlyBroker()
    if fault=='position':client.list_positions=lambda:[{'symbol':'AMZN','qty':'1'}]
    if fault=='order':client.list_orders=lambda **kw:[{'symbol':'AMZN','status':'new'}]
    if fault=='paper':monkeypatch.setenv('ALPACA_BASE_URL','https://paper-api.alpaca.markets')
    assert driver.preflight_intended_live(tmp_path,client=client)==9
    r=json.loads((tmp_path/'live_binding_preflight.json').read_text())
    assert r['status']=='NOT_CONFIRMED' and r['broker_writes']==0


def test_live_preflight_cli_rejects_send_orders_before_dispatch(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['driver','--preflight-intended-live','--send-orders'])
    assert driver.main()==2
    assert 'live_preflight_rejects_order_or_execution_flags' in capsys.readouterr().out


def test_monthly_schedule_rejects_midmonth_acceptance_as_live_strategy_entry():
    class Calendar:
        def _request(self,method,path):
            assert method=='GET' and path.startswith('/v2/calendar?')
            return [{'date':'2026-09-18'},{'date':'2026-09-21'},
                    {'date':'2026-09-30'},{'date':'2026-10-01'}]
    with pytest.raises(ValueError,match='monthly'):
        driver.validate_intended_live_schedule(Calendar(),{'signal_session':'2026-09-18','entry_session':'2026-09-21'})
    receipt=driver.validate_intended_live_schedule(Calendar(),{'signal_session':'2026-09-30','entry_session':'2026-10-01'})
    assert receipt['signal_session']=='2026-09-30' and receipt['entry_session']=='2026-10-01'


def test_mutating_binding_during_preflight_cannot_produce_validated_receipt(tmp_path,monkeypatch):
    bind(tmp_path,monkeypatch)
    class Changed(ReadOnlyBroker):
        def get_account(self):
            path=tmp_path/'binding.json';b=json.loads(path.read_text());b['capital_usd']=450.;path.write_text(json.dumps(b))
            return super().get_account()
    assert driver.preflight_intended_live(tmp_path,client=Changed())==9
    assert 'binding_changed' in json.loads((tmp_path/'live_binding_preflight.json').read_text())['error']


def test_binding_change_after_broker_snapshot_cannot_be_attested(tmp_path, monkeypatch):
    bind(tmp_path, monkeypatch)
    class Changed(ReadOnlyBroker):
        def list_orders(self, **kwargs):
            path = tmp_path / 'binding.json'
            value = json.loads(path.read_text())
            value['capital_usd'] = 450.
            path.write_text(json.dumps(value))
            return []
    assert driver.preflight_intended_live(tmp_path, client=Changed()) == 9
    assert 'binding_changed' in json.loads((tmp_path / 'live_binding_preflight.json').read_text())['error']
