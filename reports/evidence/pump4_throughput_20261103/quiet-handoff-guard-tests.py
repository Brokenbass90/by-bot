import importlib.util,unittest
from unittest.mock import patch,Mock
from pathlib import Path
spec=importlib.util.spec_from_file_location('h','/private/tmp/pump4-data-quiet-handoff-20261103.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class Guards(unittest.TestCase):
 def test_units_require_exact_pins(self):
  with self.assertRaisesRegex(ValueError,'DATA_UNIT_PIN'):h.verify_unit_bytes(b'old',b'new')
 def test_no_mutation_does_not_stop(self):
  with patch.object(h,'control') as c:self.assertEqual(h.cleanup_failure(None,b'o',b'n',{},0,False),'NO_DATA_MUTATION_REQUESTED');c.assert_not_called()
 def test_uncertain_stop_old_process_still_running(self):
  u=Mock();u.read_bytes.return_value=b'o'
  with patch.object(h,'get',return_value={'MainPID':'1'}),patch.object(h,'control') as c:
   self.assertEqual(h.cleanup_failure(u,b'o',b'n',{'MainPID':'1'},0,True),'ORIGINAL_DATA_STILL_RUNNING');c.assert_not_called()
 def test_reload_failed_after_replace_restore_actual_bytes(self):
  u=Mock();u.read_bytes.side_effect=[b'n',b'n',b'o']
  with patch.object(h,'get',return_value={'MainPID':'0'}),patch.object(h,'has_attempt',return_value=False),patch.object(h,'replace_unit') as r,patch.object(h,'control') as c:
   self.assertEqual(h.cleanup_failure(u,b'o',b'n',{'MainPID':'1'},0,True),'ORIGINAL_DATA_RESTARTED_BEFORE_NEXT_ATTEMPT');r.assert_called_once_with(u,b'o');self.assertEqual(c.call_args_list[0].args,('daemon-reload',));self.assertEqual(c.call_args_list[1].args,('start',h.UNIT))
 def test_failed_running_candidate_stopped_spent_setup_preserved(self):
  u=Mock();u.read_bytes.return_value=b'n'
  with patch.object(h,'get',side_effect=[{'MainPID':'2'},{'MainPID':'0'}]),patch.object(h,'has_attempt',return_value=True),patch.object(h,'replace_unit') as r,patch.object(h,'control') as c:
   self.assertEqual(h.cleanup_failure(u,b'o',b'n',{'MainPID':'1'},0,True),'DATA_STOPPED_SPENT_NEXT_ATTEMPT_PRESERVED_NO_RESTART');r.assert_not_called();c.assert_called_once_with('stop',h.UNIT)
 def test_foreign_unit_never_touched(self):
  u=Mock();u.read_bytes.return_value=b'foreign'
  with patch.object(h,'get',return_value={'MainPID':'2'}),patch.object(h,'control') as c:
   with self.assertRaisesRegex(ValueError,'CLEANUP_FOREIGN_UNIT'):h.cleanup_failure(u,b'o',b'n',{'MainPID':'1'},0,True)
   c.assert_not_called()
 def test_final_result_requires_patch_pid_and_financial_continuity(self):
  import inspect
  s=inspect.getsource(h.run)
  self.assertLess(s.index('ACTUAL_H1_PATCH_IDENTITY_CHANGED'),s.index("once(p/'actual-h1-after.json'"));self.assertLess(s.index('ACTUAL_H1_FINANCIAL_CONTINUITY_CHANGED'),s.index("once(p/'actual-h1-after.json'"))
if __name__=='__main__':unittest.main()
