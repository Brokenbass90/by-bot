import tempfile,json,unittest,copy
from pathlib import Path
from scripts import run_brain_context_cycle_v1 as W
from research_lab.att1_lifecycle_journal import LifecycleJournal
from research_lab import brain_context_cycle_v1 as C
from tests.test_brain_context_cycle_v1 import events
from tests.test_pump4_brain_timely_v1 import POLICY,T,H,publication

class WorkerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').is_dir() else '/tmp');self.root=Path(self.tmp.name).resolve()
  self.source=self.root/'source';self.runtime=self.root/'runtime';self.runtime.mkdir();self.btc=self.root/'btc.jsonl'
  rows=[]
  for i in range(135):
   r=publication();r['symbol']=r['decisions'][0]['decision']['symbol']='COIN'+str(i)+'USDT';rows.append(r)
  rows.extend([dict(symbol='HFTUSDT',status='UNAVAILABLE_INSTRUMENT'),dict(symbol='VELODROMEUSDT',status='UNAVAILABLE_INSTRUMENT')])
  self.receipt=dict(schema='PUMP4_WS_FULL137_DATA_RECEIPT_V1',source_hour_open_ms=T,census=137,hour_pass=True,rows=rows,expected_trading=135)
  p=self.source/str(T)/'receipt.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(self.receipt))
  for e in events():LifecycleJournal(self.btc).append(e)
 def tearDown(self):self.tmp.cleanup()
 def test_actual_cycle_writes_before_outcome_and_replay_is_one(self):
  kw=dict(policy_path=POLICY,observed_ms=T+120000,epoch_ms=T+90000,clock=lambda:T+121000)
  result=W.cycle(self.btc,self.source,self.runtime,**kw)
  self.assertEqual(result['action'],'WAIT_NO_FROZEN_SIGNAL');self.assertEqual(result['outcome_status'],'PENDING_OUTCOME')
  kw['observed_ms']+=1000;W.cycle(self.btc,self.source,self.runtime,**kw)
  self.assertEqual(len(LifecycleJournal(self.runtime/'context.jsonl').read()),2)
 def test_census_cannot_omit_active_symbol(self):
  self.receipt['rows'].pop();(self.source/str(T)/'receipt.json').write_text(json.dumps(self.receipt))
  with self.assertRaisesRegex(ValueError,'CENSUS_ROWS'):W.census(self.source,observed_ms=T+120000)
 def test_future_publication_rejected(self):
  self.receipt['rows'][0]['publication_completed_ms']=T+130000
  (self.source/str(T)/'receipt.json').write_text(json.dumps(self.receipt))
  with self.assertRaisesRegex(ValueError,'CENSUS_TIME'):W.census(self.source,observed_ms=T+120000)
 def test_source_reader_never_competes_for_producer_flock(self):
  import fcntl
  with self.btc.open('rb') as f:
   fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   self.assertEqual(len(W.read_btc(self.btc)),1)
 def test_late_durability_is_recorded_as_noncausal(self):
  result=W.cycle(self.btc,self.source,self.runtime,policy_path=POLICY,observed_ms=T+H-1,epoch_ms=T+90000,clock=lambda:T+H+1)
  self.assertEqual(result['outcome_status'],'LATE_NOT_CAUSAL')
  rows=C.reduce_events(LifecycleJournal(self.runtime/'context.jsonl').read())
  self.assertFalse(next(x for x in rows.values() if x['kind']=='CONTEXT_DURABILITY_WITNESS')['before_outcome_open'])

if __name__=='__main__':unittest.main()
