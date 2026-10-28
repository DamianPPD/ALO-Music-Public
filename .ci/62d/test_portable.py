"""Portable packaging contract only: never imports Qt or runs product tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import portable_launch as p


class Contract(unittest.TestCase):
    def test_exact_relative_paths_only(self):
        self.assertEqual(p.relative('runtime/python.exe'), Path('runtime/python.exe'))
        for name in ('../other', '/absolute', 'C:/foreign', 'runtime\\foreign', './x', 'x//y'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.relative(name)

    def test_missing_tampered_and_unlisted_files_stop(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'runtime').mkdir(); f=root/'runtime/a'; f.write_bytes(b'fixed')
            manifest={'files':[{'path':'runtime/a','bytes':5,'sha256':hashlib.sha256(b'fixed').hexdigest()}]}
            (root/'MANIFEST.json').write_text(json.dumps(manifest))
            p.verify_package(root)
            f.write_bytes(b'other')
            with self.assertRaises(ValueError): p.verify_package(root)
            f.unlink()
            with self.assertRaises((ValueError,OSError)): p.verify_package(root)
            f.write_bytes(b'fixed'); (root/'unknown.dll').write_bytes(b'x')
            with self.assertRaises(ValueError): p.verify_package(root)

    def test_result_directories_are_excluded_not_runtime_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'MANIFEST.json').write_text('{"files":[]}')
            (root/'wyniki').mkdir(); (root/'wyniki/result.zip').write_bytes(b'result')
            p.verify_package(root)
            (root/'runtime').mkdir(); (root/'runtime/foreign.py').write_bytes(b'x')
            with self.assertRaises(ValueError): p.verify_package(root)

    def test_real_failed_xml_is_never_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'01-case').mkdir()
            (root/'01-case/result.xml').write_text('<testsuites><testsuite><testcase><failure>actual assertion</failure></testcase></testsuite></testsuites>')
            run={'planned_cases':['case'+str(i) for i in range(42)],'cases':[{'case':'case0','exit':1,'status':'STOP'}],'tests_executed':1,'accepted_cases':0,'source_integrity_before':True,'source_integrity_after':True}
            s=p.summarize(run,root)
            self.assertEqual((s['passed'],s['failed'],s['not_run']),(0,1,41))
            self.assertEqual(s['classification'],'NATIVE_NOT_PASS')

    def test_missing_xml_is_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            run={'planned_cases':['x']*42,'cases':[{'case':'x','exit':1,'status':'STOP'}],'tests_executed':1,'accepted_cases':0,'source_integrity_before':True,'source_integrity_after':True}
            with self.assertRaises((ValueError,OSError)):p.summarize(run,Path(t))

if __name__=='__main__':unittest.main()
