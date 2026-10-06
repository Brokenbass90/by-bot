#!/usr/bin/env python3
"""Offline prospective selection/replacement rehearsal. No broker credentials/API.

All supplied account/gate inputs remain unauthenticated input evidence. This
entry point can never promote a plan, submit an order or change the LIVE manager.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.alpaca_dynamic_v1 import (
    DynamicBook, build_ranking, canonical, digest, instant, policy_check,
    positive, session_at, source_check,
)


def load_history(raw):
    from backtest.alpaca_exact_parity_contract import DailyBar
    history = {}
    for symbol, rows in raw.items():
        bars = []
        last = None
        for row in rows:
            day = date.fromisoformat(row['session'])
            if last is not None and day <= last:
                raise ValueError('UNORDERED_OR_DUPLICATE_BARS')
            o, h, l, c = (positive(row[k]) for k in ('open', 'high', 'low', 'close'))
            if not l <= min(o, c) <= max(o, c) <= h:
                raise ValueError('INVALID_BAR')
            bars.append(DailyBar(day, float(o), float(h), float(l), float(c)))
            last = day
        history[symbol] = bars
    return history


def run(policy, runtime, bundle, now_ms):
    """now_ms is injected only by unit fixtures; the CLI always uses wall clock."""
    try:
        policy_check(policy)
        now_ms = instant(now_ms)
        calendar = policy['calendar_sessions']
        source_check(policy, calendar)
        if now_ms < policy['first_window_ms']:
            return DynamicBook.result('NOT_DUE', first_window_ms=policy['first_window_ms'],
                                      policy_sha256=digest(policy))
        current = session_at(calendar, now_ms)
        if current is None:
            reason = 'CALENDAR_EXPIRED' if now_ms > calendar[-1]['close_ms'] else 'OUTSIDE_OPEN_WINDOW'
            return DynamicBook.result('NOT_SELECTION_WINDOW', reason=reason)
        if bundle is None:
            return DynamicBook.result('BLOCKED_DATA', reason='MISSING_CAUSAL_INPUT_BUNDLE')
        allowed = {'schema', 'captured_ms', 'history_available_ms', 'history', 'snapshot'}
        if set(bundle) != allowed or bundle['schema'] != 'ALPACA_DYNAMIC_INPUT_BUNDLE_V1':
            raise ValueError('INPUT_BUNDLE_SCHEMA')
        if not instant(bundle['history_available_ms']) <= instant(bundle['captured_ms']) <= now_ms:
            raise ValueError('FUTURE_INPUT_BUNDLE')
        snapshot = bundle['snapshot']
        if not instant(snapshot['observed_ms']) <= bundle['captured_ms']:
            raise ValueError('FUTURE_ACCOUNT_INPUT')
        history = load_history(bundle['history'])
        if set(history) != set(policy['universe']):
            raise ValueError('UNIVERSE_SOURCE_CONFLICT')
        raw = canonical(bundle)
        bundle_sha = digest(bundle)
        runtime = Path(runtime)
        inputs = runtime / 'inputs'
        inputs.mkdir(parents=True, exist_ok=True)
        saved = inputs / (bundle_sha + '.json')
        if saved.exists():
            if saved.read_bytes() != raw:
                raise ValueError('INPUT_HASH_CONFLICT')
        else:
            with saved.open('xb') as handle:
                handle.write(raw)
            saved.chmod(0o400)
        book = DynamicBook(runtime / 'replacement.sqlite', policy)
        prior = book.ranking_at(current['open_ms'])
        if prior is None:
            held = {p['symbol'] for p in snapshot['positions']}
            blocked = held | set(snapshot['blocked_symbols'])
            try:
                ranking = build_ranking(policy, calendar, history, blocked,
                                        digest(bundle['history']), bundle['history_available_ms'], now_ms)
            except ValueError as error:
                if str(error) != 'NOT_WEEKLY_REFRESH':
                    raise
            else:
                book.seal_ranking(ranking, calendar, now_ms)
        result = book.propose(snapshot, calendar, now_ms)
        return {**result, 'input_bundle_sha256': bundle_sha,
                'broker_truth_authenticated': False, 'live_deployed': False}
    except (ValueError, KeyError, TypeError, ArithmeticError, OSError) as error:
        return DynamicBook.result('BLOCKED_DATA', reason=str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=ROOT / 'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    parser.add_argument('--runtime', type=Path, default=ROOT / '.private/alpaca_dynamic_v1_20261006/rehearsal')
    parser.add_argument('--input-bundle', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text())
        bundle = None
        if args.input_bundle:
            if args.input_bundle.stat().st_size > 20_000_000:
                raise ValueError('INPUT_BUNDLE_TOO_LARGE')
            bundle = json.loads(args.input_bundle.read_text())
        result = run(policy, args.runtime, bundle, time.time_ns() // 1_000_000)
    except (OSError, ValueError, TypeError) as error:
        result = DynamicBook.result('BLOCKED_DATA', reason=str(error))
    raw = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as handle:
            handle.write(raw)
    print(raw, end='')
    return 2 if result['status'] == 'BLOCKED_DATA' else 0


if __name__ == '__main__':
    raise SystemExit(main())
