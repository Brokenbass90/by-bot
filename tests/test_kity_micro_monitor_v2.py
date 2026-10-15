from decimal import Decimal as D
import pytest

from research_lab.kity_execution_micro_runtime_v1 import MicroJournal, prepare_micro_plan
from test_kity_micro_runtime_v1 import dossier, enter, BASKET
from test_kity_micro_policy_v2 import V2


def book(symbol, bid, *, clock=2100):
    b=D(bid)
    return dict(endpoint='/v5/market/orderbook',params=dict(category='linear',symbol=symbol),
        request_ms=clock-20,receive_ms=clock,body=dict(retCode=0,time=clock-5,
            result=dict(s=symbol,b=[[str(b),'100']],a=[[str(b+D('.01')),'100']],cts=clock-10)))


def create(tmp_path):
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(dossier(),V2))
    enter(j,BASKET[0][0])
    return j


def test_loss_observation_persists_unwind_and_survives_recovery(tmp_path):
    from test_kity_micro_runtime_v1 import send,fill,terminal,protect
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(dossier(),V2));s=BASKET[0][0]
    send(j,s);fill(j,s,price='20',fee='0');terminal(j,s);protect(j,s)
    r=j.observe_risk({s:book(s,'5')},{s:'0'},funding_reserve_usdt='0',now_ms=2100)
    assert r['action']=='UNWIND_LOSS_LIMIT'
    assert j.snapshot()['entry_blocked'] is True
    p=j.plan;j.close();j=MicroJournal(tmp_path/'j.sqlite',p)
    assert j.actions(2200)[0]['kind']=='EXIT'


def test_recovery_in_price_cannot_reenable_entries_after_loss_trigger(tmp_path):
    from test_kity_micro_runtime_v1 import send,fill,terminal,protect
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(dossier(),V2));s=BASKET[0][0]
    send(j,s);fill(j,s,price='20',fee='0');terminal(j,s);protect(j,s)
    j.observe_risk({s:book(s,'5')},{s:'0'},funding_reserve_usdt='0',now_ms=2100)
    j.observe_risk({s:book(s,'20',clock=2200)},{s:'0'},funding_reserve_usdt='0',now_ms=2200)
    assert j.snapshot()['entry_blocked'] is True


@pytest.mark.parametrize('defect',['stale','missing_cts','wrong_symbol','fee_unknown','funding_unknown'])
def test_unknown_current_liquidation_value_persists_fail_closed_unwind(tmp_path,defect):
    j=create(tmp_path);s=BASKET[0][0];cap=book(s,'1');fee='0';reserve='0'
    if defect=='stale':cap['body']['result']['cts']=1
    if defect=='missing_cts':del cap['body']['result']['cts']
    if defect=='wrong_symbol':cap['body']['result']['s']='FOREIGNUSDT'
    if defect=='fee_unknown':fee=None
    if defect=='funding_unknown':reserve=None
    r=j.observe_risk({s:cap},{s:fee},funding_reserve_usdt=reserve,now_ms=3000 if defect=='stale' else 2100)
    assert r['action']=='UNWIND_DATA_UNKNOWN' and j.snapshot()['entry_blocked'] is True
    assert j.actions(3100)[0]['kind']=='EXIT'


def test_healthy_valuation_is_not_a_trade_permission(tmp_path):
    j=create(tmp_path);s=BASKET[0][0]
    r=j.observe_risk({s:book(s,'1')},{s:'.001'},funding_reserve_usdt='0',now_ms=2100)
    assert r['action']=='MONITOR' and not r['orders_allowed']
    assert j.snapshot()['entry_blocked'] is False


@pytest.mark.parametrize('captures,fees', [(None, {}), ([], {}),
    ({'BTWUSDT': None}, {'BTWUSDT': '0'}),
    ({'BTWUSDT': {'body': []}}, {'BTWUSDT': '0'})])
def test_malformed_risk_payload_is_durably_unknown_not_an_unrecorded_exception(tmp_path,captures,fees):
    j=create(tmp_path)
    r=j.observe_risk(captures,fees,funding_reserve_usdt='0',now_ms=2100)
    assert r['action']=='UNWIND_DATA_UNKNOWN'
    p=j.plan;j.close();j=MicroJournal(tmp_path/'j.sqlite',p)
    assert j.snapshot()['entry_blocked'] is True


@pytest.mark.parametrize('invalid',['nonfinite','oversized'])
def test_unserializable_or_oversized_risk_source_records_bounded_unknown(tmp_path,invalid):
    j=create(tmp_path);s=BASKET[0][0];cap=book(s,'1')
    cap['retained_source'] = float('nan') if invalid=='nonfinite' else 'x'*131072
    r=j.observe_risk({s:cap},{s:'0'},funding_reserve_usdt='0',now_ms=2100)
    assert r['action']=='UNWIND_DATA_UNKNOWN'
    assert j.actions(2200)[0]['kind']=='EXIT'


def test_same_risk_observation_is_idempotent_and_exact_threshold_includes_costs(tmp_path):
    from test_kity_micro_runtime_v1 import send,fill,terminal,protect,event
    j=MicroJournal(tmp_path/'j.sqlite',prepare_micro_plan(dossier(),V2));s=BASKET[0][0]
    send(j,s);fill(j,s,price='20',fee='.10');terminal(j,s);protect(j,s)
    j.append(event('FUNDING_CASH',symbol=s,settlement_id='f1',settlement_ms=2050,cash_usdt='-.10'))
    caps={s:book(s,'5.30')}; fees={s:'0'}
    r=j.observe_risk(caps,fees,funding_reserve_usdt='.10',now_ms=2100)
    assert D(r['net_usdt'])==D('-15') and r['action']=='UNWIND_LOSS_LIMIT'
    n=j.db.execute('select count(*) from events').fetchone()[0]
    assert j.observe_risk(caps,fees,funding_reserve_usdt='.10',now_ms=2100)==r
    assert j.db.execute('select count(*) from events').fetchone()[0]==n
