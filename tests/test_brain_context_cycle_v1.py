import copy,tempfile,unittest
from pathlib import Path
from research_lab import brain_context_cycle_v1 as C
from research_lab.att1_lifecycle_journal import SCHEMA
from tests.test_pump4_brain_timely_v1 import POLICY,T,H

def events():
 bars=[]
 for i in range(400):
  value=100+i*.1;bars.append([T-(400-i)*H,value,value+1,value-1,value+.2,1000.])
 return [dict(schema_id=SCHEMA,event_id='seed',kind='HISTORICAL_SEED',domain_schema='PUMP4_CLOSED_H1_INTAKE_V1',symbol='BTCUSDT',source_pins=C.FROZEN_SIGNAL_PINS,bars=bars,available_ms=T+1000,observed_ms=T+1100)]
def census():return dict(hour_ms=T,expected_trading=135,observations=135,signals=0,source_complete=True,source_sha256='c'*64)

class ContextTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp' if Path('/private/tmp').is_dir() else '/tmp');self.root=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def assess(self):return C.assessment(events(),census(),policy_path=POLICY,observed_ms=T+120000,epoch_ms=T+90000)
 def test_real_features_and_wait_from_original_policy(self):
  v=self.assess();self.assertEqual(v['action'],'WAIT_NO_FROZEN_SIGNAL');self.assertEqual(v['context']['btc_rezhim'],'тренд+')
  self.assertEqual(v['context']['rezhim_v1'],'UNKNOWN');self.assertGreater(v['context']['btc_ret_24h'],0)
  self.assertEqual(v['outcome_bar_open_ms'],T+H);self.assertEqual(v['outcome_bar_close_ms'],T+2*H)
  self.assertFalse(v['money_authority']);self.assertEqual(v['outcome_status'],'PENDING_OUTCOME')
 def test_future_target_excludes_part_of_hour_before_decision(self):
  v=self.assess();self.assertGreater(v['outcome_bar_open_ms'],v['observed_ms'])
 def test_incomplete_census_never_becomes_no_signal(self):
  x=census();x['source_complete']=False
  with self.assertRaisesRegex(ValueError,'CENSUS_INCOMPLETE'):C.assessment(events(),x,policy_path=POLICY,observed_ms=T+120000,epoch_ms=T+90000)
 def test_positive_signal_not_fabricated_as_absence(self):
  x=census();x['signals']=1
  v=C.assessment(events(),x,policy_path=POLICY,observed_ms=T+120000,epoch_ms=T+90000)
  self.assertEqual(v['action'],'DEFER_TO_EXISTING_SIGNAL_SHADOW')
 def test_future_and_stale_btc_rejected(self):
  for delta in [-1,2*H]:
   with self.assertRaises(ValueError):C.assessment(events(),census(),policy_path=POLICY,observed_ms=T+delta,epoch_ms=T-10000)
 def test_foreign_symbol_and_discontinuous_bars_rejected(self):
  for key in ['symbol','bars']:
   e=events()
   if key=='symbol':e[0]['symbol']='ETHUSDT'
   else:e[0]['bars'][2][0]+=H
   with self.assertRaises(ValueError):C.assessment(e,census(),policy_path=POLICY,observed_ms=T+120000,epoch_ms=T+90000)
 def test_outcome_waits_and_only_uses_fully_future_bar(self):
  d=self.assess();e=events();bar=[T+H,100.,104.,98.,102.,1000.]
  e.extend([dict(e[0],kind='CLOSED_BAR',bar=[T,100.,101.,99.,100.,1.],available_ms=T+H+1000,observed_ms=T+H+1100),dict(e[0],kind='CLOSED_BAR',bar=bar,available_ms=T+2*H+1000,observed_ms=T+2*H+1100)])
  self.assertIsNone(C.outcome(d,e,observed_ms=T+2*H-1))
  r=C.outcome(d,e,observed_ms=T+2*H+2000,witness=C.durability_witness(d,completed_ms=T+121000));self.assertAlmostEqual(r['market_return_pct'],2.)
  self.assertEqual(r['strategy_net_comparison'],'NOT_APPLICABLE_NO_TRADING_OPPORTUNITY');self.assertFalse(r['economic_pass'])
 def test_missing_future_bar_stays_pending_not_zero(self):
  self.assertIsNone(C.outcome(self.assess(),events(),observed_ms=T+3*H))
 def test_join_and_decision_replay_no_duplicates(self):
  p=self.root/'context.jsonl';v=self.assess();self.assertTrue(C.record(p,v));self.assertFalse(C.record(p,v))
  changed=copy.deepcopy(v);changed['context']['btc_ret_24h']+=1
  with self.assertRaises(ValueError):C.record(p,changed)
 def test_replaced_original_prefix_cannot_join(self):
  d=self.assess();e=events();e[0]['bars'][-1][4]-=.1
  e.extend([dict(e[0],kind='CLOSED_BAR',bar=[T,100.,101.,99.,100.,1.],available_ms=T+H+1000,observed_ms=T+H+1100),dict(e[0],kind='CLOSED_BAR',bar=[T+H,100.,103.,99.,102.,1.],available_ms=T+2*H+1000,observed_ms=T+2*H+1100)])
  with self.assertRaisesRegex(ValueError,'SOURCE_PREFIX_CHANGED'):C.outcome(d,e,observed_ms=T+2*H+2000)

if __name__=='__main__':unittest.main()
