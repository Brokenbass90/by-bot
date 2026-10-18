"""Reuse the one-attempt opening controller alongside exact proven LIVE children.

The caller must first reconcile the named actual LIVE fills GET-only. Merely
having a reservation never resolves it. Default controller behavior is intact.
Fresh portfolio/stop proof and the original runtime gates still precede a buy.
"""
import json
import sqlite3
from research_lab.alpaca_dynamic_v1 import digest,pin
from research_lab.alpaca_open_dispatch_v2 import OpeningDispatcher


class OwnedOpeningDispatcher(OpeningDispatcher):
    def __init__(self,*args,resolved_source_plans,**kwargs):
        super().__init__(*args,**kwargs)
        self.resolved=json.loads(json.dumps(resolved_source_plans))
        if len(self.resolved)>self.policy['max_positions']:raise ValueError('RESOLVED_SOURCE_CARDINALITY')
        for row in self.resolved:pin(row['plan_sha256']);pin(row['live_intake_sha256'])
        if len({row['plan_sha256'] for row in self.resolved})!=len(self.resolved):
            raise ValueError('RESOLVED_SOURCE_DUPLICATE')

    def _source_intents(self):
        plans=super()._source_intents();by_hash={digest(p):p for p in plans}
        with sqlite3.connect(self.plan_store.as_uri()+'?mode=ro',uri=True) as db:
            children=[json.loads(row[0]) for row in db.execute('SELECT payload FROM slots')]
        for known in self.resolved:
            plan=by_hash.get(known['plan_sha256'])
            if plan is None:raise ValueError('RESOLVED_SOURCE_PLAN_CHANGED')
            actual=[c for c in children if c.get('parent_receipt_id')==plan['receipt_id']]
            if (len(actual)!=1 or actual[0]['entry_order_id']!=known['child_entry_order_id']
                or actual[0].get('live_intake_sha256')!=known['live_intake_sha256']
                or actual[0]['symbol']!=plan['symbol']):
                raise ValueError('RESOLVED_SOURCE_LIVE_CHILD_REQUIRED')
        return [p for p in plans if digest(p) not in {r['plan_sha256'] for r in self.resolved}]
