#!/usr/bin/env python3
"""Pinned, file-only intake of one existing KITY packet; no judge or orders."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.research_tiny_intake_v1 import assess_kity, IntakeBlocked
from research_lab.pump4_live_observer_v1 import read_file
from research_lab.os2_shadow_journal import strict_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('signal','c2','entry'):
        p.add_argument('--'+n,type=Path,required=True);p.add_argument('--'+n+'-sha256',required=True)
    p.add_argument('--dossier-legs',type=int,required=True)
    p.add_argument('--active-owner',required=True)
    a=p.parse_args(); values=[]; pins={}
    try:
        for n in ('signal','c2','entry'):
            raw=read_file(getattr(a,n)); pin=hashlib.sha256(raw).hexdigest()
            if pin!=getattr(a,n+'_sha256'):raise IntakeBlocked(n+'_pin_mismatch')
            values.append(strict_json(raw));pins[n]=pin
        if values[1]['compared_inputs']['signal.json']!=pins['signal']:
            raise IntakeBlocked('c2_signal_pin_mismatch')
        r=assess_kity(*values,dossier_legs=a.dossier_legs,active_owner=a.active_owner)
        r['source_sha256']=pins
    except (ValueError,OSError,KeyError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)}));return 2
    print(json.dumps(r,sort_keys=True,indent=2));return 0

if __name__=='__main__': raise SystemExit(main())
