import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import run_pump4_brain_timely_v1 as R
from tests.test_pump4_brain_timely_v1 import publication,POLICY,T
from research_lab import pump4_brain_timely_v1 as B

class RunnerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').is_dir() else '/tmp');self.root=Path(self.tmp.name).resolve()
  self.source=self.root/'source';self.runtime=self.root/'runtime';self.runtime.mkdir()
  self.policy=B.FrozenBrain(POLICY)
  p=self.source/str(T)/'published'/'BTCUSDT.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(publication()))
 def tearDown(self):self.tmp.cleanup()
 def tick(self,**kw):return R.tick(self.source,self.runtime,self.policy,now_ms=T+2000,epoch_ms=T-1000,clock=lambda:T+2300,**kw)
 def test_new_public_data_is_recorded_and_replay_does_not_duplicate(self):
  a=self.tick();b=self.tick()
  self.assertEqual(a['new'],1);self.assertEqual(b['new'],0)
  self.assertEqual(a['no_opportunity'],1);self.assertEqual(a['timely'],1)
  self.assertEqual(a['shadow_pairs'],0)
 def test_restart_epoch_is_not_reset_and_pin_drift_rejected(self):
  a=R.epoch(self.runtime,'a'*64,now_ms=T-1000)
  self.assertEqual(a,R.epoch(self.runtime,'a'*64,now_ms=T+9000))
  with self.assertRaisesRegex(ValueError,'EPOCH_PIN'):R.epoch(self.runtime,'b'*64,now_ms=T+9000)
 def test_inputs_cannot_be_written_as_runtime(self):
  with self.assertRaisesRegex(ValueError,'ROOT_OVERLAP'):
   R.tick(self.source,self.source/'runtime',self.policy,now_ms=T+2000,epoch_ms=T-1000,clock=lambda:T+2300)
 def test_changed_publication_is_conflict_even_without_new_filename(self):
  self.tick();p=self.source/str(T)/'published'/'BTCUSDT.json'
  value=publication();value['publication_completed_ms']+=1;p.write_text(json.dumps(value))
  with self.assertRaisesRegex(ValueError,'SOURCE_CONFLICT'):self.tick()
 def test_no_data_reports_missing_without_fabricating_opportunity(self):
  result=R.tick(self.root/'absent',self.runtime,self.policy,now_ms=T+100000,epoch_ms=T-1000,clock=lambda:T+100001)
  self.assertEqual(result['status'],'SOURCE_MISSING');self.assertEqual(result['new'],0)
 def test_untrusted_filename_is_rejected_before_opening(self):
  p=self.source/str(T)/'published'/'config.json';p.write_text('{}')
  with self.assertRaisesRegex(ValueError,'PUBLICATION_NAME'):self.tick()

 def test_atomic_publication_hardlink_window_is_deferred_not_fatal(self):
  import os
  p=self.source/str(T)/'published'/'BTCUSDT.json';alias=p.parent/'temporary'
  os.link(p,alias)
  result=self.tick()
  self.assertEqual(result['status'],'SOURCE_PUBLISHING');self.assertEqual(result['new'],0)
  alias.unlink();self.assertEqual(self.tick()['new'],1)
 def test_signal_symbol_cannot_reach_raw_source_reader_before_validation(self):
  p=self.source/str(T)/'published'/'BTCUSDT.json';v=publication({'side':'short'})
  v['decisions'][0]['decision']['symbol']='../../app/policy'
  p.write_text(json.dumps(v))
  with patch.object(B,'next_open_from_source',side_effect=AssertionError('must not read')) as reader:
   with self.assertRaisesRegex(ValueError,'SYMBOL'):self.tick()
   reader.assert_not_called()

if __name__=='__main__':unittest.main()
