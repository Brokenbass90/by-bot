"""Validate captured process/receipt/source truth without VPS or broker writes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
PUBLIC=Path(__file__).parent
PRIVATE=ROOT/'.private/alpaca_net_arm_20261011'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
capture_path=Path(sys.argv[1]);capture=json.loads(capture_path.read_bytes());r=capture['response']
before=json.loads((PRIVATE/'prearm_source.json').read_bytes())['response']
manifest=json.loads((PUBLIC/'install_manifest.json').read_bytes())
review=json.loads((PUBLIC/'critical_review.json').read_bytes());s=r['session'];packet=s['packet']
assert review['status']=='APPROVED_FOR_PAPER_INSTALL_ONLY' and review['remaining_material_findings']==0
assert review['proposal_sha256']==manifest['proposal_sha256']==sha((PRIVATE/'install_proposal.json').read_bytes())
assert s['packet_sha256']==manifest['session_files']['packet.json']
assert not s['static_mismatches'] and not s['manifest']['mismatches']
assert s['manifest']['files']==81
assert s['manifest']['sha256']==packet['expected_sha256']['manifest']
assert s['review_sha256']==sha((PUBLIC/'critical_review.json').read_bytes())
assert packet['attempt_authorization']=={'scope':'PAPER_ONLY','session':'2026-10-12','owner_approved':True}
assert packet['symbol']=='NET' and packet['open_ms']==1791811800000
runtime=s['runtime'];prep=runtime['runtime/opening/prepared.json']['payload'];ready=runtime['runtime/opening/ready.json']['payload']
assert prep['sha256']==digest(prep['value']) and ready['sha256']==digest(ready['value'])
assert prep['value']['status']=='STATIC_PREPARED' and ready['value']['status']=='READY_TO_DISPATCH'
assert prep['value']['prepared_ms']<=1791810900000 and ready['value']['ready_ms']<=1791811740000
assert ready['value']['prepared_sha256']==digest(prep['value'])
assert prep['value']['static_sha256']==packet['expected_sha256']
for n in ['runtime/opening/terminal.json','runtime/opening/reserve.json','runtime/opening/invoking_adapter.json','runtime/guard/latest.json','runtime/guard/terminal.json']:
 assert runtime[n] is None,'UNEXPECTED_PREOPEN_AUTHORITY:'+n
for n,u in s['units'].items():
 assert u['ActiveState']=='active' and u['SubState']=='running' and u['process_alive'] is True
 assert u['NRestarts']=='0' and u['Restart']=='no' and u['UnitFileState'] in ['static','disabled']
 assert u['cwd']=='/opt/bybot-research/alpaca-net-paper-session-20261012/app'
 assert '--packet' in u['args'] and '/opt/bybot-research/alpaca-net-paper-session-20261012/session/packet.json' in u['args']
assert {p['pid'] for p in r['matching_processes']}=={int(u['MainPID']) for u in s['units'].values()}
assert r['services']==before['services']
assert r['live_runtime_pins']==before['live_runtime_pins'] and r['profile_source_pins']==before['profile_source_pins']
assert r['root_crontab']['sha256']==before['root_crontab']['sha256']
assert r['root_cron_file_sha256']==before['cron_inventory']['/var/spool/cron/crontabs']['root']['sha256']
assert r['writer_sources']==before['writer_sources']
assert r['source_manifests']==before['source_manifests']
assert r['book']['original_table_sha256']==before['book']['original_table_sha256']
assert len(r['book']['intents'])==len(r['book']['retirements'])==1 and not r['book']['attempts']
assert not r['paper']['intents'] and r['live_halt']['halted'] is True
assert r['legacy_exclusions']['payload']=={**before['legacy_exclusions']['payload'],'NET':'ALPACA_DYNAMIC_V1_PAPER_OCT12_OWNED_OR_PENDING'}
live={k:json.loads(v['raw']) for k,v in r['live_broker'].items()}
paper={k:json.loads(v['raw']) for k,v in r['paper_broker'].items() if 'raw' in v}
assert live['account']['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6' and not live['positions'] and not live['orders']
assert live['account']['pending_reg_taf_fees']==live['account']['accrued_fees']=='0'
assert paper['account']['id']==packet['paper_account'] and not paper['orders']
assert {p['symbol'] for p in paper['positions']}=={'ABNB','ABT','AMZN','MA','SCHW'}
completed=s['logs']['targeted_tests_completed.txt'];assert '96 passed' in completed['tail'] and 'failed' not in completed['tail']
local=(PUBLIC/'local_targeted_tests.txt').read_bytes();assert b'138 passed' in local
result={'schema':'ALPACA_NET_NEXT_SESSION_ARMING_RECEIPT_V1','status':'ALPACA_NEXT_SESSION_ARMED',
 'observed_ms':r['observed_ms'],'source_capture_sha256':sha(capture_path.read_bytes()),
 'proposal_sha256':manifest['proposal_sha256'],'packet_sha256':s['packet_sha256'],
 'manifest_sha256':s['manifest']['sha256'],'review_sha256':s['review_sha256'],'app_files':81,
 'prepared_ms':prep['value']['prepared_ms'],'ready_ms':ready['value']['ready_ms'],
 'target_open_ms':1791811800000,'window_end_ms':1791812100000,
 'guard_unwind_not_before_ms':1791898500000,'guard_hard_end_ms':1791900000000,
 'units':{n:{k:v for k,v in u.items() if k in ['MainPID','NRestarts','ActiveState','SubState','Restart','UnitFileState','process_alive']} for n,u in s['units'].items()},
 'production_services_unchanged':r['services'],'old_source_maps_unchanged':True,
 'cron_and_live_profiles_unchanged':True,'original_tables_unchanged_sha256':r['book']['original_table_sha256'],
 'original_intents':1,'retirements':1,'new_attempts':0,'paper_store_intents':0,
 'legacy_NET_exclusion_sha256':r['legacy_exclusions']['sha256'],'paper_legacy_symbols':sorted(p['symbol'] for p in paper['positions']),
 'live_flat':True,'live_halt':True,'live_cash_usd':live['account']['cash'],
 'live_nonmarginable_usd':live['account']['non_marginable_buying_power'],'pending_fees_usd':'0','accrued_fees_usd':'0',
 'local_targeted_tests':138,'local_test_output_sha256':sha(local),'vps_targeted_tests':96,'vps_test_output_sha256':completed['sha256'],
 'retained_failed_stage_log_sha256':s['logs']['targeted_tests.txt']['sha256'],
 'sunday_broker_writes':0,'paper_execution_pass':False,'live_go':False,
 'remaining_gates':['Monday fresh inputs and one actual PAPER entry/full stop/readback',
 'owned restart/recovery/exit and terminal costs/finality','actual TuesdayOct13 DAY rearm if held overnight','exact LIVE dossier and separate owner GO']}
out=PUBLIC/'arming_receipt.json';assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'observed_ms':r['observed_ms'],'units':result['units'],'local_tests':138,'vps_tests':96,'live_halt':True,'paper_execution_pass':False}))
