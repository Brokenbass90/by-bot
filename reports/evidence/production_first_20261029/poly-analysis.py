from pathlib import Path
from datetime import datetime,timezone
import json,collections,csv,hashlib
root=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/poly_execution_20261029');inp=root/'inputs';probe=root/'public-probe';manifest=json.loads((root/'input-manifest.json').read_bytes())
for name,m in manifest.items():assert hashlib.sha256((inp/name).read_bytes()).hexdigest()==m['sha256']
def rows(path):
 raw=path.read_bytes();end=raw.rfind(b'\n')+1;return [json.loads(l) for l in raw[:end].splitlines()]
books=rows(inp/'poly_monitor/knigi.jsonl');events=rows(inp/'poly_espn/matchi.jsonl');group=collections.defaultdict(list)
for row in books:group[row['id']].append(row)
first={}
for row in events:first.setdefault(row.get('id'),row)
matched=json.loads((probe/'matches.json').read_bytes());summaries=[]
parse=lambda x:datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()
for item in matched:
 e=item['event'];m=item['market'];mid=m['id'];g=json.loads((probe/('gamma-'+mid+'.raw')).read_bytes());c=json.loads((probe/('clob-market-'+mid+'.raw')).read_bytes());breq=json.loads((probe/('book-'+mid+'.receipt.json')).read_bytes());fee=json.loads((probe/('fee-'+mid+'.raw')).read_bytes())
 assert mid==g['id'] and e['completed'] is True and abs(parse(g['gameStartTime'])-parse(e['start']))<1
 winner=next(row[0] for row in e['komandy'] if row[3] is True);outcomes=json.loads(g['outcomes']);idx=[i for i,name in enumerate(outcomes) if winner.lower().endswith(name.lower())];assert len(idx)==1
 assert json.loads(g['clobTokenIds'])[0]==m['token']
 history=sorted(group[mid],key=lambda v:v['t']);before=[r for r in history if r['t']<=e['t']];after=[r for r in history if r['t']>=e['t']]
 cold=first[e['id']].get('completed') is True
 reasons=['HISTORICAL_REQUEST_RECEIVE_CLOCKS_MISSING','HISTORICAL_MARKET_STATE_AT_SIGNAL_UNKNOWN','FULL_DEPTH_AND_FEE_AT_SIGNAL_UNKNOWN']
 if cold:reasons.append('LEFT_CENSORED_FINAL_AT_COLLECTOR_START')
 if not after:reasons.append('NO_SAVED_BOOK_AFTER_FACT_RECEIPT')
 if g.get('closed') or c.get('closed') or not c.get('accepting_orders'):reasons.append('CURRENT_MARKET_NOT_ACCEPTING_ORDERS')
 if breq['http_status']!=200:reasons.append('CURRENT_BOOK_UNAVAILABLE')
 if idx[0]!=0:reasons.append('WINNER_TOKEN_BOOK_NOT_RECORDED')
 last=before[-1] if before else None
 summaries.append(dict(espn_event_id=e['id'],market_id=mid,question=g['question'],winner=winner,event_start=e['start'],first_final_observed_s=e['t'],final_transition_observed=not cold,last_saved_book_s=last['t'] if last else None,last_saved_book_age_s=e['t']-last['t'] if last else None,saved_books=len(history),saved_books_after_fact=len(after),current_gamma_closed=g.get('closed'),current_clob_closed=c.get('closed'),current_accepting_orders=c.get('accepting_orders'),current_book_http_status=breq['http_status'],venue_seconds_delay=c.get('seconds_delay'),gamma_fee_type=g.get('feeType'),raw_fee_base=fee.get('base_fee'),net_pnl_usd=None,net_pnl_status='NOT_ESTIMABLE_NO_PROVEN_EXECUTABLE_ENTRY',executable_opportunity_proven=False,rejection_reasons=reasons))
ws=json.loads((probe/'sports-ws.json').read_bytes());msgs=[]
for record in ws['messages']:
 try:x=json.loads(record['raw'])
 except Exception:continue
 if isinstance(x,dict):msgs.append(x)
result=dict(schema='POLY_EXECUTABLE_WINDOW_OBSERVATION_V1',status='NO_EXECUTABLE_OPPORTUNITY_PROVEN_NOT_STRUCTURAL_KILL',historical_book_rows=len(books),espn_rows=len(events),espn_unique_events=len(first),espn_completed_events=sum(v.get('completed') is True for v in first.values()),observed_final_transitions=sum(first[e['id']].get('completed') is not True and e.get('completed') is True for e in events if e.get('id')),matched_current_markets=len(summaries),unmatched_completed_events=sum(v.get('completed') is True for v in first.values())-len(summaries),current_not_accepting=sum(not v['current_accepting_orders'] for v in summaries),current_book_404=sum(v['current_book_http_status']==404 for v in summaries),historical_after_fact_books=sum(v['saved_books_after_fact'] for v in summaries),source_websocket=dict(connected=ws['connected_ms'] is not None,error=ws['error'],capture_seconds=45,messages=len(ws['messages']),completed_messages=sum(v.get('ended') is True for v in msgs)),actual_requests=len(json.loads((probe/'requests.json').read_bytes())),rows=summaries,orders_sent=0,financial_authority=False,positive_net_proven=False,structural_mechanism_fail_proven=False,coverage_warning='13 matched completed games left-censored; 45s live venue sample had no final; historical execution clocks/depth missing')
assert result['matched_current_markets']==13 and result['current_not_accepting']==13 and result['historical_after_fact_books']==0 and result['current_book_404']==13
(root/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
fields=['market_id','question','event_start','first_final_observed_s','last_saved_book_s','last_saved_book_age_s','saved_books_after_fact','current_accepting_orders','current_book_http_status','venue_seconds_delay','gamma_fee_type','raw_fee_base','net_pnl_status']
with (root/'observations.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:v[k] for k in fields} for v in summaries)
print(json.dumps({k:result[k] for k in ('status','historical_book_rows','espn_rows','espn_completed_events','observed_final_transitions','matched_current_markets','current_not_accepting','current_book_404','historical_after_fact_books','source_websocket','positive_net_proven')},ensure_ascii=False))
