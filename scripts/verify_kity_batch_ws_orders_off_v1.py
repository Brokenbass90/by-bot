#!/usr/bin/env python3
"""Offline physical source-kit verification. No writer/GO or network path."""
import argparse
import hashlib
import json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--spec')
    parser.add_argument('--spec-sha256')
    args=parser.parse_args(argv)
    if not args.spec:
        print(json.dumps(dict(status='KITY_BATCH_ORDERS_OFF_NO_NETWORK',broker_writes=0)))
        return 0
    p=Path(args.spec);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.spec_sha256:raise ValueError('BATCH_SPEC_PIN_CONFLICT')
    spec=json.loads(raw)
    if (spec.get('schema')!='TRADING_OS_DISABLED_CANDIDATE_V1' or spec.get('component')!='kity-batch-ws'
            or spec.get('default_orders_off') is not True or spec.get('monetary_transport_bound') is not False
            or spec.get('new_policy_issued') is not False or spec.get('old_go_reused') is not False):
        raise ValueError('BATCH_DISABLED_SPEC_REQUIRED')
    for rel,pin in spec['files'].items():
        if Path(rel).is_absolute() or '..' in Path(rel).parts:raise ValueError('BATCH_SOURCE_PATH_SCOPE')
        path=p.parent/'app'/rel
        if any(v.is_symlink() for v in (path,*path.absolute().parents)):
            raise ValueError('BATCH_SOURCE_SYMLINK')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pin:raise ValueError('BATCH_SOURCE_DRIFT')
    print(json.dumps(dict(status='KITY_BATCH_SOURCE_PINS_PASS_ORDERS_OFF',source_count=len(spec['files']),
        monetary_transport_bound=False,broker_writes=0)))
    return 0


if __name__=='__main__':raise SystemExit(main())
