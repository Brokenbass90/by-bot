#!/usr/bin/env python3
"""Explicit SSH read-only pull into Claude's data directory. Default no network."""
import argparse,json,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.liq_research_delivery_v1 import names,safe,import_snapshot,verify_snapshot
REMOTE='root@64.226.73.119'
EXPORTS='/opt/bybot-research/liquidation-source-v2-1-20261014/runtime/exports'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pull',action='store_true')
    p.add_argument('--day',default=datetime.now(timezone.utc).strftime('%Y%m%d'))
    p.add_argument('--identity',type=Path);p.add_argument('--staging',type=Path);p.add_argument('--destination',type=Path)
    a=p.parse_args(argv)
    if not a.pull:
        print(json.dumps({'status':'NO_NETWORK_DATA_ONLY','orders_allowed':False}));return 0
    try:
        files,last=names(a.day)
        if not a.identity or not a.staging or not a.destination:raise ValueError('EXPLICIT_PATHS_REQUIRED')
        identity=safe(a.identity);stage=safe(a.staging);dest=safe(a.destination)
        if not identity.is_file() or dest==stage or stage in dest.parents or dest in stage.parents:
            raise ValueError('PULL_PATH_SCOPE')
        stage.mkdir(parents=True,exist_ok=True,mode=0o700)
        with tempfile.TemporaryDirectory(prefix='download-',dir=stage) as tmp:
            options=['scp','-q','-i',str(identity),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10']
            # Fixed host and export namespace; every generated filename validated.
            subprocess.run([*options,*[REMOTE+':'+EXPORTS+'/'+n for n in [last,*files]],tmp],
                           check=True,capture_output=True,timeout=180)
            verify_snapshot(tmp,a.day)
            out={'status':'RESEARCH_DATA_IMPORTED',**import_snapshot(tmp,dest,a.day),'remote_writes':0}
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:
        out={'status':'BLOCKED_DATA_PULL','error_type':type(e).__name__,'orders_allowed':False,'remote_writes':0}
    print(json.dumps(out,sort_keys=True));return 2 if out['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
