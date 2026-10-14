"""Offline preparation/verification for the existing exact-plan LIVE runtime.

No broker client, reservation, owner-permit writer or service activation here.
An installed app is not a bound LIVE plan; a closed PAPER trade is not fee proof.
"""
import ast
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from research_lab.alpaca_dynamic_v1 import canonical, dec, digest, positive

BASE = '/opt/bybot-research/alpaca-dynamic-live-20261013'
POLICY = 'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json'
POLICY_PIN = 'fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'
POSTCHECK_MS = 1791900300000  # Original October13 14:05 UTC observation.
ACTIVE = {'new', 'accepted', 'pending_new', 'partially_filled', 'pending_cancel',
          'pending_replace', 'accepted_for_bidding', 'held', 'calculated', 'stopped'}
TERMINAL = {'filled', 'expired', 'canceled', 'rejected', 'replaced'}
PAPER_DOC_SHA = 'd43c9e2bdc1c4c9be8296a2a0b7b012441e6d293a44ea0d5c767d56d9709ade7'
COMMISSION_PROTOCOL_SHA = '800ac28c805fec1ed01927edc63bae1696f66eff368a6ebe6ec5281c1d517a2c'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blocked(reason, *, execution=False):
    return dict(schema='ALPACA_DYNAMIC_LIVE_READINESS_V1',
        status='BLOCKED_EXECUTION' if execution else 'BLOCKED_DATA', reason=reason,
        orders_allowed=False, live_orders_allowed=False, ready_for_live_go=False)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _physical_sources(rows, manifest):
    from research_lab.alpaca_dynamic_live_runtime_v1 import safe_path
    _require(bool(rows) and digest(rows) == manifest, 'SOURCE_MANIFEST_CONFLICT')
    for row in rows:
        path = safe_path(row['path'], exists=True)
        _require(sha(path.read_bytes()) == row['sha256'], 'PHYSICAL_SOURCE_HASH_CONFLICT')


def build_package(root):
    """Close project imports, frozen selector dependencies and static config.

    AST discovery never imports/runs a collector, selector or research judge.
    Existing .env files/credentials and old PAPER services are not packaged.
    """
    root = Path(root).resolve()
    policy = json.loads((root / POLICY).read_bytes())
    _require(digest(policy) == POLICY_PIN, 'PACKAGE_POLICY_CONFLICT')
    old = json.loads((root / 'reports/evidence/alpaca_net_arm_20261011/source_manifest.json').read_bytes())
    names = {POLICY, 'scripts/run_alpaca_dynamic_live_v1.py',
        'scripts/prepare_alpaca_live_readiness_v1.py',
        'research_lab/alpaca_live_readiness_v1.py',
        'research_lab/alpaca_dynamic_live_runtime_v1.py',
        'reports/evidence/alpaca_net_arm_20261011/source_manifest.json',
        'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json'}
    names.update(policy['selector_file_sha256'])
    # The original selector reads this config and hashes these engine sources.
    names.update(n for n in old if n.startswith(('backtest/', 'strategies/', 'forex/'))
                 or n in {'configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json',
                          'scripts/build_equities_monthly_live_cycle.py'})
    queue = sorted(names)
    while queue:
        name = queue.pop(0)
        _require((root / name).is_file() and not (root / name).is_symlink(), 'PACKAGE_SOURCE_MISSING:' + name)
        if not name.endswith('.py'):
            continue
        candidates = set()
        for node in ast.walk(ast.parse((root / name).read_bytes())):
            if isinstance(node, ast.Import):
                candidates.update(x.name for x in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                candidates.add(node.module or '')
                candidates.update((node.module + '.' + a.name) for a in node.names if node.module)
        # Native bridge's optional direct import lives in scripts/.
        candidates.add('scripts.equities_earnings_filter')
        dependencies = set()
        for module in candidates:
            target = module.replace('.', '/')
            for rel in (target + '.py', target + '/__init__.py'):
                if (root / rel).is_file():
                    dependencies.add(rel)
            for parent in Path(target).parents:
                rel = str(parent / '__init__.py')
                if (root / rel).is_file():
                    dependencies.add(rel)
        for dep in sorted(dependencies - names):
            names.add(dep); queue.append(dep)
    _require(not any(n.endswith('.env') or '.private' in Path(n).parts for n in names), 'PACKAGE_CREDENTIAL_PATH')
    for n, h in policy['selector_file_sha256'].items():
        _require(sha((root / n).read_bytes()) == h, 'PACKAGE_FROZEN_SELECTOR_CONFLICT')
    from research_lab.alpaca_dynamic_v1 import source_check
    source_check(policy, policy['calendar_sessions'])
    files = {n: dict(sha256=sha((root / n).read_bytes()),
        content_b64=base64.b64encode((root / n).read_bytes()).decode()) for n in sorted(names)}
    common = ('[Unit]\nDescription=Disabled Alpaca Dynamic exact-plan orders-OFF check\n'
        'After=network-online.target\n[Service]\nType=oneshot\nUser=root\n'
        f'WorkingDirectory={BASE}/app\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n'
        'Environment=PYTHONUNBUFFERED=1\nEnvironment=ALPACA_ALLOW_NEW_ENTRIES=0\n'
        'UMask=0077\nRestart=no\nTimeoutStartSec=120\nTimeoutStopSec=60\n'
        'MemoryMax=1G\nTasksMax=32\n'
        'ExecStart=/root/by-bot/.venv/bin/python -B scripts/run_alpaca_dynamic_live_v1.py '
        f'--binding {BASE}/session/binding.json --intake {BASE}/session/intake.json '
        '--live-profile /root/by-bot/configs/alpaca_live_v38.env')
    units = {'alpaca-dynamic-live-entry-20261013.service': common + '\n',
        'alpaca-dynamic-live-manager-20261013.service': common + ' --maintenance\n'}
    # Inert future activation drafts, NOT the installed read-only units. The
    # five-minute calendar is the existing native LIVE cron cadence. A distinct
    # owner GO must approve exclusive handoff before these drafts can be used.
    activated = {
        'alpaca-dynamic-live-entry-20261013.service': common + f' --apply --owner-go {BASE}/session/owner-go.json --first-intent {BASE}/session/first-intent.json\n',
        'alpaca-dynamic-live-manager-20261013.service': common + f' --apply --maintenance --owner-go {BASE}/session/owner-go.json --first-intent {BASE}/session/first-intent.json\n',
        'alpaca-dynamic-live-manager-20261013.timer':
            '[Unit]\nDescription=UNAPPROVED Dynamic owned maintenance activation draft\n'
            '[Timer]\nOnCalendar=*-*-* *:00/5:00 UTC\nAccuracySec=1s\nPersistent=false\n'
            'Unit=alpaca-dynamic-live-manager-20261013.service\n'}
    package = dict(schema='ALPACA_DYNAMIC_DISABLED_PACKAGE_V1', base=BASE,
        orders_allowed=False, enabled=False, files=files, units=units,
        unapproved_activation_templates=activated,
        policy_sha256=POLICY_PIN, manager_apply_arguments=['--apply', '--maintenance', '--owner-go'],
        lock='original explicit LIVE profile-derived account lock; never create a second authority',
        restart_policy='oneshot Restart=no; uncertain dispatch only exact-ID reconciliation',
        activation='NOT_AUTHORIZED; unit templates only, no enable/start/timer/cron',
        rollback='before dispatch retain HALT and disabled app; after fill retain scoped management until exit/finality; never delete ledger/journal')
    package['package_sha256'] = digest(package)
    verify_package(package)
    return package


def verify_package(package):
    _require(package['schema'] == 'ALPACA_DYNAMIC_DISABLED_PACKAGE_V1'
        and package['base'] == BASE and package['enabled'] is False
        and package['orders_allowed'] is False
        and package['policy_sha256'] == POLICY_PIN
        and package['package_sha256'] == digest({k: v for k, v in package.items() if k != 'package_sha256'}), 'PACKAGE_IDENTITY_CONFLICT')
    for n, row in package['files'].items():
        p = Path(n)
        _require(not p.is_absolute() and '..' not in p.parts and '.private' not in p.parts
                 and not n.endswith('.env'), 'PACKAGE_PATH_CONFLICT')
        _require(sha(base64.b64decode(row['content_b64'], validate=True)) == row['sha256'], 'PACKAGE_FILE_CONFLICT')
    for name, unit in package['units'].items():
        _require(Path(name).name == name and name.endswith('.service')
                 and '--apply' not in unit and '[Install]' not in unit
                 and 'Restart=no' in unit, 'PACKAGE_UNIT_AUTHORITY_CONFLICT')
    for name in package['unapproved_activation_templates']:
        _require(Path(name).name == name and name.endswith(('.service','.timer')), 'PACKAGE_ACTIVATION_PATH_CONFLICT')
    _require(digest(json.loads(base64.b64decode(package['files'][POLICY]['content_b64']))) == POLICY_PIN,
             'PACKAGE_POLICY_CONFLICT')
    return dict(status='DISABLED_PACKAGE_VERIFIED', package_sha256=package['package_sha256'],
                app_files=len(package['files']), orders_allowed=False, enabled=False)


def write_new(path, raw):
    """Exclusive/fsynced private write; never follows a link or overwrites state."""
    path = Path(path).absolute()
    _require(not any(p.is_symlink() for p in (path, *path.parents)), 'OUTPUT_SYMLINK')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    return sha(raw)


def install_disabled(package, paper, *, now_ms, target=None):
    """New app and inert unit templates only. Never touches /etc or /root/by-bot.

    Production CLI fixes target to BASE. A target argument exists only for local
    filesystem rehearsal. A repeated install verifies every byte; it cannot
    repair/overwrite a partial or drifted deployment.
    """
    verify_package(package)
    _require(now_ms >= POSTCHECK_MS and paper['status'] == 'PAPER_EXECUTION_PASS'
        and paper['receipt_sha256'] == digest({k:v for k,v in paper.items() if k!='receipt_sha256'}),
        'ACTUAL_PAPER_PASS_REQUIRED_BEFORE_INSTALL')
    base = Path(target or BASE).absolute()
    _require(not any(p.is_symlink() for p in (base, *base.parents)), 'INSTALL_SYMLINK')
    expected = {str(Path('app') / n): base64.b64decode(row['content_b64'], validate=True)
                for n,row in package['files'].items()}
    expected.update({str(Path('disabled-unit-templates') / n): text.encode()
                     for n,text in package['units'].items()})
    expected.update({str(Path('unapproved-activation-templates') / n): text.encode()
                     for n,text in package['unapproved_activation_templates'].items()})
    existing = base / 'disabled_install_receipt.json'
    if base.exists():
        _require(existing.is_file() and not existing.is_symlink(), 'PARTIAL_INSTALL_NO_REPAIR')
        from research_lab.alpaca_dynamic_live_runtime_v1 import read_json
        prior = read_json(str(existing))
        _require(prior['package_sha256'] == package['package_sha256']
                 and prior['paper_receipt_sha256'] == paper['receipt_sha256'], 'INSTALL_IDENTITY_CONFLICT')
        for name,raw in expected.items():
            path = base / name
            _require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents))
                and path.stat().st_nlink == 1 and path.stat().st_uid == os.getuid()
                and sha(path.read_bytes()) == sha(raw), 'INSTALLED_FILE_DRIFT:' + name)
        return prior
    base.mkdir(mode=0o700)
    sources = []
    for name,raw in sorted(expected.items()):
        path = base / name
        write_new(path, raw)
        sources.append(dict(path=str(path), sha256=sha(raw)))
    out = dict(schema='ALPACA_DYNAMIC_DISABLED_INSTALL_RECEIPT_V1',
        status='DISABLED_DEPLOYMENT_VERIFIED', base=str(base), enabled=False,
        orders_allowed=False, service_activation_count=0, installed_system_units=0,
        remote_app_mismatches=[], package_sha256=package['package_sha256'],
        paper_receipt_sha256=paper['receipt_sha256'], observed_ms=now_ms,
        source_files=sources, source_manifest_sha256=digest(sources),
        rollback='leave app disabled and original HALT in place; no production state changed')
    write_new(existing, canonical(out))
    return out


def initial_evidence(public_receipt, captured):
    """Recover account/parent IDs from the exact already-validated entry source."""
    raw = Path(captured).read_bytes()
    receipt = json.loads(Path(public_receipt).read_bytes())
    _require(sha(raw) == receipt['capture_sha256'], 'INITIAL_CAPTURE_PIN_CONFLICT')
    r = json.loads(raw)['response']
    rows = r['databases']['paper']['tables']['intents']['rows']
    _require(len(rows) == 1, 'INITIAL_INTENT_COUNT_CONFLICT')
    item = json.loads(rows[0][3])
    _require(item['receipt']['entry_order_id'] == receipt['entry_order_id']
        and item['receipt']['stop_order_id'] == receipt['stop_order_id'], 'INITIAL_RECEIPT_CONFLICT')
    return {**receipt, 'paper_account_id': item['account'],
            'live_account_id': r['live_broker']['account']['payload']['id'],
            'parent_receipt_id': item['plan']['receipt_id']}


def _payload(capture, group, name):
    source = capture[group][name]
    _require(source['http_status'] == 200, 'BROKER_GET_FAILED:' + group + ':' + name)
    value = source['payload']
    if isinstance(value, list):
        _require(len(value) < 100, 'BROKER_PAGE_INCOMPLETE:' + name)
    return value


def _ms(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)


def derive_paper_cost_closure(cash_before_path, after_path, paper_doc_path, protocol_path, *, now_ms):
    """Actual PAPER cash ledger + official no-regulatory-fee simulation semantics.

    Does not infer fees from an empty list. Personal commission=0 is separately
    source-bound; PAPER regulatory=0 is explicitly documented. LIVE CAT/SEC and
    liability reserves are not altered or waived by this PAPER-only closure.
    """
    from decimal import Decimal, ROUND_HALF_UP
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path
    paths=[safe_path(str(p),exists=True) for p in (cash_before_path,after_path,paper_doc_path,protocol_path)]
    pre=read_json(str(paths[0]))['response']; after=read_json(str(paths[1]))['response']
    doc=paths[2].read_bytes();protocol=read_json(str(paths[3]))
    _require(sha(doc)==PAPER_DOC_SHA and b'paper trading does not account for' in doc
        and b'Regulatory fees' in doc and sha(paths[3].read_bytes())==COMMISSION_PROTOCOL_SHA
        and dec(protocol['commission_rate'])==0 and protocol['owner_attestation']['api_commission_null_is_not_proof'] is True,
        'PAPER_FEE_PROTOCOL_SOURCE_REQUIRED')
    _require(now_ms>=POSTCHECK_MS and POSTCHECK_MS<=after['observed_ms']<=now_ms
        and after['activity_request_after_ms']<=pre['observed_ms']<after['observed_ms'], 'CASH_ACTIVITY_COVERAGE_CONFLICT')
    source=pre['paper_broker']['account']
    _require(source.get('http_status',200)==200,'PRE_ENTRY_ACCOUNT_GET_FAILED')
    original=json.loads(source['raw']) if 'raw' in source else source['payload']
    account=_payload(after,'paper_broker','account');activities=_payload(after,'paper_broker','activities')
    _require(account['id']==original['id']==after['packet']['paper_account'], 'PAPER_CASH_ACCOUNT_CONFLICT')
    _require(dec(account['accrued_fees'])==dec(account['pending_reg_taf_fees'])==0, 'PAPER_LIABILITY_UNRESOLVED')
    _require(len({a['id'] for a in activities})==len(activities),'DUPLICATE_CASH_ACTIVITY')
    item=json.loads(after['databases']['paper']['tables']['intents']['rows'][0][3])
    entry_id=item['receipt']['entry_order_id'];exits=item['terminal']['exit_orders']
    ids={entry_id}|{o['id'] for o in exits}; other=dec(0); owned=dec(0);seen_owned=set()
    for a in activities:
        at=a.get('transaction_time') or a.get('created_at')
        if not at:
            _require('date' in a and _ms(a['date']+'T00:00:00Z')>pre['observed_ms'], 'CASH_ACTIVITY_TIMING_UNKNOWN')
            at=a['date']+'T00:00:00Z'
        if _ms(at)<=pre['observed_ms']:continue
        _require(_ms(at)<=after['observed_ms'],'CASH_ACTIVITY_FUTURE')
        if a['activity_type']=='FILL':
            _require(a['side'] in {'buy','sell'},'CASH_FILL_SIDE_UNKNOWN')
            value=positive(a['qty'])*positive(a['price'])*(1 if a['side']=='sell' else -1)
            if a['order_id'] in ids:
                owned+=value;seen_owned.add(a['order_id'])
            else:other+=value
        elif a['activity_type']=='FEE':
            _require(dec(a['net_amount'])==0,'PAPER_FEE_SEMANTICS_CONFLICT')
        else:
            # No unseen movement is classified as zero; explicit broker amount.
            other+=dec(a['net_amount'])
    gross=dec(item['terminal']['gross_before_fees'])
    _require(seen_owned==ids and owned==gross,'OWNED_CASH_ACTIVITY_GROSS_CONFLICT')
    _require((dec(original['cash'])+gross+other).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)==dec(account['cash']),
             'ACCOUNT_DAY_CASH_RECONCILIATION')
    rows=[dict(path=str(p),sha256=sha(p.read_bytes())) for p in paths]
    return dict(schema='ALPACA_PAPER_ACCOUNT_DAY_FINALITY_V1',account_id=account['id'],
        entry_order_id=entry_id,exit_order_ids=sorted(o['id'] for o in exits),
        cash_before=original['cash'],cash_after=account['cash'],other_cash_net_usd=str(other),
        gross_usd=str(gross),commission_usd='0',regulatory_fees_usd='0',unresolved_liability_usd='0',
        cash_reconciliation_precision='BROKER_USD_CENTS',closure_status='ACCOUNT_DAY_FEES_RECONCILED',
        observed_ms=now_ms,capture_response_sha256=digest(after),activities_sha256=digest(activities),
        source_files=rows,source_manifest_sha256=digest(rows),
        fee_semantics='documented PAPER simulation only; future LIVE regulatory/cost contract unchanged',
        official_source='https://docs.alpaca.markets/us/docs/paper-trading',live_cost_finality_proven=False)


def _derive_paper_posted_cost_closure(*, cash_before_path, initial_path, rearm_path,
                                      terminal_path, protocol_path, now_ms, semantic_v3=False):
    """Actual posted retail fees + four captured broker-cent checkpoints.

    Narrow contract for this single NET round trip, not a publication SLA or a
    general cash-ledger guess. Both CAT/SEC account-day assessments must actually
    appear and match the already-pinned schedule. Missing rows stay BLOCKED.
    The older no-fee/documentation derivation and its receipts remain unchanged.
    """
    from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path
    names=('cash_before','initial','rearm','terminal','protocol')
    values=(cash_before_path,initial_path,rearm_path,terminal_path,protocol_path)
    paths={n:safe_path(str(p),exists=True) for n,p in zip(names,values)}
    captures={n:read_json(str(paths[n]))['response'] for n in names[:-1]}
    protocol=read_json(str(paths['protocol']))
    _require(sha(paths['protocol'].read_bytes())==COMMISSION_PROTOCOL_SHA
        and dec(protocol['commission_rate'])==0, 'POSTED_FEE_PROTOCOL_CONFLICT')
    pre,first,rearm,after=(captures[n] for n in names[:-1])
    _require(pre['observed_ms']<first['observed_ms']<rearm['observed_ms']<after['observed_ms']<=now_ms
        and after['observed_ms']>=POSTCHECK_MS
        and after['activity_request_after_ms']<=pre['observed_ms'], 'POSTED_FEE_CAPTURE_TIMING_CONFLICT')
    accounts=[]
    for capture in (pre,first,rearm,after):
        source=capture['paper_broker']['account']
        _require(source.get('http_status',200)==200,'POSTED_FEE_ACCOUNT_GET_FAILED')
        accounts.append(json.loads(source['raw']) if 'raw' in source else source['payload'])
    _require(len({a['id'] for a in accounts})==1 and accounts[-1]['id']==after['packet']['paper_account']
        and _payload(after,'live_broker','account')['id']==protocol['account_id'], 'POSTED_FEE_ACCOUNT_CONFLICT')
    _require(dec(accounts[-1]['accrued_fees'])==dec(accounts[-1]['pending_reg_taf_fees'])==0,
        'PAPER_LIABILITY_UNRESOLVED')
    acts=_payload(after,'paper_broker','activities')
    _require(len({a['id'] for a in acts})==len(acts),'DUPLICATE_CASH_ACTIVITY')
    item=json.loads(after['databases']['paper']['tables']['intents']['rows'][0][3])
    entry=item['receipt']['entry_order_id'];exit_ids={o['id'] for o in item['terminal']['exit_orders']}
    fills=[a for a in acts if a['activity_type']=='FILL' and _ms(a['transaction_time'])>pre['observed_ms']]
    _require(len(fills)==2 and {f['order_id'] for f in fills}=={entry}|exit_ids
        and all(f['symbol']=='NET' and _ms(f['transaction_time'])<=after['observed_ms'] for f in fills),
        'POSTED_FEE_EXACT_ROUND_TRIP_REQUIRED')
    buy=next(f for f in fills if f['order_id']==entry)
    sell=next(f for f in fills if f['order_id'] in exit_ids)
    _require(buy['side']=='buy' and sell['side']=='sell'
        and positive(buy['qty'])==positive(sell['qty']), 'POSTED_FEE_FILL_CONFLICT')
    days=[f['transaction_time'][:10] for f in (buy,sell)]
    _require(days[0]<days[1] and _ms(buy['transaction_time'])<=first['observed_ms']
        and rearm['observed_ms']<_ms(sell['transaction_time']), 'POSTED_FEE_CHECKPOINT_ORDER')
    model=protocol['regulatory_model'];ceil=lambda x:(x/Decimal('.01')).to_integral_value(rounding=ROUND_CEILING)*Decimal('.01')
    _require(dec(model['taf_per_share_rate'])==0, 'POSTED_FEE_TAF_CONTRACT_CONFLICT')
    expected={(days[0],'CAT'):ceil(positive(buy['qty'])*dec(model['cat_nms_executed_share_rate'])),
        (days[1],'CAT'):ceil(positive(sell['qty'])*dec(model['cat_nms_executed_share_rate'])),
        (days[1],'SEC'):ceil(positive(sell['qty'])*positive(sell['price'])*dec(model['sec_sell_value_rate']))}
    actual={}
    for row in acts:
        if row['activity_type']=='FILL':continue
        _require(row['activity_type']=='FEE','POSTED_FEE_FOREIGN_CASH_ACTIVITY')
        kind=next((k for k in ('CAT','SEC') if row.get('description','').startswith(k+' fee ')),None)
        if semantic_v3:
            kind=_posted_fee_kind_v3(row)
        key=(row.get('date'),kind)
        _require(key in expected and dec(row['net_amount'])<=0,'POSTED_FEE_UNCLASSIFIED_ACTIVITY')
        actual[key]=actual.get(key,dec(0))-dec(row['net_amount'])
    _require(actual==expected, 'PAPER_POSTED_EXIT_FEE_FINALITY_PENDING_OR_CONFLICT')
    cash=[dec(a['cash']) for a in accounts];quant=lambda x:x.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    _require(cash[1]==quant(cash[0]-positive(buy['qty'])*positive(buy['price']))
        and cash[2]==cash[1]-actual[(days[0],'CAT')]
        and cash[3]==quant(cash[2]+positive(sell['qty'])*positive(sell['price']))
                        -actual[(days[1],'CAT')]-actual[(days[1],'SEC')],
        'POSTED_FEE_CENT_CHECKPOINT_RECONCILIATION')
    gross=positive(sell['qty'])*positive(sell['price'])-positive(buy['qty'])*positive(buy['price'])
    _require(gross==dec(item['terminal']['gross_before_fees']), 'POSTED_FEE_GROSS_CONFLICT')
    regulatory=sum(actual.values(),dec(0));net=gross-regulatory
    rows=[dict(path=str(paths[n]),sha256=sha(paths[n].read_bytes())) for n in names]
    return dict(schema='ALPACA_PAPER_ACCOUNT_DAY_FINALITY_V1',account_id=accounts[-1]['id'],
        entry_order_id=entry,exit_order_ids=sorted(exit_ids),cash_before=str(cash[0]),cash_after=str(cash[3]),
        other_cash_net_usd='0',gross_usd=str(gross),commission_usd='0',regulatory_fees_usd=str(regulatory),
        unresolved_liability_usd='0',closure_status='ACCOUNT_DAY_FEES_RECONCILED',observed_ms=now_ms,
        capture_response_sha256=digest(after),activities_sha256=digest(acts),
        source_files=rows,source_manifest_sha256=digest(rows),source_paths={n:str(paths[n]) for n in names},
        cash_reconciliation_precision='BROKER_CENT_CHECKPOINT_CHAIN',cash_rounding_residual_usd=str(cash[3]-cash[0]-net),
        source_contract='ACTUAL_POSTED_NET_SINGLE_ROUND_TRIP_V3' if semantic_v3 else 'ACTUAL_POSTED_NET_SINGLE_ROUND_TRIP_V2',
        fee_semantics='actual posted account-day CAT/SEC; no documentation-derived zero',live_cost_finality_proven=False)


def _posted_fee_kind_v3(row):
    """Alpaca FEE/REG is SEC; keep legacy and unified subtype spellings explicit."""
    old=row.get('activity_sub_type');new=row.get('activity_subtype')
    _require(old is None or new is None or old==new,'POSTED_FEE_SUBTYPE_CONFLICT')
    subtype=old if old is not None else new
    prefix=next((k for k in ('CAT','SEC','REG') if row.get('description','').startswith(k+' fee ')),None)
    if subtype is None:
        _require(prefix in {'CAT','SEC'},'POSTED_FEE_DOCUMENTED_SUBTYPE_REQUIRED')
        return prefix
    _require(row.get('activity_type')=='FEE' and row.get('status')=='executed'
        and row.get('currency')=='USD' and subtype in {'CAT','REG','SEC'},'POSTED_FEE_SCHEMA_CONFLICT')
    kind='SEC' if subtype=='REG' else subtype
    _require(prefix is None or ('SEC' if prefix=='REG' else prefix)==kind,'POSTED_FEE_DESCRIPTION_SUBTYPE_CONFLICT')
    return kind


def derive_paper_posted_cost_closure_v2(**kwargs):
    return _derive_paper_posted_cost_closure(**kwargs)


def derive_paper_posted_cost_closure_v3(**kwargs):
    return _derive_paper_posted_cost_closure(**kwargs,semantic_v3=True)


def _order_timestamp_ns_v1(value):
    import re
    from datetime import timezone
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})',value or '')
    _require(match is not None,'EXECUTION_TIMESTAMP_FORMAT')
    base=datetime.fromisoformat(match[1]+match[3].replace('Z','+00:00'))
    delta=base.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    fraction=match[2] or ''
    return (delta.days*86400+delta.seconds)*1000000000+int(fraction.ljust(9,'0') or '0'),len(fraction)


def execution_identity_v1(retained,broker):
    """Exact owned economic identity, narrow REST/event representation compatibility.

    Never changes either JSON. Unknown field changes still reject. Only an added
    access_key source and 7-9 digit to <=6 digit microsecond rounding are eligible;
    equal-precision timestamp differences are not a blanket timing tolerance.
    """
    required={'id','symbol','side','type','qty','filled_qty','filled_avg_price','status'}
    _require(required<=retained.keys() and required<=broker.keys(),'EXECUTION_IDENTITY_FIELDS_REQUIRED')
    _require(bool(retained['id']),'EXECUTION_ORDER_ID_REQUIRED')
    _require(set(retained)-{'source'}==set(broker)-{'source'},'EXECUTION_FIELD_SET_CONFLICT')
    ignored=[]
    if retained.get('source')!=broker.get('source'):
        _require(retained.get('source') is None and broker.get('source')=='access_key','EXECUTION_SOURCE_CONFLICT')
        ignored.append('source')
    normalized=[]
    for key in sorted(set(retained)-{'source'}):
        old,new=retained[key],broker[key]
        if key.endswith('_at'):
            if old is None or new is None:
                _require(old is new,'EXECUTION_TIMESTAMP_NULL_CONFLICT:'+key)
                continue
            a,pa=_order_timestamp_ns_v1(old);b,pb=_order_timestamp_ns_v1(new)
            if a!=b:
                high,low,ph,pl=(a,b,pa,pb) if pa>pb else (b,a,pb,pa)
                _require(ph>6 and pl<=6 and ((high+500)//1000)*1000==low,
                    'EXECUTION_TIMESTAMP_CONFLICT:'+key)
                normalized.append(key)
        else:
            _require(old==new,'EXECUTION_MATERIAL_FIELD_CONFLICT:'+key)
    return dict(schema='ALPACA_EXECUTION_IDENTITY_V1',status='EXECUTION_IDENTITY_MATCH',
        retained_raw_sha256=digest(retained),broker_raw_sha256=digest(broker),
        hash_basis='complete canonical JSON payload; original capture/wire-source hashes retained separately',
        timestamp_compatibility='exact UTC nanoseconds, or high-precision value rounded to the REST microsecond grid',
        normalized_timestamp_fields=normalized,permitted_metadata_additions=ignored)


def verify_paper_lifecycle(arm, initial, before, after, fees, *, now_ms):
    """Captured original lifecycle; never substitutes fees=0 for missing rows.

    before is the original next-day re-arm observation; after the original final
    observation. Fee closure is a separately reviewed account/day source with
    physically pinned raw files. This function creates no runtime state.
    """
    try:
        _require(now_ms >= POSTCHECK_MS and POSTCHECK_MS <= after['observed_ms'] <= now_ms,
                 'ORIGINAL_POSTCHECK_NOT_DUE_OR_CAPTURE_FUTURE')
        _require(initial['status'] == 'ENTRY_PROTECTED_LIFECYCLE_PENDING'
                 and initial['symbol'] == 'NET' and initial['offline_captured_state_recovery']
                 and all(r['same_receipt'] and r['dispatch_calls'] == 0
                         for r in initial['offline_captured_state_recovery']), 'INITIAL_ENTRY_RECOVERY_NOT_PROVEN')
        account_id = initial['paper_account_id']
        entry_id = initial['entry_order_id']; qty = positive(initial['qty'])
        for capture in (before, after):
            _require(capture['broker_writes'] == capture['remote_writes'] == 0, 'READBACK_AUTHORITY_CONFLICT')
            _require(capture['packet_sha256'] == arm['packet_sha256']
                and capture['app_manifest']['sha256'] == arm['manifest_sha256']
                and capture['app_manifest']['files'] == arm['app_files']
                and not capture['app_manifest']['mismatches'], 'ORIGINAL_DEPLOYMENT_CHANGED')
            _require(_payload(capture, 'paper_broker', 'account')['id'] == account_id
                and capture['packet']['paper_account'] == account_id, 'PAPER_ACCOUNT_CONFLICT')
            _require(not _payload(capture, 'live_broker', 'positions')
                and not _payload(capture, 'live_broker', 'open_orders')
                and capture['live_halt']['halted'] is True, 'LIVE_NOT_FLAT_HALTED')
            _require(_payload(capture, 'live_broker', 'account')['id']==initial['live_account_id'],
                     'LIVE_READBACK_ACCOUNT_CONFLICT')
            _require(sorted(p['symbol'] for p in _payload(capture, 'paper_broker', 'positions')
                            if p['symbol'] != 'NET') == arm['paper_legacy_symbols'], 'LEGACY_HOLDINGS_CONFLICT')
            if 'legacy_NET_exclusion_sha256' in arm:
                _require(capture['legacy_exclusions']['sha256'] == arm['legacy_NET_exclusion_sha256'],
                         'LEGACY_EXCLUSION_CONFLICT')
            for name, expected in arm['production_services_unchanged'].items():
                for line in expected:
                    key, value = line.split('=', 1)
                    _require(str(capture['services'][name][key]) == value, 'PRODUCTION_SERVICE_CHANGED:' + name)
        bguard = before['runtime']['runtime/guard/latest.json']['payload']
        aguard = after['runtime']['runtime/guard/terminal.json']['payload']
        for guard in (bguard, aguard):
            _require(guard['deadline_ms'] == arm['guard_hard_end_ms']
                and guard['unwind_not_before_ms'] == arm['guard_unwind_not_before_ms'], 'ORIGINAL_SCHEDULE_CHANGED')
        tables = after['databases']['paper']['tables']['intents']
        _require(tables['count'] == len(tables['rows']) == 1, 'PERSISTENT_INTENT_COUNT_CONFLICT')
        item = json.loads(tables['rows'][0][3])
        rearm = item['rearms']['2026-10-13']
        active = [o for o in _payload(before, 'paper_broker', 'open_orders') if o['symbol'] == 'NET']
        from scripts.equities_alpaca_paper_bridge import _validated_existing_intended_lifecycle
        if bguard['receipt']['status']=='PAPER_PROTECTED':
            _require(len(active) == 1, 'DAY_REARM_FULL_NATIVE_PROTECTION_NOT_PROVEN')
            stop = active[0]
            _require(stop['id']==bguard['receipt']['stop_order_id'] and stop['status'] in ACTIVE,
                     'DAY_REARM_NOT_PROVEN')
            positions=[p for p in _payload(before,'paper_broker','positions') if p['symbol']=='NET']
            _require(len(positions)==1 and positive(positions[0]['qty'])==dec(stop['qty'])-dec(stop['filled_qty']),
                     'REARM_REMAINING_PROTECTION_CONFLICT')
            record = _validated_existing_intended_lifecycle(
                before['paper_runtime']['protective_exit_hwm.json']['payload']['NET'], account_id)
            _require(record['accepted_order_id']==stop['id'] and item['managed_stop_order_id']==stop['id'],
                     'REARM_NATIVE_OWNERSHIP_CONFLICT')
            _require(item['terminal_preparation']['owned_record']==record,'TERMINAL_NATIVE_OWNERSHIP_CONFLICT')
        else:
            # A real rearmed native stop may fill before the read-only snapshot.
            # Require its full broker fill and persisted terminal reconciliation;
            # neither flatness nor a missing open order substitutes for proof.
            _require(bguard['receipt']['status'].endswith('EXIT_PENDING_FINALITY')
                and not active and not any(p['symbol']=='NET' for p in _payload(before,'paper_broker','positions')),
                'DAY_REARM_NOT_PROVEN')
            matches=[o for o in _payload(after,'paper_broker','net_orders') if o.get('client_order_id')==rearm['cid']]
            _require(len(matches)==1,'DAY_REARM_FULL_NATIVE_PROTECTION_NOT_PROVEN')
            stop=matches[0]
            _require(stop['status']=='filled' and positive(stop['filled_qty'])==qty
                and _ms(stop['filled_at'])<=before['observed_ms'] and stop in bguard['receipt']['exit_orders'],
                'DAY_REARM_FILL_NOT_PROVEN')
            record=_validated_existing_intended_lifecycle(item['terminal_preparation']['reconciled_record'],account_id)
            owned=_validated_existing_intended_lifecycle(item['terminal_preparation']['owned_record'],account_id)
            _require(record['entry_order_id']==owned['entry_order_id']==entry_id
                and positive(owned['entry_fill_qty'])==qty and record['accepted_order_id']==stop['id'],
                'TERMINAL_NATIVE_OWNERSHIP_CONFLICT')
        _require(stop['id'] != initial['stop_order_id'] and stop['symbol']=='NET' and stop['side'] == 'sell'
            and stop['type'] == 'stop' and stop['time_in_force'] == 'day'
            and positive(stop['qty']) == qty
            and positive(stop['stop_price']) >= positive(initial['stop_price'])
            and _ms(stop['submitted_at']) >= 1791898200000
            and _ms(stop['submitted_at']) <= before['observed_ms'] < arm['guard_unwind_not_before_ms'],
            'DAY_REARM_SOURCE_OR_FLOOR_CONFLICT')
        _require(record['entry_order_id'] == entry_id and positive(record['entry_fill_qty']) == qty
            and positive(record['qty']) == qty
            and positive(record['accepted_stop_floor']) == positive(stop['stop_price']),
            'REARM_NATIVE_OWNERSHIP_CONFLICT')
        _require(not any(p['symbol'] == 'NET' for p in _payload(after, 'paper_broker', 'positions'))
            and not any(o['symbol'] == 'NET' for o in _payload(after, 'paper_broker', 'open_orders')),
            'OWNED_EXIT_NOT_FLAT')
        _require(item['account'] == account_id and item['plan']['symbol'] == 'NET'
            and item['plan']['receipt_id'] == initial['parent_receipt_id']
            and item['receipt']['entry_order_id'] == entry_id, 'PERSISTENT_OWNERSHIP_CONFLICT')
        _require(rearm['cid'] == stop['client_order_id']
            and positive(rearm['qty']) == qty
            and positive(rearm['floor']) == positive(stop['stop_price']), 'REARM_LINEAGE_CONFLICT')
        terminal = item['terminal']
        _require(terminal == aguard['receipt'] and terminal['status'].endswith('EXIT_PENDING_FINALITY'),
                 'OWNED_TERMINAL_RECEIPT_CONFLICT')
        orders = _payload(after, 'paper_broker', 'net_orders')
        _require(len({o['id'] for o in orders}) == len(orders), 'DUPLICATE_BROKER_ORDER')
        order_map = {o['id']: o for o in orders}
        entry = order_map[entry_id]
        _require(entry['symbol'] == 'NET' and entry['side'] == 'buy'
            and entry['status'] in TERMINAL and positive(entry['filled_qty']) == qty
            and dec(entry['filled_avg_price']) == positive(initial['fill_price']), 'ENTRY_FILL_CONFLICT')
        exits = terminal['exit_orders']
        _require(bool(exits) and len({o['id'] for o in exits}) == len(exits), 'EXIT_IDS_CONFLICT')
        for order in exits:
            actual = order_map[order['id']]
            execution_identity_v1(order,actual)
            _require(actual['symbol'] == 'NET' and actual['side'] == 'sell'
                and actual['type'] in {'market', 'stop'} and actual['status'] in TERMINAL,
                'EXACT_OWNED_EXIT_CONFLICT')
            _require(_ms(actual['filled_at']) <= after['observed_ms'], 'EXIT_FILL_FUTURE')
            if actual['type'] == 'market':
                _require(_ms(actual['filled_at']) >= arm['guard_unwind_not_before_ms'], 'EARLY_VALIDATION_UNWIND')
        _require(sum(dec(o['filled_qty']) for o in exits) == qty, 'EXIT_QUANTITY_INCOMPLETE')
        allowed = {entry_id, initial['stop_order_id'], stop['id']} | {o['id'] for o in exits}
        _require(all(o['id'] in allowed and o['status'] in TERMINAL for o in orders), 'FOREIGN_OR_UNRESOLVED_ORDER')
        _require('NET' not in after['paper_runtime']['protective_exit_hwm.json']['payload'], 'OWNED_NATIVE_LEDGER_NOT_RETIRED')
        fills = _payload(after, 'paper_broker', 'fills')
        _require(all(f['order_id'] in allowed for f in fills if f['symbol'] == 'NET'), 'FOREIGN_FILL')
        for order in [entry, *exits]:
            rows = [f for f in fills if f['order_id'] == order['id']]
            _require(sum(dec(f['qty']) for f in rows) == dec(order['filled_qty'])
                and sum(dec(f['qty']) * dec(f['price']) for f in rows)
                    == dec(order['filled_qty']) * dec(order['filled_avg_price']), 'FILL_ACTIVITY_RECONCILIATION')
        gross = sum(dec(o['filled_qty']) * dec(o['filled_avg_price']) for o in exits) - qty * dec(entry['filled_avg_price'])
        _require(gross == dec(terminal['gross_before_fees']), 'GROSS_PNL_CONFLICT')
        if fees is None:
            return blocked('PAPER_COST_FINALITY_SOURCE_REQUIRED')
        activities = _payload(after, 'paper_broker', 'activities')
        _physical_sources(fees['source_files'], fees['source_manifest_sha256'])
        _require(fees['schema'] == 'ALPACA_PAPER_ACCOUNT_DAY_FINALITY_V1'
            and fees['closure_status'] == 'ACCOUNT_DAY_FEES_RECONCILED'
            and fees['account_id'] == account_id and fees['entry_order_id'] == entry_id
            and sorted(fees['exit_order_ids']) == sorted(o['id'] for o in exits)
            and fees['capture_response_sha256'] == digest(after)
            and fees['activities_sha256'] == digest(activities)
            and after['observed_ms'] <= fees['observed_ms'] <= now_ms
            and dec(fees['unresolved_liability_usd']) == 0
            and dec(fees['gross_usd']) == gross, 'PAPER_COST_FINALITY_SOURCE_CONFLICT')
        commission = dec(fees['commission_usd']); regulatory = dec(fees['regulatory_fees_usd'])
        _require(min(commission, regulatory) >= 0, 'NEGATIVE_FEE')
        cash = dec(_payload(after, 'paper_broker', 'account')['cash'])
        net = gross - commission - regulatory
        expected_cash=dec(fees['cash_before'])+dec(fees['other_cash_net_usd'])+net
        if fees.get('cash_reconciliation_precision')=='BROKER_USD_CENTS':
            from decimal import Decimal,ROUND_HALF_UP
            expected_cash=expected_cash.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        elif fees.get('cash_reconciliation_precision')=='BROKER_CENT_CHECKPOINT_CHAIN':
            # Reconstruct from every physically pinned raw checkpoint. A caller
            # cannot introduce an arbitrary residual to force cash equality.
            derive=derive_paper_posted_cost_closure_v3 if fees.get('source_contract')=='ACTUAL_POSTED_NET_SINGLE_ROUND_TRIP_V3' else derive_paper_posted_cost_closure_v2
            rebuilt=derive(
                **{n+'_path':p for n,p in fees['source_paths'].items()},now_ms=fees['observed_ms'])
            _require(rebuilt==fees, 'POSTED_FEE_RECONSTRUCTION_CONFLICT')
            expected_cash+=dec(fees['cash_rounding_residual_usd'])
        _require(cash == dec(fees['cash_after']) and cash == expected_cash,
            'ACCOUNT_DAY_CASH_RECONCILIATION')
        # A separately reviewed declaration is required even if activities are
        # empty: an empty page/pending_fees=0 alone cannot close liability.
        result = dict(schema='ALPACA_PAPER_LIFECYCLE_FINAL_V1', status='PAPER_EXECUTION_PASS',
            orders_allowed=False, live_orders_allowed=False, ready_for_live_go=False,
            paper_account_id=account_id, symbol='NET', entry_order_id=entry_id,
            exit_order_ids=sorted(o['id'] for o in exits), qty=str(qty), gross_usd=str(gross),
            net_usd=str(net), before_response_sha256=digest(before), after_response_sha256=digest(after),
            fee_source_sha256=digest(fees), actual_day_rearm=True, actual_process_restart_performed=False,
            persistent_state_recovery=initial['offline_captured_state_recovery'], additional_paper_entries=0)
        result['receipt_sha256'] = digest(result)
        return result
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError, RuntimeError) as exc:
        return blocked(str(exc))


def exact_dossier(*, paper, deployment, binding, intake, policy, now_ms):
    """Existing exact-plan GO only. No preview quantity or future-plan authority."""
    from research_lab.alpaca_dynamic_live_runtime_v1 import custody
    from research_lab.alpaca_dynamic_live_intake_v1 import compile_intake
    try:
        _require(paper['status'] == 'PAPER_EXECUTION_PASS'
            and paper['receipt_sha256'] == digest({k: v for k, v in paper.items() if k != 'receipt_sha256'}),
            'PAPER_LIFECYCLE_NOT_PASS')
        _require(deployment['status'] == 'DISABLED_DEPLOYMENT_VERIFIED'
            and deployment['enabled'] is False and deployment['orders_allowed'] is False
            and deployment['paper_receipt_sha256'] == paper['receipt_sha256']
            and deployment['observed_ms'] <= now_ms
            and deployment['remote_app_mismatches'] == [] and deployment['service_activation_count'] == 0,
            'ACTUAL_DISABLED_DEPLOYMENT_REQUIRED')
        _physical_sources(deployment['source_files'], deployment['source_manifest_sha256'])
        custody(binding, intake, policy)
        _require(binding['sources']['paper']['sha256'] == sha(canonical(paper)), 'PAPER_BINDING_RECEIPT_CONFLICT')
        _require(compile_intake(intake['plan'], policy, intake['scope'], now_ms)['status']
                 == 'LIVE_INTAKE_PREPARED_ORDERS_OFF', 'EXACT_OPENING_TIME_PLAN_REQUIRED')
        plan = intake['plan']
        out = dict(schema='ALPACA_DYNAMIC_EXACT_LIVE_DOSSIER_V1', status='READY_FOR_LIVE_GO',
            ready_for_live_go=True, orders_allowed=False, live_orders_allowed=False,
            account_id=intake['account_id'], ticker=plan['symbol'], session=plan['session'],
            qty=plan['qty'], limit_price=intake['entry_payload']['limit_price'],
            notional_usd=str(dec(plan['qty']) * dec(intake['entry_payload']['limit_price'])),
            stop_distance=plan['risk_distance'], stop_logic='actual fill minus frozen distance; native monotonic HWM/floor and DAY re-arm',
            stop_distance_risk_usd=str(dec(plan['qty']) * dec(plan['risk_distance'])),
            max_loss='stop distance is not a guaranteed loss ceiling across gaps/illiquidity',
            caps={k: policy[k] for k in ('capital_usd','gross','max_positions','max_new_entries_per_session')},
            liability_reserve_usd=intake['scope']['liability_reserve_usd'],
            commission_rate=plan['fee_rate'], owner_ids=dict(entry=intake['entry_payload']['client_order_id'],
                stop=intake['stop_client_order_id']), intake_sha256=intake['intake_sha256'],
            binding_sha256=digest(binding), package_sha256=deployment['package_sha256'],
            lock_path=binding['lock_path'], paper_receipt_sha256=paper['receipt_sha256'],
            required_owner_go_text='GO ALPACA_DYNAMIC_V1 ' + intake['intake_sha256'],
            entry='one exact limit quantity, first five minutes only, no resend/reprice',
            exit='existing owned native DAY stop/ratchet; exact-ID recovery',
            kill='--apply --maintenance --kill with exact separately approved permit; owned only',
            rollback='HALT new entries; retain owned management until exit/finality; retain all state')
        out['dossier_sha256'] = digest(out)
        return out
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return blocked(str(exc))


def pre_entry_dossier(*, paper, deployment, binding, intent, policy, preparation, now_ms):
    """Concrete bounded dossier before opening; GO still absent and required.

    No provisional quantity becomes a reservation. Physical LIVE account/quote/
    asset/cost/authority sources and the independent book must already exist.
    """
    from decimal import Decimal, ROUND_DOWN
    from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path
    import sqlite3
    try:
        _require(paper['status']=='PAPER_EXECUTION_PASS'
            and paper['receipt_sha256']==digest({k:v for k,v in paper.items() if k!='receipt_sha256'}), 'PAPER_LIFECYCLE_NOT_PASS')
        _require(deployment['status']=='DISABLED_DEPLOYMENT_VERIFIED' and deployment['enabled'] is False
            and deployment['orders_allowed'] is False and deployment['service_activation_count']==0
            and deployment['observed_ms']<=now_ms
            and deployment['paper_receipt_sha256']==paper['receipt_sha256'], 'ACTUAL_DISABLED_DEPLOYMENT_REQUIRED')
        _physical_sources(deployment['source_files'],deployment['source_manifest_sha256'])
        sources={}
        for name in ('authority','paper','old_terminal','cost'):
            row=binding['sources'][name]
            _physical_sources([row],digest([row]));sources[name]=read_json(row['path'])
        _require(sources['paper']==paper, 'PAPER_BINDING_RECEIPT_CONFLICT')
        authority=sources['authority'];old=sources['old_terminal'];cost=sources['cost']
        _require(authority['account_id']==policy['account_id'] and authority['endpoint']==binding['endpoint']
            and all(authority[k] is True for k in ('single_entry_owner_verified','single_manager_verified','old_monthly_entries_off'))
            and authority['lock_path']==binding['lock_path'] and authority['ledger_path']==binding['ledger_path'],
            'ACTUAL_EXCLUSIVE_AUTHORITY_REQUIRED')
        root=Path(binding['broker_root']);runtime=Path(binding['runtime'])
        _require(root.is_absolute() and runtime==Path(binding['ledger_path']).parent
            and runtime.is_relative_to(root/'runtime'), 'ORIGINAL_RUNTIME_SCOPE_REQUIRED')
        for name in ('lock_path','ledger_path','halt_path'):
            _require(safe_path(binding[name]).is_relative_to(root/'runtime'), 'ORIGINAL_RUNTIME_SCOPE_REQUIRED')
        from scripts import equities_alpaca_paper_bridge as native
        _require(binding['native_bridge_sha256']==sha(Path(native.__file__).read_bytes()), 'NATIVE_BRIDGE_SOURCE_CONFLICT')
        slot=next(s for s in policy['inherited_slots'] if s['entry_order_id']==intent['slot_entry_order_id'])
        _require(old['status']=='TERMINAL_FINAL' and old['evidence_kind']=='BROKER_LIVE'
            and old['account_id']==policy['account_id'] and old['entry_order_id']==slot['entry_order_id']
            and positive(old['qty'])==positive(slot['qty']), 'ACTUAL_OLD_VACANCY_REQUIRED')
        _require(cost['source_status']=='SOURCE_BOUND' and cost['account_id']==policy['account_id']
            and cost['endpoint']==binding['endpoint'] and dec(cost['commission_rate'])==0
            and min(dec(cost['buy_regulatory_reserve_usd']),dec(cost['unresolved_liability_usd']))>=0, 'ACTUAL_COST_SOURCE_REQUIRED')
        _physical_sources(preparation['source_files'],preparation['source_manifest_sha256'])
        _require(any(row['sha256']==intent['price_source_sha256'] for row in preparation['source_files']), 'INTENT_PRICE_SOURCE_PIN_CONFLICT')
        snapshot=preparation['snapshot'];quote=snapshot['quote'];account=snapshot['account'];asset=snapshot['asset']
        _require(any(read_json(row['path'])==snapshot or read_json(row['path']).get('snapshot')==snapshot
                     for row in preparation['source_files']), 'PREPARATION_RAW_SNAPSHOT_CONFLICT')
        _require(account['id']==policy['account_id'] and snapshot['endpoint']==binding['endpoint']
            and account.get('trading_blocked') is False and account.get('account_blocked') is False
            and not snapshot['positions'] and not snapshot['open_orders'], 'FRESH_ACCOUNT_OR_OWNERSHIP_CONFLICT')
        _require(asset['symbol']==intent['symbol'] and asset['status']=='active' and asset['tradable'] is True
            and (positive(intent['max_qty'])==positive(intent['max_qty']).to_integral_value() or asset['fractionable'] is True),
            'FRESH_ASSET_REQUIRED')
        _require(all(snapshot['gates'][k] is True for k in ('earnings','reentry','concentration','protection')), 'FRESH_GATES_REQUIRED')
        qts=_ms(quote['t'])
        _require(qts==intent['quote_cts_ms'] and intent['prepared_ms']==snapshot['observed_ms']
            and 0<=now_ms-snapshot['observed_ms']<=policy['max_snapshot_age_ms']
            and 0<=snapshot['observed_ms']-qts<=policy['max_snapshot_age_ms']
            and positive(intent['max_limit_price'])<=positive(quote['ap']).quantize(Decimal('.01'),rounding=ROUND_DOWN),
            'FRESH_PREPARATION_PRICE_SOURCE_REQUIRED')
        reserve=dec(cost['buy_regulatory_reserve_usd'])+dec(cost['unresolved_liability_usd'])
        _require(min(dec(account['cash']),dec(account['non_marginable_buying_power']))-reserve
            >=positive(intent['max_notional_usd']), 'PRE_ENTRY_CASH_LIABILITY_REJECT')
        book=safe_path(binding['source_book'],exists=True)
        _require(not book.is_relative_to(runtime),'SOURCE_AND_DISPATCH_BOOK_MUST_BE_SEPARATE')
        with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as db:
            meta=dict(db.execute('SELECT key,value FROM meta'))
            _require(meta.get('policy')==digest(policy) and meta.get('runtime_kind')=='LIVE_DYNAMIC_SEPARATE', 'LIVE_SOURCE_BOOK_IDENTITY')
            rankings=[json.loads(raw) for raw, in db.execute('SELECT payload FROM rankings')]
            ranking=next((r for r in rankings if digest(r)==intent['ranking_sha256']),None)
            _require(ranking is not None, 'SEALED_RANKING_BOOK_PIN_REQUIRED')
            pick=next((p for p in ranking['picks'] if p['symbol']==intent['symbol']),None)
            _require(pick is not None and positive(pick['signal_close'])-positive(pick['stop_price'])
                ==positive(intent['reference_risk_distance']), 'SEALED_RANKING_STOP_DISTANCE_CONFLICT')
            _require(not db.execute('SELECT 1 FROM intents').fetchone()
                and not db.execute('SELECT 1 FROM intent_attempts').fetchone(), 'FIRST_INTENT_ALREADY_RESERVED')
        rebuilt=prepare_first_intent(policy=policy,binding=binding,ticker=intent['symbol'],session=intent['session'],
            ranking_sha256=intent['ranking_sha256'],slot_entry_order_id=intent['slot_entry_order_id'],
            risk_distance=intent['reference_risk_distance'],max_qty=intent['max_qty'],
            max_notional_usd=intent['max_notional_usd'],max_risk_usd=intent['max_risk_usd'],
            max_limit_price=intent['max_limit_price'],price_source_sha256=intent['price_source_sha256'],
            quote_cts_ms=intent['quote_cts_ms'],prepared_ms=intent['prepared_ms'])
        _require(rebuilt==intent,'FIRST_INTENT_STATIC_BINDING_CONFLICT')
        out=dict(schema='ALPACA_DYNAMIC_FIRST_INTENT_DOSSIER_V1',status='READY_FOR_LIVE_GO',
            ready_for_live_go=True,orders_allowed=False,live_orders_allowed=False,
            ticker=intent['symbol'],session=intent['session'],account_id=intent['account_id'],
            max_qty=intent['max_qty'],max_notional_usd=intent['max_notional_usd'],max_stop_risk_usd=intent['max_risk_usd'],
            max_limit_price=intent['max_limit_price'],reference_risk_distance=intent['reference_risk_distance'],
            exact_future_qty='not yet reserved; unchanged opening planner must fit every bound or reject',
            attempts_allowed=1,carry_to_other_session=False,liability_reserve_usd=str(reserve),commission_rate='0',
            stop_logic='unchanged actual-fill distance/native monotonic floor/DAY re-arm',
            loss_assumption='stop-distance cap excludes gaps; total loss is not guaranteed by a stop',
            intent_sha256=intent['intent_sha256'],static_binding_sha256=intent['static_binding_sha256'],
            native_manager_source_sha256=intent['native_manager_source_sha256'],
            source_book=binding['source_book'],lock_path=binding['lock_path'],ledger_path=binding['ledger_path'],
            package_sha256=deployment['package_sha256'],paper_receipt_sha256=paper['receipt_sha256'],
            entry='fresh existing opening checks; one exact quantity limit; no reprice/resend',
            kill='existing exact owned --maintenance --kill; never account flatten',
            rollback='HALT new entries and retain management until owned exit/finality; retain all sources/journals',
            required_owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
        out['dossier_sha256']=digest(out)
        return out
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError,StopIteration) as exc:
        return blocked(str(exc))
