"""KITY M3 public evidence assessor. Pure functions; no sender or credentials.

Hashes establish declared evidence consistency, not broker authentication.
Even complete public scenarios remain BLOCKED_DATA for selected-account money.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import re

RESEARCH_REF = 'd6ed8126c041969de0bc6191e39fefe4a1272d5b'
DAY_MS = 86_400_000
FRESH_MS = 2000
FIRST_UNSEEN = date(2026, 10, 8)
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_SYMBOL = re.compile(r'[A-Z0-9_]{1,40}USDT\Z')
_CAPTURE_FIELDS = {'venue','endpoint','params','request_ms','receive_ms','raw','sha256'}


class EvidenceError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), allow_nan=False).encode()).hexdigest()


def _result(status='BLOCKED_DATA', reasons=(), **fields):
    return {'schema_id':'kity_m3_orders_off_v1','status':status,'reasons':list(dict.fromkeys(reasons)),
            'orders_allowed':False,'money_ready':False,**fields}


def _fail(code):
    raise EvidenceError(code)


def _int(value, code, *, zero=False):
    if type(value) is not int or value < (0 if zero else 1):
        _fail(code)
    return value


def _num(value, code, *, positive=True):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        _fail(code)
    try:
        d=Decimal(str(value))
    except (ValueError,InvalidOperation):
        _fail(code)
    if not d.is_finite() or (d<=0 if positive else d<0):
        _fail(code)
    return d


def _text(d):
    return format(d,'f')


def _signed_num(value, code):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _fail(code)
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        _fail(code)
    if not result.is_finite():
        _fail(code)
    return result


def capture_payload(capture, venue, endpoint):
    if not isinstance(capture,dict) or set(capture)!=_CAPTURE_FIELDS:
        _fail('INVALID_CAPTURE')
    if capture['venue']!=venue or capture['endpoint']!=endpoint or not isinstance(capture['params'],dict):
        _fail('SOURCE_IDENTITY_MISMATCH')
    start=_int(capture['request_ms'],'INVALID_SOURCE_CLOCK')
    end=_int(capture['receive_ms'],'INVALID_SOURCE_CLOCK')
    if start>end or not isinstance(capture['raw'],str) or len(capture['raw'].encode())>2*1024*1024:
        _fail('INVALID_CAPTURE')
    if not isinstance(capture['sha256'],str) or not _SHA.fullmatch(capture['sha256']):
        _fail('SOURCE_HASH_MISMATCH')
    if hashlib.sha256(capture['raw'].encode()).hexdigest()!=capture['sha256']:
        _fail('SOURCE_HASH_MISMATCH')
    def constant(_):_fail('INVALID_SOURCE_NUMBER')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:_fail('DUPLICATE_JSON_KEY')
            out[k]=v
        return out
    try:
        return json.loads(capture['raw'],parse_constant=constant,object_pairs_hook=pairs)
    except (json.JSONDecodeError,UnicodeError):
        _fail('INVALID_SOURCE_JSON')


def _params(capture, required):
    if any(capture['params'].get(k)!=v or type(capture['params'].get(k)) is not type(v) for k,v in required.items()):
        _fail('SOURCE_QUERY_MISMATCH')


def reconstruct_signal(bundle, now_ms):
    out=_result(signal_valid=False,prospective_eligible=False)
    try:
        _int(now_ms,'INVALID_EVALUATION_CLOCK')
        if not isinstance(bundle,dict) or bundle.get('research_ref')!=RESEARCH_REF:
            _fail('RESEARCH_REF_MISMATCH')
        try:d=date.fromisoformat(bundle['day'])
        except (KeyError,TypeError,ValueError):_fail('INVALID_WEEK_GRID')
        if (d-date(2021,7,1)).days%7 or d<date(2021,7,1):_fail('INVALID_WEEK_GRID')
        t=int(datetime(d.year,d.month,d.day,tzinfo=timezone.utc).timestamp()*1000)
        cutoff=t-300000
        if now_ms<t+300000:_fail('SIGNAL_NOT_DUE')
        c=bundle['census'];body=capture_payload(c,'BINANCE','/fapi/v1/exchangeInfo')
        if c['receive_ms']>cutoff or cutoff-c['receive_ms']>FRESH_MS:_fail('PIT_CENSUS_NOT_CONFIRMED')
        if not isinstance(body,dict) or not isinstance(body.get('symbols'),list):_fail('INVALID_CENSUS')
        candidates={}
        for row in body['symbols']:
            if not isinstance(row,dict):_fail('INVALID_CENSUS')
            if row.get('contractType')!='PERPETUAL' or row.get('quoteAsset')!='USDT' or row.get('marginAsset')!='USDT':continue
            symbol=row.get('symbol')
            if not isinstance(symbol,str) or not _SYMBOL.fullmatch(symbol) or symbol in candidates:_fail('AMBIGUOUS_CENSUS')
            onboard=_int(row.get('onboardDate'),'LISTING_HISTORY_UNKNOWN')
            delivery=_int(row.get('deliveryDate'),'LISTING_HISTORY_UNKNOWN')
            if delivery<=onboard:_fail('LISTING_HISTORY_UNKNOWN')
            if onboard>cutoff or delivery<=cutoff:continue
            if row.get('status')!='TRADING':_fail('PIT_STATUS_AMBIGUOUS')
            if not isinstance(row.get('baseAsset'),str) or not row['baseAsset']:_fail('UNDERLYING_UNKNOWN')
            candidates[symbol]=row
        if not candidates:_fail('INVALID_CENSUS')
        oi=bundle.get('oi',{});kl=bundle.get('klines',{})
        if not isinstance(oi,dict) or set(oi)!=set(candidates):_fail('OI_CENSUS_INCOMPLETE')
        ranked=[];pins={'census':c['sha256']};received=[c['receive_ms']]
        for symbol in sorted(candidates):
            cap=oi[symbol];rows=capture_payload(cap,'BINANCE','/futures/data/openInterestHist')
            _params(cap,{'symbol':symbol,'period':'5m','endTime':cutoff})
            if not isinstance(rows,list):_fail('INVALID_OI')
            exact=[r for r in rows if isinstance(r,dict) and r.get('timestamp')==cutoff and type(r.get('timestamp')) is int]
            if not exact:_fail('EXACT_2355_OI_MISSING')
            if len(exact)!=1:_fail('AMBIGUOUS_2355_OI')
            if cap['receive_ms']<cutoff:_fail('NONCAUSAL_SOURCE_CAPTURE')
            if 'symbol' in exact[0] and exact[0]['symbol']!=symbol:_fail('SOURCE_IDENTITY_MISMATCH')
            value=_num(exact[0].get('sumOpenInterestValue'),'INVALID_OI',positive=False)
            f=float(value)
            if not math.isfinite(f) or (value>0 and f==0):_fail('NUMERIC_PRECISION_AMBIGUOUS')
            if value>0:ranked.append((f,symbol))
            pins['oi:'+symbol]=cap['sha256'];received.append(cap['receive_ms'])
        top=[s for _,s in sorted(ranked,reverse=True)[:50]]
        if not isinstance(kl,dict) or not set(top).issubset(kl):_fail('KLINE_CENSUS_INCOMPLETE')
        feature=[];raw_values={};excluded={}
        for symbol in top:
            cap=kl[symbol];bars=capture_payload(cap,'BINANCE','/fapi/v1/klines')
            _params(cap,{'symbol':symbol,'interval':'1d','endTime':t-1})
            if not isinstance(bars,list):_fail('INVALID_KLINE')
            times=[]
            for row in bars:
                if not isinstance(row,list) or len(row)<12:_fail('INVALID_KLINE')
                op=_int(row[0],'INVALID_KLINE_CLOCK');close=_int(row[6],'INVALID_KLINE_CLOCK')
                if op>=t or close>=t:_fail('NONCAUSAL_KLINE')
                if op%DAY_MS or close!=op+DAY_MS-1:_fail('INVALID_KLINE_CLOCK')
                if close>=cap['receive_ms']:_fail('NONCAUSAL_SOURCE_CAPTURE')
                quote=_num(row[7],'INVALID_TAKER_VOLUME',positive=False)
                bought=_num(row[10],'INVALID_TAKER_VOLUME',positive=False)
                if bought>quote:_fail('INVALID_TAKER_VOLUME')
                times.append(op)
            if len(times)!=len(set(times)):_fail('DUPLICATE_KLINE')
            if times!=sorted(times) or any(b-a!=DAY_MS for a,b in zip(times,times[1:])):_fail('KLINE_CONTINUITY_UNKNOWN')
            if len(bars)<60:
                if candidates[symbol]['onboardDate']>t-60*DAY_MS:excluded[symbol]='KNOWN_NEW_LISTING_LT60'
                else:_fail('INCOMPLETE_MATURE_HISTORY')
            elif not times or times[-1]!=t-DAY_MS:_fail('CLOSED_D_MINUS1_MISSING')
            else:
                q=_num(bars[-1][7],'INVALID_TAKER_VOLUME',positive=False)
                taker=_num(bars[-1][10],'INVALID_TAKER_VOLUME',positive=False)
                if taker>q:_fail('INVALID_TAKER_VOLUME')
                if q==0:excluded[symbol]='ZERO_QUOTE_VOLUME'
                else:
                    fq,ft=float(q),float(taker)
                    if not math.isfinite(fq) or not math.isfinite(ft) or fq==0:_fail('NUMERIC_PRECISION_AMBIGUOUS')
                    ratio=ft/fq
                    if not math.isfinite(ratio):_fail('NUMERIC_PRECISION_AMBIGUOUS')
                    feature.append((ratio,symbol));raw_values[symbol]={'quote_volume':str(bars[-1][7]),'taker_buy_quote_volume':str(bars[-1][10]),'base_asset':candidates[symbol]['baseAsset']}
            pins['klines:'+symbol]=cap['sha256'];received.append(cap['receive_ms'])
        if any(rx>now_ms for rx in received):_fail('SOURCE_NOT_YET_AVAILABLE')
        feature.sort();n=len(feature);k=n//10
        frozen={'day':d.isoformat(),'research_ref':RESEARCH_REF,'oi_cutoff_ms':cutoff,'top50':top,'feature_count':n,'decile_count':k,
                'long':[{'symbol':s,'taker':round(v,6)} for v,s in feature[-k:]] if n>=30 else [],
                'short':[{'symbol':s,'taker':round(v,6)} for v,s in feature[:k]] if n>=30 else [],
                'feature_ratios':{s:v for v,s in feature},'feature_source_values':raw_values,'feature_ineligible':excluded,
                'hold_days':7,'research_roundtrip_cost_bps':12,'source_pins':pins,'source_bundle_digest':digest(bundle)}
        late=now_ms>=t+DAY_MS or max(received)>=t+DAY_MS
        prospective=not late and d>=FIRST_UNSEEN
        reasons=[]
        if n<30:reasons.append('INSUFFICIENT_FEATURES')
        elif k!=5:reasons.append('BLOCKED_BASKET_CONTRACT')
        if late:reasons.append('MISSED_PROSPECTIVE_ENTRY_BOUNDARY')
        if d<FIRST_UNSEEN:reasons.append('PRIOR_PERIOD_DIAGNOSTIC_ONLY')
        reasons.append('EXECUTION_EVIDENCE_REQUIRED')
        return _result('BLOCKED_EXECUTION' if n<30 or k!=5 else 'BLOCKED_DATA',reasons,
            signal_valid=n>=30,prospective_eligible=prospective,evaluated_ms=now_ms,source_available_ms=max(received),
            prospective_eligibility_basis='INPUT_AVAILABILITY_ONLY_NOT_SEALED',
            frozen_signal=frozen,signal_hash=digest(frozen),source_bundle=bundle,census_basis='DECLARED_PUBLIC_POINT_SNAPSHOT_BEFORE_CUTOFF',
            evidence_authentication='HASH_CONSISTENCY_ONLY_NOT_BROKER_TRUTH')
    except EvidenceError as e:out['reasons']=[str(e)]
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError,InvalidOperation):out['reasons']=['MALFORMED_SIGNAL_EVIDENCE']
    return out


def _signal(signal):
    if not isinstance(signal,dict) or signal.get('signal_valid') is not True:_fail('SIGNAL_NOT_VALID')
    s=signal.get('frozen_signal')
    if not isinstance(s,dict) or signal.get('signal_hash')!=digest(s):_fail('SIGNAL_HASH_MISMATCH')
    source=signal.get('source_bundle')
    if not isinstance(source,dict) or s.get('source_bundle_digest')!=digest(source):_fail('SOURCE_DECISION_NOT_BOUND')
    replay=reconstruct_signal(source,_int(signal.get('evaluated_ms'),'INVALID_EVALUATION_CLOCK'))
    if not replay.get('signal_valid') or any(signal.get(k)!=replay.get(k) for k in
            ('frozen_signal','signal_hash','source_available_ms','signal_valid','prospective_eligible','status','reasons')):
        _fail('SOURCE_DECISION_MISMATCH')
    if s.get('research_ref')!=RESEARCH_REF or s.get('hold_days')!=7 or s.get('research_roundtrip_cost_bps')!=12:_fail('RESEARCH_REF_MISMATCH')
    longs=s.get('long');shorts=s.get('short')
    if not isinstance(longs,list) or not isinstance(shorts,list) or len(longs)!=5 or len(shorts)!=5:_fail('BLOCKED_BASKET_CONTRACT')
    ratios=s.get('feature_ratios');values=s.get('feature_source_values');n=s.get('feature_count')
    if type(n) is not int or not 30<=n<=50 or s.get('decile_count')!=n//10 or not isinstance(ratios,dict) or len(ratios)!=n or not isinstance(values,dict) or set(values)!=set(ratios):_fail('FROZEN_BASKET_MISMATCH')
    ordered=[]
    for symbol,value in ratios.items():
        if not isinstance(symbol,str) or not _SYMBOL.fullmatch(symbol) or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:_fail('FROZEN_BASKET_MISMATCH')
        raw=values[symbol]
        if not isinstance(raw,dict):_fail('FROZEN_BASKET_MISMATCH')
        q=_num(raw.get('quote_volume'),'FROZEN_BASKET_MISMATCH');taker=_num(raw.get('taker_buy_quote_volume'),'FROZEN_BASKET_MISMATCH',positive=False)
        if taker>q or float(taker)/float(q)!=value:_fail('FROZEN_BASKET_MISMATCH')
        ordered.append((value,symbol))
    ordered.sort();k=n//10
    if longs!=[{'symbol':x,'taker':round(v,6)} for v,x in ordered[-k:]] or shorts!=[{'symbol':x,'taker':round(v,6)} for v,x in ordered[:k]]:_fail('FROZEN_BASKET_MISMATCH')
    legs=[(x['symbol'],1) for x in longs]+[(x['symbol'],-1) for x in shorts]
    if len({s for s,_ in legs})!=10:_fail('AMBIGUOUS_BASKET')
    return s,legs


def _levels(raw, descending):
    if not isinstance(raw,list) or not raw:_fail('INVALID_BOOK')
    levels=[]
    for row in raw:
        if not isinstance(row,list) or len(row)!=2:_fail('INVALID_BOOK')
        levels.append((_num(row[0],'INVALID_BOOK'),_num(row[1],'INVALID_BOOK')))
    prices=[p for p,_ in levels]
    if len(prices)!=len(set(prices)) or prices!=sorted(prices,reverse=descending):_fail('INVALID_BOOK')
    return levels


def _vwap(levels, quantity):
    remaining=quantity;quote=Decimal(0)
    for p,available in levels:
        use=min(remaining,available);quote+=use*p;remaining-=use
        if remaining==0:return quote/quantity,quote
    _fail('DEPTH_INSUFFICIENT')


def assess_execution(signal, execution, now_ms):
    out=_result(public_checks_pass=False,legs=[])
    try:
        _int(now_ms,'INVALID_EVALUATION_CLOCK');s,basket=_signal(signal)
        if not isinstance(execution,dict):_fail('MALFORMED_EXECUTION_EVIDENCE')
        if signal.get('source_available_ms',now_ms)>now_ms or signal.get('evaluated_ms',now_ms)>now_ms:_fail('SIGNAL_NOT_YET_AVAILABLE')
        venue=execution.get('venue')
        if venue not in ('BINANCE','BYBIT'):_fail('INVALID_VENUE')
        uncertainty=_int(execution.get('clock_uncertainty_ms'),'CLOCK_UNCERTAINTY_UNKNOWN',zero=True)
        if uncertainty>FRESH_MS:_fail('CLOCK_UNCERTAINTY_UNKNOWN')
        target=_num(execution.get('per_leg_notional_usdt'),'INVALID_SCENARIO_NUMBER')
        cap=_num(execution.get('max_gross_notional_usdt'),'INVALID_SCENARIO_NUMBER')
        inscap=execution['instruments'];endpoint='/fapi/v1/exchangeInfo' if venue=='BINANCE' else '/v5/market/instruments-info'
        body=capture_payload(inscap,venue,endpoint)
        if inscap['receive_ms']>now_ms or now_ms-inscap['receive_ms']>60000:_fail('INSTRUMENT_SOURCE_STALE')
        if venue=='BINANCE':rows=body['symbols']
        else:
            _params(inscap,{'category':'linear'})
            if body.get('retCode')!=0 or body['result'].get('category')!='linear' or body['result'].get('nextPageCursor','')!='':_fail('INSTRUMENT_CENSUS_INCOMPLETE')
            rows=body['result']['list']
        if not isinstance(rows,list):_fail('INSTRUMENT_FILTER_UNKNOWN')
        funding_intervals={}
        if venue=='BINANCE' and execution.get('funding_info') is not None:
            fc=execution['funding_info'];fund_rows=capture_payload(fc,venue,'/fapi/v1/fundingInfo')
            if fc['receive_ms']>now_ms or now_ms-fc['receive_ms']>60000 or not isinstance(fund_rows,list):_fail('FUNDING_INTERVAL_UNKNOWN')
            for frow in fund_rows:
                if not isinstance(frow,dict):_fail('FUNDING_INTERVAL_UNKNOWN')
                fsymbol=frow.get('symbol')
                if not isinstance(fsymbol,str) or fsymbol in funding_intervals:_fail('FUNDING_INTERVAL_UNKNOWN')
                funding_intervals[fsymbol]=60*_int(frow.get('fundingIntervalHours'),'FUNDING_INTERVAL_UNKNOWN')
        instruments={}
        for row in rows:
            if not isinstance(row,dict):_fail('INSTRUMENT_FILTER_UNKNOWN')
            symbol=row.get('symbol')
            if symbol in instruments:_fail('AMBIGUOUS_INSTRUMENT')
            instruments[symbol]=row
        books=execution.get('books')
        if not isinstance(books,dict) or set(books)!={x for x,_ in basket}:_fail('BOOK_CENSUS_INCOMPLETE')
        legs=[];gross=Decimal(0);spread_cost=Decimal(0);fee_base=Decimal(0);funding_base=Decimal(0);minimum_targets=[]
        for symbol,side in basket:
            if symbol not in instruments:_fail('MISSING_EXECUTION_SYMBOL')
            row=instruments[symbol];source_base=s['feature_source_values'][symbol]['base_asset']
            if venue=='BINANCE':
                if (row.get('status'),row.get('contractType'),row.get('quoteAsset'),row.get('marginAsset'))!=('TRADING','PERPETUAL','USDT','USDT'):_fail('INSTRUMENT_INELIGIBLE')
                if row.get('baseAsset')!=source_base:_fail('UNDERLYING_MISMATCH')
                fs=row.get('filters',[]);f={v['filterType']:v for v in fs}
                if len(f)!=len(fs):_fail('INSTRUMENT_FILTER_UNKNOWN')
                try:
                    market=f['MARKET_LOT_SIZE'];limit=f['LOT_SIZE'];step=_num(market['stepSize'],'INSTRUMENT_FILTER_UNKNOWN')
                    if step!=_num(limit['stepSize'],'INSTRUMENT_FILTER_UNKNOWN'):_fail('INSTRUMENT_FILTER_UNKNOWN')
                    minimum=max(_num(market['minQty'],'INSTRUMENT_FILTER_UNKNOWN'),_num(limit['minQty'],'INSTRUMENT_FILTER_UNKNOWN'))
                    maximum=min(_num(market['maxQty'],'INSTRUMENT_FILTER_UNKNOWN'),_num(limit['maxQty'],'INSTRUMENT_FILTER_UNKNOWN'))
                    notional=_num(f['MIN_NOTIONAL']['notional'],'INSTRUMENT_FILTER_UNKNOWN');tick=_num(f['PRICE_FILTER']['tickSize'],'INSTRUMENT_FILTER_UNKNOWN')
                except KeyError:_fail('INSTRUMENT_FILTER_UNKNOWN')
                bookep='/fapi/v1/depth';bc=books[symbol];book=capture_payload(bc,venue,bookep);_params(bc,{'symbol':symbol})
                source_ms=book.get('T');sequence=book.get('lastUpdateId');bids=_levels(book.get('bids'),True);asks=_levels(book.get('asks'),False)
            else:
                if (row.get('status'),row.get('contractType'),row.get('quoteCoin'),row.get('settleCoin'))!=('Trading','LinearPerpetual','USDT','USDT') or row.get('isPreListing') is not False:_fail('INSTRUMENT_INELIGIBLE')
                if row.get('baseCoin')!=source_base:_fail('UNDERLYING_MISMATCH')
                try:
                    f=row['lotSizeFilter'];step=_num(f['qtyStep'],'INSTRUMENT_FILTER_UNKNOWN');minimum=_num(f['minOrderQty'],'INSTRUMENT_FILTER_UNKNOWN');maximum=_num(f['maxMktOrderQty'],'INSTRUMENT_FILTER_UNKNOWN');notional=_num(f['minNotionalValue'],'INSTRUMENT_FILTER_UNKNOWN');tick=_num(row['priceFilter']['tickSize'],'INSTRUMENT_FILTER_UNKNOWN')
                    _int(row.get('fundingInterval'),'FUNDING_INTERVAL_UNKNOWN')
                except KeyError:_fail('INSTRUMENT_FILTER_UNKNOWN')
                bc=books[symbol];book=capture_payload(bc,venue,'/v5/market/orderbook');_params(bc,{'category':'linear','symbol':symbol})
                if book.get('retCode')!=0 or book['result'].get('s')!=symbol:_fail('SOURCE_IDENTITY_MISMATCH')
                ob=book['result'];source_ms=ob.get('cts');sequence=ob.get('u');bids=_levels(ob.get('b'),True);asks=_levels(ob.get('a'),False)
            if type(source_ms) is not int or source_ms<=0:_fail('SOURCE_FRESHNESS_UNKNOWN')
            _int(sequence,'SOURCE_SEQUENCE_UNKNOWN')
            if bc['receive_ms']>now_ms or source_ms>now_ms+uncertainty or source_ms>bc['receive_ms']+uncertainty:_fail('SOURCE_CLOCK_CONFLICT')
            if max(0,now_ms-source_ms)+uncertainty>FRESH_MS or now_ms-bc['receive_ms']>FRESH_MS:_fail('COMMON_BASKET_FRESHNESS')
            if bids[0][0]>=asks[0][0]:_fail('INVALID_BOOK')
            if any(p%tick!=0 for p,_ in bids+asks):_fail('INVALID_BOOK')
            reference=asks[0][0] if side==1 else bids[0][0]
            quantity=(target/reference/step).to_integral_value(rounding=ROUND_FLOOR)*step
            diagnostic_qty=(max(minimum,notional/bids[0][0])/step).to_integral_value(rounding=ROUND_CEILING)*step
            minimum_targets.append(diagnostic_qty*reference)
            if quantity<minimum or quantity>maximum or quantity*reference<notional:_fail('VENUE_MINIMUM_REJECT')
            entry,entry_quote=_vwap(asks if side==1 else bids,quantity)
            exit_price,exit_quote=_vwap(bids if side==1 else asks,quantity)
            if entry_quote<notional:_fail('VENUE_MINIMUM_REJECT')
            gross+=entry_quote;spread_cost+=abs(entry_quote-exit_quote);fee_base+=entry_quote+exit_quote;funding_base+=max(entry_quote,exit_quote)
            legs.append({'symbol':symbol,'side':'LONG' if side==1 else 'SHORT','quantity':_text(quantity),'quantity_increased':False,
                'entry_vwap':_text(entry),'exit_reference_vwap':_text(exit_price),'entry_notional_usdt':_text(entry_quote),'exit_reference_notional_usdt':_text(exit_quote),
                'rounding_shortfall_usdt':_text(target-entry_quote),'depth_covered':True,'minimum_reference_quantity':_text(diagnostic_qty),
                'minimum_reference_notional_usdt':_text(diagnostic_qty*reference),'minimum_is_admitted_quantity':False,'source_ms':source_ms,'receive_ms':bc['receive_ms'],
                'common_assessment_ms':now_ms,'raw_source_sha256':bc['sha256'],'funding_interval_minutes':row.get('fundingInterval') if venue=='BYBIT' else funding_intervals.get(symbol)})
        if gross>cap:_fail('GROSS_CAP_REJECT')
        costs=execution.get('scenario_costs');cost_result=None
        reasons=['ACTUAL_ACCOUNT_EVIDENCE_REQUIRED','ABSOLUTE_RISK_POLICY_REQUIRED','PROTECTION_EXIT_FINALITY_REQUIRED']
        if any(l['funding_interval_minutes'] is None for l in legs):reasons.append('FUNDING_INTERVAL_UNKNOWN')
        if costs is None:reasons+=['ACTUAL_FEES_UNKNOWN','FUNDING_RESERVE_POLICY_UNKNOWN']
        else:
            if not isinstance(costs,dict) or costs.get('basis')!='DECLARED_SYNTHETIC' or not isinstance(costs.get('source_sha256'),str) or not _SHA.fullmatch(costs['source_sha256']):_fail('INVALID_COST_SCENARIO')
            entry_fee=_num(costs.get('entry_fee_rate'),'INVALID_COST_SCENARIO',positive=False);exit_fee=_num(costs.get('exit_fee_rate'),'INVALID_COST_SCENARIO',positive=False)
            funding_rate=_num(costs.get('funding_rate_envelope'),'INVALID_COST_SCENARIO',positive=False);events=_int(costs.get('settlements'),'INVALID_COST_SCENARIO')
            if any(l['funding_interval_minutes'] is not None and events < (7*1440+l['funding_interval_minutes']-1)//l['funding_interval_minutes'] for l in legs):_fail('FUNDING_SETTLEMENT_COUNT_INFEASIBLE')
            if max(entry_fee,exit_fee,funding_rate)>=1:_fail('INVALID_COST_SCENARIO')
            fees=sum((Decimal(l['entry_notional_usdt'])*entry_fee+Decimal(l['exit_reference_notional_usdt'])*exit_fee for l in legs),Decimal(0))
            reserve=funding_base*funding_rate*events
            cost_result={'basis':'DECLARED_SYNTHETIC','actual_account_truth':False,'future_bound_proven':False,'source_sha256':costs['source_sha256'],
                'fee_bps':_text((entry_fee+exit_fee)*10000),'fee_quote_usdt':_text(fees),'fee_quote_bps':_text(fees/gross*10000),
                'funding_bps':_text(funding_rate*events*10000),'funding_quote_usdt':_text(reserve),'funding_settlements_assumed':events,
                'spread_depth_quote_usdt':_text(spread_cost),'roundtrip_quote_cost_usdt':_text(fees+reserve+spread_cost),
                'roundtrip_quote_cost_bps':_text((fees+reserve+spread_cost)/gross*10000),
                'assumptions':['captured mark-neutral exit-depth reference is not a future fill','funding notional bounded by max current entry/exit reference, not future guarantee','rates/count declared, not authenticated account tier or future settlement proof']}
            reasons+=['ACTUAL_FEES_UNKNOWN','FUNDING_RESERVE_POLICY_UNKNOWN']
        if venue=='BYBIT':reasons.append('BINANCE_BYBIT_PORTABILITY_REQUIRED')
        return _result(reasons=reasons,public_checks_pass=True,venue=venue,signal_hash=signal['signal_hash'],intent_id=digest({'research_ref':RESEARCH_REF,'day':s['day'],'signal_hash':signal['signal_hash'],'venue':venue}),legs=legs,common_assessment_ms=now_ms,
            execution_bundle=execution,immutable_signal_seal_required=True,
            clock_uncertainty_ms=uncertainty,gross_notional_usdt=_text(gross),per_leg_reference_target_usdt=_text(target),
            equal_notional_reference_floor_usdt=_text(max(minimum_targets)),basket_reference_floor_usdt=_text(max(minimum_targets)*10),
            weight_rounding_tolerance_approved=False,research_roundtrip_cost_bps=12,scenario_costs=cost_result,
            reference_exit_is_fill=False,source_authentication='HASH_CONSISTENCY_ONLY_NOT_BROKER_TRUTH')
    except EvidenceError as e:
        code=str(e);execution_codes={'BLOCKED_BASKET_CONTRACT','VENUE_MINIMUM_REJECT','DEPTH_INSUFFICIENT','GROSS_CAP_REJECT','UNDERLYING_MISMATCH','MISSING_EXECUTION_SYMBOL','INSTRUMENT_INELIGIBLE'}
        out['status']='BLOCKED_EXECUTION' if code in execution_codes else 'BLOCKED_DATA';out['reasons']=[code]
    except (KeyError,TypeError,ValueError,InvalidOperation,OverflowError,AttributeError):out['reasons']=['MALFORMED_EXECUTION_EVIDENCE']
    return out


def reconcile_paper_events(signal, events, prepared=None):
    """Replay one explicitly prepared synthetic lifecycle; never broker truth."""
    positions = {}; entries = {}; expected = {}; sides = {}; final = set()
    average = {}; realized = Decimal(0); trade_cash = Decimal(0)
    fees = Decimal(0); funding = Decimal(0); seen = {}; fills = {}; settlements = {}
    current_event = None; identity = None; error = None; prepared_pin = None
    try:
        frozen, basket = _signal(signal)
        sides = dict(basket)
        positions = {symbol: Decimal(0) for symbol in sides}
        entries = dict(positions); average = dict(positions)
        if not isinstance(prepared, dict) or prepared.get('public_checks_pass') is not True:
            _fail('PAPER_PREPARATION_REQUIRED')
        rebuilt=assess_execution(signal,prepared.get('execution_bundle'),prepared.get('common_assessment_ms'))
        if prepared!=rebuilt or rebuilt.get('public_checks_pass') is not True:
            _fail('PAPER_PREPARATION_MISMATCH')
        prepared_pin=digest(prepared)
        venue = prepared.get('venue')
        if venue not in ('BINANCE', 'BYBIT') or prepared.get('signal_hash') != signal['signal_hash']:
            _fail('PAPER_PREPARATION_MISMATCH')
        intent = digest({'research_ref': RESEARCH_REF, 'day': frozen['day'],
                         'signal_hash': signal['signal_hash'], 'venue': venue})
        if prepared.get('intent_id') != intent:
            _fail('PAPER_PREPARATION_MISMATCH')
        identity = {'day': frozen['day'], 'signal_hash': signal['signal_hash'],
                    'venue': venue, 'intent_id': intent,'prepared_digest':prepared_pin}
        for leg in prepared.get('legs', []):
            if not isinstance(leg, dict): _fail('PAPER_PREPARATION_MISMATCH')
            symbol = leg.get('symbol')
            if symbol not in sides or symbol in expected or leg.get('side') != ('LONG' if sides[symbol] == 1 else 'SHORT'):
                _fail('PAPER_PREPARATION_MISMATCH')
            expected[symbol] = _num(leg.get('quantity'), 'PAPER_PREPARATION_MISMATCH')
        if set(expected) != set(sides): _fail('PAPER_PREPARATION_MISMATCH')
        if not isinstance(events, list): _fail('INVALID_PAPER_EVENTS')
        for event in events:
            current_event = event
            if not isinstance(event, dict) or not isinstance(event.get('event_id'), str) or not event['event_id']:
                _fail('INVALID_PAPER_EVENT')
            if any(event.get(key) != value for key, value in identity.items()):
                _fail('PAPER_IDENTITY_MISMATCH')
            eid = event['event_id']; pin = digest(event)
            if eid in seen:
                if seen[eid] != pin: _fail('CONFLICTING_EVENT')
                continue
            symbol = event.get('symbol'); kind = event.get('kind')
            if symbol not in sides: _fail('UNKNOWN_PAPER_SYMBOL')
            if kind in ('ENTRY_FILL', 'EXIT_FILL'):
                xid = event.get('execution_id')
                if not isinstance(xid, str) or not xid: _fail('INVALID_PAPER_EXECUTION')
                normalized = {key: value for key, value in event.items() if key != 'event_id'}
                fp = digest(normalized)
                if xid in fills:
                    if fills[xid] != fp: _fail('CONFLICTING_EXECUTION')
                    seen[eid] = pin
                    continue
                qty = _num(event.get('qty'), 'INVALID_PAPER_QUANTITY')
                price = _num(event.get('price'), 'INVALID_PAPER_PRICE')
                fee = _signed_num(event.get('fee_usdt'), 'PAPER_COST_UNKNOWN')
                if kind == 'ENTRY_FILL':
                    if entries[symbol] + qty > expected[symbol]: _fail('PAPER_ENTRY_EXCEEDS_PREPARED')
                    if symbol in final: _fail('PAPER_ENTRY_AFTER_FINALITY')
                    average[symbol] = (average[symbol] * positions[symbol] + qty * price) / (positions[symbol] + qty)
                    positions[symbol] += qty; entries[symbol] += qty
                    trade_cash -= sides[symbol] * qty * price
                else:
                    if qty > positions[symbol]: _fail('PAPER_EXIT_EXCEEDS_HELD')
                    realized += sides[symbol] * qty * (price - average[symbol])
                    positions[symbol] -= qty
                    trade_cash += sides[symbol] * qty * price
                fills[xid] = fp; final.discard(symbol); fees += fee
            elif kind == 'FUNDING':
                settlement = event.get('settlement_id')
                if not isinstance(settlement, str) or not settlement: _fail('PAPER_FUNDING_UNKNOWN')
                settlement_key = (symbol, settlement)
                normalized = {key: value for key, value in event.items() if key != 'event_id'}
                fp = digest(normalized)
                if settlement_key in settlements:
                    if settlements[settlement_key] != fp: _fail('CONFLICTING_FUNDING_SETTLEMENT')
                    seen[eid] = pin
                    continue
                qty = _num(event.get('quantity'), 'PAPER_FUNDING_UNKNOWN')
                mark = _num(event.get('mark_price'), 'PAPER_FUNDING_UNKNOWN')
                rate = _signed_num(event.get('rate'), 'PAPER_FUNDING_UNKNOWN')
                cash = _signed_num(event.get('cash_usdt'), 'PAPER_FUNDING_UNKNOWN')
                if abs(rate) >= 1 or qty != positions[symbol] or cash != -sides[symbol] * qty * mark * rate:
                    _fail('PAPER_FUNDING_MISMATCH')
                funding += cash; settlements[settlement_key] = fp; final.discard(symbol)
            elif kind == 'FINALITY':
                if positions[symbol] != 0 or entries[symbol] <= 0 or event.get('costs_complete') is not True or event.get('funding_complete') is not True:
                    _fail('PAPER_FINALITY_UNKNOWN')
                final.add(symbol)
            elif kind in ('ENTRY_REJECT', 'PROTECTION_UNKNOWN'):
                final.discard(symbol)
            elif kind == 'ROTATION':
                if any(positions.values()) or len(final) != 10: _fail('PAPER_ROTATION_BEFORE_FINALITY')
            else: _fail('UNKNOWN_PAPER_EVENT')
            seen[eid] = pin
        current_event = None
    except EvidenceError as exc:
        error = str(exc)
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError, OverflowError):
        error = 'MALFORMED_PAPER_EVIDENCE'
    exposure_reconciled = not error and len(final) == 10 and all(value == 0 for value in positions.values())
    intended_complete = bool(expected) and all(entries[symbol] == expected[symbol] for symbol in expected)
    complete = exposure_reconciled and intended_complete
    reasons = ['SYNTHETIC_ONLY_NOT_PROSPECTIVE_OR_BROKER_TRUTH']
    if error: reasons.append(error)
    elif exposure_reconciled and not intended_complete: reasons.append('PAPER_INTENDED_BASKET_INCOMPLETE')
    elif not complete: reasons.append('PAPER_LIFECYCLE_INCOMPLETE')
    return _result(reasons=reasons, synthetic_only=True, terminal_complete=complete,
        exposure_reconciled=exposure_reconciled, intended_basket_complete=complete,
        lifecycle_identity=identity, prepared_digest=prepared_pin,
        positions={symbol:_text(value) for symbol,value in positions.items()},
        signed_positions={symbol:_text(value*sides[symbol]) for symbol,value in positions.items()},
        sides={symbol:('LONG' if side==1 else 'SHORT') for symbol,side in sides.items()},
        filled_entry_quantities={symbol:_text(value) for symbol,value in entries.items()},
        expected_entry_quantities={symbol:_text(value) for symbol,value in expected.items()},
        fees_usdt=_text(fees),funding_cash_usdt=_text(funding),trade_cash_flow_usdt=_text(trade_cash),
        gross_realized_usdt=_text(realized),net_realized_usdt=_text(realized+funding-fees),
        terminal_net_is_final=complete,unresolved_liability=not complete,
        unresolved_event_id=current_event.get('event_id') if isinstance(current_event,dict) else None,
        validated_event_count=len(seen),protection='NOT_PROVEN')
