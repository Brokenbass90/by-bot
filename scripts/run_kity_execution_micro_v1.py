#!/usr/bin/env python3
"""No-send preview/replay. No --apply, credentials, dispatcher or service mode.

Real-money readiness stays BLOCKED while the owner's absolute final-loss cap
cannot be enforced. Exit2 is the expected sourced readiness result, not a reason
to retry broker observations. Explicit --events/--journal writes only a local
offline replay journal, never an order/reservation/permit.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research_lab.kity_execution_micro_runtime_v1 import (
    prepare_micro_plan, assess_micro_readiness, MicroJournal,
)


def read(path):
    if path.stat().st_size > 4_000_000:
        raise ValueError('INPUT_SIZE_BOUND')
    return json.loads(path.read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dossier', type=Path, default=ROOT/'reports/evidence/kity_micro_live_20261015/execution_intake_terminal.json')
    parser.add_argument('--bounds', type=Path, default=ROOT/'configs/research/kity_execution_micro_owner_bounds_20261015.json')
    parser.add_argument('--events', type=Path)
    parser.add_argument('--journal', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    journal = None
    try:
        if bool(args.events) != bool(args.journal):
            raise ValueError('EXPLICIT_EVENTS_AND_REPLAY_JOURNAL_REQUIRED')
        dossier, bounds = read(args.dossier), read(args.bounds)
        plan = prepare_micro_plan(dossier, bounds)
        readiness = assess_micro_readiness(plan, dict(marginMode=dossier.get('configured_margin_mode')))
        out = dict(status='ORDERS_OFF_PREVIEW', orders_allowed=False, plan=plan, readiness=readiness,
                   research_evidence_eligible=False, broker_calls=0, broker_writes=0)
        if args.events:
            events = read(args.events)
            if not isinstance(events, list) or len(events) > 4096:
                raise ValueError('REPLAY_EVENT_BOUND')
            journal = MicroJournal(args.journal, plan)
            for e in events:
                journal.append(e)
            out['lifecycle'] = journal.snapshot()
    except (ValueError, KeyError, TypeError, OSError) as exc:
        out = dict(status='BLOCKED_DATA', reason=str(exc), orders_allowed=False, broker_calls=0, broker_writes=0)
    finally:
        if journal:
            journal.close()
    raw = json.dumps(out, indent=2, allow_nan=False) + '\n'
    if args.output:
        if args.output.is_symlink() or any(p.is_symlink() for p in args.output.absolute().parents):
            raise ValueError('OUTPUT_SYMLINK')
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
    print(raw, end='')
    return 2  # real readiness is deliberately not inferred from replay/exit0


if __name__ == '__main__':
    raise SystemExit(main())
