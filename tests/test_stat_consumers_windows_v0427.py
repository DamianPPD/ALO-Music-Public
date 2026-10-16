"""Causal tests of real backend functions, real files/fds, adapted Windows stat.

No Qt, no Windows execution claim. Timestamp values model the measured Windows
API semantics; production reads/hashes and ordinary file replacements are real.
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent
if __name__=='__main__' and len(sys.argv)>1 and not sys.argv[1].startswith('-'):
    SOURCE=Path(sys.argv.pop(1)).resolve()
DEPENDENCIES=SOURCE
if __name__=='__main__' and len(sys.argv)>1 and not sys.argv[1].startswith('-'):
    DEPENDENCIES=Path(sys.argv.pop(1)).resolve()
sys.path.insert(0,str(DEPENDENCIES/'src'))
from audio_library_organizer.jobs import scanner
from audio_library_organizer.jobs.managed_files import ReadResolution,ReadPurpose,MaterialKind

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

class Stream:
    def __init__(self,stream,action):self.stream=stream;self.action=action
    def __enter__(self):self.stream.__enter__();return self
    def __exit__(self,*args):return self.stream.__exit__(*args)
    def fileno(self):return self.stream.fileno()
    def read(self,*args):
        data=self.stream.read(*args)
        if data and self.action:
            action,self.action=self.action,None;action()
        return data

def exercise(kind,*,delta=50795100,fd_changes=None,action=None,cancel=False,birth_missing=False,windows=True,wrong_sha=False):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);path=root/'synthetic.mp3';data=b'synthetic-unit-audio\0'*1024;path.write_bytes(data)
        digest=hashlib.sha256(data).hexdigest();original_stat=Path.stat;original_open=Path.open
        real_fstat=os.fstat;real_fdopen=os.fdopen;mutated=False
        def adapted(value,fd=False):
            fields={n:getattr(value,n)for n in dir(value)if n.startswith('st_')}
            fields['st_ctime_ns']=1792029639772261500+(delta if fd else 0)
            if mutated and ((fd and action=='fdctime') or (not fd and action=='pathctime')):fields['st_ctime_ns']+=1
            if fd and birth_missing:fields.pop('st_birthtime_ns',None)
            else:fields['st_birthtime_ns']=1792029639772261500
            if fd:fields.update(fd_changes or {})
            return SimpleNamespace(**fields)
        def path_stat(p,*args,**kwargs):return adapted(original_stat(p,*args,**kwargs))
        def perform():
            nonlocal mutated
            mutated=True
            if action=='append':
                with original_open(path,'ab') as f:f.write(b'actual-content-change')
            if action in ('replace','replace_large'):
                other=root/'replacement.mp3';other.write_bytes(data+(b'larger replacement' if action=='replace_large' else b''));other.replace(path)
            if action=='mtime':
                info=original_stat(path)
                os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1000000000))
        m=load('audio_library_organizer.jobs._causal_'+kind,SOURCE/'src/audio_library_organizer/jobs'/('file_reconciliation.py'if kind=='hash'else'managed_files.py'))
        proxy={n:getattr(os,n)for n in dir(os)if not n.startswith('__')};proxy.update(name='nt' if windows else 'posix',fstat=lambda fd:adapted(real_fstat(fd),True))
        proxy['fdopen']=lambda fd,mode:Stream(real_fdopen(fd,mode),perform if action else None)
        m.os=SimpleNamespace(**proxy)
        # The adapted ctime offset and missing-birthtime case model CPython 3.12.
        m.sys=SimpleNamespace(implementation=SimpleNamespace(name='cpython'),version_info=(3,12))
        def open_stream(p,*args,**kwargs):
            stream=original_open(p,*args,**kwargs)
            return Stream(stream,perform)if p==path and args and args[0]=='rb' and action else stream
        with patch.object(Path,'stat',path_stat),patch.object(Path,'open',open_stream):
            if kind=='hash':
                return m._hash_file(path,root=root,root_stat=root.stat(),expected_stat=path.stat(),cancelled=lambda:cancel),digest
            plan=m.ReadResolution('library','track',m.ReadPurpose.PLAYBACK,locator=str(path),kind=m.MaterialKind.MANAGED,
                root=str(root),expected_sha256='0'*64 if wrong_sha else digest)
            return m.recheck_read_path(plan,cancelled=lambda:cancel),digest

class ConsumersTests(unittest.TestCase):
    def test_unchanged_reconciliation_hash_with_measured_windows_semantics(self):
        value,wanted=exercise('hash');self.assertEqual(value,wanted)
    def test_unchanged_adopted_MANAGED_read_without_SOURCE(self):
        value,_=exercise('managed');self.assertTrue(value.is_verified,value.reason_code)
        self.assertEqual(value.kind,MaterialKind.MANAGED)
    def test_original_matching_semantics_control(self):
        value,wanted=exercise('hash',delta=0);self.assertEqual(value,wanted)
        value,_=exercise('managed',delta=0);self.assertTrue(value.is_verified,value.reason_code)
    def test_different_identity_fields_fail_closed(self):
        for field in ('st_dev','st_ino','st_size','st_mtime_ns'):
            for kind in ('hash','managed'):
                with self.subTest(kind=kind,field=field):
                    if kind=='hash':
                        with self.assertRaises((OSError,ValueError)):exercise(kind,fd_changes={field:1})
                    else:self.assertFalse(exercise(kind,fd_changes={field:1})[0].is_verified)
    def test_real_content_change_and_same_size_replacement_rejected(self):
        for action in ('append','replace'):
            for kind in ('hash','managed'):
                with self.subTest(kind=kind,action=action):
                    if kind=='hash':
                        with self.assertRaises((OSError,ValueError)):exercise(kind,action=action)
                    else:self.assertFalse(exercise(kind,action=action)[0].is_verified)
    def test_cancel_and_missing_identity_rejected(self):
        with self.assertRaises(InterruptedError):exercise('hash',cancel=True,delta=0)
        self.assertFalse(exercise('managed',cancel=True,delta=0)[0].is_verified)
        for kwargs in ({'birth_missing':True},{'fd_changes':{'st_ino':0}}):
            with self.assertRaises((OSError,ValueError)):exercise('hash',**kwargs)
            self.assertFalse(exercise('managed',**kwargs)[0].is_verified)
    def test_same_API_ctime_and_POSIX_guards_preserved(self):
        for kind in ('hash','managed'):
            for action in ('fdctime','pathctime'):
                with self.subTest(kind=kind,action=action):
                    if kind=='hash':
                        with self.assertRaises((OSError,ValueError)):exercise(kind,delta=0,action=action)
                    else:self.assertFalse(exercise(kind,delta=0,action=action)[0].is_verified)
            if kind=='hash':
                with self.assertRaises((OSError,ValueError)):exercise(kind,windows=False)
                value,wanted=exercise(kind,windows=False,delta=0);self.assertEqual(value,wanted)
            else:
                self.assertFalse(exercise(kind,windows=False)[0].is_verified)
                self.assertTrue(exercise(kind,windows=False,delta=0)[0].is_verified)
    def test_real_mtime_only_change_during_operation_rejected(self):
        with self.assertRaises((OSError,ValueError)):exercise('hash',delta=0,action='mtime')
        self.assertFalse(exercise('managed',delta=0,action='mtime')[0].is_verified)
    def test_real_different_sized_path_replacement_rejected(self):
        with self.assertRaises((OSError,ValueError)):exercise('hash',delta=0,action='replace_large')
        self.assertFalse(exercise('managed',delta=0,action='replace_large')[0].is_verified)
    def test_managed_full_SHA_mismatch_is_still_rejected(self):
        value,_=exercise('managed',delta=0,wrong_sha=True)
        self.assertFalse(value.is_verified)
        self.assertEqual(value.reason_code,'MANAGED_IDENTITY_CHANGED')

if __name__=='__main__':unittest.main(verbosity=2)
