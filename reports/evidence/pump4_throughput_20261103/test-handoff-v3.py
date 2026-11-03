import unittest,importlib.util,os
from unittest.mock import patch,Mock
from pathlib import Path
spec=importlib.util.spec_from_file_location('handoff_v3',Path(os.environ.get('PUMP4_HANDOFF_REVIEW_PATH','/private/tmp/pump4_handoff_v3.py')));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class ColdPreload(unittest.TestCase):
 def test_measured_147_second_cold_preload_is_allowed(self):
  self.assertGreater(h.preload_deadline(3600000,123.0,3690000)-123.0,147)
 def test_timeout_is_bounded_to_fifteen_minutes(self):
  self.assertEqual(h.preload_deadline(3600000,123.0,3690000),1023.0)
 def test_preload_cannot_consume_next_subscription_boundary(self):
  self.assertEqual(h.preload_deadline(3600000,123.0,6900000),303.0)
 def test_late_handoff_is_rejected_before_stop(self):
  with self.assertRaisesRegex(ValueError,'INSUFFICIENT_PRELOAD_HEADROOM'):h.preload_deadline(3600000,123.0,7040000)
 def test_financial_units_never_controlled(self):
  with patch.object(h.subprocess,'run') as r:
   for cmd in [('stop','pump4-execution-owner.service'),('start','alpaca-monthly-owned.service')]:
    with self.assertRaisesRegex(ValueError,'DATA_UNIT_ONLY'):h.control(*cmd)
   r.assert_not_called()
 def test_original_stays_running_on_pre_stop_failure(self):
  with patch.object(h,'control') as c:self.assertEqual(h.cleanup_failure(None,b'a',b'b',{},0,False),'NO_DATA_MUTATION_REQUESTED');c.assert_not_called()
 def test_uncertain_stop_observes_original_pid_without_restart(self):
  u=Mock();u.read_bytes.return_value=b'o'
  with patch.object(h,'get',return_value={'MainPID':'4063038'}),patch.object(h,'control') as c:
   self.assertEqual(h.cleanup_failure(u,b'o',b'n',{'MainPID':'4063038'},0,True),'ORIGINAL_DATA_STILL_RUNNING');c.assert_not_called()
class CleanupTimer(unittest.TestCase):
 def test_failure_after_timer_started_stops_timer_before_candidate_cleanup(self):
  calls=[]
  with patch.object(h,'control',side_effect=lambda *a:calls.append(a)),patch.object(h,'get',side_effect=[{'ActiveState':'inactive'},{'MainPID':'0'}]),patch.object(h,'cleanup_failure',side_effect=lambda *a:calls.append(('CLEANUP',)) or 'SPENT'):
   self.assertEqual(h.reconcile_failure(None,b'o',b'n',{},0,True,True),'SPENT')
  self.assertEqual(calls,[('stop',h.TIMER),('CLEANUP',)])
 def test_safe_original_restores_timer_after_reconciliation(self):
  with patch.object(h,'control') as c,patch.object(h,'get',side_effect=[{'ActiveState':'inactive'},{'MainPID':'4063038'}]),patch.object(h,'cleanup_failure',return_value='ORIGINAL_DATA_STILL_RUNNING'):
   h.reconcile_failure(None,b'o',b'n',{},0,True,True)
   self.assertEqual([x.args for x in c.call_args_list],[('stop',h.TIMER),('start',h.TIMER)])
 def test_uncertain_timer_stop_does_not_stop_candidate(self):
  with patch.object(h,'control',side_effect=ValueError('TIMER_STOP_UNCONFIRMED')),patch.object(h,'cleanup_failure') as cleanup:
   with self.assertRaisesRegex(ValueError,'TIMER_STOP_UNCONFIRMED'):h.reconcile_failure(None,b'o',b'n',{},0,True,True)
   cleanup.assert_not_called()
if __name__=='__main__':unittest.main()
