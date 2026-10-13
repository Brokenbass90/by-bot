#!/usr/bin/env python3
"""Prepare package / postcheck original PAPER / exact LIVE dossier. No broker IO.

postcheck is offline and cannot restart/submit/reprice. install-disabled may only
write the new isolated app after the existing actual PAPER lifecycle has passed.
No systemctl, crontab, profile writes, permission generator or HALT-clear exists.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json
from research_lab.alpaca_live_readiness_v1 import (
    build_package, verify_package, verify_paper_lifecycle, initial_evidence,
    exact_dossier, pre_entry_dossier, install_disabled, write_new, blocked, derive_paper_cost_closure,
    derive_paper_posted_cost_closure_v2,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('package'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('postcheck')
    for name in ('arm','initial-receipt','initial-capture','rearm-capture','terminal-capture'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--cost-closure', type=Path)
    p.add_argument('--cash-before-capture',type=Path)
    p.add_argument('--paper-document',type=Path)
    p.add_argument('--commission-protocol',type=Path)
    p.add_argument('--actual-posted-fees',action='store_true',
        help='strict posted CAT/SEC and four actual cash checkpoints; missing fees remain BLOCKED')
    p.add_argument('--cost-closure-output',type=Path)
    p.add_argument('--deployment', type=Path); p.add_argument('--binding', type=Path)
    p.add_argument('--intake', type=Path); p.add_argument('--policy', type=Path,
        default=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    p.add_argument('--paper-receipt-output', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('install-disabled')
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--paper-receipt', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('prepare-first-intent')
    for name in ('spec','binding','preparation','paper-receipt','deployment','intent-output','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--policy',type=Path,default=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    args = parser.parse_args(argv); now = time.time_ns() // 1_000_000
    def load(path): return read_json(str(path))
    try:
        if args.command == 'package':
            package = build_package(ROOT)
            write_new(args.output, canonical(package))
            print(json.dumps(verify_package(package))); return 0
        if args.command == 'install-disabled':
            out = install_disabled(load(args.package), load(args.paper_receipt), now_ms=now)
        elif args.command == 'prepare-first-intent':
            from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
            policy=load(args.policy);binding=load(args.binding)
            intent=prepare_first_intent(policy=policy,binding=binding,**load(args.spec))
            out=pre_entry_dossier(paper=load(args.paper_receipt),deployment=load(args.deployment),
                binding=binding,intent=intent,policy=policy,preparation=load(args.preparation),now_ms=now)
            if out['status']=='READY_FOR_LIVE_GO':write_new(args.intent_output,canonical(intent))
        else:
            initial = initial_evidence(args.initial_receipt, args.initial_capture)
            fees=load(args.cost_closure) if args.cost_closure else None
            if fees is None and args.actual_posted_fees:
                if not all((args.cash_before_capture,args.commission_protocol)):
                    raise ValueError('POSTED_FEE_SOURCES_REQUIRED')
                fees=derive_paper_posted_cost_closure_v2(cash_before_path=args.cash_before_capture,
                    initial_path=args.initial_capture,rearm_path=args.rearm_capture,
                    terminal_path=args.terminal_capture,protocol_path=args.commission_protocol,now_ms=now)
                if args.cost_closure_output:write_new(args.cost_closure_output,canonical(fees))
            elif fees is None and all((args.cash_before_capture,args.paper_document,args.commission_protocol)):
                fees=derive_paper_cost_closure(args.cash_before_capture,args.terminal_capture,
                    args.paper_document,args.commission_protocol,now_ms=now)
                if args.cost_closure_output:write_new(args.cost_closure_output,canonical(fees))
            paper = verify_paper_lifecycle(load(args.arm), initial,
                load(args.rearm_capture)['response'], load(args.terminal_capture)['response'],
                fees, now_ms=now)
            if args.paper_receipt_output: write_new(args.paper_receipt_output, canonical(paper))
            if paper['status'] != 'PAPER_EXECUTION_PASS':
                out = paper
            elif not all((args.deployment, args.binding, args.intake)):
                out = blocked('PAPER_PASS; EXACT_LIVE_BINDING_AND_DISABLED_DEPLOYMENT_REQUIRED')
                out['paper_receipt_sha256'] = paper['receipt_sha256']
            else:
                out = exact_dossier(paper=paper, deployment=load(args.deployment),
                    binding=load(args.binding), intake=load(args.intake), policy=load(args.policy), now_ms=now)
        write_new(args.output, canonical(out))
        print(json.dumps(out))
        return 2 if out['status'].startswith('BLOCKED') else 0
    except Exception as exc:
        out = blocked(str(exc) or type(exc).__name__)
        # Missing input/file is a terminal readback blocker, never an action.
        if not args.output.exists(): write_new(args.output, canonical(out))
        print(json.dumps(out)); return 2


if __name__ == '__main__': raise SystemExit(main())
