#!/usr/bin/env python3
"""Offline, sanitized inventory of retained broker orders and declared books.

UNKNOWN is explicit: absent old selection/ATR inputs are never reconstructed from
subsequent prices or profitable outcomes. No accounting journal is rewritten.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from research_lab.alpaca_strategy_parity_v1 import initial_stop


def sha(raw):return hashlib.sha256(raw).hexdigest()


def run(capture,activation):
    raw=Path(capture).read_bytes();x=json.loads(raw)
    original=json.loads(Path(activation).read_bytes())
    select=original['latest_selection.json']
    picks={p['symbol']:p for p in select['picks']}
    # Initial native prices are independently retained in first-live-cycle.json,
    # passed in alongside the earlier activation selection receipt.
    cycle_path=Path(activation).with_name('first_live_cycle.json')
    cycle=json.loads(cycle_path.read_bytes())
    stops={r['symbol']:float(r['stop_price']) for r in cycle['today_orders'] if r['type']=='stop'}
    inventories={};classified=[]
    for label,source in x['broker'].items():
        orders=[o for p in source['pages'] for o in p['payload']]
        buys=[o for o in orders if o['side']=='buy']
        for o in buys:
            filled=float(o.get('filled_qty') or 0)>0
            category='UNKNOWN';reasons=['LEGACY_SELECTION_ATR_OR_STRATEGY_LINEAGE_UNAVAILABLE']
            details={}
            if label=='paper' and o['client_order_id']=='dyp-df4ad40de2e80402b2aa55be2f5450d9':
                category='OPERATIONAL_VALIDATION';reasons=['PLANNED_LIFECYCLE_EXIT_OCT13_NOT_STRATEGY_EXIT']
            elif label=='live' and o['client_order_id']=='dyl-42f1b8d34273c8583750e3f223207243':
                category='OFF_PROTOCOL_STALE_SIGNAL'
                reasons=['OCT09_SIGNAL_INTENDED_OCT12_USED_OCT15','DYNAMIC_WEEKLY_NOT_MONTHLY_REFERENCE',
                         'OLD_ASK_ROUNDED_DISTANCE_33_54','INTRADAY_RATCHET_NOT_DAILY_PROXY']
                details=dict(signal_session='2026-10-09',intended_entry_session='2026-10-12',
                    actual_entry_session='2026-10-15',atr20_session='2026-10-09',
                    secondary_classification='OFF_PROTOCOL_RISK_REFERENCE',
                    reference_stop_for_audit_only=initial_stop(o['filled_avg_price'],16.771206665045003),
                    original_broker_stop=277.69,current_stop_change_allowed=False,
                    oct14_selection_atr='UNKNOWN_NOT_IN_SAVED_ENTRY_SOURCE')
            elif label=='live' and o['client_order_id'].startswith('alp-entry-') and o['submitted_at'].startswith('2026-10-01'):
                p=picks[o['symbol']];ref_stop=initial_stop(o['filled_avg_price'],p['atr20'])
                category='OFF_PROTOCOL_ENTRY_SCHEDULE'
                reasons=['ENTRY_14_10UTC_VS_13_30UTC_REFERENCE_OPEN']
                if stops[o['symbol']]!=ref_stop:
                    category='OFF_PROTOCOL_RISK_REFERENCE';reasons.append('INITIAL_STOP_ROUNDING_DIFFERS_FROM_REFERENCE')
                details=dict(signal_session=select['signal_session'],intended_entry_session=select['entry_session'],
                    atr20=p['atr20'],reference_initial_stop=ref_stop,actual_initial_stop=stops[o['symbol']])
            if not filled:
                category='UNKNOWN';reasons=['NO_FILL_NOT_STRATEGY_EVIDENCE']
            classified.append(dict(account_mode=label,symbol=o['symbol'],
                broker_order_sha256=sha(o['id'].encode()),raw_order_sha256=sha(json.dumps(o,sort_keys=True).encode()),
                submitted_at=o['submitted_at'],filled_at=o.get('filled_at'),has_fill=filled,
                classification=category,reasons=reasons,eligible_as_baseline_edge_evidence=False,**details))
        dates=[o['submitted_at'] for o in orders if o.get('submitted_at')]
        inventories[label]=dict(orders=len(orders),buy_orders=len(buys),filled_buy_orders=sum(float(o.get('filled_qty') or 0)>0 for o in buys),
            earliest_submitted_at=min(dates),latest_submitted_at=max(dates),
            history_exhausted=source['history_exhausted'],pages=[dict(rows=len(p['payload']),sha256=p['sha256'],receive_ms=p['receive_ms']) for p in source['pages']])
    book_rows=[]
    for name,tables in x['databases'].items():
        for table in ('intents','intent_attempts'):
            if table not in tables:continue
            t=tables[table]
            for row in t['rows']:
                payload=json.loads(row[t['columns'].index('payload')])
                plan=payload.get('plan') or payload.get('intake',{}).get('plan') or payload
                receipt=plan.get('receipt_id') or payload.get('id')
                book_rows.append(dict(source_path=name,table=table,payload_sha256=sha(row[t['columns'].index('payload')].encode()),
                    symbol=plan.get('symbol'),session=plan.get('session'),receipt_id=receipt,
                    phase=payload.get('phase'),classification='SOURCE_BOOK_INVENTORIED',
                    evidence_note='Runtime/source-book records may represent the same broker lifecycle; never count twice.'))
    return dict(schema='ALPACA_PRIOR_INTENTS_CLASSIFICATION_V1',observed_ms=x['observed_ms'],
        raw_capture_sha256=sha(raw),classification_script_sha256=sha(Path(__file__).read_bytes()),
        original_activation_sha256=sha(Path(activation).read_bytes()),first_live_cycle_sha256=sha(cycle_path.read_bytes()),
        broker_writes=0,accounting_journal_changes=0,broker_history=inventories,
        declared_source_books=len(x['databases']),declared_source_tables_complete=all(t['complete'] for d in x['databases'].values() for t in d.values()),
        source_book_intents=book_rows,classification_counts=dict(Counter(i['classification'] for i in classified)),
        buy_order_classifications=classified,
        coverage_limitation='Complete retained broker order lists and four declared books only; old raw selection/ATR lineage unavailable remains UNKNOWN. No claim all historical trades are strategy-equivalent.')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--capture',required=True)
    ap.add_argument('--activation',required=True);ap.add_argument('--output',required=True)
    a=ap.parse_args();out=run(a.capture,a.activation)
    with Path(a.output).open('x') as f:json.dump(out,f,indent=2);f.write('\n')
    print(json.dumps(dict(counts=out['classification_counts'],declared_books=out['declared_source_books'],
                         all_retained_orders={k:v['orders'] for k,v in out['broker_history'].items()})))
