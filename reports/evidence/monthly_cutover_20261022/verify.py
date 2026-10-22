"""Read-only verification of prepared local review artifacts; no broker/SSH."""
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from research_lab.alpaca_dynamic_v1 import canonical
from research_lab.alpaca_monthly_native_binding_v1 import standing_source_pins
from scripts.run_alpaca_monthly_cycle_v1 import RUNNER_CONFIG_FIELDS
private=root/'.private/monthly_cutover_20261022'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=read(Path(__file__).with_name('receipt.json'));e=read(private/'review-envelope.json')
assert sha(private/'review-envelope.json')==r['review_envelope_sha256']
assert sha(private/'readback-private.json')==r['readback_sha256']
assert e['schema']=='ALPACA_MONTHLY_CUTOVER_REVIEW_ENVELOPE_V1' and e['orders_allowed'] is e['money_authority'] is False
assert e['issued_owner_go'] is False and e['operational_config_sha256'] is e['owner_scope_sha256'] is None
assert e['operational_fields_required']==list(RUNNER_CONFIG_FIELDS)
assert all(v is None for v in e['future_inputs'].values())
assert len(e['accepted_packaged_sources'])==53 and e['standing_source_files']==standing_source_pins()
assert all(sha(root/n)==h for n,h in e['accepted_packaged_sources'].items())
assert sha(private/'net-exit-manifest.review.json')==e['exit_manifest_review_sha256']
assert sha(private/'owner-net-exit.review.sh.txt')==e['exit_launcher_review_sha256']
assert e['budget']['candidate_capital_ceiling_usd']=='400' and e['budget']['maximum_gross_usd']=='280'
assert e['budget']['restricted_cash_reserve_usd']=='40' and e['budget']['loss_admission_usd']=='8'
assert r['broker_requests']==r['broker_writes']==r['remote_writes']==r['financial_units_changed']==0
print(json.dumps(dict(status='CUTOVER_REVIEW_ARTIFACTS_VERIFIED',accepted_package=53,standing_closure=len(e['standing_source_files']),orders_allowed=False,broker_requests=0)))
