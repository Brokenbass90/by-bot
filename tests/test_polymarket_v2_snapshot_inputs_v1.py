import copy,hashlib,importlib,json
import pytest
from research_lab import polymarket_v2_orders_off_v1 as measurement

CID='0x'+'a'*64

def module():
 try:return importlib.import_module('research_lab.polymarket_v2_snapshot_inputs_v1')
 except ImportError:pytest.fail('Fresh snapshot normalizer is missing')

def capture(url,value,at=1000):
 raw=json.dumps(value,separators=(',',':'))
 return dict(url=url,method='GET',http_status=200,request_ms=at-2,received_ms=at,raw_text=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest())

def gamma(**updates):
 v=dict(id='123',conditionId=CID,clobTokenIds='["11","22"]',active=True,closed=False,enableOrderBook=True,acceptingOrders=True,feesEnabled=True,feeSchedule=dict(rate=.05,exponent=1,takerOnly=True,rebateRate=.15),takerBaseFee=1000,orderPriceMinTickSize=.01,orderMinSize=5);v.update(updates)
 return capture('https://gamma-api.polymarket.com/markets/123',v)

def book(token='22',**updates):
 v=dict(market=CID,asset_id=token,timestamp='1000',hash='venue-book-hash',asks=[dict(price='.98',size='200'),dict(price='.97',size='50')],bids=[dict(price='.96',size='100')],tick_size='.01',min_order_size='5');v.update(updates)
 return capture('https://clob.polymarket.com/book?token_id='+token,v,1001)

def test_actual_gamma_schedule_is_used_instead_of_legacy_base_fee():
 m=module().market_input(gamma(),'123',decision_ms=1010)
 assert m['fee_rate']=='0.05' and m['fee_schedule']['exponent']==1
 assert m['fee_source_sha256']==gamma()['raw_sha256'] and m['fee_issues']==[]
 assert m['condition_id']==CID and m['tokens']==['11','22']

@pytest.mark.parametrize('schedule',[None,dict(rate=.05,exponent=2,takerOnly=True),dict(rate='NaN',exponent=1,takerOnly=True),dict(rate=-.1,exponent=1,takerOnly=True),dict(rate=.05,exponent=True,takerOnly=True),dict(rate=.05,exponent=1,takerOnly=False)])
def test_unknown_schedule_never_becomes_zero_or_a_category_default(schedule):
 m=module().market_input(gamma(feeSchedule=schedule),'123',decision_ms=1010)
 assert 'fee_rate' not in m and m['fee_issues']

def test_explicit_disabled_fees_is_distinct_from_missing():
 m=module().market_input(gamma(feesEnabled=False,feeSchedule=None),'123',decision_ms=1010);assert m['fee_rate']=='0'
 c=gamma();v=json.loads(c['raw_text']);del v['feesEnabled'];m=module().market_input(capture(c['url'],v),'123',decision_ms=1010);assert 'fee_rate' not in m

def test_full_rest_snapshot_reaches_existing_measurement_with_its_scope():
 mod=module();m=mod.market_input(gamma(),'123',decision_ms=1010);b=mod.book_input(book(),m,'22',decision_ms=1010)
 assert b['continuity']=='VERIFIED_FULL_REST_SNAPSHOT'
 s=dict(market_id='123',token_id='22',policy_sha256='b'*64,received_ms=999,model_price='.97')
 r=measurement.measure(s,b,m,decision_ms=1010)
 assert r['status']=='MEASURED_ORDERS_OFF' and r['book_continuity']=='VERIFIED_FULL_REST_SNAPSHOT'
 assert r['stream_continuity_proven'] is False and r['real_fill'] is False
 assert r['captured_fee_rate']=='0.05' and r['book_age_ms']==9

@pytest.mark.parametrize('fault',['hash','future','stale','http','method','url','duplicate_json','protocol'])
def test_bad_metadata_never_qualifies(fault):
 c=gamma()
 if fault=='hash':c['raw_sha256']='0'*64
 if fault=='future':c['received_ms']=1011
 if fault=='stale':c['request_ms']=0;c['received_ms']=1
 if fault=='http':c['http_status']=500
 if fault=='method':c['method']='POST'
 if fault=='url':c['url']='https://example.com/markets/123'
 if fault=='duplicate_json':c=capture(c['url'],{});c['raw_text']='{"id":"123","id":"123"}';c['raw_sha256']=hashlib.sha256(c['raw_text'].encode()).hexdigest()
 if fault=='protocol':c=gamma(version='v2',positionIds=['33','44'])
 with pytest.raises(ValueError):module().market_input(c,'123',decision_ms=1010,max_age_ms=100)

@pytest.mark.parametrize('fault',['condition','token','route','bad_levels','timestamp','missing_hash'])
def test_wrong_or_malformed_book_is_not_reused_for_other_outcome(fault):
 m=module().market_input(gamma(),'123',decision_ms=1010);c=book()
 if fault=='condition':c=book(market='0x'+'c'*64)
 if fault=='token':c=book(asset_id='11')
 if fault=='route':c['url']='https://clob.polymarket.com/book?token_id=11'
 if fault=='bad_levels':c=book(asks=[dict(price='.97',size='-1')])
 if fault=='timestamp':c=book(timestamp='999999999')
 if fault=='missing_hash':c=book(hash=None)
 with pytest.raises(ValueError):module().book_input(c,m,'22',decision_ms=1010)

def test_missing_acceptance_preserves_unknown_and_real_displayed_depth():
 c=gamma();v=json.loads(c['raw_text']);del v['acceptingOrders'];m=module().market_input(capture(c['url'],v),'123',decision_ms=1010);b=module().book_input(book(),m,'22',decision_ms=1010)
 r=measurement.measure(dict(market_id='123',token_id='22',policy_sha256='b'*64,received_ms=999,model_price='.97'),b,m,decision_ms=1010)
 assert r['status']=='UNKNOWN' and 'ACCEPTING_STATUS_UNKNOWN' in r['issues'] and r['best_ask']=='0.97'


@pytest.mark.parametrize('c',[gamma(clobTokenIds=[['11'],'22']),gamma(version=True)])
def test_non_string_token_container_and_boolean_protocol_are_rejected(c):
 with pytest.raises(ValueError):module().market_input(c,'123',decision_ms=1010)
