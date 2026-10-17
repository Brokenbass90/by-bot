"""Local, transport-free IBIT/BTC DATA-ONLY v1.1 adapter.

Input is an explicitly saved source envelope, never credentials or live clients.
Each source is {received_at: timezone-aware ISO UTC timestamp, raw: API JSON}.
received_at MUST be the actual first receipt of that observation, not import time.
Saved-source timestamps are caller evidence; this offline adapter cannot attest
network receipt provenance. Calendar is broker-supplied, never inferred weekdays.
No execution capability exists; data_eligible is only a source quality diagnostic.
"""
from __future__ import annotations

import ast
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import stat
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
RULE_SHA = '48d57d4ca06dbfe634e22c2435f1d2c1ddff83d18f8ea9fe95858c1987c48906'
RULE_COMMIT = '07438fc782ac15157a5858ed139651cb7a4de7b1'
RULE_PATH = 'research_lab/fabrika/etf_premiya_sobytiya.py'
_VENDOR = Path(__file__).parent / 'vendor/etf_premiya_20261017/etf_premiya_sobytiya.py'
_SOURCES = {'calendar', 'alpaca_sip', 'binance', 'bybit'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _stamp(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    else:
        raise ValueError('timestamp must be timezone-aware ISO string')
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('naive timestamp')
    return parsed.astimezone(UTC)


def checked_path(value, regular=False):
    """Reject links and nonregular files without resolving attacker-controlled paths.

    Runtime roots must use physical absolute paths (for example /private/tmp on
    macOS). These checks protect against pre-existing aliases; the store requires
    exclusive filesystem ownership, not hostile concurrent directory replacement.
    """
    path = Path(os.path.abspath(value))
    for component in [*reversed(path.parents), path]:
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError('symlink in storage or input path')
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError('non-directory path ancestor')
        if component == path and regular and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise ValueError('file must be regular and not hardlinked')
    return path


def _open_file(path, mode):
    path = checked_path(path, regular=True)
    flags = {'rb':os.O_RDONLY, 'ab':os.O_WRONLY|os.O_APPEND|os.O_CREAT,
             'r+b':os.O_RDWR, 'a+b':os.O_RDWR|os.O_APPEND|os.O_CREAT,
             'xb':os.O_WRONLY|os.O_CREAT|os.O_EXCL}[mode]
    fd = os.open(path, flags|os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise ValueError('opened file is nonregular or hardlinked')
    return os.fdopen(fd, mode)


def _millis(stamp):
    delta = _stamp(stamp)-dt.datetime(1970,1,1,tzinfo=UTC)
    return delta.days*86400000+delta.seconds*1000+delta.microseconds//1000


def _day(value):
    if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
        raise ValueError('session must be YYYY-MM-DD')
    return dt.date.fromisoformat(value)


def _price(value):
    if isinstance(value, bool):
        raise ValueError('invalid boolean price')
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('price must be finite and positive')
    return value


def _rule_function():
    raw = _VENDOR.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RULE_SHA:
        raise ValueError('frozen rule hash mismatch')
    tree = ast.parse(raw)
    # Compile ONLY the unchanged pure function. Do not execute research imports,
    # sys.path mutation, filesystem loaders, main/evaluator or actual outcomes.
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sobytiya')
    return compile(ast.Module(body=[fn], type_ignores=[]), str(_VENDOR), 'exec')


def _valid_rows(rows):
    kept = [r for r in rows if r.get('ibit_close') is not None and r.get('btc_ref_binance') is not None
            and r.get('freshness') != 'MISSING']
    if len({r['session'] for r in kept}) != len(kept):
        raise ValueError('duplicate rule session')
    return sorted(kept, key=lambda r: r['session'])


def frozen_events(rows):
    """Run the exact pinned function over supplied rows only, no real-source reads."""
    rows = _valid_rows(rows)
    etf = {r['session']: {'IBIT': _price(r['ibit_close'])} for r in rows}
    btc = {r['session']: _price(r['btc_ref_binance']) for r in rows}
    scope = {'np': np, 'dt': dt, 'M': SimpleNamespace(
        etf_ryad=lambda tickers: etf,
        coin_na_zakrytii=lambda symbol: btc.get, NY=NY)}
    exec(_rule_function(), scope)
    return scope['sobytiya']('IBIT', 'BTCUSDT')


def rule_values(rows):
    """Expose the frozen ratio/20-prior median/60-prior sample-SD diagnostics.

    Event/sign come from the exact pinned function, not a reimplemented gate.
    There is no interpolation, outcome read or strategy evaluation.
    """
    ordered = _valid_rows(rows)
    out = {'premiya': None, 'z': None, 'sobytie': False, 'znak': 0,
           'history_sessions': len(ordered), 'event_ts': None}
    if not ordered:
        return out
    rat = [_price(r['ibit_close']) / _price(r['btc_ref_binance']) for r in ordered]
    prem = [rat[i] / float(np.median(rat[i-20:i])) - 1 for i in range(20, len(rat))]
    if not prem:
        return out
    out['premiya'] = prem[-1]
    history = prem[max(0, len(prem)-1-60):-1]
    if len(history) < 40:
        return out
    sd = float(np.std(history, ddof=1))
    out['z'] = prem[-1] / sd if sd > 0 else 0.0
    current = ordered[-1]['session']
    event = next((v for v in frozen_events(ordered) if v['den'] == current), None)
    if event:
        out.update(sobytie=True, znak=event['znak'], event_ts=dt.datetime.fromtimestamp(event['t_ms']/1000, UTC).isoformat())
    return out


class Adapter:
    """Append-only decision/QA store protected by a process-shared flock.

    New sessions must arrive chronologically. A finalized MISSING session cannot
    later be backfilled; revised raw observations are preserved but never rewrite
    a decision or its historical inputs. Only an unterminated tail is recovered.
    """
    def __init__(self, root):
        _rule_function()
        self.root = checked_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        checked_path(self.root)
        # Serialize marker initialization across processes without touching files
        # belonging to a foreign nonempty directory.
        fd = os.open(self.root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            marker = self.root / '.ibit_data_only_v1.json'
            expected = canonical({'owner':'IBIT_BTC_DATA_ONLY_V1', 'schema':1})
            if marker.exists() or marker.is_symlink():
                with _open_file(marker, 'rb') as f:
                    if f.read() != expected:
                        raise ValueError('foreign runtime marker')
            else:
                if any(self.root.iterdir()):
                    raise ValueError('foreign nonempty runtime root')
                self._immutable(marker, expected)
        finally:
            os.close(fd)

    @contextmanager
    def _lock(self):
        with _open_file(self.root / '.adapter.lock', 'a+b') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _read(self, name):
        path = checked_path(self.root / name, regular=True)
        if not path.exists():
            return []
        with _open_file(path, 'rb') as f:
            data = f.read()
        if data and not data.endswith(b'\n'):
            end = data.rfind(b'\n') + 1
            # Preserve crash evidence before truncating ONLY the incomplete tail.
            tail = data[end:]
            self._immutable(self.root / 'recovered_tails' / (hashlib.sha256(tail).hexdigest()+'.bin'), tail)
            with _open_file(path, 'r+b') as f:
                f.truncate(end); f.flush(); os.fsync(f.fileno())
            data = data[:end]
        rows = []
        for line in data.splitlines():
            row = json.loads(line)
            key = 'row_sha' if name == 'decisions.jsonl' else 'qa_sha'
            if row.get(key) != _sha({k:v for k,v in row.items() if k != key}):
                raise ValueError('journal hash mismatch')
            if name == 'decisions.jsonl':
                for source, source_sha in row['source_sha'].items():
                    if source not in _SOURCES or len(source_sha) != 64 or any(c not in '0123456789abcdef' for c in source_sha):
                        raise ValueError('invalid source identity')
                    raw_path = checked_path(self.root / 'raw' / source / (source_sha+'.json'), regular=True)
                    if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != source_sha:
                        raise ValueError('preserved source hash mismatch')
            rows.append(row)
        if name == 'decisions.jsonl' and len({r['session'] for r in rows}) != len(rows):
            raise ValueError('duplicate journal session')
        if name == 'decisions.jsonl' and rows:
            _, warmup_sha = self._warmup()
            if any(row.get('warmup_sha') != warmup_sha for row in rows):
                raise ValueError('decision warmup identity mismatch')
        return rows

    def _append(self, name, row):
        key = 'row_sha' if name == 'decisions.jsonl' else 'qa_sha'
        row = {**row, key: _sha(row)}
        with _open_file(self.root / name, 'ab') as f:
            f.write(canonical(row)+b'\n'); f.flush(); os.fsync(f.fileno())
        return row

    @staticmethod
    def _immutable(path, raw):
        path = checked_path(path, regular=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        checked_path(path, regular=True)
        try:
            with _open_file(path, 'xb') as f:
                f.write(raw); f.flush(); os.fsync(f.fileno())
        except FileExistsError:
            with _open_file(path, 'rb') as f:
                existing = f.read()
            if existing != raw:
                raise ValueError('immutable source hash collision or corruption')

    def _preserve(self, name, raw):
        h = _sha(raw)
        self._immutable(self.root / 'raw' / name / (h+'.json'), canonical(raw))
        return h

    def _first_receipt(self, name, session, source_sha, receipt, earliest):
        # Preserve the first valid post-close receipt across incomplete retries.
        # A pre-close observation remains raw evidence but is not a closed bar.
        if receipt < earliest:
            return receipt
        path = checked_path(self.root / 'first_receipts' / session / name / (source_sha+'.json'), regular=True)
        if path.exists():
            saved = json.loads(path.read_bytes())
            body = {k:v for k,v in saved.items() if k != 'receipt_sha'}
            if saved.get('receipt_sha') != _sha(body) or body.get('source_sha') != source_sha:
                raise ValueError('first source receipt hash mismatch')
            return _stamp(body['received_at'])
        body = {'source_sha':source_sha, 'received_at':receipt.isoformat()}
        self._immutable(path, canonical({**body, 'receipt_sha':_sha(body)}))
        return receipt

    def decisions(self):
        with self._lock():
            return self._read('decisions.jsonl')

    def qa_records(self):
        with self._lock():
            return self._read('qa.jsonl')

    def historical_seed_summary(self):
        with self._lock():
            rows, pin = self._warmup()
            return {'status':'HISTORICAL_WARMUP_ONLY' if rows else 'NO_HISTORY_SEED',
                    'sessions':len(rows),'seed_sha':pin,'prospective_sessions':0,
                    'orders_enabled':False}

    def _warmup(self, now=None):
        path = checked_path(self.root / 'warmup.json', regular=True)
        if not path.exists():
            return [], None
        with _open_file(path, 'rb') as f:
            seed = json.load(f)
        if seed.get('seed_sha') != _sha({k:v for k,v in seed.items() if k != 'seed_sha'}):
            raise ValueError('warmup hash mismatch')
        if seed.get('rule_sha') != RULE_SHA or seed.get('status') != 'HISTORICAL_WARMUP_ONLY':
            raise ValueError('warmup rule identity')
        if now is not None and any(_stamp(value) > now for value in seed['source_received_at'].values()):
            raise ValueError('warmup not available at decision')
        for name, pin in seed['source_sha'].items():
            if name not in {'calendar', 'alpaca_sip', 'binance'} or not isinstance(pin, str) or len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
                raise ValueError('warmup source identity')
            with _open_file(self.root / 'raw' / name / (pin+'.json'), 'rb') as f:
                if hashlib.sha256(f.read()).hexdigest() != pin:
                    raise ValueError('warmup source hash mismatch')
        return seed['rows'], seed['seed_sha']

    def seed_history(self, sources, now):
        """Seal archival inputs once BEFORE prospective decisions, never backdate.

        Historical retrievals retain actual receipt timestamps. They create no
        decision, freshness PASS, QA PASS or prospective session. Exactly the
        frozen rule consumes these prices, followed by future decision rows.
        The 81-session minimum supplies all 60 prior premium observations.
        """
        now = _stamp(now)
        if not isinstance(sources, dict) or set(sources) != {'calendar','alpaca_sip','binance'}:
            raise ValueError('warmup sources')
        receipts = {name:_stamp(source['received_at']) for name,source in sources.items()}
        if any(receipt > now for receipt in receipts.values()):
            raise ValueError('warmup receipt in future')
        sip, btc = sources['alpaca_sip'], sources['binance']
        if (sip.get('feed') != 'sip' or sip.get('timeframe') != '1Day'
            or btc.get('symbol') != 'BTCUSDT' or btc.get('interval') != '1h'
            or sip['raw'].get('next_page_token')):
            raise ValueError('warmup source provenance or pagination')
        calendar = sources['calendar']['raw']
        if not isinstance(calendar,list) or not 81 <= len(calendar) <= 400:
            raise ValueError('warmup requires 81 to 400 complete broker sessions')
        days = [r['date'] for r in calendar]
        if days != sorted(set(days)):
            raise ValueError('warmup calendar order or duplicate')
        bars = sip['raw']['bars']['IBIT']
        if not isinstance(bars,list) or len(bars) != len(days):
            raise ValueError('warmup SIP session coverage')
        closes = {}
        for bar in bars:
            stamp = _stamp(bar['t']);day = stamp.astimezone(NY).date().isoformat()
            if day in closes or day not in days:
                raise ValueError('warmup SIP session identity')
            closes[day] = (stamp,_price(bar['c']))
        hourly = btc['raw']
        if not isinstance(hourly,list) or len(hourly) > 12000:
            raise ValueError('warmup BTC bound')
        indexed = {}
        for bar in hourly:
            key = int(bar[0])
            if key in indexed:
                raise ValueError('warmup duplicate BTC hour')
            indexed[key] = bar
        rows = []
        for cal in calendar:
            day = _day(cal['date'])
            opened = dt.datetime.combine(day,dt.time.fromisoformat(cal['open']),NY)
            closed = dt.datetime.combine(day,dt.time.fromisoformat(cal['close']),NY).astimezone(UTC)
            ref_end = dt.datetime.combine(day,dt.time(16),NY).astimezone(UTC)
            if opened.time() != dt.time(9,30) or closed <= opened or closed.astimezone(NY).time() not in (dt.time(13),dt.time(16)):
                raise ValueError('warmup calendar geometry')
            stamp, price = closes[day.isoformat()]
            start = _millis(ref_end)-3600000;bar = indexed.get(start)
            if (stamp > closed or any(receipt < ref_end for receipt in receipts.values())
                or bar is None or int(bar[6]) != start+3599999):
                raise ValueError('warmup missing or noncausal reference')
            rows.append({'session':day.isoformat(),'ibit_close':price,'btc_ref_binance':_price(bar[4]),
                         'freshness':'HISTORICAL_WARMUP'})
        with self._lock():
            if self._read('decisions.jsonl'):
                raise ValueError('warmup must be sealed before prospective decisions')
            hashes = {name:self._preserve(name,source['raw']) for name,source in sources.items()}
            body = {'schema':'IBIT_HISTORICAL_WARMUP_V1','status':'HISTORICAL_WARMUP_ONLY',
                    'rule_sha':RULE_SHA,'source_sha':hashes,'source_received_at':{k:v.isoformat() for k,v in receipts.items()},
                    'rows':rows,'sessions':len(rows),'prospective_sessions':0,'orders_enabled':False}
            seed = {**body,'seed_sha':_sha(body)}
            self._immutable(self.root/'warmup.json',canonical(seed))
            self._warmup()
            return seed

    def _pending(self, row):
        qa = self._read('qa.jsonl')
        if not any(q['row_sha'] == row['row_sha'] for q in qa):
            self._append('qa.jsonl', {'session':row['session'], 'row_sha':row['row_sha'],
                                    'status':'PENDING_SVERKA', 'decided_at':row['decided_at']})

    def import_session(self, session, sources, now):
        try:
            return self._import(session, sources, now)
        except (KeyError, TypeError, IndexError, OverflowError) as error:
            raise ValueError('malformed saved source envelope') from error

    def _import(self, session, sources, now):
        day = _day(session); now = _stamp(now)
        if not isinstance(sources, dict) or set(sources) - _SOURCES or 'calendar' not in sources:
            raise ValueError('unknown source or missing broker calendar')
        received = {}
        for name, source in sources.items():
            received[name] = _stamp(source['received_at'])
            if received[name] > now:
                raise ValueError('source received in future')
            canonical(source)
            if name == 'alpaca_sip' and (source.get('feed') != 'sip' or source.get('timeframe') != '1Day'):
                raise ValueError('IBIT requires SIP daily request provenance')
            if name == 'binance' and (source.get('symbol') != 'BTCUSDT' or source.get('interval') != '1h'):
                raise ValueError('Binance requires BTCUSDT 1h request provenance')
            if name == 'bybit' and source.get('interval') != '60':
                raise ValueError('Bybit requires hourly request provenance')
        calendar = sources['calendar']['raw']
        if not isinstance(calendar, list) or len(calendar) != 1 or calendar[0]['date'] != session:
            raise ValueError('require exactly one matching broker calendar session')
        cal = calendar[0]
        opened = dt.datetime.combine(day, dt.time.fromisoformat(cal['open']), NY)
        closed = dt.datetime.combine(day, dt.time.fromisoformat(cal['close']), NY).astimezone(UTC)
        if opened.time() != dt.time(9,30) or closed <= opened or closed.astimezone(NY).time() not in (dt.time(13), dt.time(16)):
            raise ValueError('unsupported broker session geometry')
        ref_end = dt.datetime.combine(day, dt.time(16), NY).astimezone(UTC)
        ref_open_ms = int((ref_end-dt.timedelta(hours=1)).timestamp()*1000)
        with self._lock():
            hashes = {name:self._preserve(name, value['raw']) for name,value in sources.items()}
            # Preserve timestamped envelopes as well as canonical raw responses.
            self._preserve('observations', {'session':session, 'sources':sources})
            rows = self._read('decisions.jsonl')
            warmup, warmup_sha = self._warmup(now=now)
            previous = next((r for r in rows if r['session'] == session), None)
            if previous:
                if previous.get('warmup_sha') != warmup_sha:
                    raise ValueError('decision warmup identity mismatch')
                self._pending(previous)
                return previous
            if warmup and session <= warmup[-1]['session']:
                raise ValueError('prospective session warmup overlap')
            if rows and session <= max(r['session'] for r in rows):
                raise ValueError('out-of-order session would revise frozen history')
            ready = True; ibit = binance = bybit = bar_t = None
            if 'alpaca_sip' in sources:
                raw = sources['alpaca_sip']['raw']; bars = raw['bars'].get('IBIT', [])
                if not isinstance(bars, list) or len(bars) > 1:
                    raise ValueError('at most one daily IBIT bar required')
                if bars:
                    bar = bars[0]; bar_t = bar['t']; bar_stamp = _stamp(bar_t)
                    if bar_stamp.astimezone(NY).date() != day:
                        ready = False
                    elif bar_stamp > closed:
                        raise ValueError('after-hours IBIT timestamp')
                    else:
                        ibit = _price(bar['c'])
                        received['alpaca_sip'] = self._first_receipt('alpaca_sip', session, hashes['alpaca_sip'], received['alpaca_sip'], closed)
                        ready &= received['alpaca_sip'] >= closed
                else:
                    ready = False
            else:
                ready = False
            if 'binance' in sources:
                bars = sources['binance']['raw']
                if not isinstance(bars, list) or len(bars) > 1:
                    raise ValueError('at most one Binance reference bar required')
                if bars:
                    if int(bars[0][0]) != ref_open_ms or int(bars[0][6]) != ref_open_ms+3599999:
                        raise ValueError('Binance must contain the frozen closed reference bar')
                    binance = _price(bars[0][4])
                    received['binance'] = self._first_receipt('binance', session, hashes['binance'], received['binance'], ref_end)
                    ready &= received['binance'] >= ref_end
                else:
                    ready = False
            else:
                ready = False
            if 'bybit' in sources:
                raw = sources['bybit']['raw']; result = raw['result']; bars = result['list']
                if raw['retCode'] != 0 or result['symbol'] != 'BTCUSDT' or result['category'] != 'linear':
                    raise ValueError('wrong Bybit reference identity')
                if not isinstance(bars, list) or len(bars) > 1:
                    raise ValueError('at most one Bybit reference bar required')
                if bars:
                    if int(bars[0][0]) != ref_open_ms:
                        raise ValueError('Bybit must contain the frozen closed reference bar')
                    bybit = _price(bars[0][4])
                    received['bybit'] = self._first_receipt('bybit', session, hashes['bybit'], received['bybit'], ref_end)
                    ready &= received['bybit'] >= ref_end
                else:
                    ready = False
            else:
                ready = False
            if now < closed or (not ready and now <= closed+dt.timedelta(hours=6)):
                return {'session':session, 'status':'NOT_READY', 'execution':'NO_SEND', 'orders_enabled':False}
            first_receipt = received.get('alpaca_sip')
            lag = (first_receipt-closed).total_seconds() if first_receipt is not None else None
            freshness = 'MISSING' if not ready or lag is None or lag > 21600 else 'FRESH' if lag <= 1800 else 'LATE'
            discrepancy_decimal = abs(Decimal(str(bybit))/Decimal(str(binance))-1) if binance is not None and bybit is not None else None
            discrepancy = float(discrepancy_decimal) if discrepancy_decimal is not None else None
            discrepancy_flag = discrepancy_decimal is not None and discrepancy_decimal > Decimal('0.002')
            half = closed.astimezone(NY).time() != dt.time(16)
            row = {'session':session, 'ibit_close':ibit, 'bar_t_raw':bar_t,
                   'session_close_ts':closed.isoformat(), 'received_at':first_receipt.isoformat() if first_receipt else None,
                   'source_received_at':{k:v.isoformat() for k,v in received.items()},
                   'btc_ref_binance':binance,'btc_ref_bybit':bybit,'btc_ref_end_ts':ref_end.isoformat(),
                   'btc_discrepancy':discrepancy,'btc_discrepancy_flag':discrepancy_flag,
                   'feed':'SIP' if ibit is not None else None,'sokrashchennyy':half,
                   'freshness':freshness,'decided_at':now.isoformat(),'rule_sha':RULE_SHA,
                   'rule_source_commit':RULE_COMMIT,'rule_source_path':RULE_PATH,'source_sha':hashes,
                   'execution':'NO_SEND','orders_enabled':False,'sverka_massive':'PENDING_SVERKA',
                   'status':'DECISION','data_eligible':freshness=='FRESH' and not half and discrepancy is not None and not discrepancy_flag,
                   'warmup_sha':warmup_sha}
            if freshness != 'MISSING':
                row.update(rule_values([*warmup, *rows, row]))
            else:
                row.update(premiya=None,z=None,sobytie=False,znak=0,event_ts=None,history_sessions=len(_valid_rows([*warmup,*rows])))
            row.update(received_at_ms=_millis(first_receipt) if first_receipt is not None else None,
                       session_close_ts_ms=_millis(closed), decided_at_ms=_millis(now),
                       source_received_at_ms={k:_millis(v) for k,v in received.items()})
            row = self._append('decisions.jsonl', row)
            self._pending(row)
            return row

    def reconcile(self, session, raw, received_at):
        """Record separate Massive QA; revisions never alter a decision."""
        _day(session); receipt = _stamp(received_at)
        try:
            if raw['date'] != session:
                raise ValueError('Massive wrong session')
            matches = [r for r in raw['rows'] if r[0] == 'IBIT']
            if len(matches) != 1:
                raise ValueError('exactly one Massive IBIT row required')
            close = _price(matches[0][4])
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError('malformed Massive response') from error
        with self._lock():
            row = next((r for r in self._read('decisions.jsonl') if r['session']==session), None)
            if row is None or row['ibit_close'] is None:
                raise ValueError('no matching IBIT decision for QA')
            if receipt < _stamp(row['session_close_ts']):
                raise ValueError('Massive receipt before session close')
            source_sha = self._preserve('massive', raw)
            qa = self._read('qa.jsonl')
            prior = next((q for q in qa if q['row_sha']==row['row_sha'] and q.get('source_sha')==source_sha),None)
            if prior:
                return prior
            self._pending(row)
            difference_decimal = abs(Decimal(str(row['ibit_close']))/Decimal(str(close))-1)
            difference = float(difference_decimal)
            return self._append('qa.jsonl', {'session':session,'row_sha':row['row_sha'],
                    'status':'DEFECT' if difference_decimal>Decimal('0.005') else 'SVERKA_PASS',
                    'difference':difference,'massive_close':close,'source_sha':source_sha,
                    'received_at':receipt.isoformat()})
