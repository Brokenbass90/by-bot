"""Public-only cold-epoch observations; never grants route or order authority.

This exports source-backed bars and current-limit funding scenarios for the
existing handoff builder. It neither calls that builder nor updates a money DB.
"""
from __future__ import annotations

import argparse
import fcntl
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.att1_lifecycle_profile import BROKER_ADMISSION_SYMBOLS
from scripts.run_att1_lifecycle_zero_risk import decode_public_json, _NoRedirect

M5 = 300_000
H1 = 3_600_000


def _observation_get(symbol, *, kline):
    # The lifecycle runner intentionally accepts H1 only. Do not change its
    # contract: this separate observation seam has one fixed public M5 endpoint.
    if symbol not in BROKER_ADMISSION_SYMBOLS:
        raise ValueError('M5 symbol outside existing broker admission')
    params = {'category':'linear','symbol':symbol}
    if kline: params.update(interval='5', limit=1000)
    path = '/v5/market/kline' if kline else '/v5/market/instruments-info'
    request = Request('https://api.bybit.com' + path + '?' + urlencode(params), method='GET',
                      headers={'User-Agent':'att1-cold-observation/1'})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=10) as response:
        if response.status != 200:
            raise ValueError('M5 public HTTP status')
        raw = response.read(5_000_001)
    value = decode_public_json(raw, 5_000_000)
    result = value.get('result', {})
    if (type(value.get('retCode')) is not int or value['retCode'] != 0
            or result.get('category') != 'linear'
            or (kline and result.get('symbol') != symbol)
            or (not kline and (not isinstance(result.get('list'), list)
                or any(not isinstance(r,dict) or r.get('symbol') != symbol for r in result['list'])))):
        raise ValueError('M5 public envelope')
    return value


def request_m5(symbol):
    return _observation_get(symbol, kline=True)


def request_instrument(symbol):
    return _observation_get(symbol, kline=False)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def decimal(value):
    if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
        raise ValueError('invalid decimal')
    return Fraction(value)


def analyze_quarantine(pages, *, fence_ms, observed_ms):
    if (type(fence_ms) is not int or fence_ms <= 0 or fence_ms % H1
            or type(observed_ms) is not int or observed_ms <= 0
            or set(pages) != set(BROKER_ADMISSION_SYMBOLS)):
        raise ValueError('invalid clock or admitted-symbol coverage')
    by_symbol = {}
    fence_available = True
    for symbol, page in pages.items():
        server = page.get('time')
        result = page.get('result', {})
        if (type(page.get('retCode')) is not int or page['retCode'] != 0
                or type(server) is not int or not 0 <= observed_ms - server < 60_000
                or result.get('category') != 'linear' or result.get('symbol') != symbol
                or not isinstance(result.get('list'), list)):
            raise ValueError('invalid public kline envelope')
        rows = {}; seen = set(); fence_seen = False
        for row in result['list']:
            if not isinstance(row, list) or len(row) != 7 or not isinstance(row[0], str) or not row[0].isdigit():
                raise ValueError('invalid M5 row')
            start = int(row[0])
            if start % M5 or start in seen or start > server:
                raise ValueError('duplicate/misaligned/future M5 start')
            seen.add(start)
            o,h,l,c,v,t = [decimal(x) for x in row[1:]]
            if not (0 < l <= o <= h and l <= c <= h and v >= 0 and t >= 0):
                raise ValueError('invalid M5 prices/volume')
            close = start + M5
            if close > min(server, observed_ms):
                continue
            if close == fence_ms:
                fence_seen = True
            if close > fence_ms:
                rows[close] = row
        fence_available = fence_available and fence_seen
        by_symbol[symbol] = rows
    common = sorted(set.intersection(*(set(x) for x in by_symbol.values())))
    previous, run, completed = fence_ms, 0, None
    bars = []
    for close in common:
        run = run + 1 if close == previous + M5 else 1
        previous = close
        if run == 96 and completed is None:
            completed = close
        bars.append({'close_ms': close, 'source_sha256': digest({s: by_symbol[s][close] for s in by_symbol})})
    current = bool(common) and 0 <= observed_ms - common[-1] < M5
    return {'fence_h1_ms': fence_ms, 'fence_available': fence_available,
            'observed_ms': observed_ms, 'symbols': list(BROKER_ADMISSION_SYMBOLS),
            'per_symbol_closed_bars': {s: len(r) for s,r in by_symbol.items()},
            'consecutive_closed_m5': run, 'quarantine_complete_ms': completed,
            'current': current, 'common_bars': bars, 'orders_allowed': False}


def funding_stress(instrument, *, side, notional_usdt):
    interval = instrument.get('fundingInterval')
    if type(interval) is not int or interval <= 0 or side not in ('LONG', 'SHORT'):
        raise ValueError('invalid funding interval/side')
    lower, upper = decimal(instrument.get('lowerFundingRate')), decimal(instrument.get('upperFundingRate'))
    notional = decimal(notional_usdt)
    if lower > upper or notional <= 0:
        raise ValueError('invalid funding bounds/notional')
    hold_minutes = 4032 * 5  # Existing frozen 14-day hold, unchanged.
    events = (hold_minutes + interval - 1) // interval + 1
    rate = max(Fraction(0), -lower if side == 'SHORT' else upper)
    return {'symbol': instrument['symbol'], 'side': side, 'hold_minutes': hold_minutes,
            'funding_interval_minutes': interval, 'lower_rate': str(lower), 'upper_rate': str(upper),
            'events_with_phase_reserve': events, 'notional_envelope_usdt': notional_usdt,
            'funding_usdt': str(notional * rate * events),
            'future_ceiling_proven': False, 'policy_approved': False,
            'assumption': 'Current interval/limits persist; fixed notional envelope. Excludes fees/slippage and price-envelope growth.'}


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def collect(retirement_path, output_dir):
    retirement_raw = retirement_path.read_bytes()
    retirement = json.loads(retirement_raw)
    retired, fence = retirement.get('retired_at_ms'), retirement.get('fence_h1_ms')
    if (retirement.get('schema_id') != 'att1_old_retirement_receipt_v1'
            or retirement.get('retirement_verified') is not True
            or retirement.get('orders_allowed') is not False
            or retirement.get('initial_process_retirement_flag') != '1'
            or type(retired) is not int or not 0 < retired <= int(time.time()*1000)
            or fence != (retired + H1 - 1) // H1 * H1):
        raise ValueError('accepted retirement receipt required; no fabricated epoch')
    retirement_sha = hashlib.sha256(retirement_raw).hexdigest()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (output_dir / 'collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = output_dir / 'observation.json'
        saved = json.loads(state_path.read_text()) if state_path.exists() else None
        if saved and saved['retirement_receipt_sha256'] != retirement_sha:
            raise ValueError('retirement source changed; no silent epoch reset')
        try:
            if (len(list(output_dir.glob('capture_*.json'))) >= 256
                    or shutil.disk_usage(output_dir).free < 500_000_000):
                raise ValueError('bounded capture storage exhausted; preserve archives')
            pages, instruments, funding = {}, {}, {}
            for symbol in BROKER_ADMISSION_SYMBOLS:
                pages[symbol] = request_m5(symbol)
                instrument = request_instrument(symbol)
                rows = instrument['result']['list']
                if len(rows) != 1 or rows[0].get('status') != 'Trading':
                    raise ValueError('admitted contract is not currently Trading')
                instruments[symbol] = instrument
                funding[symbol] = {**funding_stress(rows[0], side='SHORT', notional_usdt='5'),
                                   'source_sha256': digest(instrument)}
            now = int(time.time()*1000)
            result = analyze_quarantine(pages, fence_ms=fence, observed_ms=now)
            capture = {'observed_ms':now,'klines':pages,'instruments':instruments}
            capture_path = output_dir / ('capture_' + str(now) + '.json')
            atomic_json(capture_path, capture)
            proven = result['quarantine_complete_ms']
            if saved and saved.get('first_quarantine_complete_ms') is not None:
                if proven != saved['first_quarantine_complete_ms']:
                    raise ValueError('earliest maturity no longer source-backed; preserve prior evidence')
            status = ('QUARANTINE_OBSERVED' if proven and result['current'] and result['fence_available']
                      else 'QUARANTINE_IN_PROGRESS')
            result.update({'status':status,'capture_path':str(capture_path),
                           'capture_sha256':hashlib.sha256(capture_path.read_bytes()).hexdigest(),
                           'retirement_receipt_sha256':retirement_sha,
                           'first_quarantine_complete_ms':proven,
                           'funding_current_limit_scenarios':funding,
                           'actual_handoff_ready':False,
                           'scope':'initial eight execution-admitted symbols; Fixed51 bootstrap not established',
                           'broker_writes':0,'private_api_calls':0})
        except Exception as exc:
            result = {'status':'BLOCKED_OBSERVATION','error_type':type(exc).__name__,
                      'observed_ms':int(time.time()*1000),'current':False,
                      'retirement_receipt_sha256':retirement_sha,
                      'first_quarantine_complete_ms':saved.get('first_quarantine_complete_ms') if saved else None,
                      'actual_handoff_ready':False,'orders_allowed':False,'broker_writes':0,'private_api_calls':0}
            atomic_json(state_path, result)
            raise
        atomic_json(state_path, result)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retirement-receipt', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    receipt = collect(args.retirement_receipt, args.output_dir)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('common_bars','funding_current_limit_scenarios')}, indent=2))
