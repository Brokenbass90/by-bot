#!/usr/bin/env python3
"""Preloaded one-shot PAPER opening. Default prepares/reads; no LIVE sender.

The actual source packet/handoff and target PAPER attempt must be independently
reviewed before installation. This command is not an approval or a scheduler.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib import request
from urllib.parse import quote,urlencode
import fcntl

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_open_dispatch_v2 import OpeningDispatcher,PreloadedSourcePublisher,WallClock,existing_paper_path,receipt
from research_lab.alpaca_dynamic_v1 import DynamicBook,canonical,digest,source_check
from scripts.run_alpaca_dynamic_paper import PaperClient,shared_lock_path,NoRedirect

SOURCE_BOOK=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/rehearsal/replacement.sqlite')
PAPER_RUNTIME=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/broker_paper')
POLICY_PIN='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'

class LiveGetSource:
    """Only opening GETs. A LIVE POST/DELETE cannot pass through this client."""
    base_url='https://api.alpaca.markets'
    def __init__(self,key,secret):
        self.headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
        self.opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
    def _get(self,host,path):
        req=request.Request(host+path,method='GET',headers=self.headers)
        with self.opener.open(req,timeout=3) as response:raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('OPENING_RESPONSE_TOO_LARGE')
        return json.loads(raw)
    def _request(self,method,path):
        if method!='GET' or not path.startswith('/v2/assets/') or '?' in path or '..' in path:
            raise ValueError('LIVE_READ_ONLY_SOURCE_ROUTE')
        return self._get(self.base_url,path)
    def get_account(self):return self._get(self.base_url,'/v2/account')
    def list_positions(self):return self._get(self.base_url,'/v2/positions')
    def list_orders(self,**kwargs):
        if kwargs!={'status':'open','limit':100}:raise ValueError('OPEN_ORDER_SOURCE_ROUTE')
        return self._get(self.base_url,'/v2/orders?status=open&limit=100&nested=true')
    def latest_quote(self,symbol):
        value=self._get('https://data.alpaca.markets','/v2/stocks/'+quote(symbol,safe='')+'/quotes/latest?feed=iex')
        return {'quote':value['quote'],'received_ms':time.time_ns()//1_000_000,'feed':'iex','not_nbbo':True}


def preload(packet):
    """All imports/profile/source mapping work happens before T−15m."""
    from dotenv import dotenv_values
    policy=json.loads(Path(packet['policy']).read_text())
    if digest(policy)!=POLICY_PIN:raise ValueError('SEALED_POLICY_CONFLICT')
    source_check(policy,policy['calendar_sessions'])
    if (Path(packet['source_book'])!=SOURCE_BOOK or Path(packet['paper_runtime'])!=PAPER_RUNTIME
        or packet['paper_account']!='4cdbfb77-d1e0-4789-86b2-341bc886efaf'):
        raise ValueError('EXISTING_BOOK_PAPER_SCOPE_REQUIRED')
    template=json.loads(Path(packet['source_template']).read_text())
    protocol=json.loads(Path(packet['protocol']).read_text())
    for field in ['single_owner_verified','cash_finality_verified']:
        if template.get(field) is not True:raise ValueError('SOURCE_TEMPLATE_UNCONFIRMED:'+field)
    e=dotenv_values(packet['live_env']);p=dotenv_values(packet['paper_env'])
    if e.get('ALPACA_BASE_URL')!='https://api.alpaca.markets' or p.get('ALPACA_BASE_URL')!='https://paper-api.alpaca.markets':
        raise ValueError('EXACT_SOURCE_PROFILE_REQUIRED')
    live=LiveGetSource(e['ALPACA_API_KEY_ID'],e['ALPACA_API_SECRET_KEY'])
    paper=PaperClient(p['ALPACA_API_KEY_ID'],p['ALPACA_API_SECRET_KEY'])
    lock=shared_lock_path(Path(packet['paper_env']),p,paper.key_id)
    static=dict(packet['static_paths'])
    required={name:str(Path(packet[key]).absolute()) for name,key in
              [('policy','policy'),('template','source_template'),('protocol','protocol'),('paper_env','paper_env'),('live_env','live_env')]}
    if any(static.get(name)!=path for name,path in required.items()):raise ValueError('STATIC_PROFILE_PIN_PATHS_MISSING')
    # Freeze the already computed selector result. No selector/research/data
    # reconstruction is performed in the opening callback.
    proposal=None
    if packet.get('ranking_proposal'):
        if static.get('ranking_proposal')!=str(Path(packet['ranking_proposal']).absolute()):
            raise ValueError('RANKING_PROPOSAL_PIN_PATH_MISSING')
        draft=json.loads(Path(packet['ranking_proposal']).read_text())
        if (draft['status']!='PRECOMPUTED_NOT_SEALED' or draft['money_authority'] is not False
            or draft['prepared_ms']>packet['open_ms']-900000
            or draft['ranking']['window_ms']!=packet['open_ms']
            or draft['ranking']['policy_sha256']!=digest(policy)):
            raise ValueError('PRECOMPUTED_RANKING_CONFLICT')
        proposal=draft['ranking']
        if not proposal['gate_ok'] or not proposal['picks'] or proposal['picks'][0]['symbol']!=packet['symbol']:
            raise ValueError('PRECOMPUTED_SYMBOL_OR_CASH_GATE')
        pick=proposal['picks'][0]
        template['quotes'][packet['symbol']]['risk_distance']=str(pick['signal_close']-pick['stop_price'])
    for name,path in static.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=packet['expected_sha256'][name]:
            raise ValueError('STATIC_SOURCE_PIN_CONFLICT:'+name)
    return policy,template,protocol,live,paper,lock,static,proposal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--run-opening',action='store_true',help='otherwise static preparation only')
    parser.add_argument('--paper-submit',action='store_true',help='requires exact independently reviewed PAPER authorization in packet')
    args=parser.parse_args();out=None
    try:
        packet=json.loads(args.packet.read_text());policy,template,protocol,live,paper,lock,paths,proposal=preload(packet)
        clock=WallClock();controller=OpeningDispatcher(args.runtime,policy,packet['open_ms'],paths,packet['checks'],clock,plan_store=SOURCE_BOOK)
        out=controller.prepare()
        if out['status']!='STATIC_PREPARED':raise ValueError(out['reason'])
        if args.run_opening:
            if args.paper_submit:
                authority=packet['attempt_authorization']
                expected_session=next(s['session'] for s in policy['calendar_sessions'] if s['open_ms']==packet['open_ms'])
                if authority!={'scope':'PAPER_ONLY','session':expected_session,'owner_approved':True}:
                    raise ValueError('EXACT_PAPER_ATTEMPT_APPROVAL_REQUIRED')
            ready=controller.ready()
            if ready['status']!='READY_TO_DISPATCH':raise ValueError(ready.get('reason','NOT_READY'))
            # Everything is preloaded before waiting. No repository discovery or
            # source reconstruction is allowed in the opening callback.
            while clock.wall_ms()<packet['open_ms']:
                time.sleep(min(1,(packet['open_ms']-clock.wall_ms())/1000))
            source=PreloadedSourcePublisher(policy,template,protocol,packet['symbol'],live,live.latest_quote,clock)
            with lock.open('a') as shared:
                fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
                book=DynamicBook(SOURCE_BOOK,policy)
                if proposal is not None:
                    book.seal_ranking(proposal,policy['calendar_sessions'],clock.wall_ms())
                def existing(plan):
                    identity=digest({'parent':plan['receipt_id'],'paper_account':packet['paper_account']})
                    paper.owned_client_ids=frozenset(['dyp-'+identity[:32],'dys-'+identity[:32]])
                    return existing_paper_path(plan,policy,paper,packet['paper_account'],PAPER_RUNTIME,clock.wall_ms(),send=args.paper_submit)
                out=controller.run(fresh=source.capture,
                    reserve=lambda snapshot:book.propose(snapshot,policy['calendar_sessions'],clock.wall_ms()),execute=existing)
    except Exception as exc:
        out=receipt('BLOCKED_DATA',reason=str(exc) or type(exc).__name__)
    print(json.dumps(out,indent=2))
    return 2 if out['status'].startswith('BLOCKED') else 0

if __name__=='__main__':raise SystemExit(main())
