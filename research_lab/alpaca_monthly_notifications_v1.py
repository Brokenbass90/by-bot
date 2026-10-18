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
