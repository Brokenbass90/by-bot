"""Bounded metadata-only read; deliberately does not calculate or print outcomes."""
import collections
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path('/root/by-bot')
BOUND = 32 * 1024 * 1024
out = {'schema': 'BOUNCE1_METADATA_INTAKE_V1',
       'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'orders_allowed': False, 'outcome_analysis': False, 'judge_run': False}

def read_file(path):
    with path.open('rb') as handle:
        before = handle.seek(0, 2)
        if before > BOUND: raise ValueError('byte_bound')
        handle.seek(0)
        raw = handle.read(before)
        after = path.stat()
    return raw, {'path': str(path), 'bytes': before, 'sha256': hashlib.sha256(raw).hexdigest(),
                 'mtime_ns': after.st_mtime_ns, 'size_after': after.st_size,
                 'stable_size': after.st_size == before}

services = {}
for unit in ('bybot.service', 'bybot-web.service', 'att1-ets2s-public-shadow.service'):
    r = subprocess.run(['systemctl', 'show', unit, '--property=MainPID,NRestarts,ActiveState,SubState'],
                       capture_output=True, text=True, timeout=5)
    services[unit] = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
out['services'] = services
sources = {}
for rel in ('smart_pump_reversal_bot.py', 'bot/strategy_shadow_ledger.py',
            'strategies/bounce1_live.py', 'strategies/alt_support_bounce_v1.py',
            'configs/approved_strategy_params.env'):
    path = BASE / rel
    try: _, sources[rel] = read_file(path)
    except FileNotFoundError: sources[rel] = {'missing': True}
out['sources'] = sources
out['runtime_report'] = {}
for rel in ('runtime/bot_heartbeat.json', 'runtime/runtime_diagnostics.json'):
    try:
        raw, info = read_file(BASE / rel)
        data = json.loads(raw)
        cfg = data.get('strategy_runtime_config', {})
        out['runtime_report'][rel] = {'source': info, 'top_keys': sorted(data),
            'reported_timestamps': {k: data[k] for k in ('ts_utc', 'ts', 'ts_ms', 'timestamp') if k in data},
            'bounce_config': {k: cfg.get(k, {}).get('bounce1') for k in ('enabled','risk_mult','allowlist')}}
    except FileNotFoundError: out['runtime_report'][rel] = {'missing': True}

# Only explicitly safe BOUNCE1 values; never output an env file or general process env.
safe = ('ENABLE_BOUNCE1_TRADING', 'BOUNCE1_RISK_MULT', 'BOUNCE1_SHADOW_ENABLE',
        'BOUNCE1_SYMBOL_ALLOWLIST', 'BOUNCE1_SL_ATR_MULT', 'BOUNCE1_TP1_FRAC',
        'BOUNCE1_TRAIL_ATR_MULT', 'BOUNCE1_ALLOW_LONGS', 'BOUNCE1_ALLOW_SHORTS',
        'BOUNCE1_SHADOW_STATE_PATH', 'BOUNCE1_SHADOW_LEDGER_PATH')
out['file_configuration_not_in_memory_proof'] = {}
for rel in ('.env', 'configs/approved_strategy_params.env', 'runtime/strategy_pause.env'):
    path = BASE / rel
    if not path.exists(): continue
    raw, info = read_file(path)
    selected = {}
    for line in raw.decode().splitlines():
        text = line.strip()
        if text.startswith('export '): text = text[7:]
        key, sep, value = text.partition('=')
        if sep and key in safe: selected[key] = value.strip().strip('"\'')
    out['file_configuration_not_in_memory_proof'][rel] = {'source': info, 'selected': selected}

ledger = BASE / 'runtime/bounce1_shadow_ledger.jsonl'
state = BASE / 'runtime/bounce1_shadow_state.json'
try:
    raw, info = read_file(ledger)
    counts, seen, all_ids = collections.Counter(), collections.defaultdict(collections.Counter), set()
    required = ('decision_ts_ms', 'fill_ts_ms', 'close_ts_ms', 'source_hash',
                'config_hash', 'funding', 't_available', 'regime')
    missing_close = collections.Counter()
    errors, stamps, symbols, close_ids = [], [], set(), []
    for line_no, line in enumerate(raw.splitlines(), 1):
        try:
            event = json.loads(line)
            if event.get('schema_id') != 'strategy_risk_zero_shadow_v1': raise ValueError('schema')
            if event.get('strategy') != 'alt_support_bounce_v1': raise ValueError('strategy')
            if event.get('broker_calls') is not False or event.get('mode') != 'shadow': raise ValueError('authority')
            name, sid = event.get('event'), event.get('signal_id')
            if not isinstance(sid, str) or not sid: raise ValueError('signal_id')
            counts[name] += 1
            seen[name][sid] += 1
            all_ids.add(sid)
            stamps.append(int(event['ts_ms']))
            symbols.add(event.get('symbol'))
            if name == 'close':
                close_ids.append(sid)
                missing_close.update(k for k in required if k not in event)
        except (ValueError, KeyError, TypeError): errors.append(line_no)
    out['ledger'] = {'source': info, 'complete_tail': not raw or raw.endswith(b'\n'),
        'event_counts': dict(counts), 'unique_decisions': len(seen['decision']),
        'unique_closed_decisions': len(seen['close']), 'unique_fills': len(seen['fill']),
        'duplicate_close_ids': sorted(k for k,v in seen['close'].items() if v != 1),
        'duplicate_decision_ids': sorted(k for k,v in seen['decision'].items() if v != 1),
        'closed_without_decision': sorted(set(seen['close']) - set(seen['decision'])),
        'closed_without_fill': sorted(set(seen['close']) - set(seen['fill'])),
        'unknown_event_types': sorted(set(counts) - {'decision','fill','target','cancel','close'}),
        'malformed_lines': errors, 'symbols': sorted(symbols),
        'first_ts_ms': min(stamps) if stamps else None, 'last_ts_ms': max(stamps) if stamps else None,
        'timestamp_backsteps': sum(b < a for a,b in zip(stamps,stamps[1:])),
        'missing_fields_on_closed_events': dict(missing_close),
        'close_id_sequence_sha256': hashlib.sha256(json.dumps(close_ids).encode()).hexdigest()}
except FileNotFoundError: out['ledger'] = {'missing': True, 'path': str(ledger)}
try:
    raw, info = read_file(state)
    data = json.loads(raw)
    out['state'] = {'source': info, 'schema_id': data.get('schema_id'),
        'strategy': data.get('strategy'), 'broker_calls': data.get('broker_calls'),
        'mode': data.get('mode'), 'closed_count': data.get('closed_count'),
        'open_symbols': sorted(data.get('open', {})), 'pending_symbols': sorted(data.get('pending', {}))}
except FileNotFoundError: out['state'] = {'missing': True, 'path': str(state)}
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
