#!/usr/bin/env python3
"""Offline cap300 proposal; cannot create a live policy, permit or order."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_lab.kity_cap300_proposal_v1 import build_saved_proposal, owner_review_packet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--capture-sha256')
    parser.add_argument('--owner-review-packet', action='store_true', help='inert authority request, never a live policy')
    args = parser.parse_args(argv)
    if args.capture is None:
        print(json.dumps(dict(status='NO_NETWORK_ORDERS_OFF', orders_allowed=False, money_authority=False)))
        return 0
    try:
        bounds = json.loads((ROOT / 'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
        result = build_saved_proposal(args.capture, args.capture_sha256, bounds)
        capacity_fits = result['capacity_status'] == 'FITS_PROPOSED_CAP'
        if args.owner_review_packet:
            result = owner_review_packet(result)
    except Exception as exc:
        print(json.dumps(dict(status='PROPOSAL_INPUT_BLOCKED', error_type=type(exc).__name__, orders_allowed=False, money_authority=False)))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if capacity_fits else 2


if __name__ == '__main__':
    raise SystemExit(main())
