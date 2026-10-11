"""Prepare exact isolated Oct12 PAPER install proposal; no SSH or orders."""
import base64, hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[3]
BASE='/opt/bybot-research/alpaca-net-paper-session-20261012'
PUBLIC=Path(__file__).parent
PRIVATE=ROOT/'.private/alpaca_net_arm_20261011'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(path,obj):
 raw=(json.dumps(obj,indent=2,allow_nan=False)+'\n').encode()
 with path.open('xb') as f:os.chmod(path,0o600);f.write(raw)
 return sha(raw)
source_path=PRIVATE/'prearm_source.json';source=json.loads(source_path.read_bytes())['response']
live={k:json.loads(v['raw']) for k,v in source['live_broker'].items()}
paper={k:json.loads(v['raw']) for k,v in source['paper_broker'].items() if 'raw' in v}
assert live['account']['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6' and not live['positions'] and not live['orders']
assert source['live_halt']['halted'] is True and live['account']['pending_reg_taf_fees']==live['account']['accrued_fees']=='0'
assert live['account']['cash']==live['account']['non_marginable_buying_power']=='496.12'
assert paper['account']['id']=='4cdbfb77-d1e0-4789-86b2-341bc886efaf' and not paper['orders']
assert {p['symbol'] for p in paper['positions']}=={'ABNB','ABT','AMZN','MA','SCHW'}
assert not source['matching_processes'] and source['shared_lock_available']
assert all(not v['mismatches'] for v in source['source_manifests'].values())
asset=json.loads(source['asset_NET']['raw'])
assert all(asset[k]==v for k,v in {'symbol':'NET','status':'active','tradable':True,'fractionable':True}.items())
policy_path=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json';policy=json.loads(policy_path.read_bytes())
orders=json.loads(source['closed_order_source']['raw']);activities=json.loads(source['account_activity_source']['raw'])
fills=[o for o in orders if Decimal(o.get('filled_qty','0'))>0];fees=[a for a in activities if a['activity_type']=='FEE']
assert len(fills)==6 and len([a for a in activities if a['activity_type']=='FILL'])==6 and len(fees)==5
assert sum(Decimal(a['net_amount']) for a in fees)==Decimal('-.05')
exits=[];gross=Decimal(0)
for s in policy['inherited_slots']:
 buys=[o for o in fills if o['symbol']==s['symbol'] and o['side']=='buy']
 sells=[o for o in fills if o['symbol']==s['symbol'] and o['side']=='sell']
 assert len(buys)==1 and buys[0]['id']==s['entry_order_id'] and Decimal(buys[0]['filled_qty'])==Decimal(s['qty'])
 assert sum(Decimal(o['filled_qty']) for o in sells)==Decimal(s['qty'])
 gross+=sum(Decimal(o['filled_qty'])*Decimal(o['filled_avg_price']) for o in sells)-Decimal(buys[0]['filled_qty'])*Decimal(buys[0]['filled_avg_price'])
 exits.append({'entry_order_id':s['entry_order_id'],'orders':[{k:o[k] for k in ['id','symbol','side','status','filled_qty','filled_avg_price']}|{'filled_ms':int(datetime.fromisoformat(o['filled_at'].replace('Z','+00:00')).timestamp()*1000)} for o in sells]})
assert not source['book']['attempts'] and len(source['book']['retirements'])==1
names=set()
for root,m in source['app_source_maps'].items():
 if 'alpaca-intended-paper' not in root:names.update(m)
names.update(['research_lab/alpaca_open_dispatch_v2.py','scripts/run_alpaca_open_dispatch_v2.py','scripts/run_alpaca_paper_session_guard.py','tests/test_alpaca_open_dispatch_v2.py','tests/test_alpaca_expired_reservation_handoff.py','tests/test_alpaca_paper_source_plan.py','tests/test_alpaca_paper_session_guard.py','tests/test_alpaca_initial_protection_recovery.py'])
# The opening regression tests read the exact archived protocol as a fixture.
# Include that byte-identical dependency; the session uses its reviewed NET binding.
names.add('reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json')
files={}
for n in sorted(names):
 raw=(ROOT/n).read_bytes()
 if n.endswith('.env'):
  assert all(token not in raw for token in [b'API_KEY',b'API_SECRET',b'TG_TOKEN',b'PASSWORD']), 'NO_CREDENTIAL_CONFIG_COPY'
 files[n]=raw
manifest={n:sha(raw) for n,raw in files.items()}
files['source_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
parent_path=ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json'
protocol=json.loads(parent_path.read_bytes())
protocol.update(captured_utc=datetime.fromtimestamp(source['observed_ms']/1000,timezone.utc).isoformat().replace('+00:00','Z'),
 current_window='PROPOSED October12 PAPER-only source binding; no LIVE GO',
 review='Executable NET binding requires independent review of this complete session install proposal',
 parent_source_contract_sha256=sha(parent_path.read_bytes()),
 asset_source_sha256=source['asset_NET']['sha256'])
protocol['fractional_protocol']['requires_fresh_asset']['symbol']='NET'
protocol_bytes=(json.dumps(protocol,indent=2)+'\n').encode()
ranking_path=ROOT/'reports/evidence/sunday_preparation_20261011/monday_ranking_draft.json'
ranking=json.loads(ranking_path.read_bytes());assert ranking['ranking']['picks'][0]['symbol']=='NET'
template={'account_id':policy['account_id'],'observed_ms':source['observed_ms'],'source_sha256':sha(source_path.read_bytes()),
 'single_owner_verified':True,'cash_finality_verified':True,'cash_usd':'496.12','liability_reserve_usd':'0','fee_rate':'0',
 'positions':[],'open_orders':[],'exits':exits,'blocked_symbols':['AMD','CRWD','META'],
 'quotes':{'NET':{'risk_distance':str(Decimal(str(ranking['ranking']['picks'][0]['signal_close']))-Decimal(str(ranking['ranking']['picks'][0]['stop_price']))) }},
 'gates':{'NET':{'earnings':True,'concentration':True,'symbol':True,'protection':True}}}
template_bytes=(json.dumps(template,indent=2)+'\n').encode()
exclusions={**source['legacy_exclusions']['payload'],'NET':'ALPACA_DYNAMIC_V1_PAPER_OCT12_OWNED_OR_PENDING'}
exclusions_bytes=(json.dumps(exclusions,indent=2)+'\n').encode()
unit_common='''[Unit]\nDescription=One owner-approved isolated NET PAPER session October12\nAfter=network-online.target\nWants=network-online.target\n[Service]\nType=simple\nUser=root\nWorkingDirectory={base}/app\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=PYTHONUNBUFFERED=1\nEnvironment=ALPACA_ALLOW_NEW_ENTRIES=0\nUMask=0077\nRestart=no\nMemoryMax=1G\nTasksMax=32\nTimeoutStopSec=60\nStandardOutput=append:{base}/runtime/{kind}.log\nStandardError=append:{base}/runtime/{kind}.log\nExecStart=/root/by-bot/.venv/bin/python -B scripts/{script} --packet {base}/session/packet.json {args}\n'''
units={
 'alpaca-net-paper-open-20261012.service':unit_common.format(base=BASE,kind='open',script='run_alpaca_open_dispatch_v2.py',args='--runtime '+BASE+'/runtime/opening --run-opening --paper-submit'),
 'alpaca-net-paper-guard-20261012.service':unit_common.format(base=BASE,kind='guard',script='run_alpaca_paper_session_guard.py',args='--opening-runtime '+BASE+'/runtime/opening --runtime '+BASE+'/runtime/guard')}
static={'policy':BASE+'/app/reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json','template':BASE+'/session/template.json','protocol':BASE+'/session/protocol.json','ranking_proposal':BASE+'/session/ranking.json',
 'paper_env':'/root/by-bot/configs/alpaca_paper_local.env','live_env':'/root/by-bot/configs/alpaca_live_v38.env','legacy_exclusions':'/root/by-bot/runtime/alpaca_intended_paper/legacy_exclusions.json','root_crontab':'/var/spool/cron/crontabs/root'}
# The static validator reads the spool file, including cron's three generated
# header lines; `crontab -l` is a different byte source. Pin the captured file.
cron_file_source=source['cron_inventory']['/var/spool/cron/crontabs']['root']
assert cron_file_source['contains_alpaca'] and cron_file_source['bytes']>0
pins={'policy':sha(policy_path.read_bytes()),'template':sha(template_bytes),'protocol':sha(protocol_bytes),'ranking_proposal':sha(ranking_path.read_bytes()),'legacy_exclusions':sha(exclusions_bytes),'root_crontab':cron_file_source['sha256']}
for name in ['paper_env','live_env']:pins[name]=source['profile_source_pins'][static[name]]
for n,info in source['writer_sources'].items():static['writer:'+n]='/root/by-bot/'+n;pins['writer:'+n]=info['sha256']
for n,h in source['live_runtime_pins'].items():static['live_binding:'+n]='/root/by-bot/runtime/alpaca_intended_live/'+n;pins['live_binding:'+n]=h
for n,h in manifest.items():static['app:'+n]=BASE+'/app/'+n;pins['app:'+n]=h
static['manifest']=BASE+'/app/source_manifest.json';pins['manifest']=sha(files['source_manifest.json'])
for n,raw in units.items():static['unit:'+n]='/etc/systemd/system/'+n;pins['unit:'+n]=sha(raw.encode())
binding={'schema':'ALPACA_OCT12_STATIC_SOURCE_BINDING_V1','status':'PROPOSED_REQUIRES_INDEPENDENT_FINANCIAL_REVIEW','source_archive_sha256':sha(source_path.read_bytes()),
 'source_observed_ms':source['observed_ms'],'old_known_fills':6,'posted_fee_count':5,'old_gross_exact':str(gross),'old_posted_fees':'.05','old_net_at_broker_cents':'8.70',
 'net_asset_source_sha256':source['asset_NET']['sha256'],'ranking_draft_sha256':sha(ranking_path.read_bytes()),
 'closed_history_source_sha256':'3ee3add36ae0b28b8fbb85ab690078dae88e97633a931e489249b44e0c403b45',
 'earnings_source_sha256':'746e21715dd8c9caf049c66825b24230cd1b4fcbaac5034115996a1ad1d10b11','next_net_earnings':'2026-10-29',
 'legacy_exclusion_before_sha256':source['legacy_exclusions']['sha256'],'legacy_exclusion_after_sha256':sha(exclusions_bytes),
 'ownership':'original shared PAPER lock; unchanged preserve-only legacy wrapper excludes NET; refresh cron has no --send-orders; no other enabled Alpaca units/writers in captured inventory',
 'handoff':'one retired unfilled XOM original row retained; exact new Monday attempt in intent_attempts; membership recovery now reads exact active receipt',
 'paper_scope':'direct owner October11 evening instruction: exact Monday PAPER-only NET attempt; no LIVE approval',
 'maintenance':'guard rejects BUY at client boundary; only exact persisted NET attempt; Oct13 13:35UTC owned PAPER test unwind, Oct13 14UTC hard end; any unresolved ownership/partial/finality remains BLOCKED',
 'money_authority':False,'live_orders_allowed':False,'app_manifest_sha256':sha(files['source_manifest.json'])}
binding_bytes=(json.dumps(binding,indent=2)+'\n').encode();static['binding']=BASE+'/session/source_binding.json';pins['binding']=sha(binding_bytes)
checks={n:{'status':'CLEAR_OR_REVIEWED' if n=='reservation_handoff' else 'VERIFIED','source_sha256':sha(binding_bytes)} for n in ['source_config','ownership','protection_eligibility','earnings','concentration','cost_protocol','reservation_handoff']}
packet={'schema':'ALPACA_OPEN_DISPATCH_V2_PACKET','symbol':'NET','open_ms':1791811800000,
 'policy':static['policy'],'source_template':static['template'],'protocol':static['protocol'],'ranking_proposal':static['ranking_proposal'],
 'paper_env':static['paper_env'],'live_env':static['live_env'],'source_book':'/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/rehearsal/replacement.sqlite',
 'paper_runtime':'/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/broker_paper','paper_account':'4cdbfb77-d1e0-4789-86b2-341bc886efaf',
 'attempt_authorization':{'scope':'PAPER_ONLY','session':'2026-10-12','owner_approved':True},'static_paths':static,'expected_sha256':pins,'checks':checks}
session={'packet.json':(json.dumps(packet,indent=2)+'\n').encode(),'protocol.json':protocol_bytes,'template.json':template_bytes,'ranking.json':ranking_path.read_bytes(),'source_binding.json':binding_bytes}
proposal={'schema':'ALPACA_NET_PAPER_INSTALL_PROPOSAL_V1','base':BASE,
 'app_files':{n:base64.b64encode(raw).decode() for n,raw in files.items()},'session_files':{n:base64.b64encode(raw).decode() for n,raw in session.items()},
 'units':units,'legacy_exclusions_after_b64':base64.b64encode(exclusions_bytes).decode(),
 'legacy_exclusions_before_sha256':source['legacy_exclusions']['sha256'],'source_archive_sha256':sha(source_path.read_bytes()),
 'expected_original_table_sha256':source['book']['original_table_sha256'],'services':source['services'],
 'expected_original_manifests':source['source_manifests']}
write(PRIVATE/'install_proposal.json',proposal)
write(PUBLIC/'source_binding_proposal.json',binding);write(PUBLIC/'packet_proposal.json',packet)
write(PUBLIC/'source_manifest.json',manifest);write(PUBLIC/'protocol_net_review_proposal.json',protocol)
write(PUBLIC/'install_manifest.json',{'proposal_sha256':sha((PRIVATE/'install_proposal.json').read_bytes()),'base':BASE,'app_files':len(manifest),
 'session_files':{n:sha(raw) for n,raw in session.items()},'unit_files':{n:sha(raw.encode()) for n,raw in units.items()},'source_archive_sha256':sha(source_path.read_bytes()),'live_changes':False,'broker_writes_before_open':0})
print(json.dumps({'proposal_sha256':sha((PRIVATE/'install_proposal.json').read_bytes()),'app_files':len(manifest),'symbols':['NET'],'live_orders':False}))
