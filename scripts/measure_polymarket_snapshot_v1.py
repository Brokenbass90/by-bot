#!/usr/bin/env python3
"""Bounded ORDERS_OFF measurement of one already-monitored market. GET only.

No second WebSocket producer, wallet, order submission, judge or service install.
Default performs no network. Three samples are three quotes, never three trades.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research_lab import polymarket_v2_orders_off_v1 as measurement
from research_lab.polymarket_v2_snapshot_inputs_v1 import market_input, book_input
from research_lab.polymarket_ws_data_v1 import once, encoded, read, mkdirs_durable
from scripts.pull_polymarket_ws_data_v1 import validate_segment


def need(ok, why):
    if not ok:
        raise ValueError(why)


def membership(archive, seal_path, market_id):
    archive = Path(archive).absolute()
    seal_path = Path(seal_path).absolute()
    need(seal_path.is_relative_to(archive / 'catalog' / 'sealed'), 'CATALOGUE_SCOPE')
    seal = json.loads(read(seal_path, 16384))
    raw = read(archive / seal['file'])
    validate_segment(seal, raw)
    pin = hashlib.sha256(encoded(seal)).hexdigest()
    receipt = read(archive / 'receipts' / (pin + '.json'), 16384)
    r = json.loads(receipt)
    need(r['seal_sha256'] == pin and r['file_sha256'] == seal['sha256'], 'CATALOGUE_IMPORT_RECEIPT')
    import gzip
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    catalogues = [row for row in rows if row['kind'] == 'CATALOGUE']
    need(catalogues, 'CATALOGUE_RECORD_REQUIRED')
    matches = [m for m in catalogues[-1]['payload']['markets'] if str(m['id']) == market_id]
    need(len(matches) == 1, 'FIXED_MARKET_NOT_IN_EXISTING_MONITOR_NO_SUBSTITUTION')
    return matches[0], dict(seal_sha256=pin, raw_sha256=seal['raw_sha256'],
                           import_receipt_sha256=hashlib.sha256(receipt).hexdigest(),
                           catalogue_received_ms=catalogues[-1]['received_ms'])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Reject before a second request can leave the allowlist.


def get_capture(url):
    need(re.fullmatch(r'https://data-api\.polymarket\.com/v2/resolutions\?condition=0x[0-9a-fA-F]{64}|https://gamma-api\.polymarket\.com/markets/[0-9]{1,32}|https://clob\.polymarket\.com/book\?token_id=[0-9]{1,100}', url), 'PUBLIC_GET_ALLOWLIST')
    started = time.time_ns() // 1000000
    mono = time.monotonic_ns()
    req = urllib.request.Request(url, headers={'User-Agent': 'TradingOS-ORDERS-OFF-measurement'}, method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
            need(response.geturl() == url, 'PUBLIC_GET_REDIRECT')
            status, raw = response.status, response.read(2_000_001)
    except urllib.error.HTTPError as error:
        need(error.geturl() == url, 'PUBLIC_GET_REDIRECT')
        status, raw = error.code, error.read(2_000_001)
    received = time.time_ns() // 1000000
    mono_end = time.monotonic_ns()
    need(len(raw) <= 2_000_000, 'PUBLIC_RESPONSE_LIMIT')
    need(abs((received - started) - (mono_end - mono) / 1e6) <= 1000, 'CAPTURE_CLOCK_STEP')
    return dict(method='GET', url=url, http_status=status, request_ms=started,
                received_ms=received, request_monotonic_ns=mono,
                received_monotonic_ns=mono_end, raw_text=raw.decode('utf-8'),
                raw_sha256=hashlib.sha256(raw).hexdigest())


def run(archive, seal, market_id, destination, *, signal=None, repeat=1, interval=10):
    member, proof = membership(archive, seal, market_id)
    return run_member(member, proof, destination, signal=signal, repeat=repeat, interval=interval)


def run_member(member, proof, destination, *, signal=None, repeat=1, interval=10):
    market_id = member['id']
    need(type(repeat) is int and 1 <= repeat <= 3 and 1 <= interval <= 60, 'BOUNDED_MEASUREMENT_ONLY')
    need(isinstance(market_id, str) and re.fullmatch(r'[0-9]{1,32}', market_id), 'MARKET_ID')
    tokens = member['tokens']
    need(isinstance(tokens, list) and len(tokens) == 2 and all(isinstance(t, str) and re.fullmatch(r'[0-9]{1,100}', t) for t in tokens) and len(set(tokens)) == 2, 'CATALOGUE_TOKEN_PAIR')
    if signal is not None:
        need(signal.get('market_id') == market_id and signal.get('token_id') in tokens and measurement._pin(signal.get('policy_sha256')) and measurement._ms(signal.get('received_ms')), 'SUPPLIED_SIGNAL_IDENTITY')
    destination = Path(destination).absolute()
    need(not destination.exists() and not any(p.is_symlink() for p in (destination, *destination.parents)), 'DESTINATION_CREATE_EXCLUSIVE')
    mkdirs_durable(destination.parent)
    destination.mkdir(mode=0o700)
    once(destination / 'source-membership.json', encoded(dict(market=member, proof=proof)))
    once(destination / 'input-signal.json', encoded(signal))
    summaries = []
    for index in range(repeat):
        if index:
            time.sleep(interval)
        folder = destination / ('sample-' + str(index))
        mkdirs_durable(folder)
        try:
            gamma = get_capture('https://gamma-api.polymarket.com/markets/' + market_id)
            once(folder / 'gamma.json', encoded(gamma))
            before_books = time.time_ns() // 1000000
            m = market_input(gamma, market_id, decision_ms=before_books)
            need(m['tokens'] == tokens, 'CURRENT_TOKEN_PAIR_DRIFT_NO_SUBSTITUTION')
            captures = []
            for token_index, token in enumerate(tokens):
                c = get_capture('https://clob.polymarket.com/book?token_id=' + token)
                once(folder / ('book-' + str(token_index) + '.json'), encoded(c))
                captures.append(c)
            decision_ms = time.time_ns() // 1000000
            m = market_input(gamma, market_id, decision_ms=decision_ms)
            books = [book_input(c, m, token, decision_ms=decision_ms) for c, token in zip(captures, tokens)]
            if signal is not None:
                for stamp in (signal['received_ms'], signal.get('signal_ms', signal['received_ms']), signal.get('score_on_mac_ms', decision_ms)):
                    need(measurement._ms(stamp) and 0 <= decision_ms - stamp <= 120000, 'STALE_SIGNAL_AT_MEASUREMENT')
            results = []
            for b in books:
                supplied = signal is not None and signal['token_id'] == b['asset_id']
                s = signal if supplied else dict(market_id=market_id, token_id=b['asset_id'],
                    policy_sha256=hashlib.sha256(Path(measurement.__file__).read_bytes()).hexdigest(),
                    received_ms=decision_ms, model_price=None, kind='NON_STRATEGIC_DEPTH_PROBE')
                r = measurement.measure(s, b, m, decision_ms=decision_ms, model_budget=s.get('stake_model_usd', 100), limit_price=s.get('price_limit', '.985'))
                results.append(dict(measurement=r, normalized_book=b, supplied_signal=supplied))
            out = dict(schema='POLY_PUBLIC_SNAPSHOT_MEASUREMENT_V1', sample_index=index,
                decision_ms=decision_ms, market_id=market_id, metadata=m, outcomes=results,
                source_membership=proof, supplied_signal_sha256=measurement.sha(signal) if signal else None,
                signal_observation_id=signal.get('signal_observation_id', measurement.sha(signal)) if signal is not None else None,
                independent_opportunities=0, independence_qualified=False,
                real_strategy_signal_verified=False,
                full_rest_snapshots=True, stream_continuity_proven=False, simultaneous_pair=False,
                displayed_depth_not_fill=True, actual_fees=None, actual_net_pnl=None,
                order_posts=0, real_fills=0, money_authority=False)
            once(folder / 'measurement.json', encoded(out))
            summary = dict(sample=index, decision_ms=decision_ms,
                status='MEASURED_SNAPSHOTS' if all(x['measurement']['status'] == 'MEASURED_ORDERS_OFF' for x in results) else 'UNKNOWN',
                fee_rate=m.get('fee_rate'), fee_issues=m['fee_issues'],
                accepting_orders=m['accepting_orders'], outcomes=[dict(token=x['normalized_book']['asset_id'],
                    status=x['measurement']['status'], best_ask=x['measurement']['best_ask'],
                    depth_to_limit=x['measurement']['depth_to_limit'], vwap=x['measurement']['observed_vwap'],
                    estimated_fee=x['measurement']['estimated_fee'], book_age_ms=x['measurement']['book_age_ms'],
                    issues=x['measurement']['issues']) for x in results])
        except Exception as error:
            summary = dict(sample=index, decision_ms=time.time_ns() // 1000000,
                           status='UNKNOWN', reason=type(error).__name__ + ':' + str(error)[:300])
        once(folder / 'summary.json', encoded(summary))
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
        if summary['status'] == 'UNKNOWN':
            break  # No retry or silent market substitution after uncertain input.
    result = dict(schema='POLY_BOUNDED_SNAPSHOT_RUN_V1', market_id=market_id,
        observed_ms=time.time_ns() // 1000000, samples=summaries, requested_samples=repeat,
        supplied_signal=signal is not None, distinct_supplied_signals=1 if signal is not None else 0,
        actual_strategy_trades=0, real_fills=0, order_posts=0, continuous_worker_installed=False)
    once(destination / 'summary.json', encoded(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--capture', action='store_true')
    modes.add_argument('--cycle-once', action='store_true')
    parser.add_argument('--research-root', type=Path)
    parser.add_argument('--signal-journal')
    parser.add_argument('--signal-epoch', choices=['E2_20261104'])
    parser.add_argument('--state-root', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--catalogue-seal', type=Path)
    parser.add_argument('--market-id')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--signal', type=Path)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--interval-seconds', type=float, default=10)
    args = parser.parse_args(argv)
    if args.cycle_once:
        from research_lab.polymarket_signal_cycle_v1 import cycle_once, cycle_many
        root = args.research_root if args.research_root is not None else Path.cwd() / 'research_lab'
        state = args.state_root if args.state_root is not None else ROOT / '.private/poly_signal_cycle_20261104'
        result = cycle_many(root, state, journals=(args.signal_journal,) if args.signal_journal else None, epoch=args.signal_epoch)
        print(json.dumps(result), flush=True)
        return 2 if result['status'] == 'UNKNOWN' else 0
    if not args.capture:
        print(json.dumps(dict(status='NO_NETWORK_ORDERS_OFF', order_posts=0, money_authority=False)))
        return 0
    need(all(x is not None for x in (args.archive, args.catalogue_seal, args.market_id, args.destination)), 'EXPLICIT_CAPTURE_PATHS_REQUIRED')
    signal = json.loads(read(args.signal)) if args.signal else None
    result = run(args.archive, args.catalogue_seal, args.market_id, args.destination,
                 signal=signal, repeat=args.repeat, interval=args.interval_seconds)
    return 0 if result['samples'] and all(s['status'] == 'MEASURED_SNAPSHOTS' for s in result['samples']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
