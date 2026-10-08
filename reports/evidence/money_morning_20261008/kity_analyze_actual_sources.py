import hashlib
import importlib.util
import json
from pathlib import Path
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

root=Path(__file__).resolve().parent
oi=json.loads((root/'exact_oi_archive.json').read_text())
wire=json.loads((root/'closed_and_venue_archive.json').read_text())
def capture(name):return json.loads(wire['files'][name])
for archive in (oi,wire):
    assert all(hashlib.sha256(v.encode()).hexdigest()==archive['sha256'][k] for k,v in archive['files'].items())
diag=capture('closed-research-projection/diagnostic.json')
census=json.loads((root/'remote_runtime/census-2026-10-08.json').read_text())
bundle=dict(day='2026-10-08',research_ref='d6ed8126c041969de0bc6191e39fefe4a1272d5b',census=census,
            oi={k[3:-5]:json.loads(v) for k,v in oi['files'].items() if k.startswith('oi-')},
            klines={k.split('klines-',1)[1][:-5]:json.loads(v) for k,v in wire['files'].items() if k.startswith('closed-research-projection/klines-')})
raw=json.dumps(bundle,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
with (root/'actual_complete_capture_bundle.json').open('xb') as f:f.write(raw)
spec=importlib.util.spec_from_file_location('core',Path('bot/kity_m3_orders_off.py'))
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
now=time.time_ns()//1000000
strict=core.reconstruct_signal(bundle,now)
assert strict['signal_valid'] is False and strict['reasons']==['PIT_STATUS_AMBIGUOUS']
external_root=Path('../bybit-bot-clean-v28/research_lab/data/kity_m3_ten/2026-10-08')
external=json.loads((external_root/'signal.json').read_text())
assert all(hashlib.sha256((external_root/'syroe'/k).read_bytes()).hexdigest()==h for k,h in external['sha256'].items())
external_oi=json.loads((external_root/'syroe/oi_2355.json').read_text())
external_top=[s for s,_ in sorted(external_oi.items(),key=lambda z:-z[1])[:50]]
parity={side:diag[side]==[dict(symbol=r['s'],taker=r['taker']) for r in external[side]] for side in ('long','short')}
parity.update(feature_count=diag['feature_count']==external['monet_s_priznakom'],top50_order=diag['top50']==external_top,
    all_rounded_features={s:round(v,6) for s,v in diag['all_features'].items()}==external['vse_priznaki'])
spec=importlib.util.spec_from_file_location('facade',Path('scripts/kity_m3_orders_off.py'))
facade=importlib.util.module_from_spec(spec);spec.loader.exec_module(facade)
external_acceptance=facade.compare_forward(bundle,external_root,now)
instruments={r['symbol']:r for r in json.loads(capture('venue-evidence/binance-instruments.json')['raw'])['symbols']}
funding_info={r['symbol']:r for r in json.loads(capture('venue-evidence/binance-funding-info.json')['raw'])}
rows=[]
for side in ('long','short'):
 for leg in diag[side]:
    s=leg['symbol'];row={'symbol':s,'side':side.upper(),'diagnostic_only':True}
    for venue in ('binance','bybit'):
        meta=instruments[s] if venue=='binance' else json.loads(capture('venue-evidence/bybit-instrument-'+s+'.json').get('raw','{}')).get('result',{}).get('list',[])
        if venue=='bybit':
            if len(meta)!=1:
                row[venue]={'status':'BLOCKED_EXECUTION','reason':'EXACT_EXECUTION_SYMBOL_UNAVAILABLE','retCode':json.loads(capture('venue-evidence/bybit-instrument-'+s+'.json').get('raw','{}')).get('retCode')}
                continue
            meta=meta[0]
        bc=capture('venue-evidence/'+venue+'-book-'+s+'.json')
        book=json.loads(bc.get('raw','{}'))
        if venue=='binance':
            f={r['filterType']:r for r in meta['filters']}
            market,limit=f['MARKET_LOT_SIZE'],f['LOT_SIZE']
            assert market['stepSize']==limit['stepSize']
            step=Decimal(market['stepSize']); minimum=max(Decimal(market['minQty']),Decimal(limit['minQty']))
            min_n=Decimal(f['MIN_NOTIONAL']['notional']); bids,asks=book['bids'],book['asks'];source_ms=book.get('T')
            interval=funding_info.get(s,{}).get('fundingIntervalHours')
            interval=60*interval if interval is not None else None
        else:
            f=meta['lotSizeFilter'];step=Decimal(f['qtyStep']);minimum=Decimal(f['minOrderQty']);min_n=Decimal(f['minNotionalValue'])
            bids,asks=book['result']['b'],book['result']['a'];source_ms=book['result'].get('cts');interval=meta['fundingInterval']
        common=capture('venue-evidence/'+venue+'-common-assessment.json')['now_ms']
        uncertainties=[]
        for phase in ('before','after'):
            clock=capture('venue-evidence/'+venue+'-clock-'+phase+'.json');cb=json.loads(clock['raw'])
            server=cb['serverTime'] if venue=='binance' else int(cb['result']['timeNano'])//1000000
            uncertainties.append(max(abs(server-clock['request_ms']),abs(clock['receive_ms']-server)))
        uncertainty=max(uncertainties)
        bid,ask=Decimal(bids[0][0]),Decimal(asks[0][0]);ref=ask if side=='long' else bid
        q=(max(minimum,min_n/bid)/step).to_integral_value(rounding=ROUND_CEILING)*step
        ready=type(source_ms) is int and source_ms>0 and max(0,common-source_ms)+uncertainty<=2000 and 0<=common-bc['receive_ms']<=2000
        levels=asks if side=='long' else bids
        rem=q;notional=Decimal(0)
        for price,qty in levels:
            used=min(rem,Decimal(qty));notional+=used*Decimal(price);rem-=used
            if rem==0:break
        funding_cap=capture('venue-evidence/'+venue+'-funding-'+s+'.json')
        history=json.loads(funding_cap.get('raw','{}'))
        if venue=='bybit':history=history.get('result',{}).get('list',[])
        row[venue]=dict(status='DIAGNOSTIC_MINIMUM_ONLY',qty_step=str(step),min_qty=str(minimum),min_notional_usdt=str(min_n),
            best_bid=str(bid),best_ask=str(ask),minimum_reference_quantity=str(q),minimum_reference_target_usdt=str(q*ref),
            minimum_entry_notional_usdt=str(notional),minimum_depth_covered=rem==0,source_ms=source_ms,receive_ms=bc['receive_ms'],
            common_assessment_ms=common,clock_uncertainty_observed_bound_ms=uncertainty,
            source_age_ms=common-source_ms if type(source_ms)is int else None,receive_age_ms=common-bc['receive_ms'],
            common_2s_freshness_pass=ready,current_funding_interval_minutes=interval,
            funding_points=len(history) if isinstance(history,list) else None,
            instrument_raw_sha256=(capture('venue-evidence/binance-instruments.json')['sha256'] if venue=='binance' else capture('venue-evidence/bybit-instrument-'+s+'.json')['sha256']),book_raw_sha256=bc['sha256'])
    rows.append(row)
target=max(Decimal(r['binance']['minimum_reference_target_usdt']) for r in rows)
gross=Decimal(0);sized=[]
for row in rows:
    r=row['binance'];ref=Decimal(r['best_ask'] if row['side']=='LONG' else r['best_bid']);step=Decimal(r['qty_step'])
    q=(target/ref/step).to_integral_value(rounding=ROUND_FLOOR)*step
    bc=capture('venue-evidence/binance-book-'+row['symbol']+'.json');book=json.loads(bc['raw']);levels=book['asks'] if row['side']=='LONG' else book['bids']
    rem=q;notional=Decimal(0)
    for price,qty in levels:
        used=min(rem,Decimal(qty));notional+=used*Decimal(price);rem-=used
        if rem==0:break
    assert rem==0 and q>=Decimal(r['min_qty']) and notional>=Decimal(r['min_notional_usdt'])
    gross+=notional;sized.append(dict(symbol=row['symbol'],side=row['side'],quantity=str(q),notional_usdt=str(notional),not_admitted_quantity=True))
out=dict(schema='KITY_OCT8_ACTUAL_SOURCE_DIAGNOSTIC_V1',observed_ms=now,orders_allowed=False,money_ready=False,
    strict_verdict=strict,strict_signal_hash=None,strict_prospective_seal_exists=False,
    complete_raw_bundle_sha256=hashlib.sha256(raw).hexdigest(),complete_raw_bundle_bytes=len(raw),
    frozen_rule_diagnostic=diag,diagnostic_parity=parity,external_strict_acceptance=external_acceptance,
    venue_feasibility=rows,binance_diagnostic_equal_notional_target_usdt=str(target),binance_diagnostic_gross_usdt=str(gross),
    diagnostic_quantities=sized,account_fees_cash_mode_caps_or_order_path_collected=False,
    binance_all_books_common_2s_fresh=all(r['binance']['common_2s_freshness_pass'] for r in rows),
    bybit_terminal='BLOCKED_EXECUTION',bybit_reason='EXACT_BASKET_SYMBOL_UNAVAILABLE: 币安人生USDT')
data=json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode()
with (root/'actual_analysis.json').open('xb') as f:f.write(data)
print(json.dumps({k:v for k,v in out.items() if k in ('strict_verdict','diagnostic_parity','complete_raw_bundle_bytes','binance_diagnostic_equal_notional_target_usdt','binance_diagnostic_gross_usdt','binance_all_books_common_2s_fresh','bybit_terminal','bybit_reason')},ensure_ascii=False))
for row in rows:print(row['symbol'],row['binance']['minimum_reference_target_usdt'],row['binance']['common_2s_freshness_pass'],row['bybit']['status'])
