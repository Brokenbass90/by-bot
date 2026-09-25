#!/usr/bin/env python3
"""Offline source/encoding checks; never executes or promotes a hypothesis."""
import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
from scripts.validate_alpaca_pit_daily import atomic_json, canonical_sha, date_from_ms


def validate(source, archive):
    manifest=json.loads((archive/'deep_history_manifest.json').read_text())
    membership=json.loads((source/'membership_intervals.json').read_text())
    counts=collections.Counter(); problems={}; stats={}; common=0; changed=0
    schemas=set(); months=collections.Counter(); years=collections.Counter()
    metadata={name:hashlib.sha256((archive/name).read_bytes()).hexdigest()==hashlib.sha256((source/name).read_bytes()).hexdigest()
              for name in ('membership_intervals.json','universe.json','ticker_reference.json')}
    for member in membership['intervals']:
        symbol=member['symbol']; p=archive/'bars'/f'{symbol}.json'; issue=[]
        if not p.exists():
            problems[symbol]=['missing_validated_file'];counts['missing_files']+=1;continue
        doc=json.loads(p.read_text()); rows=doc['records']; schemas.add(doc['schema_id'])
        assert doc['symbol']==symbol and doc['adjusted'] is True
        assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['files'][symbol]['sha256']
        assert doc['payload_sha256']==canonical_sha(rows)
        times=[r['t'] for r in rows]; assert times==sorted(set(times))
        for r in rows:assert set(r)=={'o','h','l','c','v','vw','n','t'}
        dates=[date_from_ms(t).isoformat() for t in times]
        assert all(manifest['request']['start']<=d<=manifest['request']['end'] for d in dates)
        after=[d for d in dates if member.get('delisted_utc') and d>member['delisted_utc'][:10]]
        zeros=sum(r['v']==0 and r['n']==0 for r in rows)
        counts['bars']+=len(rows);counts['zero_trade_rows']+=zeros;counts['verified_files']+=1
        if not rows:issue.append('empty_provider_history');counts['empty_symbols']+=1
        if after:issue.append('ticker_identity_conflict_bar_after_delist');counts['post_delist_symbols']+=1
        if dates:
            if dates[0]<'2017-01-01':counts['symbols_reaching_2016']+=1
            if dates[0]<'2019-01-01':counts['symbols_reaching_2018_or_earlier']+=1
        for d in dates:months[d[:7]]+=1;years[d[:4]]+=1
        old=json.loads((source/'bars'/f'{symbol}.json').read_text())['records']; new={r['t']:r for r in rows}
        shared=[r for r in old if r['t'] in new];diff=[abs(new[r['t']]['c']/r['c']-1) for r in shared if r['c']>0]
        common+=len(diff);changed+=sum(x>1e-6 for x in diff)
        stats[symbol]={'bars':len(rows),'from':dates[0] if dates else None,'through':dates[-1] if dates else None,
                       'zero_trade_rows':zeros,'after_delist_bars':len(after),'overlap_closes':len(diff),
                       'overlap_close_max_relative_difference':max(diff,default=None)}
        if issue:problems[symbol]=issue
    return {'schema':'equity_history_extension_quality_v1','hypothesis':'P_AKC_OSTATOCHNYY_MOMENT',
        'source_archive':str(source),'archive':str(archive),'provider':'Alpaca SIP','source_provider_changed':True,
        'request':{k:v for k,v in manifest['request'].items() if k!='universe_symbols'},
        'manifest_sha256':hashlib.sha256((archive/'deep_history_manifest.json').read_bytes()).hexdigest(),
        'frozen_metadata_identical':metadata,'requested_symbols':len(membership['intervals']),
        'counts':dict(counts),'bar_schemas':sorted(schemas),'by_year_rows':dict(sorted(years.items())),
        'overlap':{'closes_compared':common,'different_over_1ppm':changed,
                   'provider_parity_proven':False},'problems':problems,'symbols':stats,
        'encoding_hash_integrity_pass':all(metadata.values()),'full_fixed_universe_ready':not problems,
        'factory_blind_run_authorized':False,'promotion_authorized':False,
        'caveats':['Current-liquidity candidate-pool selection remains historically biased; this is not full-market PIT.',
                   'Split-adjusted data has current corporate-action vintage; no claim of historical unadjusted price-filter parity.',
                   'asof=- prevents automatic rename stitching, but ticker reuse/identity still needs provenance.',
                   'Zero-trade provider observations retained exactly: no imputation, no fabricated VWAP.',
                   'Frozen membership observed spans refer to old archive; actual deep spans are in symbols.',
                   'Existing consumer must not silently drop missing/quarantined symbols or auto-run sealed confirmation.']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--report',type=Path,required=True)
    a=ap.parse_args();report=validate(a.source,a.archive);atomic_json(a.report,report)
    print(json.dumps({k:report[k] for k in ('counts','requested_symbols','full_fixed_universe_ready','encoding_hash_integrity_pass')}))
    print(json.dumps({'quarantine_symbols':len(report['problems']),'reasons':dict(collections.Counter(v for values in report['problems'].values() for v in values))}))
