#!/usr/bin/env python3
"""Explicit DATA-ONLY ETS2S first-decision intake; no default source or sender."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.elder_hedge_event_intake_v1 import receive,contexts_from_brain,PRODUCER_SHA256
from research_lab.kity_oct15_deadline_v1 import publish_once


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','producer','book','brain-opportunities','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args(argv);now=time.time_ns()//1000000
    contexts=contexts_from_brain(a.brain_opportunities,now_ms=now)
    out=receive(a.source,producer=a.producer,producer_sha256=PRODUCER_SHA256,
        book=a.book,contexts=contexts,now_ms=now)
    out.update(observed_ms=now,producer_sha256=PRODUCER_SHA256,causal_context_candidates=len(contexts))
    publish_once(Path(a.output).absolute(),(json.dumps(out,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(out,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
