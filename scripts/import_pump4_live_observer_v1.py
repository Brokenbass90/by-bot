#!/usr/bin/env python3
"""File-only immutable capture -> separate Brain observation journal."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.pump4_live_observer_v1 import import_capture, ObserverBlocked


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--scope-sha256',required=True)
    p.add_argument('--config-sha256',required=True)
    p.add_argument('--target',type=Path,required=True)
    a=p.parse_args()
    try:
        r=import_capture(a.manifest,a.manifest_sha256,a.target,
                         expected_scope=a.scope_sha256,expected_config=a.config_sha256)
    except (ObserverBlocked,OSError,ValueError) as e:
        print(json.dumps({'status':'BLOCKED','reason':getattr(e,'reason','source_invalid')}));return 2
    print(json.dumps(r,sort_keys=True));return 0

if __name__=='__main__': raise SystemExit(main())
