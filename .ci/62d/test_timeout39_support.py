"""Infrastructure tests: wrong selection or unsafe continuation must be caught."""
from pathlib import Path
import json,unittest,importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('portable',HERE/'portable_run.py');portable=importlib.util.module_from_spec(spec);spec.loader.exec_module(portable)
class ContinuationTests(unittest.TestCase):
 def test_default_runs_only_failed_en_and_106_not_run(self):
  cases=json.loads((HERE/'cases.json').read_text())['cases']
  actual=getattr(portable,'select_continuation',lambda rows:rows)(cases)
  self.assertEqual(len(actual),107)
  self.assertTrue(actual[0]['case'].endswith('column_filter_sort[en]'))
  self.assertFalse(any(r['case'].endswith('column_filter_sort[pl]')for r in actual))
 def test_timeout_may_resume_only_after_verified_reaping_and_integrity(self):
  check=getattr(portable,'safe_isolated_timeout',lambda *a:False)
  row={'exit':124,'raw_outcome':'STOP_PROCESS'};proof={'job_closed':True,'process_reaped':True,'kill_on_close':True}
  self.assertTrue(check(row,proof,True,True))
  for key in proof:
   bad=dict(proof,**{key:False});self.assertFalse(check(row,bad,True,True))
  self.assertFalse(check(dict(row,exit=1),proof,True,True))
  self.assertFalse(check(dict(row,raw_outcome='ISOLATION_OR_QT_ERROR'),proof,True,True))
  self.assertFalse(check(row,proof,False,True))
  self.assertFalse(check(row,proof,True,False))
if __name__=='__main__':unittest.main()
