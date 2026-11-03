"""Compose exact unique-node evidence; never erase or relabel the failed run."""
import hashlib,json,xml.etree.ElementTree as E
EXPECTED={('tests.test_alpaca_monthly_production_runner_v1','test_full_frozen_rotation_runs_through_production_cli'),('tests.test_alpaca_monthly_production_runner_v1','test_default_cli_clock_is_sampled_after_slow_authority_checks')}
def need(v,why):
 if not v:raise ValueError(why)
def qualify(candidate,packet,read):
 material=packet['source_material_sha256'];proof=packet['qualification_proofs']
 blobs={n:read(candidate/n,h) for n,h in proof.items()}
 original=json.loads(blobs['acceptance.json']);rerun=json.loads(blobs['two-resource-rerun.json'])
 for v in [original,rerun]:need(v['source_material_sha256']==material and v['checkout_fallback']==[] and v['network_denied'] is True and v['real_broker_requests']==v['real_broker_writes']==0,'QUALIFICATION_SOURCE_OR_NETWORK')
 need(original['status']=='FAIL' and original['counts']==dict(tests=302,failures=2,errors=0,skipped=0),'ORIGINAL_RESULT_CHANGED')
 need(rerun['status']=='PASS' and rerun['counts']==dict(tests=2,failures=0,errors=0,skipped=0),'RERUN_NOT_PASS')
 for key,name in [('original_acceptance_sha256','acceptance.json'),('original_xml_sha256','exact-tests.xml'),('rerun_xml_sha256','two-resource-rerun.xml')]:need(rerun[key]==hashlib.sha256(blobs[name]).hexdigest(),'RERUN_PROOF_LINK')
 def cases(xml):
  rows=list(E.fromstring(xml).iter('testcase'));out={(r.attrib['classname'],r.attrib['name']):r for r in rows};need(len(out)==len(rows),'DUPLICATE_TEST_ID');return out
 first=cases(blobs['exact-tests.xml']);again=cases(blobs['two-resource-rerun.xml'])
 need(len(first)==302 and set(again)==EXPECTED,'QUALIFICATION_NODE_SET')
 failed={k for k,r in first.items() if r.find('failure') is not None};need(failed==EXPECTED,'UNEXPECTED_FAILED_NODE')
 need(not any(r.find('error') is not None or r.find('skipped') is not None for r in first.values()),'ORIGINAL_ERRORS_OR_SKIPS')
 need(not any(any(c.tag in {'failure','error','skipped'} for c in r) for r in again.values()),'RERUN_ERRORS_OR_SKIPS')
 need('Timeout (>600.0s)' in first[('tests.test_alpaca_monthly_production_runner_v1','test_full_frozen_rotation_runs_through_production_cli')].find('failure').get('message',''),'ORIGINAL_TIMEOUT_CLASSIFICATION')
 need('CLI_FROZE_TIME_BEFORE_AUTHORITY_CHECKS' in first[('tests.test_alpaca_monthly_production_runner_v1','test_default_cli_clock_is_sampled_after_slow_authority_checks')].find('failure').get('message',''),'ORIGINAL_CLOCK_CLASSIFICATION')
 return dict(status='EXACT_302_QUALIFIED_WITH_TWO_RESOURCE_RERUNS',unique_tests=302,initial_pass=300,resource_rerun_pass=2,skipped=0,source_material_sha256=material,original_failure_retained=True,network_denied=True,real_broker_writes=0)
