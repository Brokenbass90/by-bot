"""One local synthetic replay, never a research judge or broker operation."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from research_lab.brain_v2_a1 import BrainJournal, COST_MODEL, HOUR, build_contexts
from research_lab.brain_v2_frozen_primitives import Opportunity, canonical


def main():
    hour=1_791_763_200_000
    pin='a'*64
    xs=[Opportunity(sleeve,symbol,side,hour-HOUR,hour,'next_open',.02,48,COST_MODEL,pin)
        for sleeve,symbol,side in [('BOUNCE1','BTCUSDT','long'),('ATT1','ETHUSDT','short')]]
    init={'request_id':'synthetic_init','kind':'INIT','initial_equity_usd':1000,
          'epoch_start_ms':hour,'source_hash':pin,'capital_known':True,
          'positions_known':True,'protection_known':True}
    opening={'request_id':'synthetic_hour1','kind':'HOUR','hour_ms':hour,
             'sealed_at_ms':hour+HOUR,'coverage_end_ms':hour+HOUR,'source_hash':pin,
             'positions_known':True,'protection_known':True,'costs_known':True,
             'opportunities':[asdict(x) for x in xs],
             'contexts':build_contexts(xs,hour_ms=hour,btc_h4=None,symbol_h1={}),
             'terminals':[]}
    close_hour=hour+HOUR
    closing={**opening,'request_id':'synthetic_hour2','hour_ms':close_hour,
             'sealed_at_ms':close_hour+HOUR,'coverage_end_ms':close_hour+HOUR,
             'opportunities':[],'contexts':{},'terminals':[
                 {'opportunity_id':x.id,'actual_exit_ms':close_hour+100,
                  'available_ms':close_hour+101,'source_hash':pin,'finality':'FINAL',
                  'cost_model_id':COST_MODEL,'gross_return_frac':.02,
                  'exit_notional_ratio':1.02,'funding_cost_frac':.001}
                 for x in xs]}
    with tempfile.TemporaryDirectory(prefix='brain-v2-a2-synthetic-') as temporary:
        runtime=Path(temporary).resolve()/'paired'
        with BrainJournal(runtime) as writer:
            receipts=[writer.process(request) for request in (init,opening,closing)]
        with BrainJournal(runtime) as writer:
            replay=writer.process(closing)
            assert replay==receipts[-1]
            assert canonical(replay)==canonical(receipts[-1])
            assert writer.state==receipts[-1]['state_after']
    output={'synthetic':True,'status':'SYNTHETIC_PAIRED_REPLAY_PASS',
            'orders_allowed':False,'money_authority':False,'raw_outcomes_read':False,
            'restart_receipt_identical':True,'receipts':receipts}
    Path(__file__).with_name('synthetic_paired_receipts.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Synthetic paired receipts3; restart byte-content exact; broker/service writes0.')


if __name__=='__main__':main()
