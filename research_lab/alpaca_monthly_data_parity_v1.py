"""Immutable Monthly58 daily view of the SAME frozen hourly capture.

No fetcher, corporate-action recalculator, source substitution, financial book
or broker. The existing aggregator and frozen selector remain authoritative.
"""
import csv
from dataclasses import asdict
from datetime import date
import json
import math
from pathlib import Path
import re
import sys

from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_dynamic_v1 import digest,canonical
from research_lab.kity_oct15_deadline_v1 import publish_once,stable_bytes
from scripts.run_alpaca_dynamic_v1_orders_off import load_history
from scripts.alpaca_adaptive_paper import prepare_intended_report,_frozen_clusters
from backtest import alpaca_honest_portfolio as frozen
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP

SCHEMA='ALPACA_MONTHLY58_DAILY_PARITY_V1'
POLICY=dict(auto_adjust=False,consumer_price_factor='NONE',provider_price_basis='YAHOO_OHLC_AS_CAPTURED',
    yfinance_adj_close_ratio_applied=False,consumer_dividend_total_return_adjustment=False,
    split_policy='PRESERVE_VENDOR_HISTORY_NO_REBASE_OR_SECOND_SPLIT_FACTOR',
    corporate_action_point_in_time_reconstruction='NOT_PROVEN_NOT_REQUIRED_FOR_SAME_CAPTURE_PARITY',
    close='LAST_RTH_HOURLY_BAR_CLOSE_NOT_SIP_OFFICIAL_AUCTION',
    aggregation='EXISTING_UTC_DAY_FIRST_OPEN_MAX_HIGH_MIN_LOW_LAST_CLOSE_SUM_VOLUME')
NUMERIC_PARITY=dict(abs_tol=1e-12,rel_tol=1e-12,
    scope='RECOMPUTED_METRICS_ONLY_EXACT_BAR_HASHES_AND_SYMBOL_ORDER')


def equivalent(a,b):
    if type(a) in (float,int) and type(b) in (float,int):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
    if isinstance(a,dict) and isinstance(b,dict):
        return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b


def view_proof(x):
    return {k:digest(x[n]) for k,n in [('history_sha256','history'),('coverage_sha256','coverage'),
        ('calendar_sha256','calendar'),('capture_sha256','source_capture')]}


def selection(history,session,entry):
    r=prepare_intended_report(history,signal_session=date.fromisoformat(session),entry_session=date.fromisoformat(entry))
    return {k:r[k] for k in ('gate_ok','reason','picks')}


def ranking(history):
    values={s:frozen._universe_health(b) for s,b in history.items() if s!='SPY'}
    return [dict(symbol=s,health_score=v if math.isfinite(v) else None)
        for s,v in sorted(values.items(),key=lambda x:x[1] if math.isfinite(x[1]) else -math.inf,reverse=True)]


def build_delivery(bundle,*,now_ms,warmup=260):
    if type(warmup) is not int or warmup<200:raise ValueError('WARMUP_AT_LEAST_200')
    rebuilt=ops.compile_source(bundle['cache_root'],bundle['cache_capture'],bundle['calendar'],now_ms=now_ms)
    if rebuilt!=bundle:raise ValueError('MONTHLY_SOURCE_DERIVATION')
    session=bundle['signal_session'];calendar=bundle['calendar']
    closed=[r for r in calendar if r['session']<=session]
    if len(closed)<warmup:raise ValueError('WARMUP_260_CALENDAR_REQUIRED')
    window=closed[-warmup:];days=[r['session'] for r in window]
    expected={r['session']:list(range(r['open_ms']//1000,r['close_ms']//1000,3600)) for r in window}
    history={};raw_sources={};hours=0;coverage_by_symbol={}
    for symbol in ops.required_symbols():
        p=ops.safe_path(Path(bundle['cache_root'])/(symbol+'_M5.csv'))
        times={d:[] for d in days}
        with p.open() as stream:
            for row in csv.DictReader(stream):
                t=int(row['ts']);day=ops.datetime.fromtimestamp(t,ops.timezone.utc).date().isoformat()
                if day in times:times[day].append(t)
        incomplete=[d for d in days if times[d]!=expected[d]]
        if any(d in days[-200:] for d in incomplete):raise ValueError('CORE200_RTH_COVERAGE:'+symbol)
        rows=[dict(session=b.day,open=b.o,high=b.h,low=b.l,close=b.c,volume=b.v)
              for b in ops._aggregate_daily(p) if b.day in expected]
        if [b['session'] for b in rows]!=days:raise ValueError('WARMUP_DAILY_COVERAGE:'+symbol)
        if ops.sha(p)!=bundle['cache_capture']['files'][p.name]:raise ValueError('RAW_CHANGED')
        history[symbol]=rows;raw_sources[p.name]=ops.sha(p);hours+=sum(map(len,times.values()))
        coverage_by_symbol[symbol]=dict(exported_sessions=len(rows),
            fully_checked_sessions=warmup-len(incomplete),incomplete_older_sessions=incomplete)
    direct=load_history(bundle['history']);reader=load_history(json.loads(canonical(history)))
    left=selection(direct,session,bundle['entry_session']);right=selection(reader,session,bundle['entry_session'])
    ranks=ranking(reader)
    if left!=right or ranking(direct)!=ranks:raise ValueError('MONTHLY_SELECTION_OR_RANK_PARITY')
    cap=bundle['cache_capture'];out=dict(schema=SCHEMA,provider='YAHOO_HOURLY',session_date=session,
        entry_session=bundle['entry_session'],source_available_ms=bundle['source_available_ms'],
        source_started_ms=cap['started_ms'],universe=list(ops.required_symbols()),
        universe_sha256=digest(list(ops.required_symbols())),adjustment_policy=dict(POLICY),
        history=history,calendar=calendar,raw_source_files=raw_sources,
        source_capture=cap,source_code_sha256=bundle['source_code_sha256'],
        source_content_sha256=digest(dict(capture=cap,calendar=calendar,history=bundle['history'])),
        coverage=dict(exported_sessions=warmup,fully_checked_sessions=min(r['fully_checked_sessions'] for r in coverage_by_symbol.values()),
            core200_complete=True,earlier_warmup_policy='PRESERVE_AND_FLAG_NEVER_FILL_OR_REBASE',
            by_symbol=coverage_by_symbol,first_session=days[0],last_session=days[-1],
            symbols=58,observed_hourly_rows=hours),
        source_last_bar_open_ms=expected[session][-1]*1000,
        source_session_close_ms=closed[-1]['close_ms'],
        historical_warmup_prospective_credit=0,orders_allowed=False,money_authority=False,
        parity=dict(selection_equal=True,ranking_equal=True,selection=right,ranking=ranks,
                    selection_sha256=digest(right),ranking_sha256=digest(ranks)))
    out['parity']['numeric_comparison']=dict(NUMERIC_PARITY)
    out['source_view_proof']=view_proof(out)
    out['data_sha256']=digest(out);verify_delivery(out);return out


def verify_delivery(x):
    if x.get('data_sha256')!=digest({k:v for k,v in x.items() if k!='data_sha256'}):raise ValueError('DATA_HASH')
    universe=list(ops.required_symbols())
    if (x['schema']!=SCHEMA or x['provider']!='YAHOO_HOURLY' or x['universe']!=universe
        or set(x['history'])!=set(universe) or x['universe_sha256']!=digest(universe)
        or x['adjustment_policy']!=POLICY or x['orders_allowed'] is not False
        or x['money_authority'] is not False):raise ValueError('CONTROL_SOURCE_OR_UNIVERSE')
    if x.get('source_view_proof')!=view_proof(x):raise ValueError('SOURCE_VIEW_PROOF')
    if (x['source_started_ms']!=x['source_capture']['started_ms']
        or x['source_available_ms']!=x['source_capture']['completed_ms']
        or not 0<x['source_session_close_ms']<=x['source_started_ms']<=x['source_available_ms']
        or x['raw_source_files']!=x['source_capture']['files']):raise ValueError('SOURCE_CLOCK_OR_CAPTURE_CONFLICT')
    n=x['coverage']['exported_sessions']
    if type(n) is not int or n<200:raise ValueError('READER_WARMUP')
    expected=[r['session'] for r in x['calendar'] if r['session']<=x['session_date']][-n:]
    if type(n) is not int or n<200 or len(expected)!=n:raise ValueError('READER_WARMUP')
    for rows in x['history'].values():
        if [r['session'] for r in rows]!=expected:raise ValueError('READER_SESSION_COVERAGE')
        if any(type(r.get('volume')) not in (int,float) or not math.isfinite(r['volume']) or r['volume']<0 for r in rows):
            raise ValueError('READER_VOLUME')
    for s,c in x['coverage']['by_symbol'].items():
        if (s not in universe or any(d in expected[-200:] or d not in expected for d in c['incomplete_older_sessions'])
            or c['fully_checked_sessions']!=n-len(c['incomplete_older_sessions'])):raise ValueError('READER_CORE200_COVERAGE')
    if set(x['coverage']['by_symbol'])!=set(universe) or x['coverage']['core200_complete'] is not True:
        raise ValueError('READER_CORE200_COVERAGE')
    if not 0<x['source_session_close_ms']<=x['source_available_ms']:raise ValueError('SOURCE_AVAILABILITY')
    h=load_history(x['history']);s=selection(h,x['session_date'],x['entry_session']);r=ranking(h)
    if (not equivalent(s,x['parity']['selection']) or not equivalent(r,x['parity']['ranking'])
        or x['parity']['selection_equal'] is not True or x['parity']['ranking_equal'] is not True):
        raise ValueError('READER_SELECTION_PARITY')
    if (x['parity'].get('numeric_comparison')!=NUMERIC_PARITY
        or digest(x['parity']['selection'])!=x['parity']['selection_sha256']
        or digest(x['parity']['ranking'])!=x['parity']['ranking_sha256']):
        raise ValueError('READER_PARITY_HASH')
    return x


def diagnostic(x):
    verify_delivery(x);history=load_history(x['history']);ranks=x['parity']['ranking'];metrics={}
    def trace(frame,event,arg):
        if event=='return' and frame.f_code is frozen._v38_candidate.__code__:
            local=frame.f_locals
            metrics[local['symbol']]={k:v for k,v in local.items() if k in
                ('close','sma20','sma28','momentum20','momentum28','pullback','atr','volatility20')}
    if sys.getprofile() is not None:raise ValueError('DIAGNOSTIC_TRACE_ALREADY_ACTIVE')
    sys.setprofile(trace)
    try:candidates={s:frozen._v38_candidate(s,b) for s,b in history.items() if s!='SPY'}
    finally:sys.setprofile(None)
    picks=x['parity']['selection'];selected={p['symbol'] for p in picks['picks']};stocks=[]
    for i,row in enumerate(ranks,1):
        s=row['symbol'];m=metrics.get(s,{});reasons=[];candidate=candidates[s]
        if i>18:reasons.append('OUTSIDE_FROZEN_HEALTH_TOP18')
        if candidate is None:
            if len(history[s])<61:reasons.append('INSUFFICIENT_CANDIDATE_HISTORY')
            elif not math.isfinite(m.get('atr',math.nan)) or m['atr']<=0:reasons.append('INVALID_ATR20')
            else:
                if m['close']<m['sma28']:reasons.append('BELOW_SMA28')
                if m['momentum28']<=.05:reasons.append('MOMENTUM28_NOT_ABOVE_5PCT')
                if not -.12<=m['pullback']<=-.015:reasons.append('PULLBACK_OUTSIDE_MINUS12_TO_MINUS1_5PCT')
        elif s not in selected:
            if not picks['gate_ok']:reasons.append('PORTFOLIO_SPY200_CASH_GATE')
            else:
                if sum(SECTOR_MAP.get(z,'unknown')==SECTOR_MAP.get(s,'unknown') for z in selected)>=2:
                    reasons.append('FINAL_SET_SECTOR_CAP2')
                if any(s in g and set(g)&selected for g in _frozen_clusters()):reasons.append('FINAL_SET_CLUSTER_CAP1')
                if any((frozen._correlation(history[s],history[z],60) or 0)>=.75 for z in selected):
                    reasons.append('FINAL_SET_CORRELATION_AT_LEAST_075')
                if len(selected)>=4:reasons.append('FINAL_SET_MAX4_RANK_OR_CORRELATION_PENALTY')
        reasons=reasons or (['SELECTED_FROZEN_SELECTOR'] if s in selected else ['FROZEN_SELECTOR_NOT_SELECTED'])
        stocks.append(dict(row,health_rank=i,candidate_score=candidate.score if candidate else None,
            candidate_pass=candidate is not None,selected=s in selected,metrics=m,reasons=reasons))
    closes=[b.close for b in history['SPY']];sma200=sum(closes[-200:])/200
    return dict(schema='ALPACA_SAME_SNAPSHOT_DIAGNOSTIC_V1',session_date=x['session_date'],
        source_available_ms=x['source_available_ms'],data_sha256=x['data_sha256'],
        universe_sha256=x['universe_sha256'],stocks=stocks,
        hypothetical_monthly=dict(picks,hypothetical_out_of_schedule=True),
        hypothetical_weekly=dict(picks,common_monthly58_universe=True,blocked_symbols=[],
            existing_positions_not_assumed=True,max_new_entries_per_session=1,
            hypothetical_first_new_symbol=picks['picks'][0]['symbol'] if picks['picks'] else None,
            financial_go=False,scope='COMMON_INPUT_SELECTOR_ONLY_NOT_FULL_PORTFOLIO_SIMULATION'),
        monthly_calendar_due=x['session_date'][:7]!=x['entry_session'][:7],
        spy_gate=dict(close=closes[-1],sma200=sma200,gate_ok=picks['gate_ok'],
            sma50_observation_only=sum(closes[-50:])/50,extra_regime_veto='NONE_IN_FROZEN_MONTHLY'),
        account_cash_gate='UNKNOWN_NOT_READ_DATA_ONLY',orders_allowed=False,money_authority=False)


def markdown(d):
    lines=['# Alpaca DATA_ONLY — закрытие '+d['session_date'],'',
        'Один Monthly58 snapshot для обеих диагностических версий. Покупки не разрешены.',
        'Source available ms: '+str(d['source_available_ms'])+'. Account cash: UNKNOWN (не читался).',
        'Monthly calendar due: '+str(d['monthly_calendar_due'])+'. SPY200 gate: '+str(d['spy_gate']['gate_ok'])+'.',
        'Выбраны: '+(', '.join(p['symbol'] for p in d['hypothetical_monthly']['picks']) or 'CASH')+'.',
        'Reasons FINAL_SET описывают ограничения относительно конечного набора; это не новый отбор.',
        '', '| Health rank | Symbol | Health score | Candidate score | Selected | Reasons |',
        '|---:|---|---:|---:|---|---|']
    for r in d['stocks']:
        fmt=lambda v:'—' if v is None else format(v,'.7f')
        lines.append(f"| {r['health_rank']} | {r['symbol']} | {fmt(r['health_score'])} | {fmt(r['candidate_score'])} | {r['selected']} | {', '.join(r['reasons'])} |")
    return '\n'.join(lines)+'\n'


def put(path,raw):
    if path.exists():
        if stable_bytes(path)!=raw:raise ValueError('IMMUTABLE_DELIVERY_CONFLICT')
    else:publish_once(path,raw)


def publish_delivery(root,x):
    verify_delivery(x);root=ops.safe_path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    day=x['session_date'];date.fromisoformat(day);d=diagnostic(x)
    files={day+'.json':canonical(x),day+'.diagnostic.json':canonical(d),day+'.diagnostic.md':markdown(d).encode()}
    seal=dict(schema='ALPACA_MONTHLY58_DELIVERY_SEAL_V1',session_date=day,
        files={n:ops.hashlib.sha256(raw).hexdigest() for n,raw in files.items()},
        universe_sha256=x['universe_sha256'],data_sha256=x['data_sha256'],orders_allowed=False)
    path=root/(day+'.delivery.json');already=path.exists()
    for n,raw in files.items():put(root/n,raw)
    put(path,canonical(seal));verify_files(root,day)
    return dict(status='MONTHLY58_DATA_ONLY_DELIVERED',session_date=day,already_published=already,seal=seal,
        broker_requests=0,broker_writes=0,orders_allowed=False)


def verify_files(root,day):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('SESSION_DATE')
    date.fromisoformat(day);root=ops.safe_path(root);seal=json.loads(stable_bytes(root/(day+'.delivery.json')))
    expected={day+s for s in ('.json','.diagnostic.json','.diagnostic.md')}
    if set(seal['files'])!=expected or seal['session_date']!=day or seal['orders_allowed'] is not False:
        raise ValueError('DELIVERY_SEAL_SCOPE')
    for n,pin in seal['files'].items():
        if ops.sha(root/n)!=pin:raise ValueError('DELIVERY_FILE_HASH')
    x=verify_delivery(json.loads(stable_bytes(root/(day+'.json'))))
    if (x['session_date']!=day or x['data_sha256']!=seal['data_sha256']
        or x['universe_sha256']!=seal['universe_sha256']):raise ValueError('DELIVERY_DATA_IDENTITY')
    if not equivalent(json.loads(stable_bytes(root/(day+'.diagnostic.json'))),diagnostic(x)):
        raise ValueError('DIAGNOSTIC_DERIVATION')
    return seal
