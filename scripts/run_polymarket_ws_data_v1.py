#!/usr/bin/env python3
"""Explicit public DATA-only collector; default no files/network."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'vendor') not in sys.path:sys.path.insert(0,str(ROOT/'vendor'))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.polymarket_ws_data_v1 import read,sha,need,FrozenSelection,update_catalogue,run_worker,DataStop

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--run-data-only',action='store_true');p.add_argument('--spec',type=Path);p.add_argument('--spec-sha256');p.add_argument('--role',choices=['sports','clob','catalog']);a=p.parse_args(argv)
    if not a.run_data_only:print(json.dumps(dict(status='DATA_ONLY_NO_REQUESTS')));return 0
    need(a.spec and a.spec_sha256 and a.role,'EXPLICIT_SCOPE');raw=read(a.spec);need(sha(raw)==a.spec_sha256,'SPEC_PIN');spec=json.loads(raw)
    need(spec['schema']=='POLY_WS_DATA_SPEC_V1' and spec['orders_allowed'] is False,'DATA_ONLY_SPEC')
    for name,pin in spec['source_files'].items():need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(read(ROOT/name))==pin,'SOURCE_DRIFT')
    selection=FrozenSelection(ROOT/spec['prototype_root'],spec['prototype_pins'])
    try:
        if a.role=='catalog':x=update_catalogue(spec['runtime'],selection);print(json.dumps(dict(status='CATALOGUE_CAPTURED',markets=len(x['markets']))));return 0
        run_worker(spec['runtime'],a.role,selection)
    except DataStop:print(json.dumps(dict(status='DATA_BUDGET_STOP',role=a.role)));return 78

if __name__=='__main__':raise SystemExit(main())
