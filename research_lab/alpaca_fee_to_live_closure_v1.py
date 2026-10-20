"""One offline actual-fee-to-first-dossier transaction; always orders-OFF.

Reuse the existing posted-cost/lifecycle/physical-binding/intent/dossier rules.
No broker client, polling, installer, reservation, permit or activation path.
The account-cost source collector accepts an injected GET-only reader; it never
derives fee finality or changes the existing single-round-trip closure contract.
The caller supplies one actual terminal capture and a fresh LIVE preparation.
"""
import hashlib
from pathlib import Path
from decimal import Decimal, ROUND_DOWN

from research_lab.alpaca_dynamic_v1 import canonical, digest
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json, safe_path
from research_lab.alpaca_dynamic_first_intent_v1 import prepare_first_intent
from research_lab import alpaca_live_readiness_v1 as readiness
from research_lab.alpaca_orders_off_handoff_v2 import bind_final_paper

ROLES={'cash_before','initial','rearm','protocol','arm','initial_evidence',
       'deployment','binding_template','policy','fixed_intent'}


def pin(path):
    p=safe_path(str(Path(path).absolute()),exists=True)
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def check_rows(rows):
    for row in rows:
        if pin(row['path'])!=row:raise ValueError('CLOSURE_STATIC_SOURCE_DRIFT')


def unused_output(value):
    p=Path(value)
    if p.exists() and not p.is_symlink():raise ValueError('CLOSURE_ATTEMPT_ALREADY_EXISTS')
    return safe_path(value)


def code_pins():
    from research_lab import alpaca_dynamic_first_intent_v1,alpaca_orders_off_handoff_v2
    return [pin(p) for p in (Path(__file__),Path(readiness.__file__),
        Path(alpaca_dynamic_first_intent_v1.__file__),Path(alpaca_orders_off_handoff_v2.__file__))]


def freeze_manifest(inputs,*,output_dir):
    if set(inputs)!=ROLES:raise ValueError('CLOSURE_EXACT_STATIC_ROLES_REQUIRED')
    out=unused_output(str(Path(output_dir).absolute()))
    row=dict(schema='ALPACA_FEE_TO_LIVE_CLOSURE_MANIFEST_V1',
        inputs={n:pin(p) for n,p in sorted(inputs.items())},code_files=code_pins(),
        output_dir=str(out),orders_allowed=False,live_orders_allowed=False,
        automatic_retry=False,polling=False)
    return {**row,'manifest_sha256':digest(row)}


def close_once(manifest,*,terminal_capture,live_preparation,now_ms):
    if manifest.get('manifest_sha256')!=digest({k:v for k,v in manifest.items() if k!='manifest_sha256'}):
        raise ValueError('CLOSURE_MANIFEST_PIN_CONFLICT')
    if (manifest.get('schema')!='ALPACA_FEE_TO_LIVE_CLOSURE_MANIFEST_V1'
        or set(manifest['inputs'])!=ROLES or manifest['orders_allowed'] is not False
        or manifest['live_orders_allowed'] is not False or manifest['polling'] is not False
        or manifest['automatic_retry'] is not False):raise ValueError('CLOSURE_SCOPE_CONFLICT')
    out=unused_output(manifest['output_dir'])
    out.mkdir(mode=0o700)
    try:
        check_rows(manifest['code_files']);check_rows(manifest['inputs'].values())
        paths={n:row['path'] for n,row in manifest['inputs'].items()}
        terminal=read_json(str(terminal_capture))
        fee=readiness.derive_paper_posted_cost_closure_v2(
            cash_before_path=paths['cash_before'],initial_path=paths['initial'],
            rearm_path=paths['rearm'],terminal_path=str(terminal_capture),
            protocol_path=paths['protocol'],now_ms=now_ms)
        paper=readiness.verify_paper_lifecycle(read_json(paths['arm']),read_json(paths['initial_evidence']),
            read_json(paths['rearm'])['response'],terminal['response'],fee,now_ms=now_ms)
        if paper['status']!='PAPER_EXECUTION_PASS':result=paper
        else:
            deployment=bind_final_paper(read_json(paths['deployment']),paper,now_ms=now_ms)
            readiness.write_new(out/'cost-closure.json',canonical(fee))
            readiness.write_new(out/'paper.json',canonical(paper))
            readiness.write_new(out/'deployment-bound.json',canonical(deployment))
            binding=read_json(paths['binding_template'])
            # A new separate attestation; never edit the original install receipt.
            binding['sources']['paper']=pin(out/'paper.json')
            readiness.write_new(out/'binding.json',canonical(binding))
            preparation=read_json(str(live_preparation));snapshot=preparation['snapshot']
            fixed=read_json(paths['fixed_intent']);policy=read_json(paths['policy'])
            price_pin=next(row['sha256'] for row in preparation['source_files']
                if read_json(row['path'])==snapshot or read_json(row['path']).get('snapshot')==snapshot)
            # Price and time are the fresh original-source fields, not an old preview.
            intent=prepare_first_intent(policy=policy,binding=binding,**fixed,
                max_limit_price=str(Decimal(str(snapshot['quote']['ap'])).quantize(Decimal('.01'),rounding=ROUND_DOWN)),
                price_source_sha256=price_pin,
                quote_cts_ms=readiness._ms(snapshot['quote']['t']),prepared_ms=snapshot['observed_ms'])
            result=readiness.pre_entry_dossier(paper=paper,deployment=deployment,binding=binding,
                intent=intent,policy=policy,preparation=preparation,now_ms=now_ms)
            if result['status']=='READY_FOR_LIVE_GO':readiness.write_new(out/'first-intent.json',canonical(intent))
    except (ValueError,KeyError,TypeError,OSError,StopIteration,ArithmeticError) as exc:
        result=readiness.blocked(str(exc) or type(exc).__name__)
    readiness.write_new(out/'terminal.json',canonical(result))
    return result


class CostSourceCaptureError(ValueError):
    """Fail closed while retaining bounded received HTTP evidence for the caller."""
    def __init__(self, reason, captures, request=None):
        from copy import deepcopy
        super().__init__(reason)
        self.captures = tuple(deepcopy(captures))
        self.request = deepcopy(request)


def collect_account_cost_source(get, *, account_id, after, until, now_ms=None,
                                page_size=100, max_pages=20):
    """One bounded account/activities/account capture, with no order routes.

    Alpaca filters `after`/`until` on creation time. A fee's `date` may refer to
    the preceding trading day, so preserve every returned row without applying
    a second trade-date filter. Exhaustion is a short page, including an empty
    page after an exactly full last page. The injected reader returns raw HTTP
    evidence; retry/persistence belong to the caller, never to a financial owner.

    This produces source evidence only. Missing fees, zero pending balances and
    a complete activity page do not attest fees or per-position allocation final.
    """
    import json
    import time
    from datetime import datetime

    if (not isinstance(account_id, str) or not account_id
        or (now_ms is not None and (type(now_ms) is not int or now_ms < 0))
        or type(page_size) is not int or not 1 <= page_size <= 100
        or type(max_pages) is not int or not 1 <= max_pages <= 100):
        raise ValueError('COST_SOURCE_ARGUMENTS')
    clock = (lambda: now_ms) if now_ms is not None else (lambda: time.time_ns() // 1_000_000)
    try:
        bounds = [datetime.fromisoformat(v.replace('Z', '+00:00')) for v in (after, until)]
        if (any(t.tzinfo is None for t in bounds)
            or not 0 <= bounds[0].timestamp() < bounds[1].timestamp() <= clock() / 1000):
            raise ValueError('invalid bounds')
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError('COST_SOURCE_COVERAGE_TIME') from None

    cutoff_ms = int(bounds[1].timestamp() * 1000)
    captures = []
    def fail(reason, query=None):
        raise CostSourceCaptureError(reason, captures, query)

    def request(route, query):
        attempt = dict(route=route, query=dict(query))
        try:
            response = get(route, dict(query))
        except Exception:
            fail('COST_SOURCE_GET_EXCEPTION', attempt)
        if not isinstance(response, dict):
            fail('COST_SOURCE_GET_FAILED', attempt)
        raw = response.get('raw')
        encoded = raw.encode() if isinstance(raw, str) else None
        pin = hashlib.sha256(encoded).hexdigest() if encoded is not None else None
        started, received = response.get('started_ms'), response.get('received_ms')
        previous_received = captures[-1]['received_ms'] if captures else None
        evidence = dict(route=route, query=dict(query), started_ms=started,
            received_ms=received, http_status=response.get('http_status'),
            raw=raw if encoded is not None and len(encoded) <= 5_000_000 else None,
            sha256=pin)
        binary=response.get('raw_base64')
        if isinstance(binary,str) and len(binary)<=6_666_668:
            import base64
            try:
                payload_bytes=base64.b64decode(binary,validate=True)
                if len(payload_bytes)<=5_000_000:
                    evidence.update(raw_base64=binary,raw_decode_status=response.get('raw_decode_status'),
                        sha256=hashlib.sha256(payload_bytes).hexdigest())
            except ValueError:pass
        if response.get('raw_truncated') is True:
            evidence.update(raw_truncated=True,received_bytes_at_least=response.get('received_bytes_at_least'))
        if encoded is not None and len(encoded) > 5_000_000:
            evidence.update(raw=encoded[:5_000_000].decode(errors='replace'), raw_truncated=True)
        captures.append(evidence)
        if response.get('http_status') != 200:
            fail('COST_SOURCE_GET_FAILED', attempt)
        if (type(started) is not int or type(received) is not int
            or not cutoff_ms <= started <= received <= clock()):
            fail('COST_SOURCE_CAPTURE_TIME', attempt)
        if previous_received is not None and started < previous_received:
            fail('COST_SOURCE_CAPTURE_ORDER', attempt)
        if encoded is None or len(encoded) > 5_000_000 or response.get('raw_truncated') is True:
            fail('COST_SOURCE_RAW_REQUIRED', attempt)
        if response.get('sha256', pin) != pin:
            fail('COST_SOURCE_RAW_PIN', attempt)
        try:
            payload = json.loads(raw)
            canonical(payload)  # reject nonfinite JSON without changing raw evidence
        except (ValueError, TypeError):
            fail('COST_SOURCE_JSON', attempt)
        return payload

    fields = ('cash', 'accrued_fees', 'pending_reg_taf_fees')
    def account():
        row = request('/v2/account', {})
        if not isinstance(row, dict) or row.get('id') != account_id:
            fail('COST_SOURCE_ACCOUNT_CONFLICT')
        if any(k not in row for k in fields):
            fail('COST_SOURCE_ACCOUNT_FIELDS_REQUIRED')
        try:
            for name in fields:
                value = Decimal(str(row[name]))
                if not value.is_finite() or (name != 'cash' and value < 0):
                    raise ValueError('bad account number')
        except (ValueError, ArithmeticError):
            fail('COST_SOURCE_ACCOUNT_NUMBER')
        return row

    before = account()
    query = dict(after=after, until=until, direction='asc', page_size=page_size)
    activities = []; seen = set(); pages = 0
    for _ in range(max_pages):
        rows = request('/v2/account/activities', query); pages += 1
        if not isinstance(rows, list) or len(rows) > page_size:
            fail('COST_SOURCE_PAGE_SCHEMA')
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not row['id'] or not isinstance(row.get('activity_type'), str)
                or not row['activity_type']):
                fail('COST_SOURCE_ACTIVITY_IDENTITY')
            if row['id'] in seen:
                fail('COST_SOURCE_DUPLICATE_ACTIVITY')
            seen.add(row['id']); activities.append(row)
        if len(rows) < page_size:
            break
        query = {**query, 'page_token': rows[-1]['id']}
    else:
        fail('COST_SOURCE_PAGE_BOUND')
    after_account = account()
    if any(Decimal(str(before[k])) != Decimal(str(after_account[k])) for k in fields):
        fail('COST_SOURCE_ACCOUNT_MOVED')
    return dict(schema='ALPACA_ACCOUNT_COST_ACTIVITY_SOURCE_V1', account_id=account_id,
        account_before=before, account_after=after_account, activities=activities,
        captures=captures, capture_manifest_sha256=digest(captures), observed_ms=clock(),
        coverage=dict(after=after, until=until, page_size=page_size, page_count=pages,
            pagination_exhausted=True, filter_semantics='CREATION_TIME_NOT_SETTLEMENT_DATE'),
        source_get_requests=len(captures), broker_writes=0, orders_allowed=False,
        money_authority=False, terminal_cost_finality_proven=False)


def reconcile_account_day_fees(source, *, protocol, protocol_sha256,
                               calendar, calendar_sha256, assets, assets_sha256,
                               pending=False):
    """Confirm posted account-day components under an explicit pinned protocol.

    Aggregate executions, including partial fills, over the whole account day.
    Compare charged fee amounts, never fee/fill row counts. A closed calendar
    session, executed post-close assessments and the source-pinned fee model are
    all required. This is neither cash reconciliation nor per-position fee
    attribution; it cannot release capital or satisfy the terminal cost schema.
    """
    from collections import defaultdict
    from datetime import datetime, timedelta
    from decimal import ROUND_CEILING
    from zoneinfo import ZoneInfo

    def fail(reason):
        raise ValueError('COST_FEE_' + reason)
    if type(pending) is not bool:fail('EXPLICIT_ESTIMATE_MODE_REQUIRED')
    try:
        recorded = iter(source['captures'])
        def replay(route, query):
            row = next(recorded)
            if row['route'] != route or row['query'] != query:
                fail('SOURCE_DRIFT')
            return row
        rebuilt = collect_account_cost_source(replay, account_id=source['account_id'],
            after=source['coverage']['after'], until=source['coverage']['until'],
            now_ms=source['observed_ms'], page_size=source['coverage']['page_size'],
            max_pages=source['coverage']['page_count'])
        if next(recorded, None) is not None or rebuilt != source:
            fail('SOURCE_DRIFT')
    except (KeyError, TypeError, ValueError, StopIteration):
        fail('SOURCE_DRIFT')
    if (digest(protocol) != protocol_sha256
        or protocol.get('schema') != 'ALPACA_PROTOCOL_SOURCE_CONTRACT_V1'
        or protocol.get('account_id') != source['account_id']
        or protocol.get('owner_attestation', {}).get('api_commission_null_is_not_proof') is not True
        or digest(calendar) != calendar_sha256 or not isinstance(calendar, list)):
        fail('PINNED_PROTOCOL_OR_CALENDAR_REQUIRED')

    def number(value, *, positive=False):
        try:
            row = Decimal(str(value))
            if not row.is_finite() or (positive and row <= 0):
                raise ValueError('bad number')
            return row
        except (ValueError, ArithmeticError):
            fail('INVALID_NUMBER')
    try:
        model = protocol['regulatory_model']
        cat = number(model['cat_nms_executed_share_rate'], positive=True)
        sec = number(model['sec_sell_value_rate'])
        if (number(protocol['commission_rate']) != 0
            or number(model['taf_per_share_rate']) != 0 or sec < 0
            or model['rounding'] != 'each fee type aggregated daily per account then ceiling to USD0.01; exact fractional executed quantities'):
            fail('UNSUPPORTED_ACCOUNT_FEE_PROTOCOL')
    except (KeyError, TypeError):
        fail('PINNED_PROTOCOL_OR_CALENDAR_REQUIRED')

    def timestamp(value):
        try:
            row = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if row.tzinfo is None:
                raise ValueError('timezone required')
            return row
        except (ValueError, TypeError, AttributeError):
            fail('TIMESTAMP_REQUIRED')
    sessions = {}
    for row in calendar:
        if (not isinstance(row, dict) or not isinstance(row.get('session'), str)
            or row['session'] in sessions
            or type(row.get('open_ms')) is not int or type(row.get('close_ms')) is not int
            or not 0 <= row['open_ms'] < row['close_ms']):
            fail('CALENDAR_CONFLICT')
        sessions[row['session']] = row
    if (not isinstance(assets, list) or digest(assets) != assets_sha256
        or source['account_before'].get('currency') != 'USD'
        or source['account_after'].get('currency') != 'USD'):
        fail('INSTRUMENT_SCOPE')
    instruments = {}
    for row in assets:
        if (not isinstance(row, dict) or not isinstance(row.get('symbol'), str)
            or row['symbol'] in instruments or not row.get('id')
            or row.get('asset_class', row.get('class')) != 'us_equity'
            or any(row[k]!='us_equity' for k in ('class','asset_class') if k in row)
            or row.get('exchange') not in {'NYSE', 'NASDAQ', 'ARCA', 'AMEX', 'BATS', 'NYSEAMERICAN'}
            or row.get('currency', 'USD') != 'USD'):
            fail('INSTRUMENT_SCOPE')
        instruments[row['symbol']] = row
    start = timestamp(source['coverage']['after']).timestamp() * 1000
    end = timestamp(source['coverage']['until']).timestamp() * 1000
    days = defaultdict(lambda: dict(qty=Decimal(0), sells=Decimal(0), fills=[]))
    for row in source['activities']:
        if row['activity_type'] != 'FILL':
            continue
        if (row.get('symbol') not in instruments or row.get('asset_class', 'us_equity') != 'us_equity'
            or any(row[k]!='us_equity' for k in ('class','asset_class') if k in row)
            or ('asset_id' in row and row['asset_id']!=instruments[row['symbol']]['id'])
            or row.get('currency', 'USD') != 'USD'):
            fail('INSTRUMENT_SCOPE')
        at = timestamp(row.get('transaction_time'))
        day = at.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        session = sessions.get(day)
        midnight = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('America/New_York'))
        if (session is None or start > midnight.timestamp() * 1000
            or (not pending and end < (midnight + timedelta(days=1)).timestamp() * 1000)
            or at.timestamp()*1000 > end
            or not session['open_ms'] <= at.timestamp() * 1000 <= session['close_ms']):
            fail('DAY_COVERAGE_OR_SESSION_NOT_CLOSED')
        qty, price = number(row.get('qty'), positive=True), number(row.get('price'), positive=True)
        if row.get('side') not in {'buy', 'sell'}:
            fail('FILL_SIDE_UNKNOWN')
        days[day]['qty'] += qty
        if row['side'] == 'sell':
            days[day]['sells'] += qty * price
        days[day]['fills'].append(row['id'])
    if not days:
        fail('NO_COVERED_TRADES')
    posted = defaultdict(lambda: dict(CAT=Decimal(0), SEC=Decimal(0)))
    ids = defaultdict(list)
    uncovered_fees = []
    for row in source['activities']:
        if row['activity_type'] != 'FEE':
            continue
        day = row.get('date')
        if day not in days:
            uncovered_fees.append(row['id']); continue
        try:
            kind = readiness._posted_fee_kind_v3(row)
        except (ValueError, TypeError):
            fail('UNCLASSIFIED_ASSESSMENT')
        if row.get('status') != 'executed' or row.get('currency') != 'USD':
            fail('ASSESSMENT_NOT_EXECUTED_USD')
        at = timestamp(row.get('created_at')).timestamp() * 1000
        amount = number(row.get('net_amount'))
        if ((not pending and at < sessions[day]['close_ms']) or at > end or amount > 0
            or (pending and amount % Decimal('.01') != 0)):
            fail('ASSESSMENT_TIMING_OR_AMOUNT')
        posted[day][kind] -= amount
        ids[day].append(row['id'])
    ceil = lambda value: (value / Decimal('.01')).to_integral_value(rounding=ROUND_CEILING) * Decimal('.01')
    result = []; total = Decimal(0); unposted = Decimal(0)
    for day, values in sorted(days.items()):
        expected = dict(CAT=ceil(values['qty'] * cat), SEC=ceil(values['sells'] * sec))
        if (any(posted[day][k] > expected[k] for k in expected)
            or (not pending and posted[day] != expected)):
            fail('POSTING_PENDING_OR_CONFLICT')
        unposted += sum((expected[k]-posted[day][k] for k in expected),Decimal(0))
        total += sum(posted[day].values(), Decimal(0))
        result.append(dict(session=day, fill_count=len(values['fills']),
            fee_activity_count=len(ids[day]), fill_activity_ids=values['fills'],
            fee_activity_ids=ids[day], expected={k: str(v) for k, v in expected.items()},
            posted={k: str(v) for k, v in posted[day].items()}))
    out=dict(schema='ALPACA_ACCOUNT_DAY_POSTED_FEE_SOURCE_V1',
        status='ACCOUNT_DAY_FEE_SOURCE_PASS', account_id=source['account_id'],
        source_sha256=digest(source), protocol_sha256=protocol_sha256,
        calendar_sha256=calendar_sha256, assets_sha256=assets_sha256,
        observed_ms=source['observed_ms'], days=result,
        commission_usd='0', regulatory_fees_usd=str(total), uncovered_fee_activity_ids=uncovered_fees,
        creation_time_coverage_only=True, late_adjustments_possible=True,
        cash_reconciled=False, position_cost_allocation_produced=False,
        terminal_cost_finality_proven=False, capital_released=False, money_authority=False)
    if pending:
        out.update(status='ACCOUNT_DAY_FEE_ESTIMATE_ONLY',unposted_account_fees_usd=str(unposted))
    return out
