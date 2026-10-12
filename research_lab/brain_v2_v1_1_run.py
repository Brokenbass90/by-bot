"""Prepared A7 V1.1 one-shot runner; default requires separate written owner GO.

--verify-only reads pins without outcomes, run directory or start marker.
No old source/table rewrite, retraining, B3 judge, broker or live authority.
"""
from dataclasses import asdict
import json
from pathlib import Path
import shutil

from research_lab.brain_v2_frozen_primitives import _require
from research_lab.brain_v2_sources import PinnedSources
from research_lab.brain_v2_develop import START,END,TICK,DATES,A5_PIN,A6_PIN
from research_lab.brain_v2_develop_run import (
    verify_inputs as verify_original_inputs, RealInputs, CompressedLedger,
    save_exclusive, MIN_FREE_BYTES,
)
from research_lab.brain_v2_v1_1_a7 import (
    A7Table,DevelopEngineV11,partition,run_once_authorized,OWNER_GO,A7_PIN,FREEZE_PIN,
)

BASE=Path('reports/evidence/brain_v2_v1_1_20261012')
OLD_MANIFEST=Path('reports/evidence/brain_v2_develop_20261012/A5_A6_PRE_RUN_MANIFEST.json')
OLD_PIN='476fc7ba3c00264ca11e8d79dbd90ba424c8a8a3495f77c2df05c1dd1c68721c'


def verify_inputs(root,raw,expected_pin):
    guard=PinnedSources(root,raw,expected_manifest_sha256=expected_pin);guard.verify()
    d=json.loads(raw)
    _require(d.get('scope')=='BRAIN_V2_V1_1_A7_FROZEN_DEVELOPMENT'
        and d.get('owner_go_required') is True and d.get('attempts_if_owner_go')==1
        and d.get('a7_sha256')==A7_PIN and d.get('freeze_sha256')==FREEZE_PIN
        and d.get('a5_sha256')==A5_PIN and d.get('a6_sha256')==A6_PIN,'V11_manifest_scope')
    adapter,_=verify_original_inputs(root,guard.read(str(OLD_MANIFEST)),OLD_PIN)
    pub=json.loads(guard.read(str(BASE/'TABLE_HASH_PUBLICATION.json')))
    _require(pub['outcome_run_started'] is False and pub['owner_go_required'] is True,'A7_table_publication')
    by_name={Path(r['path']).name:r for r in pub['files']}
    def table(name,cutoff):
        r=by_name[name]
        return A7Table(guard.read(r['path']),expected_pin=r['sha256'],cutoff=cutoff)
    folds=tuple(table('MU_SIGMA_V1_A7_fold_'+date+'.json',date) for date in DATES)
    prospective=table('MU_SIGMA_V1_A7.json','2025-10-01')
    _require(prospective.source_hash==d['prospective_table_sha256'],'A7_prospective_table_pin')
    return adapter,folds,prospective


def evaluate(adapter,tables,output):
    """Called only within the authorized one-shot boundary, never preparation."""
    inputs=RealInputs(adapter);engine=DevelopEngineV11(tables)
    files={key:CompressedLedger(output/(key+'.jsonl.gz')) for key in (
        'paired_decisions','equity_ticks','closed_RAW_SAFE','closed_FOUNDATION','closed_BRAIN_DET')}
    at=START;artifacts={}
    try:
        while at<END or any(a['positions'] for a in engine.arms.values()):
            entries=inputs.entries.get(at,[]) if at<END else []
            feasible,_=partition(entries)
            contexts={e.opportunity.id:inputs.context(e) for e in feasible}
            outcomes={e.opportunity.id:inputs.outcome(e) for e in feasible}
            result=engine.step(at,entries,contexts,outcomes)
            files['equity_ticks'].append(dict(tick_ms=at,arms=result['ticks'],before_current_packet=True))
            for entry in sorted(entries,key=lambda e:e.opportunity.id):
                key=entry.opportunity.id
                files['paired_decisions'].append(dict(tick_ms=at,opportunity=asdict(entry.opportunity),
                    opportunity_id=key,entry_metadata=dict(entry.metadata),context=contexts.get(key),
                    arms=result['decisions'][key]))
            for arm,closed in result['closed'].items():
                for row in closed:files['closed_'+arm].append(row)
            at+=TICK
    finally:
        for key,ledger in files.items():artifacts[key]=ledger.close()
        save_exclusive(output/'ARTIFACTS.json',artifacts)
    return {**engine.report(),'artifacts':artifacts,'test_start_ms':START,
        'new_entry_end_exclusive_ms':END,'last_tick_ms':engine.last_tick,
        'release_only_tail':engine.last_tick>=END,'opportunities':len(engine.seen),
        'source_manifest_sha256':adapter.manifest_sha256,
        'research_scope':'V11_CONTAMINATION_DISCLOSED_DEVELOPMENT_NOT_INDEPENDENT_EDGE',
        'B3_runs':0,'new_holdout_decisions':0,'live_or_vps_operations':0}


def main():
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest',required=True);ap.add_argument('--expected-pin',required=True)
    ap.add_argument('--verify-only',action='store_true')
    ap.add_argument('--owner-go',default=None,help='Only after direct written owner GO; not manager/Claude approval')
    args=ap.parse_args();root=Path.cwd()
    if not args.verify_only:_require(args.owner_go==OWNER_GO,'explicit_owner_go_required')
    adapter,tables,prospective=verify_inputs(root,Path(args.manifest).read_bytes(),args.expected_pin)
    if args.verify_only:
        print(json.dumps(dict(status='V11_PINS_VERIFIED_RUN_NOT_STARTED',table_pins=[t.source_hash for t in tables],
            prospective_pin=prospective.source_hash,filter_runs=0,owner_go_required=True,orders_allowed=False)))
        return
    _require(shutil.disk_usage(root).free>=MIN_FREE_BYTES,'disk_preflight')
    report=run_once_authorized(root/BASE/'run_v1_1',args.expected_pin,args.owner_go,
        lambda output:evaluate(adapter,tables,output))
    print(json.dumps({k:report[k] for k in ('status','manifest_sha256','filter_runs','orders_allowed')}))


if __name__=='__main__':main()
