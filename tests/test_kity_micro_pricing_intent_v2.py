"""Bounded permission may select prices once; it cannot retry a spent plan."""
import copy
from decimal import Decimal as D
import json
import pytest

from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan, validate_plan
from test_kity_micro_runtime_v1 import dossier
from test_kity_micro_integration_v3 import V3
from research_lab.kity_micro_pricing_intent_v2 import (
    make_intent, validate_intent, materialize, consume_once, load_source,
)

PIN='d'*64
PREVIOUS='ffeb4bc4924fe64586469377372dca88caaa9545544dc2920f3d1bc438ee6570'


def source(at=1000, price='1'):
    raw=dossier();profile=raw['profiles'][0]
    profile.update(common_reference_target='20',observed_depth_gross='200')
    for l in profile['legs']:
        l.update(quantity='20',entry_reference_notional='20',entry_book_notional='20')
        l['draft_entry']['qty']='20'
    p=prepare_micro_plan(raw,V3)
    for l in p['legs']:
        l['request']['price']=price
        l['request'].update(stopLoss='.9' if l['side']=='Buy' else '1.1',
            slTriggerBy='LastPrice',slOrderType='Market',tpslMode='Full')
    p['planned_limit_gross_usdt']=str(D(price)*200)
    p['reference_gross_usdt']=str(D(price)*200)
    p['reference_source_ms']=at
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'})
    instruments=[];caps={}
    for l in p['legs']:
        s=l['symbol']
        instruments.append(dict(symbol=s,side=l['side'],tick_size='.0001',quantity_step='.001',
            minimum_quantity='.001',minimum_notional='.1',configured_leverage='3',taker_fee='.00055',
            next_funding_ms=at+86400000,funding_interval_minutes=480,funding_upper='.01',funding_lower='-.01'))
        caps['book:'+s]=dict(request_ms=at,receive_ms=at,
            body=dict(time=at,result=dict(s=s,b=[[price,'1000']],a=[[price,'1000']],cts=at)))
        caps['instrument:'+s]=dict(body=dict(result=dict(list=[dict(symbol=s,lotSizeFilter=dict(
            minOrderQty='.001',maxOrderQty='1000',qtyStep='.001',minNotionalValue='.1'))])))
    d=dict(plan=p,instruments=instruments,observed_end_ms=at,physical_config_sha256=PIN,
        common_clock_at_capture=dict(status='OBSERVED_COMMON_2S_PASS'),
        all_linear_usdt_positions=0,all_linear_usdt_open_orders=0,account_trade_permissions_observed=True,
        wallet_total_available_usd='1000')
    return d,caps


def intent():
    d,_=source()
    return make_intent(d,at_ms=1000,collar_bps='50',ttl_ms=600000,
        predecessor_plan_id=PREVIOUS)


def test_late_human_reply_selects_fresh_prices_once_inside_fixed_envelope():
    i=intent();d,c=source(481000,'1.002')
    result=materialize(i,d,c,now_ms=481001)
    p=result['plan'];validate_plan(p)
    assert p['plan_id']!=i['reference_plan']['plan_id']
    assert p['bounds']==i['reference_plan']['bounds']
    assert all(l['quantity']=='20' for l in p['legs'])
    assert all(l['request']['price']==('1.005' if l['side']=='Buy' else '0.995') for l in p['legs'])
    assert all(l['request']['orderLinkId'].startswith('KXM2-') for l in p['legs'])
    assert result['broker_writes']==0 and not result['orders_allowed']
    assert result['rounding_basis']=='FROZEN_INTENT_REFERENCE_ONLY'


@pytest.mark.parametrize('price',['1.0051','.9949'])
def test_current_book_outside_collar_is_terminal_no_send(price):
    d,c=source(2000,price)
    with pytest.raises(ValueError,match='PRICE_ENVELOPE'):
        materialize(intent(),d,c,now_ms=2001)


@pytest.mark.parametrize('at',[999,601000,601001])
def test_clock_before_creation_or_at_expiry_never_authorizes_entry(at):
    d,c=source(max(at,1))
    with pytest.raises(ValueError,match='INTENT_CLOCK'):
        materialize(intent(),d,c,now_ms=at)


def test_expiry_belongs_to_entry_permission_not_thirty_minute_holding_deadline():
    d,c=source(600999)
    p=materialize(intent(),d,c,now_ms=600999)['plan']
    assert p['bounds']['duration_ms']==1800000
    assert p['pricing_intent']['expires_ms']==601000
    assert p['reference_source_ms']==600999


@pytest.mark.parametrize('field,value',[
    ('collar_bps','51'),('collar_bps',True),('ttl_ms',600001),('ttl_ms',True),
    ('physical_config_sha256','x'),('predecessor_plan_id','x'),
])
def test_intent_rehash_cannot_expand_supported_proposal_or_lose_custody(field,value):
    i=intent();i[field]=value;i['intent_id']=digest({k:v for k,v in i.items() if k!='intent_id'})
    with pytest.raises(ValueError):validate_intent(i)


def test_rehashed_custom_price_band_is_rejected_against_frozen_reference():
    i=intent();i['price_bands'][0]['max_price']='2'
    i['intent_id']=digest({k:v for k,v in i.items() if k!='intent_id'})
    with pytest.raises(ValueError,match='BAND'):validate_intent(i)


@pytest.mark.parametrize('mutation',[
    lambda d,c:d.update(physical_config_sha256='e'*64),
    lambda d,c:d.update(account_trade_permissions_observed=False),
    lambda d,c:d.update(all_linear_usdt_open_orders=[{'foreign':'order'}]),
    lambda d,c:d.update(all_linear_usdt_positions=False),
    lambda d,c:d.update(all_linear_usdt_positions='0'),
    lambda d,c:d['instruments'][0].update(tick_size='.001'),
    lambda d,c:c['book:BTWUSDT']['body']['result'].update(s='OTHER'),
    lambda d,c:d.update(common_clock_at_capture={'status':'UNKNOWN'}),
])
def test_materialization_preserves_account_source_and_exact_instrument_contract(mutation):
    d,c=source(2000);mutation(d,c)
    with pytest.raises(ValueError):materialize(intent(),d,c,now_ms=2001)


def test_claim_is_durable_before_capture_and_failed_capture_cannot_be_retried(tmp_path):
    i=intent();calls=[]
    def unavailable():calls.append(1);raise ValueError('network unknown')
    text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id']
    with pytest.raises(ValueError,match='network unknown'):
        consume_once(tmp_path,i,text,unavailable,clock=lambda:2000)
    assert json.loads((tmp_path/'intent-claim.json').read_bytes())['intent_id']==i['intent_id']
    with pytest.raises(FileExistsError):consume_once(tmp_path,i,text,unavailable,clock=lambda:2001)
    assert calls==[1] and not (tmp_path/'materialized.json').exists()
    assert (tmp_path/'no-send.json').exists()


def test_old_exact_go_and_wrong_intent_cannot_be_converted_to_new_authority(tmp_path):
    i=intent();calls=[]
    for text in ('GO KITY_EXECUTION_MICRO_LIVE '+PREVIOUS,
                 'GO KITY_EXECUTION_MICRO_INTENT_V2 '+'a'*64):
        with pytest.raises(ValueError,match='EXACT_INTENT_GO'):
            consume_once(tmp_path,i,text,lambda:calls.append(1),clock=lambda:2000)
    assert not calls and not list(tmp_path.iterdir())


def test_success_creates_one_immutable_materialized_plan_and_retains_literal_go(tmp_path):
    i=intent();d,c=source(2000)
    text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id']
    r=consume_once(tmp_path,i,text,lambda:(d,c),clock=lambda:2001)
    assert r['plan']['pricing_intent']['intent_id']==i['intent_id']
    assert json.loads((tmp_path/'intent-claim.json').read_bytes())['owner_go_text']==text
    with pytest.raises(FileExistsError):consume_once(tmp_path,i,text,lambda:(d,c),clock=lambda:2002)


def test_reference_and_fresh_source_are_not_changed_by_compiler():
    i=intent();d,c=source(2000);before=copy.deepcopy((i,d,c))
    materialize(i,d,c,now_ms=2001)
    assert (i,d,c)==before


def test_saved_source_loader_checks_exact_bytes_before_using_account_fields(tmp_path):
    p=tmp_path/'capture.json';p.write_text('{}')
    with pytest.raises(ValueError,match='CAPTURE_PIN_CONFLICT'):
        load_source(p,'a'*64,V3,PIN)


def test_failed_expired_go_does_not_even_capture_or_claim(tmp_path):
    i=intent();calls=[]
    with pytest.raises(ValueError,match='INTENT_CLOCK'):
        consume_once(tmp_path,i,'GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'],
            lambda:calls.append(1),clock=lambda:601000)
    assert not calls and not list(tmp_path.iterdir())


def test_book_cts_missing_or_stale_is_unknown_even_when_dossier_has_pass_flag():
    for stamp in (None,True,1):
        d,c=source(5000);c['book:BTWUSDT']['body']['result']['cts']=stamp
        with pytest.raises(ValueError,match='COMMON_2S'):
            materialize(intent(),d,c,now_ms=5001)


def test_reference_envelope_cannot_fit_above_preapproved_215_cap():
    d,_=source(price='1.074')
    with pytest.raises(ValueError,match='215'):
        make_intent(d,at_ms=1000,collar_bps='50',ttl_ms=600000,predecessor_plan_id=PREVIOUS)
