"""Bounded read-only hook for confirmed POLY_SIGNAL_V1; no daemon or trade authority."""
import datetime as dt
import fcntl
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import re
import time
import uuid
from scripts import measure_polymarket_snapshot_v1 as snap
from . import polymarket_v2_orders_off_v1 as model
from .polymarket_v2_snapshot_inputs_v1 import decoded, pairs, bad_constant, market_input
from .polymarket_ws_data_v1 import once, encoded, read, mkdirs_durable



PRODUCERS = {
    'POLY_95_V2_SHIROKO.jsonl': ('poly_signaly.py', '0f7e5f9dbc2e409ec634f2d6f8ea127feadbf06d4605bc54b11a55ec58f306fa'),
    'POLY_SCHET_V3.jsonl': ('poly_signaly_v3.py', 'cb6c6bd18d46a8d61be7ab0e8e44e5a0e28ad896004457efbb206f2b34a9d04a'),
}
JOURNAL_MODULE_PIN = 'a2b3a0f34f4c9a28ec604e2f0496775c39dc3be56400b87859783d5afa294b30'

def need(ok, why):
    if not ok:
        raise ValueError(why)


def now_ms():return time.time_ns() // 1_000_000

def sha(b):return hashlib.sha256(b).hexdigest()

def load(raw):return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def safe(root, relative):
    rel = Path(relative)
    need(not rel.is_absolute() and '..' not in rel.parts, 'PATH_CUSTODY')
    p = Path(root).absolute() / rel
    need(p.is_relative_to(Path(root).absolute()) and not any(x.is_symlink() for x in (p, *p.parents)), 'PATH_CUSTODY')
    return p


def producer_binding(root, journal_name, epoch):
    need(epoch == 'E2_20261104' and journal_name in PRODUCERS, 'SOURCE_EPOCH')
    filename, pin = PRODUCERS[journal_name]
    path = safe(root, 'data/poly_signaly/' + epoch + '/MANIFEST_' + Path(journal_name).stem + '.json')
    if not path.exists():return None
    raw = read(path); manifest = load(raw)
    need(manifest.get('schema') == 'POLY_SIGNAL_V1' and manifest.get('epoha') == epoch
         and manifest.get('pravilo') == Path(journal_name).stem
         and manifest.get('zhurnal') == 'research_lab/data/poly_signaly/' + epoch + '/' + journal_name
         and manifest.get('producer') == filename, 'PRODUCER_BINDING')
    need(manifest.get('producer_sha256') == pin == sha(read(safe(root, filename)))
         and manifest.get('zhurnal_modul_sha256') == JOURNAL_MODULE_PIN == sha(read(safe(root, 'fabrika/poly_signal_zhurnal.py'))), 'PRODUCER_DRIFT')
    need(type(manifest.get('pid')) is int and manifest['pid'] > 0 and isinstance(manifest.get('start_utc'), str), 'PRODUCER_IDENTITY')
    return dict(manifest_sha256=sha(raw), manifest=manifest)


def chain(raw):
    end = raw.rfind(b'\n') + 1
    prefix = raw[:end]
    rows, previous = [], '0' * 64
    for line in prefix.splitlines():
        need(line and len(rows) < 4096, 'CHAIN_BOUND')
        obj = load(line)
        need(isinstance(obj, dict) and obj.get('prev_sha256') == previous, 'CHAIN_LINK')
        rows.append((obj, line))
        previous = sha(line)  # Claude hashes literal line bytes without newline.
    return prefix, rows, previous


def quote_tail(path):
    """Bounded suffix of an append-only source; never lock, repair or follow a link."""
    need(not path.is_symlink(), 'SOURCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as f:
        before = os.fstat(f.fileno()); offset = max(0, before.st_size - 2 * 2**20)
        f.seek(offset); raw = f.read(before.st_size - offset)
        after = os.fstat(f.fileno())
    need((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino) == (path.stat().st_dev, path.stat().st_ino) and after.st_size >= before.st_size, 'SOURCE_CHANGED')
    if offset:raw = raw[raw.find(b'\n') + 1:]
    raw = raw[:raw.rfind(b'\n') + 1]
    return [(load(line), line) for line in raw.splitlines()]


def qualify(s, root, observed):
    need(s.get('schema') == 'POLY_SIGNAL_V1' and s.get('side') == 'BUY' and s.get('status') == 'SHADOW' and s.get('finance_allowed') is False, 'SIGNAL_SCOPE')
    policy, mid, token = s.get('policy'), s.get('market_id'), s.get('token_id')
    need(isinstance(policy, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,100}', policy)
         and isinstance(mid, str) and re.fullmatch(r'[0-9]{1,32}', mid)
         and (isinstance(token, str) and re.fullmatch(r'[0-9]{1,100}', token) or token is None and 'outcome_index' in s), 'SIGNAL_IDENTITY')
    index = s.get('outcome_index')
    if 'outcome_index' in s:need(type(index) is int and index in (0, 1), 'OUTCOME_INDEX')
    identity_key = str(index) if 'outcome_index' in s else token
    identity = sha((policy + '|' + mid + '|' + identity_key).encode())[:24]
    need(s.get('signal_observation_id') == identity, 'SIGNAL_IDENTITY')
    prereg = read(safe(root, 'prereg/' + policy + '.md'))
    need(sha(prereg) == s.get('policy_sha256'), 'POLICY_DRIFT')
    a, b = s.get('received_ms'), s.get('signal_ms')
    need(model._ms(a) and model._ms(b) and a <= b <= observed, 'SIGNAL_TIME')
    need(observed - a <= 120000 and observed - b <= 120000, 'STALE_SIGNAL')
    if 'outcome_index' in s:return qualify_v3(s, root, observed)
    need(s.get('source') == 'poly_sport_shiroko/knigi.jsonl', 'SOURCE_PATH')
    registry = read(safe(root, 'data/poly_sport_shiroko/rynki.jsonl'))
    rows = [load(x) for x in registry[:registry.rfind(b'\n') + 1].splitlines()]
    matches = [x for x in rows if x.get('id') == mid and x.get('sob') == 'dobavlen']
    need(matches, 'MARKET_MEMBERSHIP')
    market = matches[0]; tokens = market.get('tokeny')
    need(isinstance(tokens, list) and len(tokens) == 2 and len(set(tokens)) == 2 and token in tokens, 'SIGNAL_IDENTITY')
    q = s.get('quote'); need(isinstance(q, dict), 'SOURCE_PROVENANCE')
    source = [(x, raw) for x, raw in quote_tail(safe(root, 'data/' + s['source'])) if x.get('id') == mid and x.get('token') in tokens]
    selected = [(x, raw) for x, raw in source if x.get('token') == token and int(x['t'] * 1000) == a and x.get('ask') == q.get('ask') and x.get('bid') == q.get('bid') and x.get('lest_ask') == q.get('ask_ladder') and x.get('gl_ask') == q.get('ask_depth_usd')]
    proof = None
    for x, ar in source:
        if x.get('token') != tokens[0] or int(x['t'] * 1000) > b:continue
        for y, br in selected:
            if y['t'] > x['t']:continue
            raw = ar + b'\n' + (br if token != tokens[0] else b'')
            if sha(raw) == s.get('source_sha256') and (token != tokens[0] or ar == br):proof = raw
    need(proof is not None, 'SOURCE_PROVENANCE')
    need(0 < model._number(s.get('price_limit')) <= model.LIMIT and 0 < model._number(s.get('stake_model_usd')) <= model.MODEL_BUDGET, 'MODEL_BOUNDS')
    normalized = dict(market_id=mid, token_id=token, policy_sha256=s['policy_sha256'],
        received_ms=a, signal_ms=b, signal_observation_id=identity, source_sha256=s['source_sha256'],
        model_price=q['ask'], stake_model_usd=s['stake_model_usd'], price_limit=s['price_limit'])
    member = dict(id=mid, tokens=tokens)
    provenance = dict(source_sha256=sha(proof), source_raw_text=proof.decode(),
                      registry_sha256=sha(registry), market_record=market, policy_sha256=sha(prereg))
    return normalized, member, provenance


def verify_sports_witness(s, root):
    """Verify existing sealed DATA bytes and local availability, without replaying a producer."""
    score = s['score']; w = score['source_witness']
    segment = w.get('segment')
    prefix = 'research_lab/data/poly_ws_vps_v1/'
    need(isinstance(segment, str) and re.fullmatch(re.escape(prefix) + r'sports/sealed/[0-9]+-[0-9a-f]{32}-[0-9]+\.jsonl\.gz', segment), 'SCORE_SOURCE_PATH')
    archive = safe(root, 'data/poly_ws_vps_v1')
    name = segment[len(prefix):]
    file = safe(archive, name); sealfile = safe(archive, name + '.delivery.json')
    raw = read(file); sealraw = read(sealfile, 16384); seal = load(sealraw)
    need(seal.get('file') == name and sha(raw) == w.get('segment_sha256') == seal.get('sha256'), 'SCORE_SEGMENT_HASH')
    snap.validate_segment(seal, raw)
    receiptfile = safe(archive, 'receipts/' + sha(encoded(seal)) + '.json')
    receiptraw = read(receiptfile, 16384); receipt = load(receiptraw)
    need(receipt.get('schema') == 'POLY_WS_DATA_IMPORT_V1' and receipt.get('epoch') == seal['epoch']
         and receipt.get('orders_allowed') is False and receipt.get('file') == name
         and receipt.get('file_sha256') == sha(raw) and receipt.get('seal_sha256') == sha(sealraw)
         and receipt.get('first_local_mtime_ns') == file.stat().st_mtime_ns, 'SCORE_IMPORT_RECEIPT')
    imported = receipt.get('actual_import_ms')
    need(model._ms(imported) and imported >= seal['closed_ms'], 'SCORE_IMPORT_TIME')
    available = max(imported, *(p.stat().st_mtime_ns // 1_000_000 for p in (file, sealfile, receiptfile)))
    need(available <= s['signal_ms'], 'SCORE_AVAILABLE_AFTER_DECISION')
    delivery = sealfile.stat().st_mtime_ns // 1_000_000
    need(w.get('delivery_mtime_ms') == delivery == score.get('score_on_mac_ms'), 'SCORE_DELIVERY_TIME')
    seen = w.get('segment_first_seen_by_producer_ms')
    need(model._ms(seen) and available <= seen <= s['signal_ms'], 'SCORE_FIRST_SEEN_TIME')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:plain = stream.read(8 * 2**20 + 1)
    need(len(plain) <= 8 * 2**20, 'SCORE_FRAME_BOUND')
    lines = plain.splitlines(); index = w.get('line_index')
    need(type(index) is int and 0 <= index < len(lines), 'SCORE_FRAME_INDEX')
    line = lines[index]; need(sha(line) == w.get('line_sha256'), 'SCORE_FRAME_HASH')
    row = load(line)
    need(row.get('kind') == 'RECV' and row.get('received_ms') == w.get('received_ms') == score.get('score_received_ms'), 'SCORE_FRAME_TIME')
    need(type(w.get('monotonic_ns')) is int and row.get('monotonic_ns') == w['monotonic_ns'], 'SCORE_MONOTONIC')
    need(w.get('book_received_ms') == s['received_ms'] and row['received_ms'] < s['received_ms'] <= s['signal_ms'], 'SCORE_CAUSAL_TIME')
    frame = load(row['payload']['frame'])
    games = frame if isinstance(frame, list) else [frame]
    matches = [g for g in games if isinstance(g, dict) and g.get('gameId') == score.get('gameId')]
    need(len(matches) == 1, 'SCORE_GAME_IDENTITY'); game = matches[0]
    need(game.get('score') == score.get('score_away_home') and game.get('period') == score.get('period')
         and game.get('elapsed') == score.get('clock'), 'SCORE_FRAME_MISMATCH')
    return dict(sports_frame_provenance_verified=True, score_available_by_decision=True,
        score_available_before_book=available <= s['received_ms'], score_available_ms=available,
        raw_frame_reports_live=(game.get('live') is True or game.get('status') in ('inprogress', 'in_progress', 'live')) and game.get('ended') is not True,
        before_sports_final_proven=False, segment_sha256=sha(raw), line_sha256=sha(line),
        import_receipt_sha256=sha(receiptraw), claimed_producer_first_seen_ms=seen,
        limitation='SEALED_FRAME_AND_LOCAL_IMPORT_VERIFIED_NOT_A_MATCH_FINALITY_OR_FILL_PROOF')


def qualify_v3(s, root, observed):
    # Caller already checked policy, identity, SHADOW scope, source/decision clocks.
    src = s.get('source')
    need(src in {'poly_monitor+poly_ws_vps_v1/sports', 'poly_sport_shiroko+poly_ws_vps_v1/sports'}, 'SOURCE_PATH')
    source_dir = src.split('+')[0]
    rows = quote_tail(safe(root, 'data/' + source_dir + '/knigi.jsonl'))
    matches = [(x, raw) for x, raw in rows if x.get('id') == s['market_id'] and sha(raw) == s.get('source_sha256')]
    need(len(matches) == 1 and int(matches[0][0]['t'] * 1000) == s['received_ms'], 'SOURCE_PROVENANCE')
    q, raw = matches[0]
    score = s.get('score')
    need(isinstance(score, dict) and score.get('gameId') is not None, 'SCORE_PROVENANCE_UNKNOWN')
    a, b = score.get('score_received_ms'), score.get('score_on_mac_ms')
    need(model._ms(a) and model._ms(b) and a <= b <= s['signal_ms'] <= observed, 'FUTURE_SCORE')
    need(observed - b <= 120000, 'STALE_SCORE')
    registry = read(safe(root, 'data/' + source_dir + '/rynki.jsonl'))
    records = [load(x) for x in registry[:registry.rfind(b'\n') + 1].splitlines()]
    markets = [x for x in records if x.get('id') == s['market_id'] and x.get('sob') == 'dobavlen']
    need(markets, 'MARKET_MEMBERSHIP')
    m = markets[0]
    need(all(x.get('tokeny') == m.get('tokeny') and x.get('token') == m.get('token') for x in markets), 'AMBIGUOUS_MARKET_MEMBERSHIP')
    tokens = m.get('tokeny')
    if tokens is not None:
        need(isinstance(tokens, list) and len(tokens) == 2 and len(set(tokens)) == 2 and all(isinstance(t, str) and re.fullmatch(r'[0-9]{1,100}', t) for t in tokens), 'SIGNAL_IDENTITY')
        need(s['token_id'] in (None, tokens[s['outcome_index']]), 'TOKEN_INDEX_MISMATCH')
    need(model._number(s['price_limit']) > 0 and model._number(s['price_limit']) <= model.LIMIT, 'MODEL_BOUNDS')
    signal = dict(market_id=s['market_id'], token_id=s['token_id'], outcome_index=s['outcome_index'],
        signal_observation_id=s['signal_observation_id'], policy_sha256=s['policy_sha256'],
        received_ms=s['received_ms'], signal_ms=s['signal_ms'], score_on_mac_ms=b, source_sha256=s['source_sha256'],
        model_price=s['quote']['ask'], price_limit=s['price_limit'],
        stake_model_usd=100 if s.get('stake_model_usd') is None else s['stake_model_usd'])
    provenance = dict(source_sha256=sha(raw), source_raw_text=raw.decode(), market_record=m,
        registry_sha256=sha(registry), policy_sha256=s['policy_sha256'],
        source_quote_is_execution_price=False, sports_frame_provenance_verified=False,
        limitation='SCORE_TIMESTAMPS_ASSERTED_NO_IMMUTABLE_FRAME_REFERENCE',
        model_budget_unspecified_by_producer=s.get('stake_model_usd') is None)
    if 'source_witness' in score:provenance.update(verify_sports_witness(s, root))
    return signal, dict(id=s['market_id'], tokens=tokens), provenance


def resolve_index(signal, member, provenance, folder):
    if 'outcome_index' not in signal:return
    capture = snap.get_capture('https://gamma-api.polymarket.com/markets/' + signal['market_id'])
    once(folder / 'token-lookup.json', encoded(capture))
    market = market_input(capture, signal['market_id'], decision_ms=now_ms())
    tokens = market['tokens']; old = member['tokens']
    if old is not None:need(old == tokens, 'TOKEN_CATALOGUE_AMBIGUOUS')
    source_a = provenance['market_record'].get('token')
    if source_a is not None:need(tokens[0] == source_a, 'TOKEN_A_CATALOGUE_MISMATCH')
    selected = tokens[signal['outcome_index']]
    need(signal['token_id'] in (None, selected), 'TOKEN_INDEX_MISMATCH')
    signal['token_id'] = selected; member['tokens'] = tokens
    provenance['token_resolution_capture_sha256'] = capture['raw_sha256']


def verified_manifest(folder):
    raw = read(folder / 'measurement-manifest.json'); manifest = load(raw)
    anchor = load(read(folder.parent.parent / 'measurement-anchors' / (folder.name + '.json')))
    need(anchor['manifest_sha256'] == sha(raw), 'MANIFEST_DRIFT')
    required = {'source-signal.json', 'intake.json', 'capture/source-membership.json',
        'capture/input-signal.json', 'capture/sample-0/gamma.json', 'capture/sample-0/book-0.json',
        'capture/sample-0/book-1.json', 'capture/sample-0/measurement.json',
        'capture/sample-0/summary.json', 'capture/summary.json'}
    files = manifest['files']
    need(isinstance(files, dict) and set(files) in (required, required | {'token-lookup.json'}), 'MANIFEST_FILE_SET')
    for name, pin in files.items():
        need(model._pin(pin) and sha(read(safe(folder, name))) == pin, 'MEASUREMENT_DRIFT')
    detail = load(read(folder / 'capture/sample-0/measurement.json'))
    intake = load(read(folder / 'intake.json')); source = load(read(folder / 'source-signal.json'))
    need(manifest['tokens'] == detail['metadata']['tokens'] and manifest['condition_id'] == detail['metadata']['condition_id']
         and manifest['signal_observation_id'] == folder.name == intake['signal']['signal_observation_id'] == source['signal_observation_id']
         and detail['signal_observation_id'] == folder.name, 'MANIFEST_IDENTITY')
    manifest['anchored_after_fsync_ms'] = anchor['observed_after_manifest_fsync_ms']
    return raw, manifest


def last_attempt(folder):
    files = sorted((folder / 'attempts').glob('*.json')) if (folder / 'attempts').exists() else []
    return load(read(files[-1]))['observed_ms'] if files else 0


def outcome(folder, at):
    manifest_bytes, manifest = verified_manifest(folder)
    if (folder / 'outcome.json').exists():return 'ALREADY_JOINED'
    if last_attempt(folder) and at - last_attempt(folder) < 60000:return 'PENDING_OUTCOME'
    once(folder / 'attempts' / (str(at) + '-' + uuid.uuid4().hex + '.json'), encoded(dict(observed_ms=at)))
    url = 'https://data-api.polymarket.com/v2/resolutions?condition=' + manifest['condition_id']
    capture = snap.get_capture(url)
    poll_ms = now_ms(); obj = decoded(capture, url, poll_ms, 60000)
    poll = dict(observed_ms=poll_ms, capture=capture)
    once(folder / 'polls' / (str(poll_ms) + '-' + uuid.uuid4().hex + '.json'), encoded(poll))
    rows = obj.get('data'); need(isinstance(rows, list) and len(rows) <= 1, 'RESOLUTION_SCHEMA')
    if not rows:return 'PENDING_OUTCOME'
    row = rows[0]; need(row.get('condition_id') == manifest['condition_id'], 'RESOLUTION_CONDITION')
    if row.get('status') != 'resolved':return 'PENDING_OUTCOME'
    stamp = dt.datetime.fromisoformat(row['resolved_at'].replace('Z', '+00:00'))
    need(stamp.tzinfo is not None, 'RESOLUTION_TIME')
    resolved_ms = int(stamp.timestamp() * 1000)
    need(manifest['anchored_after_fsync_ms'] < resolved_ms <= poll_ms, 'RESOLUTION_BEFORE_MEASUREMENT')
    payouts = row.get('payouts'); need(isinstance(payouts, list) and len(payouts) == 2, 'RESOLUTION_PAYOUTS')
    pay = [model._number(x) for x in payouts]
    need(all(x >= 0 for x in pay) and sum(x > 0 for x in pay) == 1, 'AMBIGUOUS_PAYOUT')
    winner = manifest['tokens'][next(i for i, x in enumerate(pay) if x > 0)]
    stored = load(read(folder / 'capture/sample-0/measurement.json'))
    selected = next(x['measurement'] for x in stored['outcomes'] if x['supplied_signal'])
    joined = model.join_outcome(selected, winner, resolved_ms=resolved_ms, joined_ms=poll_ms)
    joined.update(signal_observation_id=manifest['signal_observation_id'],
        parent_manifest_sha256=sha(manifest_bytes), official_capture_sha256=capture['raw_sha256'],
        official_source=url, official_resolution_ms=resolved_ms,
        outcome_received_ms=capture['received_ms'], e2e_sports_before_final_confirmed=False,
        limitation='PRE_OFFICIAL_RESOLUTION_WITNESS_NOT_PROOF_OF_PRE_SPORTS_FINAL')
    once(folder / 'outcome.json', encoded(joined)); return 'JOINED_MODEL_OUTCOME'


def cycle_once(research_root, journal_name, state_root, *, epoch=None):
    need(isinstance(journal_name, str) and re.fullmatch(r'[A-Z0-9_]{1,80}\.jsonl', journal_name), 'JOURNAL_NAME')
    root, state = Path(research_root).absolute(), Path(state_root).absolute()
    binding = producer_binding(root, journal_name, epoch) if epoch is not None else None
    journal = safe(root, 'data/poly_signaly/' + (epoch + '/' if epoch is not None else '') + journal_name)
    result = dict(status='WAITING_REAL_SIGNAL', measured=0, joined=0, blocked=0, issues=[], order_posts=0, money_authority=False)
    if epoch is not None and binding is None:
        result['status'] = 'WAITING_PRODUCER_MANIFEST';return result
    if not journal.exists():return result
    safe(state, 'cycle.lock'); mkdirs_durable(state)
    fd = os.open(state / 'cycle.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prefix, rows, last = chain(read(journal)); observed = now_ms()
        anchors = sorted((state / 'observations').glob('*/prefix.json'))
        old = load(read(anchors[-1])) if anchors else None
        if old:
            need(len(prefix) >= old['prefix_bytes'] and sha(prefix[:old['prefix_bytes']]) == old['prefix_sha256'], 'WITNESSED_PREFIX_DRIFT')
        if not old or len(prefix) != old['prefix_bytes']:
            anchor = state / 'observations' / (str(observed) + '-' + uuid.uuid4().hex)
            once(anchor / 'source-prefix.jsonl', prefix)
            witness = dict(producer_binding=binding, observed_after_prefix_fsync_ms=now_ms(), prefix_bytes=len(prefix), prefix_sha256=sha(prefix), last_line_sha256=last)
            once(anchor / 'prefix.json', encoded(witness))
        made = set()
        for s, raw in rows:
            identity = s.get('signal_observation_id')
            need(isinstance(identity, str) and re.fullmatch(r'[0-9a-f]{24}', identity), 'SIGNAL_IDENTITY')
            folder = state / 'signals' / identity
            if (folder / 'source-signal.json').exists():
                need(read(folder / 'source-signal.json') == raw + b'\n', 'SIGNAL_ID_CONFLICT')
                if not (folder / 'measurement-manifest.json').exists() and not (folder / 'blocked.json').exists():
                    result['issues'].append('INTERRUPTED_MEASUREMENT_NO_REPLAY:' + identity)
                continue  # Never replay after interruption or re-price a spent observation.
            if len(made) >= 4:break
            made.add(identity); once(folder / 'source-signal.json', raw + b'\n')
            try:
                signal, member, provenance = qualify(s, root, now_ms())
                resolve_index(signal, member, provenance, folder)
                intake = dict(signal=signal, provenance=provenance,
                    source_signal_sha256=sha(raw), prefix_sha256=sha(prefix), producer_binding=binding,
                    consumer_observed_after_signal_fsync_ms=now_ms(), before_sports_final_proven=False,
                    producer_saved_ms_independently_proven=False, orders_allowed=False)
                once(folder / 'intake.json', encoded(intake))
                captured = snap.run_member(member, dict(kind='EXISTING_BROAD_MONITOR_SIGNAL', source_sha256=s['source_sha256']), folder / 'capture', signal=signal)
                need(captured['samples'][0]['status'] == 'MEASURED_SNAPSHOTS', 'FRESH_MEASUREMENT_UNKNOWN')
                detail = load(read(folder / 'capture/sample-0/measurement.json')); condition = detail['metadata']['condition_id']
                need(s.get('condition_id') in (None, condition) and provenance['market_record'].get('conditionId') in (None, condition), 'SIGNAL_CONDITION')
                files = {str(p.relative_to(folder)):sha(read(p)) for p in sorted(folder.rglob('*.json'))}
                manifest = dict(signal_observation_id=identity, files=files, condition_id=condition,
                    tokens=detail['metadata']['tokens'], saved_after_measurement_ms=now_ms(),
                    model_only=True, before_sports_final_proven=False)
                manifest_raw = encoded(manifest)
                once(folder / 'measurement-manifest.json', manifest_raw)
                once(state / 'measurement-anchors' / (identity + '.json'), encoded(dict(manifest_sha256=sha(manifest_raw), observed_after_manifest_fsync_ms=now_ms())))
                result['measured'] += 1
            except (ValueError, OSError, KeyError, TypeError) as error:
                reason = type(error).__name__ + ':' + str(error)[:180]
                once(folder / 'blocked.json', encoded(dict(observed_ms=now_ms(), reason=reason, no_replay=True)))
                result['blocked'] += 1; result['issues'].append(reason)
        pending = sorted((state / 'signals').glob('*/measurement-manifest.json'), key=lambda p:(last_attempt(p.parent), p.parent.name))
        checked = 0
        for file in pending:
            if file.parent.name in made or (file.parent / 'outcome.json').exists():continue
            if checked >= 4:break
            if last_attempt(file.parent) and now_ms() - last_attempt(file.parent) < 60000:continue
            checked += 1
            try:
                if outcome(file.parent, now_ms()) == 'JOINED_MODEL_OUTCOME':result['joined'] += 1
            except (ValueError, OSError, KeyError, TypeError) as error:
                if 'MEASUREMENT_DRIFT' in str(error) or 'MANIFEST_' in str(error) or 'PATH_CUSTODY' in str(error):raise
                result['issues'].append(str(error))
        result['status'] = 'MODEL_OUTCOME_JOINED' if result['joined'] else ('SIGNAL_MEASURED_PENDING_OUTCOME' if result['measured'] else 'PENDING_OUTCOME' if pending else 'WAITING_REAL_SIGNAL')
        if result['issues']:result['status'] = 'UNKNOWN'
        result['observed_ms'] = now_ms()
        return result
    finally:os.close(fd)


def cycle_many(research_root, state_root, journals=None, epoch=None):
    """Same existing-producer invocation, isolated journal anchors and one consumer."""
    state = Path(state_root).absolute();safe(state, 'hook-consumer.lock');mkdirs_durable(state)
    fd = os.open(state / 'hook-consumer.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return dict(status='BUSY_OTHER_CONSUMER', journals={}, order_posts=0, money_authority=False)
        results = {}
        names = ('POLY_95_V2_SHIROKO.jsonl', 'POLY_SCHET_V3.jsonl')
        selected = names if journals is None else journals
        need(all(name in names for name in selected), 'JOURNAL_SCOPE')
        for name in selected:
            try:results[name] = cycle_once(research_root, name, (state / epoch if epoch is not None else state) / Path(name).stem, epoch=epoch)
            except (ValueError, OSError) as e:results[name] = dict(status='UNKNOWN', reason=type(e).__name__ + ':' + str(e)[:200])
        return dict(status='UNKNOWN' if any(x['status'] == 'UNKNOWN' for x in results.values()) else 'CYCLE_CHECKED',
                    observed_ms=now_ms(), journals=results, order_posts=0, money_authority=False)
    finally:os.close(fd)
