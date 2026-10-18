"""Monthly events through the existing durable Monitor + Telegram transport."""
from datetime import datetime
from pathlib import Path
import json
from zoneinfo import ZoneInfo

from research_lab.alpaca_day_monitor_v1 import Monitor,telegram,atomic,publish
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_monthly_source_ops_v1 import safe_path


def event_delivery(config,*,now_ms,failure_code=None,test=False,sender=None,component='manager'):
    if component not in {'source','manager'}:raise ValueError('MONTHLY_ALERT_COMPONENT')
    root=safe_path(config['output_root']);active=root/('monthly-'+component+'-incident.json')
    day=datetime.fromtimestamp(now_ms/1000,ZoneInfo('America/New_York')).date().isoformat()
    with Monitor(root,clock=lambda:now_ms) as monitor:
        send=sender or (lambda event:telegram(config,event))
        if test:return monitor.notify(dict(kind='DELIVERY_TEST',incident_id='MONTHLY_E2E_20261018',meaning='NO_ORDERS_NO_PROTECTION_OR_PROFIT_CLAIM'),send)
        if failure_code:
            old=json.loads(active.read_bytes()) if active.exists() else {}
            same=(old.get('code')==failure_code and old.get('session')==day and old.get('resolved') is not True)
            generation=old.get('generation',0)+(0 if same else 1)
            identity=digest(dict(component=component,session=day,code=failure_code,generation=generation))
            event=dict(kind='CRITICAL',incident_id=identity,session=day,first_evidence_id=identity,
                component=component,code=failure_code,generation=generation,
                issues=[dict(code=failure_code,severity='CRITICAL')])
            atomic(active,event);return monitor.notify(event,send)
        if not active.exists():return dict(status='QUIET')
        old=json.loads(active.read_bytes())
        if old.get('resolved') is True:return dict(status='QUIET')
        event=dict(kind='RECOVERED',incident_id=old['incident_id'],evidence_id=old['first_evidence_id'],
            status='MONTHLY_SOURCE_MANAGER_RECOVERED',session=day)
        out=monitor.notify(event,send);atomic(active,dict(old,resolved=True));return out


def cycle_delivery(config,native,*,now_ms,failure=False,sender=None):
    """Read the one owned book/cost journal; reuse durable Monitor claims."""
    import sqlite3
    from research_lab.alpaca_monthly_binding_v1 import CONTRACT
    entries={p['entry_id']:p for p in native.book.rows('positions')}
    exits=native.book.rows('exits')
    entries.update({x['entry_id']:x['retired_position'] for x in exits})
    events=[];deliveries=[]
    for eid,p in sorted(entries.items()):
        e=p['raw_entry'];events.append(dict(kind='MONTHLY_ENTRY',entry_order_id=eid,
            symbol=p['symbol'],quantity=e['filled_qty'],price=e['filled_avg_price'],
            evidence_id=digest(e),financial_source='EXISTING_OWNED_MONTHLY_BOOK'))
    for x in exits:
        events.append(dict(kind='MONTHLY_EXIT',entry_order_id=x['entry_id'],symbol=x['symbol'],
            reason=x['reason'],net_status='COST_FINALITY_REPORTED_SEPARATELY',
            evidence_id=digest(x),financial_source='EXISTING_OWNED_MONTHLY_BOOK'))
        identity=digest(dict(schema=CONTRACT['schema'],entry_id=x['entry_id']))
        path=native.runtime/'safety'/identity/'live.sqlite'
        if path.is_file():
            with sqlite3.connect(safe_path(path).as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
            item=json.loads(row[0]) if row else {};final=item.get('cost_finality')
            if final and final.get('status')=='LIVE_TERMINAL_COST_FINALITY':
                events.append(dict(kind='MONTHLY_COST_FINAL',entry_order_id=x['entry_id'],
                    symbol=x['symbol'],net_usd_exact=final['net_usd_exact'],
                    evidence_id=item['cost_finality_sha256'],financial_source='EXISTING_ACCOUNTING_FINALIZER'))
    with Monitor(safe_path(config['output_root']),clock=lambda:now_ms) as monitor:
        for event in events:
            event.update(incident_id=digest(dict(account=native.account,kind=event['kind'],
                entry_order_id=event['entry_order_id'])))
            deliveries.append(monitor.notify(event,sender or (lambda e:telegram(config,e))))
    health=event_delivery(config,now_ms=now_ms,failure_code='MONTHLY_DISPATCH_BLOCKED' if failure else None,sender=sender)
    return dict(trades=deliveries,health=health)
