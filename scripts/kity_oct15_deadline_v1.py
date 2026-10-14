#!/usr/bin/env python3
"""Fixed first KITY source deadline only. No snapshot, transport or PnL operation."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.kity_oct15_deadline_v1 import DAY,END,decode,stable_bytes,run_once,path,sha
OWN=ROOT/'.private/kity_bybit_c2'
CONFIG=OWN/'oct15_source_deadline_config.json'
OUTPUT=OWN/DAY/'receipts/source-deadline.json'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=CONFIG);p.add_argument('--config-sha256')
    a=p.parse_args(argv);now=time.time_ns()//1000000
    try:
        config=path(str(a.config.absolute()))
        if config!=CONFIG:raise ValueError('FIXED_OWN_CONFIG_ONLY')
        if now<END:out=dict(status='WATCH_PENDING',day=DAY,deadline_ms=END,orders_allowed=False)
        else:
            if config.exists():
                raw=stable_bytes(config)
                if not a.config_sha256 or sha(raw)!=a.config_sha256:raise ValueError('FROZEN_CONFIG_PIN_REQUIRED')
                cfg=decode(raw)
                if cfg['output_path']!=str(OUTPUT):raise ValueError('FIXED_OWN_OUTPUT_ONLY')
            else:
                # Failure-only fallback after deadline; never approves an unpinned source.
                cfg=dict(schema='KITY_OCT15_DEADLINE_OBSERVER_V1',day=DAY,output_path=str(OUTPUT),approval_scope='PENDING')
            out=run_once(cfg,now_ms=now)
    except Exception as e:out=dict(status='CAPTURE_OBSERVER_BLOCKED',reason=str(e),orders_allowed=False)
    print(json.dumps(out));return 2 if out['status'] in ('CAPTURE_BLOCKED','CAPTURE_OBSERVER_BLOCKED') else 0


if __name__=='__main__':raise SystemExit(main())
