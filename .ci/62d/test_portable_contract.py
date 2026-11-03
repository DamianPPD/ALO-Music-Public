import unittest, tempfile, pathlib, importlib.util
ROOT=pathlib.Path(__file__).resolve().parent
class PolicyTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('policy',ROOT/'portable_policy.py')
        self.p=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.p)
    def test_writes_stay_in_private_root(self):
        with tempfile.TemporaryDirectory()as d:
            r=pathlib.Path(d);w=r/'private';w.mkdir()
            self.assertTrue(self.p.inside(w/'new.mp3',w))
            self.assertFalse(self.p.inside(r/'user.mp3',w))
            self.assertFalse(self.p.inside(w/'..'/'user.mp3',w))
    def test_junction_command_is_narrow(self):
        with tempfile.TemporaryDirectory()as d:
            r=pathlib.Path(d)
            self.assertTrue(self.p.junction_command(['/d','/c','mklink','/J',str(r/'link'),str(r/'target')],r))
            self.assertFalse(self.p.junction_command(['/d','/c','del',str(r/'file')],r))
            self.assertFalse(self.p.junction_command(['/d','/c','mklink','/J',str(r/'link'),'C:/outside'],r))
    def test_null_device_exception_is_not_a_path_allowlist(self):
        self.assertTrue(self.p.null_device('nul'))
        self.assertTrue(self.p.null_device('NUL'))
        self.assertFalse(self.p.null_device('C:/outside/nul'))
        self.assertFalse(self.p.null_device('private.mp3'))
    def test_summary_never_makes_missing_cases_pass(self):
        self.assertEqual(self.p.summary_status(['PASS']*145,145),'PASS')
        self.assertEqual(self.p.summary_status(['PASS'],145),'STOP')
        for outcome in ['FAIL','ERROR','SKIP','BLOCKED','TIMEOUT']:
            self.assertNotEqual(self.p.summary_status([outcome],1),'PASS')
if __name__=='__main__':unittest.main()
