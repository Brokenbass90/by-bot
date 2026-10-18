#!/usr/bin/env python3
"""Explicit immutable FILE-ONLY delivery into Claude's data folder; default OFF."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.alpaca_monthly_data_parity_v1 import verify_files,put
from research_lab.alpaca_monthly_source_ops_v1 import safe_path
from research_lab.kity_oct15_deadline_v1 import stable_bytes

REMOTE='root@64.226.73.119'
EXPORTS='/opt/bybot-research/alpaca-monthly58-daily-20261018/runtime/exports'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pull',action='store_true')
    for n in ('session','identity','staging','destination'):p.add_argument('--'+n)
    a=p.parse_args(argv)
    if not a.pull:
        print(json.dumps(dict(status='NO_NETWORK_DATA_ONLY',orders_allowed=False)));return 0
    try:
        import re
        from datetime import date
        if not a.session or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',a.session):raise ValueError('SESSION_DATE')
        date.fromisoformat(a.session)
        stage=safe_path(a.staging);dest=safe_path(a.destination);identity=safe_path(a.identity)
        if dest==stage or stage in dest.parents or dest in stage.parents:raise ValueError('PULL_SCOPE')
        stage.mkdir(parents=True,exist_ok=True,mode=0o700);dest.mkdir(parents=True,exist_ok=True,mode=0o700)
        names=[a.session+s for s in ('.json','.diagnostic.json','.diagnostic.md','.delivery.json')]
        already=(dest/names[-1]).exists()
        with tempfile.TemporaryDirectory(prefix='download-',dir=stage) as temp:
            subprocess.run(['scp','-q','-i',str(identity),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                '-o','ConnectTimeout=10',*[REMOTE+':'+EXPORTS+'/'+n for n in names],temp],
                check=True,capture_output=True,timeout=180)
            seal=verify_files(temp,a.session)
            for n in names:put(dest/n,stable_bytes(Path(temp)/n))
        verify_files(dest,a.session)
        out=dict(status='MONTHLY58_RESEARCH_DATA_IMPORTED',already_imported=already,seal=seal,
            broker_writes=0,remote_writes=0,orders_allowed=False)
    except (ValueError,TypeError,KeyError,OSError,subprocess.SubprocessError) as e:
        out=dict(status='DATA_PULL_BLOCKED',error_type=type(e).__name__,orders_allowed=False,remote_writes=0)
    print(json.dumps(out,sort_keys=True));return 2 if out['status']=='DATA_PULL_BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
