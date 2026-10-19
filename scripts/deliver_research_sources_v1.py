#!/usr/bin/env python3
"""Explicit DATA_ONLY requests from Claude: BIL/SGOV or Polymarket availability.

No strategy run, broker-account constructor, orders, wallets or financial grants.
Polymarket mode is deliberately an availability audit, NOT the requested full
2023-2026 hourly census; unavailable history/cost vintages remain UNKNOWN.
"""
import argparse
from datetime import date,datetime,timezone
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab import research_source_delivery_v1 as d
from scripts.extend_equity_history_readonly import normalize
from scripts.materialize_alpaca_pit_daily import _load_env,_alpaca_headers,_canonical_sha


def etfs(root,end,env):
    identity=dict(schema='BIL_SGOV_SIP_REQUEST_V1',symbols=['BIL','SGOV'],start='2016-01-01',end=end,
        feed='sip',adjustments=['all','split'],asof='-')
    if (root/'delivery.json').exists():
        old=d.verify_delivery(root)
        if old['request']!=identity:raise ValueError('ETF_RESUME_IDENTITY_CONFLICT')
        return old
    a=_load_env(env);headers=_alpaca_headers(a['ALPACA_API_KEY_ID'],a['ALPACA_API_SECRET_KEY'])
    cap=d.Capture(root/'raw');calendar=cap.get('https://paper-api.alpaca.markets/v2/calendar',
        dict(start=identity['start'],end=end),headers=headers)
    if not isinstance(calendar,list) or not calendar:raise ValueError('ETF_CALENDAR_REQUIRED')
    sessions=[r['date'] for r in calendar]
    if sessions!=sorted(set(sessions)):raise ValueError('ETF_CALENDAR_ORDER')
    d.put(root/'calendar.json',d.canonical(calendar)+b'\n');qa={}
    for symbol in identity['symbols']:
        records={}
        for adj in identity['adjustments']:
            rows=d.alpaca_pages(cap.get,symbol,adj,start=identity['start'],end=end,headers=headers)
            records[adj]=normalize(rows,date.fromisoformat(identity['start']),date.fromisoformat(end))
            doc=dict(schema_id='massive_adjusted_daily_symbol_v1',authority='research_only_get_no_orders_no_risk_mutation',
                provider='Alpaca SIP',symbol=symbol,start=identity['start'],end=end,feed='sip',adjustment=adj,
                adjusted=True,asof='-',records=records[adj],payload_sha256=_canonical_sha(records[adj]),
                first_bar_ms=records[adj][0]['t'] if records[adj] else None,last_bar_ms=records[adj][-1]['t'] if records[adj] else None,
                schema_name_is_legacy_encoding_not_provider_claim=True)
            d.put(root/adj/'bars'/(symbol+'.json'),d.canonical(doc)+b'\n')
        qa[symbol]=d.bars_qa(records['all'],records['split'],sessions)
        if qa[symbol]['missing_sessions_after_first'] or not qa[symbol]['adjustment_timestamps_match']:
            raise ValueError('ETF_PAIR_OR_SESSION_COVERAGE_BLOCKED')
    return d.seal(root,dict(schema='BIL_SGOV_DATA_ONLY_DELIVERY_V1',status='DATA_ACQUIRED_QA_PASS_NOT_STRATEGY_PASS',
        request=identity,qa=qa,source_received_ms=max(r['received_ms'] for r in cap.receipts.values()),
        acquired_ms=time.time_ns()//1000000,sip_yahoo_parity_proven=False,
        monthly_strategy_changed=False,performance_or_overlay_run=False,not_risk_free_cash=True))


def polymarket(root,end,limit,history_days=14):
    identity=dict(schema='POLYMARKET_AVAILABILITY_REQUEST_V1',requested_contract='6548410',
        requested_start='2023-01-01',requested_end=end,closed_only=True,cohort_rule='FIRST_ID_ASC_PER_PLANNED_END_YEAR',
        markets_per_year=limit,fidelity_minutes=60,history_mode='EXPLICIT_14_DAY_WINDOWS',
        history_days=history_days,full_lifetime_requested=history_days==0,full_census=False)
    if (root/'delivery.json').exists():
        old=d.verify_delivery(root)
        if old['request']!=identity:raise ValueError('POLY_RESUME_IDENTITY_CONFLICT')
        return old
    cap=d.Capture(root/'raw');markets=[];seen=set();cohorts={};profiles=[];histories={};http=[]
    for year in range(2023,2027):
        start=str(year)+'-01-01';stop=min(end+'T23:59:59Z',str(year)+'-12-31T23:59:59Z')
        if start>end:continue
        rows=cap.get('https://gamma-api.polymarket.com/markets',dict(closed='true',limit=limit,order='id',
            ascending='true',end_date_min=start+'T00:00:00Z',end_date_max=stop))
        if not isinstance(rows,list):raise ValueError('GAMMA_MARKETS_SCHEMA')
        cohorts[str(year)]=dict(returned=len(rows),full_year_census=False,filter='planned_endDate, NOT actual closedTime')
        for row in rows:
            key=str(row['id'])
            if row.get('closed') is not True:raise ValueError('GAMMA_CLOSED_FILTER')
            if key in seen:continue
            seen.add(key);markets.append(row)
    d.put(root/'markets.jsonl',b''.join(d.canonical(m)+b'\n' for m in markets))
    for m in markets:
        tokens=d.array(m.get('clobTokenIds',[]))
        stamp=lambda x:int(datetime.fromisoformat(x.replace('Z','+00:00')).timestamp())
        close=stamp(m['closedTime'])
        start=min(stamp(m[k]) for k in ('createdAt','startDate') if m.get(k))
        if history_days:start=max(start,close-history_days*86400)
        for token in tokens:
            if not isinstance(token,str) or not token.isdecimal():raise ValueError('CLOB_TOKEN_IDENTITY')
            if token in histories:continue
            try:
                value=d.explicit_history(cap.get,token,start,close)
                d.price_profile(value);histories[token]=value
                d.put(root/'prices'/(token+'.json'),d.canonical(value)+b'\n')
            except d.SourceHTTP as e:http.append(dict(token=token,route='prices-history',http=e.status))
            for route in ['fee-rate','tick-size','spread']:
                try:value=cap.get('https://clob.polymarket.com/'+route,dict(token_id=token))
                except d.SourceHTTP as e:http.append(dict(token=token,route=route,http=e.status));continue
                d.put(root/'current-microstructure'/route/(token+'.json'),d.canonical(value)+b'\n')
        condition=m.get('conditionId','')
        if condition:
            try:
                value=cap.get('https://clob.polymarket.com/markets/'+condition,{})
                d.put(root/'current-resolution'/(str(m['id'])+'.json'),d.canonical(value)+b'\n')
            except d.SourceHTTP as e:http.append(dict(market_id=str(m['id']),route='clob-market',http=e.status))
        profiles.append(d.market_profile(m,histories))
    d.put(root/'qa.json',d.canonical(dict(cohorts=cohorts,markets=profiles,http_failures=http))+b'\n')
    return d.seal(root,dict(schema='POLYMARKET_DATA_ONLY_AVAILABILITY_DELIVERY_V1',
        status='PARTIAL_AVAILABILITY_AUDIT_NOT_SCREEN_READY',request=identity,markets=len(markets),
        tokens_requested=len({t for m in markets for t in d.array(m.get('clobTokenIds',[]))}),
        tokens_with_history=sum(bool(p['history']) for p in histories.values()),
        price_points=sum(len(p['history']) for p in histories.values()),
        source_received_ms=max(r['received_ms'] for r in cap.receipts.values()),acquired_ms=time.time_ns()//1000000,
        screen_ready=False,full_hourly_census=False,historical_fee_spread_vintage='UNKNOWN',
        actual_settlement_availability_time='NOT_PROVEN',pit_metadata_vintage='NOT_PROVEN',
        logical_exhaustive_groups='NOT_PROVEN',prereg_or_strategy_run=False))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',choices=['etfs','polymarket'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--end',required=True)
    p.add_argument('--alpaca-env',type=Path);p.add_argument('--markets-per-year',type=int,default=10)
    p.add_argument('--history-days',type=int,default=14,help='0 requests full known market life; positive is an explicit bounded availability window')
    p.add_argument('--allow-readonly-network',action='store_true');a=p.parse_args(argv)
    if not a.allow_readonly_network:raise ValueError('EXPLICIT_DATA_NETWORK_REQUIRED')
    end=date.fromisoformat(a.end)
    if end>=datetime.now(timezone.utc).date():raise ValueError('COMPLETED_DATES_ONLY')
    root=a.output.absolute()
    if not 1<=a.markets_per_year<=50:raise ValueError('AVAILABILITY_REQUEST_BUDGET')
    if not 0<=a.history_days<=3650:raise ValueError('HISTORY_DAYS_BUDGET')
    if a.source=='etfs' and a.alpaca_env is None:raise ValueError('EXPLICIT_EXISTING_DATA_ENV_REQUIRED')
    result=etfs(root,a.end,a.alpaca_env) if a.source=='etfs' else polymarket(root,a.end,a.markets_per_year,a.history_days)
    print(json.dumps({k:v for k,v in result.items() if k!='files'},sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
