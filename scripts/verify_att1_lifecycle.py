#!/usr/bin/env python3
"""Standalone synthetic ATT1 lifecycle/restart oracle, usable in target Python."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from research_lab.att1_lifecycle_profile import build_profile
from research_lab.att1_lifecycle_session import LifecycleSession, implementation_hash
from research_lab.att1_lifecycle_coordinator import replay_lifecycle, digest

DEFAULT_FIXTURE=ROOT/'tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json'


class VerificationViolation(ValueError):
    pass


def pairs(items):
    result={}
    for key,value in items:
        if key in result: raise VerificationViolation('duplicate fixture JSON key')
        result[key]=value
    return result


def bad_constant(value):
    raise VerificationViolation('nonfinite fixture JSON')


def require(test,message):
    if not test: raise VerificationViolation(message)


def verify_fixture(path=DEFAULT_FIXTURE):
    path=Path(path)
    require(path.stat().st_size<=1048576,'oversized fixture')
    raw=path.read_bytes()
    fixture=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad_constant)
    require(fixture['schema_id']=='att1_lifecycle_e2e_fixture_v1','fixture schema')
    require(fixture['evidence_kind']=='SYNTHETIC_ONLY_NO_MARKET_OUTCOMES','fixture authority')
    profile=build_profile(ROOT)
    cases=[];boundaries=0
    with tempfile.TemporaryDirectory(prefix='att1-lifecycle-verifier-') as temporary:
        for i,case in enumerate(fixture['cases']):
            journal=Path(temporary).resolve()/f'case-{i}.jsonl'
            session=LifecycleSession(journal,profile,intent=case['intent'])
            events=case['events'];expected_held=case['expected_held_prefix']
            require(len(events)==len(expected_held),f'prefix oracle length:{case["name"]}')
            prefix_hashes=[]
            for index,event in enumerate(events):
                before=session.apply(event)
                restored=LifecycleSession(journal,profile)
                independent_replay=replay_lifecycle(profile,case['intent'],events[:index+1])
                require(before==restored.receipt==independent_replay,f'restart mismatch:{case["name"]}:{index}')
                require(before['held_qty']==expected_held[index],f'held oracle:{case["name"]}:{index}')
                prefix_hashes.append(digest(before))
                session=restored;boundaries+=1
            final=session.receipt
            for key,value in case['expected_final'].items():
                require(final[key]==value,f'final oracle:{case["name"]}:{key}')
            for key,value in case['expected_accounting'].items():
                require(final['accounting'][key]==value,f'account oracle:{case["name"]}:{key}')
            cases.append({'name':case['name'],'events':len(events),'prefix_receipt_sha256':prefix_hashes,
                          'final_receipt_sha256':digest(final),'final_net_r':final['final_net_r'],
                          'journal_sha256':hashlib.sha256(journal.read_bytes()).hexdigest()})
    return {'schema_id':'att1_lifecycle_e2e_receipt_v1','status':'PASS',
            'scope':'SYNTHETIC_ARITHMETIC_AND_DURABLE_RESTART_NOT_PROFIT_OR_BROKER_PARITY',
            'fixture_sha256':hashlib.sha256(raw).hexdigest(),'profile_sha256':profile['profile_sha256'],
            'implementation_sha256':implementation_hash(),'case_count':len(cases),
            'restart_boundaries':boundaries,'cases':cases,'money_authority':False,
            'orders_allowed':False,'private_api_allowed':False,'promotion_authority':False}


def verify_public_runtime_fixture():
    """Execute the real public runtime against a deterministic synthetic HTTP tape."""
    from copy import deepcopy
    from scripts.run_att1_lifecycle_zero_risk import PublicLifecycleRuntime
    fixture=json.loads(DEFAULT_FIXTURE.read_bytes())
    intent=deepcopy(fixture['cases'][0]['intent'])
    class Tape:
        def __init__(self):self.now=intent['submit_ms'];self.bid='100';self.ask='100.01';self.calls=0
        def clock(self):return self.now
        def sleep(self,seconds):self.now+=int(seconds*1000)
        def fetch(self,url,params,**kwargs):
            self.now+=100;self.calls+=1
            if url.endswith('/orderbook'):
                result={'s':'BTCUSDT','b':[[self.bid,'10']],'a':[[self.ask,'10']],
                        'ts':self.now,'cts':self.now,'u':self.now,'seq':self.now}
            elif url.endswith('/funding/history'):result={'category':'linear','list':[]}
            else:raise VerificationViolation('unexpected synthetic request')
            return json.dumps({'retCode':0,'result':result,'time':self.now}).encode()
    tape=Tape();proof=[]
    with tempfile.TemporaryDirectory(prefix='att1-public-fixture-') as temporary:
        root=Path(temporary).resolve();(root/'cache').mkdir()
        config=json.loads((ROOT/'configs/research/att1_lifecycle_public_v1.json').read_bytes())
        config.update(enabled=True,runtime_dir=str(root/'runtime'),l1_cache_dir=str(root/'cache'))
        def restore():return PublicLifecycleRuntime(config,clock_ms=tape.clock,transport=tape.fetch,sleep_fn=tape.sleep)
        runtime=restore();session=runtime.admit_candidate(intent['signal'],intent['instrument'])
        for stage,held in [('ENTRY','1/10'),('TP1','1/20'),('TP2','0'),('FINAL_COSTS','0')]:
            if stage=='TP1':tape.bid='87.99';tape.ask='88';runtime.manage(session)
            elif stage=='TP2':tape.bid='74.99';tape.ask='75';runtime.manage(session)
            elif stage=='FINAL_COSTS':tape.now+=65000;runtime.reconcile_funding(session)
            require(session.receipt['held_qty']==held,'public runtime held oracle:'+stage)
            before=runtime.state();after=restore().state()
            require(before==after,'public runtime restart mismatch:'+stage)
            proof.append({'stage':stage,'held_qty':held,'state_sha256':before['state_sha256']})
        require(session.receipt['final_net_r']=='36637/20000','public runtime finalR oracle')
        require(session.receipt['accounting']['known_fee_total']=='363/20000','public runtime fee oracle')
        return {'status':'PASS','scope':'SYNTHETIC_HTTP_TAPE_REAL_RUNTIME_NO_PUBLIC_OR_BROKER_FILLS',
                'restarted_stages':proof,'final_net_r':session.receipt['final_net_r'],
                'fees':session.receipt['accounting']['known_fee_total'],'funding':session.receipt['accounting']['settled_funding'],
                'requests':tape.calls,'authority':config['authority']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=DEFAULT_FIXTURE)
    args=parser.parse_args()
    try:
        result=verify_fixture(args.fixture)
        result["public_runtime_fixture"]=verify_public_runtime_fixture()
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'status':'FAIL_CLOSED','error':str(exc),'money_authority':False},sort_keys=True))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
