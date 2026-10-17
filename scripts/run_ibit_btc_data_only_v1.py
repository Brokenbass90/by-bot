#!/usr/bin/env python3
"""Saved-source only IBIT/BTC adapter. No HTTP/credentials/client discovery.

No arguments prints a NO_NETWORK status. Import accepts JSON mapping each source
name to {raw, received_at, ...request provenance}. alpaca_sip additionally needs
feed='sip', timeframe='1Day'; binance needs symbol='BTCUSDT', interval='1h'; bybit
needs interval='60'. Raw API responses are not enriched or rewritten. Calendar
raw is exactly one broker session {date,open,close}. See module for source shapes.
Use actual first source receipt times. --now is for deterministic offline replay;
otherwise the local current UTC clock is used. This is never a money runner.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_lab.ibit_btc_data_only_v1 import Adapter, RULE_SHA, checked_path


def _strict_load(path):
    def pairs(values):
        obj = {}
        for k,v in values:
            if k in obj:
                raise ValueError('duplicate JSON key')
            obj[k] = v
        return obj
    def invalid(value):
        raise ValueError('non-finite JSON number')
    return json.loads(checked_path(path, regular=True).read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command')
    imp = commands.add_parser('import', help='verify explicit saved source envelope')
    imp.add_argument('--sources', required=True)
    qa = commands.add_parser('qa', help='append Massive saved-source reconciliation')
    qa.add_argument('--massive', required=True)
    qa.add_argument('--received-at', required=True)
    for command in (imp, qa):
        command.add_argument('--store', required=True)
        command.add_argument('--session', required=True)
    imp.add_argument('--now', help='offline replay clock, timezone-aware ISO')
    args = parser.parse_args(argv)
    if args.command is None:
        print(json.dumps({'status':'NO_NETWORK', 'orders_enabled':False, 'rule_sha':RULE_SHA}))
        return 0
    try:
        store = checked_path(args.store)
        source = checked_path(args.sources if args.command == 'import' else args.massive, regular=True)
        if source == store or store in source.parents or source in store.parents:
            raise ValueError('saved input overlaps runtime store')
        adapter = Adapter(store)
        if args.command == 'import':
            result = adapter.import_session(args.session, _strict_load(args.sources),
                                            args.now or dt.datetime.now(dt.timezone.utc))
        else:
            result = adapter.reconcile(args.session, _strict_load(args.massive), args.received_at)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
    except (ValueError, OSError) as error:
        # Never echo source payloads, receipt file contents or credentials.
        print(json.dumps({'status':'REJECTED', 'error_type':type(error).__name__,
                          'orders_enabled':False}), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
