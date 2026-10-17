#!/usr/bin/env python3
"""Explicit file-only Brain receiver. No network clients or producer execution."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.brain_shadow_readonly_bridge_v1 import ImportBlocked, import_sources, _safe_path, require
from research_lab.os2_shadow_journal import strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opportunities', required=True, type=Path)
    parser.add_argument('--decisions', required=True, type=Path)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--registry-sha256', required=True)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--since-ms', required=True, type=int,
                        help='inclusive decision t_recorded_ms intake boundary; full chains still verified')
    parser.add_argument('--target', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        registry_path, target = _safe_path(args.registry), _safe_path(args.target)
        require(target != registry_path and target not in registry_path.parents, 'registry_target_overlap')
        for name in ('writer.lock', 'journal.jsonl'):
            candidate = target / name
            require(not candidate.exists() or not os.path.samefile(registry_path, candidate), 'registry_target_alias')
        rows = import_sources(opportunities=args.opportunities, decisions=args.decisions,
                              registry=strict_json(registry_path.read_bytes()),
                              registry_sha256=args.registry_sha256, source_id=args.source_id,
                              target=args.target, now_ms=time.time_ns() // 1_000_000, since_ms=args.since_ms)
    except (ImportBlocked, OSError, ValueError) as error:
        result = {'status': 'BLOCKED', 'reason': getattr(error, 'reason', 'invalid_registry')}
        if hasattr(error, 'capacity'):
            result['capacity'] = error.capacity
        print(json.dumps(result))
        return 2
    print(json.dumps({'status': 'SHADOW_ONLY', 'verified_receipts': len(rows), 'money_authority': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
