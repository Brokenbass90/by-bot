#!/usr/bin/env python3
"""Offline exact planner/adapter rehearsal. No credentials, network or broker.

Imports existing synthetic test fixtures explicitly. Simulated network elapsed
time and measured local wall time are separate; neither is production latency.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_alpaca_dynamic_v1 import policy as policy_fixture, snapshot as snapshot_fixture, ranking as ranking_fixture
from test_alpaca_dynamic_paper import Broker
from test_alpaca_open_dispatch_v2 import Clock, OPEN, ReadOnlyLive
from research_lab.alpaca_dynamic_v1 import DynamicBook, digest
from research_lab.alpaca_open_dispatch_v2 import OpeningDispatcher, PreloadedSourcePublisher, STATIC_CHECKS, existing_paper_path


def rehearse(iterations=10):
    results=[]
    with tempfile.TemporaryDirectory(prefix='alpaca-v2-offline-',dir=Path(tempfile.gettempdir()).resolve()) as temp:
        for delay_ms in (0,500,2500):
            for index in range(iterations):
                begin=time.monotonic_ns();root=Path(temp)/f'{delay_ms}-{index}';root.mkdir()
                policy=policy_fixture.__wrapped__();template=snapshot_fixture.__wrapped__(policy)
                template.update(positions=[],open_orders=[])
                template['quotes']['NET']['risk_distance']='4'
                clock=Clock(OPEN-900001)
                protocol=json.loads((ROOT/'reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json').read_text())
                protocol['fractional_protocol']['requires_fresh_asset']['symbol']='NET'
                static=root/'static.json';static.write_text(json.dumps({'fixture':True}))
                book=DynamicBook(root/'book.sqlite',policy)
                checks={k:{'status':'VERIFIED','source_sha256':'a'*64} for k in STATIC_CHECKS}
                checks['reservation_handoff']['status']='CLEAR_OR_REVIEWED'
                controller=OpeningDispatcher(root/'dispatch',policy,OPEN,{'static':static},checks,clock,plan_store=book.path)
                assert controller.prepare()['status']=='STATIC_PREPARED'
                clock.advance(840001);assert controller.ready()['status']=='READY_TO_DISPATCH'
                clock.advance(61000)
                rank=ranking_fixture.__wrapped__(policy);rank['policy_sha256']=digest(policy)
                book.seal_ranking(rank,policy['calendar_sessions'],clock.wall_ms())
                class DelayedSource(ReadOnlyLive):
                    def get_account(self):clock.advance(delay_ms);return super().get_account()
                    def list_positions(self):clock.advance(delay_ms);return super().list_positions()
                    def list_orders(self,**kw):clock.advance(delay_ms);return super().list_orders(**kw)
                    def _request(self,*args):clock.advance(delay_ms);return super()._request(*args)
                def quote(symbol):
                    clock.advance(delay_ms)
                    return {'quote':{'t':datetime.fromtimestamp(clock.wall_ms()/1000,timezone.utc).isoformat(),'ap':100},
                            'received_ms':clock.wall_ms()}
                source=PreloadedSourcePublisher(policy,template,protocol,'NET',DelayedSource(policy['account_id']),quote,clock)
                class CurrentClockBroker(Broker):
                    def get_clock(self):
                        return {'is_open':True,'timestamp':datetime.fromtimestamp(clock.wall_ms()/1000,timezone.utc).isoformat()}
                broker=CurrentClockBroker()
                def execute(plan):
                    broker.fill_qty=plan['qty']
                    return existing_paper_path(plan,policy,broker,broker.account_id,root/'paper',clock.wall_ms(),send=True)
                result=controller.run(fresh=source.capture,
                    reserve=lambda s:book.propose(s,policy['calendar_sessions'],clock.wall_ms()),
                    execute=execute)
                assert result['status']=='OPENING_PATH_COMPLETED',result
                assert result['execution']['status']=='PAPER_PROTECTED',result
                assert len(broker.writes)==2 and broker.writes[1]['side']=='sell'
                assert controller.run(fresh=lambda:None,reserve=lambda _:None,execute=lambda _:None)==result
                results.append({'synthetic_get_delay_ms':delay_ms,'iteration':index,
                    'simulated_completion_after_open_ms':clock.wall_ms()-OPEN,
                    'measured_local_wall_ms':(time.monotonic_ns()-begin)/1_000_000,
                    'phase_timings':result['timings'],'receipt_sha256':digest(result),
                    'adapter_status':result['execution']['status'],'synthetic_write_count':len(broker.writes)})
    wall=[r['measured_local_wall_ms'] for r in results]
    return {'status':'LOCAL_REHEARSAL_PASS','evidence_kind':'SYNTHETIC_BROKER_ONLY',
        'actual_broker_lifecycle_pass':False,'money_authority':False,'network_requests':0,
        'iterations':len(results),'synthetic_get_delay_profiles_ms':[0,500,2500],
        'measured_local_wall_ms':{'median':statistics.median(wall),'max':max(wall)},
        'maximum_simulated_completion_after_open_ms':max(r['simulated_completion_after_open_ms'] for r in results),
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (Path(__file__).resolve(),ROOT/'research_lab/alpaca_open_dispatch_v2.py',
                                   ROOT/'scripts/run_alpaca_open_dispatch_v2.py')},'runs':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=rehearse();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'}))
