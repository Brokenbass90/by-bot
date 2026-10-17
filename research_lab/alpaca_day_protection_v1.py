"""Point-in-time DAY-stop readback; no transport, credential or trading interface.

The existing manager alone owns re-arm/unwind. This observer consumes a bounded
authenticated GET capture and produces reporting issues. It does not infer
continuous protection, a completed exit or fee finality from point samples.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from zoneinfo import ZoneInfo


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _number(value):
    if isinstance(value,bool):raise ValueError('INVALID_QUANTITY_OR_PRICE')
    v=Decimal(str(value))
    if not v.is_finite() or v<=0:raise ValueError('INVALID_QUANTITY_OR_PRICE')
    return v


def _stamp(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:raise ValueError('CLOCK_TIMEZONE_REQUIRED')
    return d


def evaluate(source,*,now_ms):
    """Require both the open-order list and actual owned GET-order readback.

    Callers retain raw captures privately and pin their collector. Source flags
    describe the GET collector's checks; they do not grant money authority.
    Unknown/conflicting source evidence never becomes protection confirmation.
    """
    out=dict(schema='ALPACA_DAY_PROTECTION_OBSERVATION_V1',status='DAY_PROTECTION_UNKNOWN',
        observed_ms=now_ms,orders_allowed=False,money_authority=False,broker_writes=0,
        coverage=[],issues=[],session=None,session_open_ms=None,regular_session=False,
        regular_session_elapsed_minutes=None,actual_unprotected_minutes=None)
    try:
        if (source['schema']!='ALPACA_DAY_PROTECTION_SOURCE_V1'
            or any(source[k] is not True for k in ('orders_complete','account_identity_verified','ledger_unchanged'))
            or type(source['source_pins_verified']) is not int or source['source_pins_verified']<=0):
            raise ValueError('INCOMPLETE_OR_UNVERIFIED_READBACK')
        start,end=source['started_ms'],source['completed_ms']
        if (any(type(v) is not int for v in (start,end,now_ms))
            or not 0<start<=end<=now_ms or now_ms-end>5000):
            raise ValueError('STALE_OR_INVALID_CAPTURE_TIME')
        clock=source['clock'];stamp=_stamp(clock['timestamp'])
        if type(clock['is_open']) is not bool or abs(int(stamp.timestamp()*1000)-end)>5000:
            raise ValueError('BROKER_CLOCK_CONFLICT')
        day=stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        out['session']=day
        calendar=source['calendar']
        if not isinstance(calendar,list) or len(calendar)>1:raise ValueError('CALENDAR_CONFLICT')
        regular=False;elapsed=0
        if calendar:
            row=calendar[0]
            if row['date']!=day:raise ValueError('CALENDAR_DATE_CONFLICT')
            def boundary(key):
                d=datetime.fromisoformat(day+'T'+row[key])
                if d.tzinfo is not None:raise ValueError('CALENDAR_LOCAL_TIME_REQUIRED')
                return int(d.replace(tzinfo=ZoneInfo('America/New_York')).timestamp()*1000)
            opened,closed=boundary('open'),boundary('close')
            if opened>=closed:raise ValueError('CALENDAR_BOUNDARIES_CONFLICT')
            regular=opened<=end<closed
            elapsed=max(0,min(end,closed)-opened)/60000
            out.update(session_open_ms=opened,session_close_ms=closed)
        if clock['is_open']!=regular:raise ValueError('CALENDAR_CLOCK_CONFLICT')
        out.update(regular_session=regular,regular_session_elapsed_minutes=elapsed)
        expected=source['expected'];positions=source['positions'];orders=source['open_orders']
        reads=source['stop_readbacks']
        if (not isinstance(expected,dict) or not expected or len(expected)>4
            or any(not isinstance(v,list) for v in (positions,orders,reads))):
            raise ValueError('SOURCE_SCOPE_CONFLICT')
        out['source_sha256']=_digest(source)
        for symbol,record in sorted(expected.items()):
            matching=[p for p in positions if p['symbol']==symbol]
            active=[o for o in orders if o['symbol']==symbol]
            status='UNKNOWN'
            if len(matching)>1:raise ValueError('AMBIGUOUS_POSITION')
            if not matching:
                status='NO_POSITION_OBSERVED' if not active else 'UNKNOWN'
            else:
                position=matching[0];qty=_number(position['qty'])
                if (position['side']!='long' or qty!=_number(record['qty'])
                    or _number(position['avg_entry_price'])!=_number(record['entry_price'])):
                    raise ValueError('OWNED_POSITION_CONFLICT')
                if not regular:status='OUTSIDE_RTH'
                elif not active:
                    prior=[r for r in reads if r['id']==record['accepted_order_id']]
                    if (len(prior)==1 and prior[0]['status'] in {'expired','canceled','rejected'}
                        and Decimal(str(prior[0]['filled_qty']))==0):status='MISSING'
                elif len(active)==1:
                    stop=active[0]
                    expected_tif='gtc' if qty==qty.to_integral_value() else 'day'
                    readback=[r for r in reads if r['id']==stop['id']]
                    fields=('id','symbol','side','type','status','time_in_force','qty','filled_qty','stop_price')
                    if (len(readback)==1 and all(readback[0].get(k)==stop.get(k) for k in fields)
                        and stop['id']==record['accepted_order_id'] and stop['side']=='sell'
                        and stop['type']=='stop' and stop['time_in_force']==expected_tif
                        and stop['status'] in {'new','accepted','partially_filled'}):
                        filled=Decimal(str(stop['filled_qty']))
                        if (filled.is_finite() and filled>=0 and _number(stop['qty'])-filled==qty
                            and _number(stop['stop_price'])>=_number(record['accepted_stop_floor'])):
                            status='PROTECTED'
            out['coverage'].append(dict(symbol=symbol,status=status))
            if regular and status in {'MISSING','UNKNOWN'}:
                out['issues'].append(dict(code='DAY_STOP_MISSING' if status=='MISSING' else 'DAY_STOP_READBACK_UNKNOWN',
                    severity='CRITICAL',symbol=symbol))
        states={r['status'] for r in out['coverage']}
        out['status']=('DAY_CLOSED_SESSION' if not regular else
            'DAY_PROTECTION_UNKNOWN' if 'UNKNOWN' in states else
            'DAY_PROTECTION_MISSING' if 'MISSING' in states else
            'DAY_PROTECTION_CONFIRMED' if 'PROTECTED' in states else 'DAY_NO_OWNED_EXPOSURE_OBSERVED')
    except (ValueError,KeyError,TypeError,AttributeError,InvalidOperation,OverflowError):
        out['status']='DAY_PROTECTION_UNKNOWN'
        out['issues']=[dict(code='DAY_READBACK_SOURCE_UNKNOWN',severity='CRITICAL')]
    out['evidence_id']=_digest(out)
    return out


def summarize(receipts,*,session):
    """Report observed delays/gaps, preserving unknowable continuous durations."""
    unique={}
    for r in receipts:
        unsigned={k:v for k,v in r.items() if k!='evidence_id'}
        if r.get('evidence_id')!=_digest(unsigned):raise ValueError('OBSERVATION_HASH_CONFLICT')
        if r['session']==session and r['regular_session']:unique[r['evidence_id']]=r
    rows=sorted(unique.values(),key=lambda r:r['observed_ms'])
    protected=[r for r in rows if r['status']=='DAY_PROTECTION_CONFIRMED']
    return dict(schema='ALPACA_DAY_PROTECTION_SESSION_REPORT_V1',session=session,observations=len(rows),
        protected_observations=len(protected),
        unprotected_observations=sum(r['status']=='DAY_PROTECTION_MISSING' for r in rows),
        unknown_observations=sum(r['status']=='DAY_PROTECTION_UNKNOWN' for r in rows),
        first_confirmed_protection_delay_minutes=(protected[0]['observed_ms']-protected[0]['session_open_ms'])/60000 if protected else None,
        maximum_observation_gap_minutes=max(((b['observed_ms']-a['observed_ms'])/60000 for a,b in zip(rows,rows[1:])),default=None),
        actual_unprotected_minutes=None,duration_status='UNKNOWN_BETWEEN_POINT_OBSERVATIONS')
