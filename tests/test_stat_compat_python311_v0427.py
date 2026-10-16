"""Linux unit evidence, not native Windows or full inspect_audio evidence.

The reconciliation and MANAGED functions are loaded intact. Only stat metadata
and module-local platform/version metadata are adapted; bytes, fd reads, SHA-256,
path scoping and replacements are real. With mutagen absent, identity coverage
executes its exact AST helper plus stat_identity, without fake dependencies.
"""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
if __name__ == '__main__' and len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
    SOURCE = Path(sys.argv.pop(1)).resolve()
DEPENDENCIES = SOURCE
if __name__ == '__main__' and len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
    DEPENDENCIES = Path(sys.argv.pop(1)).resolve()
sys.path.insert(0, str(DEPENDENCIES / 'src'))


def load(kind):
    relative = ('audio/identity.py' if kind == 'identity' else
                'jobs/file_reconciliation.py' if kind == 'hash' else 'jobs/managed_files.py')
    source = SOURCE / 'src/audio_library_organizer' / relative
    name = 'audio_library_organizer.jobs._proposal311_' + kind
    if kind == 'identity':
        module = ModuleType(name)
        tree = ast.parse(source.read_text(encoding='utf-8'))
        wanted = {'stat_identity', '_opened_file_matches'}
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
        module.os, module.sys = os, sys
        exec(compile(tree, str(source), 'exec'), module.__dict__)
    else:
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def platform(module, *, version=(3, 11), implementation='cpython', windows=True):
    module.sys = SimpleNamespace(version_info=version, implementation=SimpleNamespace(name=implementation))
    values = {key: getattr(os, key) for key in dir(os) if not key.startswith('__')}
    values['name'] = 'nt' if windows else 'posix'
    module.os = SimpleNamespace(**values)


def helper(module):
    return module._opened_file_matches if hasattr(module, '_opened_file_matches') else module._opened_stat_matches


def metadata(**changes):
    values = dict(st_dev=7, st_ino=9, st_size=4, st_mtime_ns=1792029639772261500,
                  st_ctime_ns=1792029639772261600, st_nlink=1)
    values.update(changes)
    return SimpleNamespace(**values)


class Stream:
    def __init__(self, stream, action):
        self.stream, self.action = stream, action

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def fileno(self):
        return self.stream.fileno()

    def read(self, *args):
        data = self.stream.read(*args)
        if data and self.action:
            action, self.action = self.action, None
            action()
        return data


def exercise(kind, *, version=(3, 11), implementation='cpython', windows=True,
             birth=None, action=None, wrong_sha=False, cancel=False):
    module = load(kind)
    platform(module, version=version, implementation=implementation, windows=windows)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / 'synthetic.mp3'
        data = b'real-full-file-hash\0' * 140000 + b'last-byte-check'
        path.write_bytes(data)
        wanted = hashlib.sha256(data).hexdigest()
        original_stat, original_open = Path.stat, Path.open
        original_fstat, original_fdopen = os.fstat, os.fdopen
        mutated = False

        def adapt(value, *, fd=False):
            values = {name: getattr(value, name) for name in dir(value) if name.startswith('st_')}
            values['st_ctime_ns'] = 1792029639772261500 + (50795100 if fd and version >= (3, 12) else 0)
            if mutated and action == ('fdctime' if fd else 'pathctime'):
                values['st_ctime_ns'] += 1
            if birth is True:
                values['st_birthtime_ns'] = 1792029639772261500
            else:
                values.pop('st_birthtime_ns', None)
            return SimpleNamespace(**values)

        def perform():
            nonlocal mutated
            mutated = True
            if action == 'replace':
                other = root / 'replacement.mp3'
                other.write_bytes(data)
                other.replace(path)
            elif action == 'append':
                with original_open(path, 'ab') as stream:
                    stream.write(b'actual-change')
            elif action == 'mtime':
                before = original_stat(path)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))

        def adapted_open(locator, *args, **kwargs):
            stream = original_open(locator, *args, **kwargs)
            return Stream(stream, perform) if locator == path and args and args[0] == 'rb' and action else stream

        module.os.fstat = lambda fd: adapt(original_fstat(fd), fd=True)
        module.os.fdopen = lambda fd, mode: Stream(original_fdopen(fd, mode), perform if action else None)
        with patch.object(Path, 'stat', lambda locator, *a, **kw: adapt(original_stat(locator, *a, **kw))), \
             patch.object(Path, 'open', adapted_open):
            if kind == 'hash':
                value = module._hash_file(path, root=root, root_stat=root.stat(),
                                          expected_stat=path.stat(), cancelled=lambda: cancel)
            else:
                plan = module.ReadResolution('library', 'track', module.ReadPurpose.PLAYBACK,
                    locator=str(path), kind=module.MaterialKind.MANAGED, root=str(root),
                    expected_sha256='0' * 64 if wrong_sha else wanted)
                value = module.recheck_read_path(plan, cancelled=lambda: cancel)
        return value, wanted


class Python311CompatibilityTests(unittest.TestCase):
    def test_cpython311_uses_real_integer_creation_without_birthtime(self):
        for kind in ('identity', 'hash', 'managed'):
            with self.subTest(kind=kind):
                module = load(kind)
                platform(module)
                try:
                    matches = helper(module)(metadata(), metadata())
                except ValueError as exc:
                    self.fail('real integer CPython 3.11 creation evidence was rejected: ' + str(exc))
                self.assertTrue(matches)

    def test_cpython311_real_reads_hash_whole_file_and_verify_managed(self):
        for kind in ('hash', 'managed'):
            with self.subTest(kind=kind):
                try:
                    value, wanted = exercise(kind)
                except ValueError as exc:
                    self.fail('unchanged CPython 3.11 metadata was rejected: ' + str(exc))
                if kind == 'hash':
                    self.assertEqual(value, wanted)
                else:
                    self.assertTrue(value.is_verified, value.reason_code)
                    self.assertEqual(value.material_identity[-1], wanted)

    def test_312_requires_birthtime_even_if_ctime_matches(self):
        for kind in ('identity', 'hash', 'managed'):
            module = load(kind)
            platform(module, version=(3, 12))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                helper(module)(metadata(), metadata())
        for kind in ('hash', 'managed'):
            if kind == 'hash':
                with self.assertRaises(ValueError):
                    exercise(kind, version=(3, 12))
            else:
                self.assertFalse(exercise(kind, version=(3, 12))[0].is_verified)

    def test_312_keeps_measured_stat_fstat_difference_working(self):
        for kind in ('hash', 'managed'):
            value, wanted = exercise(kind, version=(3, 12), birth=True)
            self.assertEqual(value, wanted) if kind == 'hash' else self.assertTrue(value.is_verified)

    def test_other_interpreters_and_versions_do_not_get_311_exception(self):
        for kind in ('identity', 'hash', 'managed'):
            for version, implementation in (((3, 11), 'pypy'), ((3, 10), 'cpython'), ((3, 13), 'cpython')):
                module = load(kind)
                platform(module, version=version, implementation=implementation)
                with self.subTest(kind=kind, version=version, implementation=implementation), self.assertRaises(ValueError):
                    helper(module)(metadata(), metadata())

    def test_all_311_identity_fields_still_detect_difference(self):
        for kind in ('identity', 'hash', 'managed'):
            module = load(kind)
            platform(module)
            for field in vars(metadata()):
                with self.subTest(kind=kind, field=field):
                    original = metadata()
                    changed = metadata(**{field: getattr(original, field) + 1})
                    self.assertFalse(helper(module)(original, changed))

    def test_missing_invalid_and_zero_inode_evidence_fail_closed(self):
        invalid = [('st_dev', -1), ('st_ino', 0), ('st_size', -1), ('st_nlink', 0),
                   ('st_ctime_ns', None), ('st_ctime_ns', 1.0), ('st_ctime_ns', True)]
        for kind in ('identity', 'hash', 'managed'):
            module = load(kind)
            platform(module)
            for field, value in invalid:
                for first in (True, False):
                    before, opened = metadata(), metadata()
                    setattr(before if first else opened, field, value)
                    with self.subTest(kind=kind, field=field, value=value, first=first), self.assertRaises(ValueError):
                        helper(module)(before, opened)
            missing = metadata()
            del missing.st_ctime_ns
            with self.assertRaises(ValueError):
                helper(module)(missing, metadata())

    def test_real_path_swap_content_change_and_same_api_ctime_change_reject(self):
        for kind in ('hash', 'managed'):
            for action in ('replace', 'append', 'mtime', 'fdctime', 'pathctime'):
                with self.subTest(kind=kind, action=action):
                    if kind == 'hash':
                        with self.assertRaises((OSError, ValueError)):
                            exercise(kind, action=action)
                    else:
                        self.assertFalse(exercise(kind, action=action)[0].is_verified)

    def test_managed_full_sha_mismatch_rejects(self):
        value, _ = exercise('managed', wrong_sha=True)
        self.assertFalse(value.is_verified)
        self.assertEqual(value.reason_code, 'MANAGED_IDENTITY_CHANGED')

    def test_311_cancel_preserves_refusal(self):
        with self.assertRaises(InterruptedError):
            exercise('hash', cancel=True)
        managed, _ = exercise('managed', cancel=True)
        self.assertFalse(managed.is_verified)
        self.assertEqual(managed.reason_code, 'CANCELLED')

    def test_posix_ctime_and_real_reads_are_unchanged(self):
        for kind in ('identity', 'hash', 'managed'):
            module = load(kind)
            platform(module, windows=False)
            self.assertTrue(helper(module)(metadata(), metadata()))
            self.assertFalse(helper(module)(metadata(), metadata(st_ctime_ns=1792029639772261501)))
        for kind in ('hash', 'managed'):
            value, wanted = exercise(kind, windows=False)
            self.assertEqual(value, wanted) if kind == 'hash' else self.assertTrue(value.is_verified)


if __name__ == '__main__':
    unittest.main(verbosity=2)
