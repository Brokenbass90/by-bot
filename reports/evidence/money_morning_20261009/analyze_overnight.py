#!/usr/bin/env python3
"""Pinned observation analysis and existing ATT1 receipt replay, never a strategy judge."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = Path(sys.argv[2]).resolve()
MANIFEST = json.loads((SOURCE_ROOT/'deployed_public_manifest.json').read_text())
for relative, pin in MANIFEST.items():
    assert hashlib.sha256((SOURCE_ROOT/relative).read_bytes()).hexdigest()==pin
sys.path.insert(0, str(SOURCE_ROOT))
from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_session import implementation_hash
from research_lab.att1_lifecycle_coordinator import replay_lifecycle
from scripts.run_att1_lifecycle_zero_risk import _canonical, _normalized_receipt


def analyze(path):
    raw = path.read_bytes()
    archive = json.loads(raw)
    response = archive['response']
    a = response['reports/evidence/money_morning_20261008/alpaca_broker_read_only.py']
    q = response['reports/evidence/money_morning_20261008/alpaca_quote_lineage_read_only.py']
    p = response['extra_public_observation']
    h = json.loads(p['heartbeat_after']['raw'])
    assert p['heartbeat_before']['sha256'] == p['heartbeat_after']['sha256']
    profile = build_profile(SOURCE_ROOT)
    assert profile['profile_sha256'] == h['profile_sha256']
    expected = {x['decision_id']: x for x in h['sessions']}
    assert len(expected) == h['session_count'] == len(p['session_members'])
    cutoff = int(datetime(2026, 10, 9, tzinfo=ZoneInfo('Asia/Nicosia')).timestamp() * 1000)
    reason_counts = Counter()
    replayed = []
    new_starts = overnight_events = 0
    start_times = []
    for name, member in p['session_members'].items():
        data = member['raw'].encode()
        assert hashlib.sha256(data).hexdigest() == member['sha256']
        assert data.endswith(b'\n')
        events = []
        tip = '0' * 64
        seen = set()
        for seq, line in enumerate(data.splitlines(), 1):
            row = json.loads(line)
            assert row['seq'] == seq and row['prev_hash'] == tip and line == _canonical(row)
            event = row['event'];eid = event['event_id']
            assert eid not in seen
            assert row['event_sha256'] == hashlib.sha256(_canonical(event)).hexdigest()
            assert row['hash'] == hashlib.sha256(_canonical({k:v for k,v in row.items() if k!='hash'})).hexdigest()
            seen.add(eid);tip = row['hash'];events.append(event)
            observed = event['intent']['submit_ms'] if event['kind']=='START' else event.get('received_ms')
            assert type(observed) is int
            overnight_events += observed >= cutoff
            if event['kind']=='RECOVERY_GAP': reason_counts[event['reason']] += 1
        header = events[0]
        assert header['kind']=='START' and header['implementation_sha256']==implementation_hash()
        assert header['profile_sha256']==profile['profile_sha256']
        assert header['event_id']=='start:'+hashlib.sha256(_canonical({k:v for k,v in header.items() if k!='event_id'})).hexdigest()
        start = header['intent']['submit_ms'];start_times.append(start);new_starts += start>=cutoff
        receipt = replay_lifecycle(profile,header['intent'],events[1:])
        normalized = _normalized_receipt(receipt)
        normalized['full_receipt_sha256'] = hashlib.sha256(_canonical(receipt)).hexdigest()
        normalized['receipt_sha256'] = hashlib.sha256(_canonical(normalized)).hexdigest()
        did = normalized['decision_id']
        assert name == did+'.jsonl' and normalized == expected[did]
        replayed.append({'decision_id':did,'symbol':normalized['symbol'],'start_ms':start,
                         'journal_sha256':member['sha256'],'records':len(events),
                         'reconstructed_receipt_sha256':normalized['receipt_sha256']})
    clean = [x for x in h['sessions'] if x['lifecycle_terminal'] and not x['incidents']
             and x['costs_complete'] and x['final_net_r'] is not None]
    live = {k:json.loads(v['raw']) for k,v in a['live'].items()}
    paper = {k:json.loads(v['raw']) for k,v in a['paper'].items()}
    account=live['account']
    assert account['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6'
    assert paper['account']['id']=='4cdbfb77-d1e0-4789-86b2-341bc886efaf'
    assert len(live['activity_source'])<100 and len(live['order_source'])<100
    assert all(not x['mismatches'] for x in a['source_manifests'].values())
    quote=q['quote_sources']['iex'];wire=json.loads(quote['raw'])['quote']
    assert hashlib.sha256(quote['raw'].encode()).hexdigest()==quote['raw_sha256']
    return {
        'schema':'OCT9_MORNING_READINESS_DELTA_V1','status':'PREOPEN_SOURCE_VERIFIED_NO_PLAN',
        'observed_ms':a['observed_ms'],'completed_ms':a['completed_ms'],
        'raw_archive_sha256':hashlib.sha256(raw).hexdigest(),
        'capture_source_pins':archive['capture_source_pins'],
        'replay_source':{'root':str(SOURCE_ROOT.relative_to(ROOT)),
            'manifest_sha256':hashlib.sha256((SOURCE_ROOT/'deployed_public_manifest.json').read_bytes()).hexdigest(),
            'files':len(MANIFEST),'implementation_sha256':implementation_hash(),
            'binding':f'all{len(MANIFEST)} archived deployment pins match; header implementation and profile match; no current money-candidate code used'},
        'overnight_window':{'timezone':'Asia/Nicosia','start_local':'2026-10-09T00:00:00+03:00',
            'start_utc_ms':cutoff,'end_observed_ms':p['observed_ms'],
            'att1_new_start_events':new_starts,'att1_new_journal_events':overnight_events},
        'alpaca':{'live_cash':account['cash'],'equity':account['equity'],
            'non_marginable_buying_power':account['non_marginable_buying_power'],
            'pending_reg_taf_fees':account['pending_reg_taf_fees'],
            'accrued_fees':account['accrued_fees'],'live_positions':len(live['positions']),
            'live_open_orders':len(live['open_orders']),'entry_halt':a['live_runtime']['entry_halt']['halted'],
            'next_open':live['clock']['next_open'],'paper_positions':len(paper['positions']),
            'paper_XOM_positions':sum(x['symbol']=='XOM' for x in paper['positions']),
            'paper_open_orders':len(paper['open_orders']),
            'paper_lifecycle_started':a['paper_lifecycle_runtime_exists'],
            'books':a['books'],'source_manifests':a['source_manifests'],
            'legacy_exclusions_sha256':a['paper_runtime']['legacy_exclusions_sha256'],
            'quote':{'feed':'IEX','raw_timestamp':wire['t'],'bid':wire['bp'],'ask':wire['ap'],
                'fresh_receive_ms':quote['receive_ms'],'usable_for_entry':False,
                'reason':'PREOPEN_STALE_RAW_TIMESTAMP_AND_ZERO_ASK','sip_http_status':q['quote_sources']['sip']['http_status']},
            'sealed_XOM_earnings':q['closed_source']['XOM_earnings'],
            'all_writer_opening_ownership':'NOT_YET_VERIFIED_EXHAUSTIVELY_AT_OPEN',
            'qty_plan':'NOT_PREPARED_NOT_DUE'},
        'att1':{'snapshot_as_of_ms':h['as_of_ms'],'sessions':len(h['sessions']),
            'gaps':sum('RECOVERY_GAP' in x['incidents'] for x in h['sessions']),
            'clean_terminals':len(clean),'clean':[{'decision_id':x['decision_id'],'symbol':x['symbol'],'final_net_r':x['final_net_r']} for x in clean],
            'held':h['open_positions'],'broker_calls':h['broker_calls'],'order_calls':h['order_calls'],
            'poll_errors':h['poll_errors'],'gap_reason_counts':dict(reason_counts),
            'latest_start_utc':datetime.fromtimestamp(max(start_times)/1000,timezone.utc).isoformat(),
            'journal_replay':'26_OF_26_EXACT_HEARTBEAT_RECEIPT_MATCH',
            'replayed_sessions':replayed,'old_entry_retirement':p['old_entry_retirement'],
            'gap_clock_caveat':'rejected-book RECOVERY_GAP exchange_ms defaults to last accepted event, not rejected raw CTS; delta is not wire age or measured REST latency',
            'new_money_gate':'UNCHANGED_2_TO_3_CLEAN_PLUS_ACTUAL_DOSSIER_AND_SEPARATE_GO'},
        'services':a['services'],'completed_probe_services':p['services'],
        'read_only':True,'broker_writes':0,'remote_writes':0,'plan_reservations':0,
        'no_new_strategy_research_or_judge':True,
        'next_action':'One XOM PAPER13:30–13:35UTC Oct9 only after fresh raw quote/account/fees/qty/gates and exhaustive shared-lock/writer checks; LIVE HALT remains',
    }


if __name__=='__main__':
    print(json.dumps(analyze(Path(sys.argv[1])),ensure_ascii=False,indent=2))
