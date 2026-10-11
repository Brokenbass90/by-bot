"""Offline projection of dated Sunday sources; no network, orders or judge.

Writes new receipts exclusively. Does not mutate data, policies, authority,
sealed evidence or the prepared ranking; private raw sources remain local.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.materialize_bybit_research_archive import _sha256
from research_lab.alpaca_dynamic_v1 import canonical, digest

PRIVATE = ROOT/'.private/alpaca_monday_20261011'
OUT = Path(__file__).parent
consumed = {}

def read(path):
    p = ROOT/path
    raw = p.read_bytes()
    consumed[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)

def write(name, value):
    raw = canonical(value)
    with (OUT/name).open('xb') as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()

now = time.time_ns()//1_000_000
sources = read(Path('.private/alpaca_monday_20261011/source_preparation_receipt.json'))
ranking = read(Path('.private/alpaca_monday_20261011/ranking_draft.json'))
candidate = read(Path('.private/alpaca_monday_20261011/candidate_source.json'))['response']
broker = read(Path('.private/alpaca_monday_20261011/broker_source.json'))['response']
asset = json.loads(candidate['asset']['raw'])
assert hashlib.sha256(candidate['asset']['raw'].encode()).hexdigest()==candidate['asset']['sha256']
assert all(asset[k]==v for k,v in {'symbol':'NET','status':'active','tradable':True,'fractionable':True}.items())
assert ranking['status']=='PRECOMPUTED_NOT_SEALED' and ranking['money_authority'] is False
assert sources['first_pick']=='NET' and sources['first_pick_conflicts_with_paper_legacy'] is False
assert ranking['ranking']['signal_session']=='2026-10-09' and ranking['ranking']['window_ms']==1791811800000
assert consumed['.private/alpaca_monday_20261011/ranking_draft.json']==sources['ranking_draft_sha256']
account = json.loads(broker['live_broker']['account']['raw'])
paper_account = json.loads(broker['paper_broker']['account']['raw'])
assert account['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6' and broker['live_halt']['halted'] is True
assert json.loads(broker['live_broker']['positions']['raw'])==json.loads(broker['live_broker']['orders']['raw'])==[]
assert account['pending_reg_taf_fees']==account['accrued_fees']=='0'
assert not any(v['mismatches'] for v in broker['source_manifests'].values())
assert len(broker['book']['intents'])==len(broker['book']['retirements'])==1 and broker['book']['attempts']==[]
assert broker['paper']['intents']==[] and json.loads(broker['paper_broker']['orders']['raw'])==[]
assert 'NET' not in broker['legacy_exclusions']['payload']
protocol = read(Path('reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json'))
parent_protocol_pin = consumed['reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json']
assert parent_protocol_pin=='800ac28c805fec1ed01927edc63bae1696f66eff368a6ebe6ec5281c1d517a2c'
projection = json.loads(canonical(protocol))
projection.update(schema='ALPACA_PROTOCOL_SOURCE_PROJECTION_V1', status='PROPOSED_NOT_RUNNER_BOUND',
    parent_contract_schema=protocol['schema'], parent_contract_status=protocol['status'])
projection['fractional_protocol']['requires_fresh_asset']={'symbol':'NET','status':'active','tradable':True,'fractionable':True}
projection.update(captured_utc=datetime.fromtimestamp(now/1000,timezone.utc).isoformat(),
    projection_status='SOURCE_ELIGIBILITY_ONLY_NOT_RUNNER_BOUND',
    parent_protocol_sha256=parent_protocol_pin,
    asset_source_sha256=candidate['asset']['sha256'],
    current_window='Oct12 candidate preparation only; no PAPER order or runner authority',
    review='Sunday independent source review required; original Oct8 review applies to retained global protocol only',
    next_gate='Bind reviewed NET isolation/session/static sources; fresh broker eligibility and actual PAPER acceptance at opening')
projection_sha = write('net_protocol_projection.json',projection)
write('monday_ranking_draft.json',ranking)
alpaca = {'schema':'ALPACA_SUNDAY_PREOPEN_SOURCE_RECEIPT_V1','status':'MONDAY_RANKING_SOURCE_READY_NOT_DISPATCHABLE',
    'observed_ms':broker['observed_ms'],'prepared_ms':sources['prepared_ms'],'signal_session':'2026-10-09','entry_session':'2026-10-12',
    'ranking_draft_sha256':sources['ranking_draft_sha256'],'ranking_sealed':False,
    'candidate':ranking['ranking']['picks'][0], 'gates':sources['gates']['NET'],
    'inherited_reentry_excluded':sources['inherited_reentry_excluded'],
    'source_pins':sources['source_pins'],'preparation_script_sha256':hashlib.sha256((PRIVATE/'prepare_ranking.py').read_bytes()).hexdigest(),
    'closed_universe_count':59,'earnings_stock_count':57,'selector_repeat_byte_parity':True,
    'dated_live':{'halted':True,'positions':0,'open_orders':0,'cash':account['cash'],'non_marginable_buying_power':account['non_marginable_buying_power'],
                  'pending_reg_taf_fees':account['pending_reg_taf_fees'],'accrued_fees':account['accrued_fees']},
    'dated_paper':{'account_id':paper_account['id'],'legacy_symbols':sources['paper_legacy_symbols'],'open_orders':0,'dispatch_intents':0},
    'source_book':{'history_intents':1,'retirements':1,'attempts':0,'original_tables_sha256':broker['book']['original_table_sha256']},
    'net_asset':{'source_sha256':candidate['asset']['sha256'],'received_ms':candidate['asset']['received_ms'],
                 'status':'active','tradable':True,'fractionable':True,'native_stop_accepted':False},
    'protocol_projection_sha256':projection_sha,'source_manifests':broker['source_manifests'],
    'root_crontab_sha256':broker['root_crontab']['sha256'],
    'writer_source_sha256':{k:v['sha256'] for k,v in broker['writer_sources'].items()},
    'services':broker['services'],'shared_lock_available':broker['shared_lock_available'],
    'legacy_exclusion_sha256':broker['legacy_exclusions']['sha256'],'net_legacy_exclusion_applied':False,
    'cap_usd':'487.42','gross':'0.70','max_positions':4,'max_new_entries_per_session':1,
    'open_ms':1791811800000,'static_deadline_ms':1791810900000,'ready_deadline_ms':1791811740000,'dispatch_deadline_ms':1791812100000,
    'remaining_static_actions':['CAS append NET exclusion with all-writer/original-lock review, preserve every existing exclusion',
        'stage exact reviewed retirement-aware controller/dependency closure and NET static template in isolated app; existing services unchanged',
        'bind fresh known-old finality, terminal exits and exact Monday PAPER-only session authorization; no inherited True flags',
        'finish static preparation before T-15 and READY before T-1; do not code/read docs in opening window'],
    'fresh_opening_checks':['account/cash/pending liabilities','survivors/open orders/ownership','NET asset eligibility','actual raw quote timestamp and IEX feed limitation','CAT quantity ceiling reserve reduces funding before reservation'],
    'first_overnight_rearm_session':'2026-10-13','paper_lifecycle_pass':False,'runner_armed':False,'orders_allowed':False,'money_authority':False,
    'broker_writes':0,'remote_writes':0,'live_go_required':True}
write('alpaca_monday_source.json',alpaca)
funding = []
for directory in ['bybit_public_archive_2023','bybit_public_preholdout_2023_20250930']:
    for symbol in ['BTCUSDT','ETHUSDT']:
        path = Path('research_lab/data')/directory/'funding'/(symbol+'.json')
        x=read(path);rows=x['records'];times=[int(r['funding_time_ms']) for r in rows]
        assert x['payload_sha256']==_sha256(rows)
        assert len(times)==len(set(times)) and all(b-a==28800000 for a,b in zip(times,times[1:]))
        assert all(r['symbol']==symbol and r['venue']=='bybit' for r in rows)
        assert all(t<=x['as_of_ms'] for t in times) and int(x['instrument']['fundingInterval'])==480
        funding.append({'path':str(path),'file_sha256':consumed[str(path)],'symbol':symbol,'records':len(rows),
            'payload_sha256':x['payload_sha256'],'first_settlement_ms':times[0],'last_settlement_ms':times[-1],
            'as_of_ms':x['as_of_ms'],'unique_contiguous_8h_grid':True,'payload_hash_verified':True})
write('crypto_source_delta.json',{'schema':'CRYPTO_SUNDAY_SOURCE_DELTA_V1','observed_ms':now,
    'status':'FUNDING_ARCHIVE_INTEGRITY_PASS_RESEARCH_CONTRACT_BLOCKED',
    'funding_sources':funding,'rate_return_or_outcome_analysis':False,
    'funding_treatment_approved':False,'independent_holdout_certified':False,'raw_h1_pit_lineage_proven':False,
    'funding_source_population':'historical Bybit public archive, not selected-account truth or newly captured Oct11 rates',
    'holding_window_cost_coverage':'bar-span source only; complete future-held settlement coverage not certified',
    'breakout_exact_path_query_sha256':consumed['.private/alpaca_monday_20261011/candidate_source.json'],
    'breakout_exact_vps_paths':candidate['m5_paths'],'broader_vps_archive_search_performed':False,
    'remaining_claude_inputs':['explicit versioned funding treatment','raw M5/provider/assembly/PIT lineage','consumed-period ledger and admissible validation or frozen forward'],
    'judge_run':False,'strategy_or_context_changed':False,'orders_allowed':False,'broker_writes':0})
terminal_path = Path('.private/ets2m_verdict_20261010/terminal.json')
terminal=read(terminal_path);schedule=read(Path('.private/ets2m_verdict_20261010/schedule.json'))
assert terminal['sha256']==digest(terminal['result'])
assert terminal['result']['status']=='BLOCKED_DATA' and terminal['result']['reason']=='COHORT_PIN_MISMATCH'
assert terminal['result']['observed_ms']>=schedule['due_ms'] and terminal['result']['manifest_sha256']==schedule['manifest_sha256']
blocker=read(Path('reports/ETS2M_PRE_DUE_DATA_BLOCKER_2026_10_06.json'))
write('ets2m_terminal.json',{'schema':'ETS2M_ORIGINAL_DEADLINE_TERMINAL_INTAKE_V1',
    'result':terminal['result'],'canonical_result_sha256':terminal['sha256'],'raw_terminal_file_sha256':consumed[str(terminal_path)],
    'schedule':schedule,'terminal_result_observed_at_or_after_original_due':True,
    'deadline_extended':False,'rerun_performed':False,'outcomes_read_this_cycle':False,'judge_run_this_cycle':False,
    'pre_due_blocker':blocker,'next_action':'Retain original terminal BLOCKED_DATA; no repin/new cohort or rerun. Research owner may locate original archive under separate scope.'})
for path,pin in consumed.items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==pin,'SOURCE_CHANGED:'+path
write('source_verification.json',{'schema':'SUNDAY_SOURCE_VERIFICATION_V1','observed_ms':now,
    'status':'CONSUMED_SOURCE_HASHES_AND_METADATA_PASS','source_pins':consumed,
    'funding_rates_analyzed':False,'new_research_or_judge':False,'product_code_changed':False,
    'selector_repeat_byte_parity':True,'full_suite_run':False,'existing_full_suite_status':'NOT_GREEN_NOT_RETESTED',
    'foreign_allowlist_sha256':hashlib.sha256((ROOT/'configs/allowlist_change_log.json').read_bytes()).hexdigest(),
    'workers':[{'task':'ets2m_sunday_terminal_intake','thread_id':'01a1297b-1913-71c1-b3f4-8b46309853c7','model':'gpt-5.6-luna','effort':'medium','runtime_verified':True},
               {'task':'crypto_sunday_source_inventory','thread_id':'01a1297c-2cc2-7f91-aa14-31ce51844cb7','model':'gpt-5.6-luna','effort':'medium','runtime_verified':True}]})
print(json.dumps({'status':'SOURCE_RECEIPTS_WRITTEN','candidate':'NET','funding_files':len(funding),
                  'ets2m':'BLOCKED_DATA_COHORT_PIN_MISMATCH','orders':0,'judges':0}))
