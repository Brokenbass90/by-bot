"""Public raw source fixtures exercise frozen semantics and financial refusals."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
from decimal import Decimal

import pytest

REF='d6ed8126c041969de0bc6191e39fefe4a1272d5b'
DAY=86400000
T=int(datetime(2026,10,8,tzinfo=timezone.utc).timestamp()*1000)
NOW=T+600000
CUTOFF=T-300000


def api(name):
    try:m=importlib.import_module('bot.kity_m3_orders_off')
    except ModuleNotFoundError:pytest.fail('missing orders-OFF interface: '+name)
    assert hasattr(m,name),'missing orders-OFF interface: '+name
    return getattr(m,name)


def cap(venue,endpoint,data,params=None,rx=NOW-10):
    raw=json.dumps(data,separators=(',',':'),allow_nan=False)
    return dict(venue=venue,endpoint=endpoint,params=params or {},request_ms=rx-100,receive_ms=rx,raw=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())


def bundle(n=50):
    syms=[f'S{i:02d}USDT' for i in range(50)]
    candidates=[dict(symbol=s,baseAsset=s[:-4],quoteAsset='USDT',marginAsset='USDT',contractType='PERPETUAL',status='TRADING',onboardDate=T-100*DAY,deliveryDate=T+1000*DAY) for s in syms]
    b={'day':'2026-10-08','research_ref':REF,'census':cap('BINANCE','/fapi/v1/exchangeInfo',{'symbols':candidates},rx=CUTOFF-1),'oi':{},'klines':{}}
    for i,s in enumerate(syms):
        b['oi'][s]=cap('BINANCE','/futures/data/openInterestHist',[{'timestamp':CUTOFF,'sumOpenInterestValue':str(1000-i)}],{'symbol':s,'period':'5m','startTime':CUTOFF-900000,'endTime':CUTOFF,'limit':10})
        # Known new listings are legitimately excluded after top50 selection.
        count=60 if i<n else 30
        if i>=n:candidates[i]['onboardDate']=T-30*DAY
        bars=[]
        for j in range(count):
            ts=T-(count-j)*DAY
            bars.append([ts,'100','110','90','100','1',ts+DAY-1,'100','1','1',str(10+i),'0'])
        b['klines'][s]=cap('BINANCE','/fapi/v1/klines',bars,{'symbol':s,'interval':'1d','endTime':T-1,'limit':75})
    b['census']=cap('BINANCE','/fapi/v1/exchangeInfo',{'symbols':candidates},rx=CUTOFF-1)
    return b


def rewrap(c,data):return cap(c['venue'],c['endpoint'],data,c['params'],c['receive_ms'])


def sig(n=50):return api('reconstruct_signal')(bundle(n),NOW)


def execution(venue='BINANCE',now=NOW):
    s= sig()['frozen_signal'];symbols=[x['symbol'] for x in s['long']+s['short']]
    e={'venue':venue,'clock_uncertainty_ms':0,'per_leg_notional_usdt':'100','max_gross_notional_usdt':'1000','books':{}}
    instruments=[]
    for symbol in symbols:
        if venue=='BINANCE':
            instruments.append({'symbol':symbol,'baseAsset':symbol[:-4],'quoteAsset':'USDT','marginAsset':'USDT','contractType':'PERPETUAL','status':'TRADING','filters':[{'filterType':'LOT_SIZE','minQty':'0.01','maxQty':'100','stepSize':'0.01'},{'filterType':'MARKET_LOT_SIZE','minQty':'0.01','maxQty':'100','stepSize':'0.01'},{'filterType':'MIN_NOTIONAL','notional':'5'},{'filterType':'PRICE_FILTER','tickSize':'0.01'}]})
            e['books'][symbol]=cap(venue,'/fapi/v1/depth',{'T':now-500,'lastUpdateId':100,'bids':[['99','100'],['98','100']],'asks':[['101','100'],['102','100']]},{'symbol':symbol,'limit':1000},rx=now-100)
        else:
            instruments.append({'symbol':symbol,'baseCoin':symbol[:-4],'quoteCoin':'USDT','settleCoin':'USDT','contractType':'LinearPerpetual','status':'Trading','isPreListing':False,'lotSizeFilter':{'qtyStep':'0.01','minOrderQty':'0.01','maxMktOrderQty':'100','minNotionalValue':'5'},'priceFilter':{'tickSize':'0.01'},'fundingInterval':480})
            e['books'][symbol]=cap(venue,'/v5/market/orderbook',{'retCode':0,'time':now-100,'result':{'s':symbol,'cts':now-500,'ts':now-100,'u':100,'b':[['99','100'],['98','100']],'a':[['101','100'],['102','100']]}},{'category':'linear','symbol':symbol,'limit':200},rx=now-100)
    ep='/fapi/v1/exchangeInfo' if venue=='BINANCE' else '/v5/market/instruments-info'
    data={'symbols':instruments} if venue=='BINANCE' else {'retCode':0,'time':now-100,'result':{'category':'linear','list':instruments,'nextPageCursor':''}}
    e['instruments']=cap(venue,ep,data,{} if venue=='BINANCE' else {'category':'linear','limit':1000},rx=now-100)
    return e


def test_valid_fifty_reconstructs_exact_frozen_basket_without_money():
    r=sig();assert r['signal_valid'] is True
    assert [x['symbol'] for x in r['frozen_signal']['long']]==[f'S{i:02d}USDT' for i in range(45,50)]
    assert [x['symbol'] for x in r['frozen_signal']['short']]==[f'S{i:02d}USDT' for i in range(5)]
    assert r['orders_allowed'] is False and r['money_ready'] is False
    assert r['status']=='BLOCKED_DATA' and 'EXECUTION_EVIDENCE_REQUIRED' in r['reasons']


@pytest.mark.parametrize('n,k',[(30,3),(40,4)])
def test_smaller_frozen_deciles_are_emitted_and_block_ten_leg_contract(n,k):
    r=sig(n);assert r['signal_valid'] is True
    assert len(r['frozen_signal']['long'])==len(r['frozen_signal']['short'])==k
    assert r['status']=='BLOCKED_EXECUTION' and 'BLOCKED_BASKET_CONTRACT' in r['reasons']


@pytest.mark.parametrize('change,reason',[
    ('missing_oi','OI_CENSUS_INCOMPLETE'),('fallback_oi','EXACT_2355_OI_MISSING'),
    ('duplicate_oi','AMBIGUOUS_2355_OI'),('duplicate_bar','DUPLICATE_KLINE'),
    ('mature_history','INCOMPLETE_MATURE_HISTORY'),('current_bar','NONCAUSAL_KLINE'),
    ('bad_hash','SOURCE_HASH_MISMATCH'),('bad_ref','RESEARCH_REF_MISMATCH'),
    ('wrong_day','INVALID_WEEK_GRID'),('old_census','PIT_CENSUS_NOT_CONFIRMED'),
    ('bad_ratio','INVALID_TAKER_VOLUME'),('census_duplicate','AMBIGUOUS_CENSUS')])
def test_invalid_sources_fail_closed(change,reason):
    b=bundle();s='S00USDT'
    if change=='missing_oi':del b['oi'][s]
    elif change=='fallback_oi':
        x=json.loads(b['oi'][s]['raw']);x[0]['timestamp']-=300000;b['oi'][s]=rewrap(b['oi'][s],x)
    elif change=='duplicate_oi':
        x=json.loads(b['oi'][s]['raw']);b['oi'][s]=rewrap(b['oi'][s],x+x)
    elif change in ('duplicate_bar','mature_history','current_bar','bad_ratio'):
        x=json.loads(b['klines'][s]['raw'])
        if change=='duplicate_bar':x[-2]=x[-1]
        elif change=='mature_history':x=x[-30:]
        elif change=='current_bar':x[-1][0]=T;x[-1][6]=T+DAY-1
        else:x[-1][10]='101'
        b['klines'][s]=rewrap(b['klines'][s],x)
    elif change=='bad_hash':b['oi'][s]['raw']='[]'
    elif change=='bad_ref':b['research_ref']='0'*40
    elif change=='wrong_day':b['day']='2026-10-09'
    elif change=='old_census':b['census']['receive_ms']=CUTOFF-3000;b['census']['request_ms']=CUTOFF-4000
    elif change=='census_duplicate':
        x=json.loads(b['census']['raw']);x['symbols'].append(x['symbols'][0]);b['census']=rewrap(b['census'],x)
    r=api('reconstruct_signal')(b,NOW);assert r['status']=='BLOCKED_DATA' and reason in r['reasons']
    assert not r['orders_allowed']


def test_unseen_not_due_and_late_reconstruction_are_not_prospective():
    assert 'SIGNAL_NOT_DUE' in api('reconstruct_signal')(bundle(),T-1)['reasons']
    r=api('reconstruct_signal')(bundle(),T+DAY+1);assert r['prospective_eligible'] is False
    assert 'MISSED_PROSPECTIVE_ENTRY_BOUNDARY' in r['reasons']


def test_equal_feature_and_oi_ties_follow_frozen_tuple_order():
    b=bundle()
    for s in b['oi']:
        x=json.loads(b['oi'][s]['raw']);x[0]['sumOpenInterestValue']='1000';b['oi'][s]=rewrap(b['oi'][s],x)
        bars=json.loads(b['klines'][s]['raw']);bars[-1][10]='50';b['klines'][s]=rewrap(b['klines'][s],bars)
    r=api('reconstruct_signal')(b,NOW)
    assert r['frozen_signal']['top50'][0]=='S49USDT'
    assert [x['symbol'] for x in r['frozen_signal']['long']]==[f'S{i:02d}USDT' for i in range(45,50)]


@pytest.mark.parametrize('venue',['BINANCE','BYBIT'])
def test_full_public_execution_has_math_but_never_account_or_money_readiness(venue):
    r=api('assess_execution')(sig(),execution(venue),NOW)
    assert r['public_checks_pass'] is True and len(r['legs'])==10
    assert r['status']=='BLOCKED_DATA' and 'ACTUAL_ACCOUNT_EVIDENCE_REQUIRED' in r['reasons']
    assert r['orders_allowed'] is False and r['money_ready'] is False
    assert Decimal(r['gross_notional_usdt'])<=1000
    assert all(Decimal(x['quantity'])>0 for x in r['legs'])


@pytest.mark.parametrize('change,reason',[
    ('small_size','VENUE_MINIMUM_REJECT'),('missing_filter','INSTRUMENT_FILTER_UNKNOWN'),
    ('shallow','DEPTH_INSUFFICIENT'),('old_book','COMMON_BASKET_FRESHNESS'),
    ('no_clock','CLOCK_UNCERTAINTY_UNKNOWN'),('gross_cap','GROSS_CAP_REJECT'),
    ('bad_base','UNDERLYING_MISMATCH'),('crossed','INVALID_BOOK'),('signal_tamper','SIGNAL_HASH_MISMATCH'),
    ('missing_book','BOOK_CENSUS_INCOMPLETE'),('bool_qty','INVALID_SCENARIO_NUMBER')])
def test_execution_refusals(change,reason):
    e=execution();s=sig();sym=s['frozen_signal']['long'][0]['symbol']
    if change=='small_size':e['per_leg_notional_usdt']='1'
    elif change=='no_clock':del e['clock_uncertainty_ms']
    elif change=='gross_cap':e['max_gross_notional_usdt']='100'
    elif change=='bool_qty':e['per_leg_notional_usdt']=True
    elif change=='signal_tamper':s['frozen_signal']['long'][0]['symbol']='OTHERUSDT'
    elif change=='missing_book':del e['books'][sym]
    elif change in ('missing_filter','bad_base'):
        x=json.loads(e['instruments']['raw'])
        if change=='missing_filter':x['symbols'][0]['filters']=[]
        else:x['symbols'][0]['baseAsset']='OTHER'
        e['instruments']=rewrap(e['instruments'],x)
    else:
        c=e['books'][sym];x=json.loads(c['raw'])
        if change=='shallow':x['bids']=[['99','0.001']];x['asks']=[['101','0.001']]
        elif change=='old_book':x['T']=NOW-2100
        elif change=='crossed':x['bids'][0][0]='102'
        e['books'][sym]=rewrap(c,x)
    r=api('assess_execution')(s,e,NOW);assert reason in r['reasons'];assert not r['orders_allowed']


def test_bybit_missing_cts_does_not_use_fresh_publication_ts():
    e=execution('BYBIT');sym=next(iter(e['books']));c=e['books'][sym];x=json.loads(c['raw']);del x['result']['cts'];e['books'][sym]=rewrap(c,x)
    assert 'SOURCE_FRESHNESS_UNKNOWN' in api('assess_execution')(sig(),e,NOW)['reasons']


def test_clock_uncertainty_is_charged_to_common_two_second_budget():
    e=execution();e['clock_uncertainty_ms']=1600
    assert 'COMMON_BASKET_FRESHNESS' in api('assess_execution')(sig(),e,NOW)['reasons']


def test_costs_weight_exact_leg_notional_not_ten_times_bps():
    e=execution();e['scenario_costs']={'entry_fee_rate':'0.0006','exit_fee_rate':'0.0006','funding_rate_envelope':'0.0001','settlements':21,'basis':'DECLARED_SYNTHETIC','source_sha256':'a'*64}
    r=api('assess_execution')(sig(),e,NOW)
    assert Decimal(r['scenario_costs']['fee_bps'])==Decimal('12')
    assert Decimal(r['scenario_costs']['funding_bps'])==Decimal('21')
    assert r['scenario_costs']['actual_account_truth'] is False
    assert Decimal(r['scenario_costs']['roundtrip_quote_cost_usdt'])>0


def test_depth_vwap_consumes_multiple_levels_for_exact_quantity():
    e=execution();e['max_gross_notional_usdt']='1001';sym=sig()['frozen_signal']['long'][0]['symbol'];c=e['books'][sym];x=json.loads(c['raw']);x['asks']=[['101','0.1'],['102','100']];e['books'][sym]=rewrap(c,x)
    r=api('assess_execution')(sig(),e,NOW);leg=next(x for x in r['legs'] if x['symbol']==sym)
    assert Decimal(leg['entry_vwap'])>101 and leg['depth_covered'] is True


def test_paper_replay_duplicate_fill_does_not_credit_twice_and_partial_stays_open():
    s,p,identity=paper_context();symbol=s['frozen_signal']['long'][0]['symbol'];event={**identity,'event_id':'x','kind':'ENTRY_FILL','symbol':symbol,'execution_id':'f','qty':'0.5','price':'100','fee_usdt':'0.01'}
    r=api('reconcile_paper_events')(s,[event,event],p);assert r['positions'][symbol]=='0.5'
    assert r['terminal_complete'] is False and r['synthetic_only'] is True
    assert r['fees_usdt']=='0.01'
    bad=deepcopy(event);bad['qty']='0.6'
    assert 'CONFLICTING_EVENT' in api('reconcile_paper_events')(s,[event,bad],p)['reasons']


def test_paper_terminal_requires_full_basket_closes_and_explicit_finality():
    s,p,events=paper_events()
    r=api('reconcile_paper_events')(s,events,p);assert r['terminal_complete'] is True
    assert r['orders_allowed'] is False and r['synthetic_only'] is True
    assert api('reconcile_paper_events')(s,events[:-1],p)['terminal_complete'] is False


def test_binance_funding_interval_is_explicit_or_unknown_never_guessed():
    e=execution();r=api('assess_execution')(sig(),e,NOW)
    assert 'FUNDING_INTERVAL_UNKNOWN' in r['reasons']
    symbols=list(e['books'])
    e['funding_info']=cap('BINANCE','/fapi/v1/fundingInfo',[{'symbol':s,'fundingIntervalHours':4,'adjustedFundingRateCap':'0.01','adjustedFundingRateFloor':'-0.01'} for s in symbols],rx=NOW-100)
    r=api('assess_execution')(sig(),e,NOW)
    assert all(x['funding_interval_minutes']==240 for x in r['legs'])
    assert 'FUNDING_INTERVAL_UNKNOWN' not in r['reasons']


def test_synthetic_settlement_count_cannot_understate_seven_day_current_intervals():
    e=execution('BYBIT');e['scenario_costs']={'entry_fee_rate':'0.0006','exit_fee_rate':'0.0006','funding_rate_envelope':'0.0001','settlements':1,'basis':'DECLARED_SYNTHETIC','source_sha256':'a'*64}
    assert 'FUNDING_SETTLEMENT_COUNT_INFEASIBLE' in api('assess_execution')(sig(),e,NOW)['reasons']


def test_rehashed_modified_basket_cannot_change_frozen_selector():
    s=sig();s['frozen_signal']['long'][0]['symbol']='S00USDT';s['signal_hash']=api('digest')(s['frozen_signal'])
    assert 'SOURCE_DECISION_MISMATCH' in api('assess_execution')(s,execution(),NOW)['reasons']


def test_inert_intent_identity_is_stable_across_observation_time():
    a=api('assess_execution')(sig(),execution(),NOW)
    b=api('assess_execution')(sig(),execution(),NOW+1)
    assert len(a['intent_id'])==64 and a['intent_id']==b['intent_id']
    assert a['intent_id']!=api('assess_execution')(sig(),execution('BYBIT'),NOW)['intent_id']


def test_execution_cannot_use_a_signal_not_yet_available():
    e=execution();s=sig()
    assert 'SIGNAL_NOT_YET_AVAILABLE' in api('assess_execution')(s,e,NOW-1)['reasons']

@pytest.mark.parametrize('change', ['day','cutoff','top50','pins','source_clock'])
def test_review_rehashed_source_identity_and_date_cannot_bypass_reconstruction(change):
    s=sig();f=s['frozen_signal']
    if change=='day':f['day']='2026-10-09'
    elif change=='cutoff':f['oi_cutoff_ms']=1
    elif change=='top50':f['top50']=[]
    elif change=='pins':f['source_pins']={}
    else:s['source_available_ms']=1
    s['signal_hash']=api('digest')(f)
    r=api('assess_execution')(s,execution(),NOW)
    assert r['public_checks_pass'] is False

@pytest.mark.parametrize('source',['oi','klines'])
def test_review_sources_cannot_capture_unavailable_closed_data(source):
    b=bundle();s=next(iter(b[source]));c=b[source][s]
    c['receive_ms']=CUTOFF-1 if source=='oi' else T-9000
    c['request_ms']=c['receive_ms']-100
    r=api('reconstruct_signal')(b,NOW)
    assert r['signal_valid'] is False
    assert 'NONCAUSAL_SOURCE_CAPTURE' in r['reasons']

@pytest.mark.parametrize('nested',['instrument','funding','frozen_value'])
def test_review_malformed_nested_evidence_returns_blocked_receipt(nested):
    e=execution();s=sig()
    if nested=='instrument':e['instruments']=rewrap(e['instruments'],{'symbols':[None]})
    elif nested=='funding':e['funding_info']=cap('BINANCE','/fapi/v1/fundingInfo',[None])
    else:
        key=next(iter(s['frozen_signal']['feature_source_values']));s['frozen_signal']['feature_source_values'][key]=None;s['signal_hash']=api('digest')(s['frozen_signal'])
    r=api('assess_execution')(s,e,NOW)
    assert r['status']=='BLOCKED_DATA' and not r['public_checks_pass']

def test_review_nonfinite_volume_anywhere_in_required_history_blocks():
    b=bundle();s=next(iter(b['klines']));c=b['klines'][s];rows=json.loads(c['raw']);rows[0][7]='NaN';b['klines'][s]=rewrap(c,rows)
    assert not api('reconstruct_signal')(b,NOW)['signal_valid']

def paper_context():
    s=sig();p=api('assess_execution')(s,execution(),NOW)
    identity={'day':s['frozen_signal']['day'],'signal_hash':s['signal_hash'],'venue':p['venue'],'intent_id':p['intent_id'],'prepared_digest':api('digest')(p)}
    return s,p,identity

def paper_events():
    s,p,identity=paper_context();events=[]
    for i,l in enumerate(p['legs']):
        for kind in ('ENTRY_FILL','EXIT_FILL'):
            events.append({**identity,'event_id':f'{kind}{i}','kind':kind,'symbol':l['symbol'],'execution_id':f'{kind}{i}','qty':l['quantity'],'price':'100' if kind=='ENTRY_FILL' else '102','fee_usdt':'0.01'})
        events.append({**identity,'event_id':f'final{i}','kind':'FINALITY','symbol':l['symbol'],'costs_complete':True,'funding_complete':True})
    return s,p,events

@pytest.mark.parametrize('field',['day','signal_hash','venue','intent_id'])
def test_review_replay_rejects_another_lifecycle(field):
    s,p,events=paper_events();events[0][field]='wrong'
    r=api('reconcile_paper_events')(s,events,p)
    assert not r['terminal_complete'] and 'PAPER_IDENTITY_MISMATCH' in r['reasons']

def test_review_replay_preserves_known_prefix_exposure_and_costs_on_error():
    s,p,events=paper_events();event=events[0];bad={**events[1],'kind':'UNKNOWN'}
    r=api('reconcile_paper_events')(s,[event,bad],p)
    assert r['positions'][event['symbol']]==event['qty'] and r['fees_usdt']=='0.01'
    assert r['unresolved_event_id']==bad['event_id'] and not r['terminal_complete']

def test_review_partial_basket_can_be_flat_but_not_complete_intended_basket():
    s,p,events=paper_events()
    for e in events:
        if e['kind'].endswith('FILL'):e['qty']=str(Decimal(e['qty'])/2)
    r=api('reconcile_paper_events')(s,events,p)
    assert r['exposure_reconciled'] is True and r['terminal_complete'] is False
    assert 'PAPER_INTENDED_BASKET_INCOMPLETE' in r['reasons']

def test_review_signed_short_funding_and_net_cash_accounting():
    s,p,identity=paper_context();l=next(x for x in p['legs'] if x['side']=='SHORT');q=Decimal(l['quantity'])
    entry={**identity,'event_id':'entry','kind':'ENTRY_FILL','symbol':l['symbol'],'execution_id':'entry','qty':str(q),'price':'100','fee_usdt':'-0.01'}
    funding={**identity,'event_id':'funding','settlement_id':'settlement-1','kind':'FUNDING','symbol':l['symbol'],'quantity':str(q),'mark_price':'101','rate':'0.001','cash_usdt':str(q*Decimal('101')*Decimal('0.001'))}
    r=api('reconcile_paper_events')(s,[entry,funding],p)
    assert r['signed_positions'][l['symbol']]==str(-q)
    assert Decimal(r['fees_usdt'])==Decimal('-0.01')
    assert Decimal(r['funding_cash_usdt'])>0
    funding['cash_usdt']='-1'
    assert 'PAPER_FUNDING_MISMATCH' in api('reconcile_paper_events')(s,[entry,funding],p)['reasons']

def test_review_full_intended_terminal_has_signed_net_pnl():
    s,p,events=paper_events();r=api('reconcile_paper_events')(s,events,p)
    expected=sum(Decimal(l['quantity'])*Decimal(2)*(1 if l['side']=='LONG' else -1) for l in p['legs'])-Decimal('0.20')
    assert r['terminal_complete'] and Decimal(r['net_realized_usdt'])==expected
    assert r['protection']=='NOT_PROVEN' and r['synthetic_only']

def test_review_prepared_quantities_cannot_be_rehashed_or_replaced():
    s,p,events=paper_events();p['legs'][0]['quantity']='0.01'
    r=api('reconcile_paper_events')(s,[],p)
    assert 'PAPER_PREPARATION_MISMATCH' in r['reasons']

def test_review_funding_settlement_replay_cannot_double_credit():
    s,p,identity=paper_context();l=p['legs'][0];q=Decimal(l['quantity'])
    entry={**identity,'event_id':'entry','kind':'ENTRY_FILL','symbol':l['symbol'],'execution_id':'entry','qty':str(q),'price':'100','fee_usdt':'0'}
    cash=-q*Decimal('100')*Decimal('0.001')
    funding={**identity,'event_id':'fund','kind':'FUNDING','symbol':l['symbol'],'settlement_id':'F1','quantity':str(q),'mark_price':'100','rate':'0.001','cash_usdt':str(cash)}
    duplicate={**funding,'event_id':'different-delivery'}
    r=api('reconcile_paper_events')(s,[entry,funding,duplicate],p)
    assert Decimal(r['funding_cash_usdt'])==cash
    conflict={**duplicate,'rate':'0.002','cash_usdt':str(cash*2)}
    r=api('reconcile_paper_events')(s,[entry,funding,conflict],p)
    assert 'CONFLICTING_FUNDING_SETTLEMENT' in r['reasons'] and Decimal(r['funding_cash_usdt'])==cash

def test_review_malformed_preparation_keeps_explicit_blocked_outcome():
    s,p,_=paper_events();p['legs'][0]['quantity']=float('nan')
    r=api('reconcile_paper_events')(s,[],p)
    assert r['status']=='BLOCKED_DATA' and not r['terminal_complete']
