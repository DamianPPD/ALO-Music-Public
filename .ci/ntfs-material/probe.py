"""Measure native NTFS material proofs using only newly created synthetic data.

Run on Windows x64 with either isolated product checkout's src on PYTHONPATH:
    python probe.py --temp <new absolute local directory> --output <absolute JSON>
This is an observation program, separate from the unchanged pytest reproduction.
A proof collision is reported as data; setup or measurement errors return 1.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import ctypes as C
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
import traceback


BASELINE = b'0123456789abcdef'
EDITED = b'fedcba9876543210'
TICK = 10_000_000
# Deliberately distinct old FILETIME values: neither zero nor near today's clock.
MARKER_WRITE = 132_223_104_000_000_000
MARKER_CHANGE = MARKER_WRITE + 3 * TICK
SHARE_ALL = 7
READ_DATA = 0x1
READ_ATTRIBUTES = 0x80
WRITE_ATTRIBUTES = 0x100
GENERIC_WRITE = 0x40000000
OPEN_REPARSE_POINT = 0x00200000
ERROR_SHARING_VIOLATION = 32


class BasicInfo(C.Structure):
    _fields_ = [('creation_time', C.c_int64), ('last_access', C.c_int64),
                ('last_write', C.c_int64), ('change_time', C.c_int64),
                ('attributes', C.c_uint32)]


class StandardInfo(C.Structure):
    _fields_ = [('allocation_size', C.c_int64), ('size', C.c_int64),
                ('links', C.c_uint32), ('delete_pending', C.c_ubyte),
                ('directory', C.c_ubyte)]


class IdInfo(C.Structure):
    _fields_ = [('volume_serial', C.c_uint64), ('file_id', C.c_ubyte * 16)]


class FileTime(C.Structure):
    _fields_ = [('low', C.c_uint32), ('high', C.c_uint32)]

    @property
    def ticks(self):
        return (self.high << 32) | self.low


def serializable(value):
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f'unexpected JSON value {value!r}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def error_data(exc):
    return {'type': type(exc).__name__, 'message': str(exc),
            'errno': getattr(exc, 'errno', None), 'winerror': getattr(exc, 'winerror', None)}


def attempt(fn):
    try:
        return {'ok': True, 'value': fn()}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'error': error_data(exc)}


class IndependentWin32:
    """Separate ctypes declarations and Win32 handles; no application API reuse."""

    def __init__(self):
        require(sys.platform == 'win32' and C.sizeof(C.c_void_p) == 8, 'Windows x64 required')
        require([C.sizeof(t) for t in (BasicInfo, StandardInfo, IdInfo, FileTime)] == [40, 24, 24, 8],
                'Incorrect Windows ctypes ABI')
        dll = C.WinDLL('kernel32', use_last_error=True)
        ptr, dw, boolean, string = C.c_void_p, C.c_uint32, C.c_int32, C.c_wchar_p

        def bind(name, types, returns=boolean):
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = types, returns
            return fn

        self.create = bind('CreateFileW', [string, dw, dw, ptr, dw, dw, ptr], ptr)
        self.close = bind('CloseHandle', [ptr])
        self.get_info = bind('GetFileInformationByHandleEx', [ptr, C.c_int32, ptr, dw])
        self.set_info = bind('SetFileInformationByHandle', [ptr, C.c_int32, ptr, dw])
        self.get_final = bind('GetFinalPathNameByHandleW', [ptr, string, dw, dw], dw)
        self.get_volume = bind('GetVolumeInformationByHandleW',
                               [ptr, string, dw, C.POINTER(dw), C.POINTER(dw), C.POINTER(dw), string, dw])
        self.get_drive = bind('GetDriveTypeW', [string], dw)
        self.read = bind('ReadFile', [ptr, ptr, dw, C.POINTER(dw), ptr])
        self.coarse_time = bind('GetSystemTimeAsFileTime', [C.POINTER(FileTime)], None)
        self.precise_time = bind('GetSystemTimePreciseAsFileTime', [C.POINTER(FileTime)], None)

    @staticmethod
    def check(ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    @contextmanager
    def handle(self, path, access):
        h = self.create(str(path), access, SHARE_ALL, None, 3, OPEN_REPARSE_POINT, None)
        self.check(h not in (None, C.c_void_p(-1).value))
        try:
            yield h
        finally:
            self.check(self.close(h))

    def metadata(self, h):
        basic, standard, identity = BasicInfo(), StandardInfo(), IdInfo()
        for kind, data in ((0, basic), (1, standard), (18, identity)):
            self.check(self.get_info(h, kind, C.byref(data), C.sizeof(data)))
        return {**{name: getattr(basic, name) for name, _ in BasicInfo._fields_},
                **{name: getattr(standard, name) for name, _ in StandardInfo._fields_},
                'volume_serial': identity.volume_serial, 'file_id': bytes(identity.file_id).hex()}

    def final(self, h, flags):
        name = C.create_unicode_buffer(32768)
        length = self.get_final(h, name, len(name), flags)
        self.check(length != 0)
        require(length < len(name), 'GetFinalPathNameByHandleW buffer was too short')
        return name.value

    def observe(self, path):
        with self.handle(path, READ_DATA | READ_ATTRIBUTES) as h:
            data = self.metadata(h)
            before_access = data['last_access']
            filesystem = C.create_unicode_buffer(64)
            flags = C.c_uint32()
            self.check(self.get_volume(h, None, 0, None, None, C.byref(flags), filesystem, len(filesystem)))
            final = self.final(h, 0)
            guid_path = self.final(h, 1)
            prefix = re.match(r'^(\\\\\?\\Volume\{[0-9A-Fa-f-]+\}\\)', guid_path)
            require(final.startswith('\\\\?\\') and prefix, f'Unexpected native paths: {final!r}, {guid_path!r}')
            data.update(filesystem=filesystem.value, filesystem_flags=flags.value,
                        drive_type=self.get_drive(path.anchor), final_path=final[4:],
                        volume_guid=prefix.group(1).casefold(), final_guid_path=guid_path)
            require((data['filesystem'], data['drive_type']) == ('NTFS', 3), 'Not a local fixed NTFS volume')
            require(data['final_path'].casefold() == str(path).casefold(), 'Independent reader reached a different path')
            require(data['size'] == len(BASELINE) and not data['delete_pending'] and not data['directory'],
                    f'Unexpected fixture state: {data}')
            buf, got = C.create_string_buffer(64), C.c_uint32()
            self.check(self.read(h, buf, len(buf), C.byref(got), None))
            require(got.value == data['size'], 'Short or mismatched ReadFile result')
            payload = buf.raw[:got.value]
            after_read = self.metadata(h)
            # Last access may be delayed or change as a result of reading; save it independently.
            for field in ('volume_serial', 'file_id', 'size', 'creation_time', 'last_write', 'change_time', 'attributes'):
                require(data[field] == after_read[field], f'Independent reader metadata changed while reading: {field}')
            data.update(sha256=sha(payload), bytes_hex=payload.hex(), read_size=got.value,
                        last_access_before_read=before_access, last_access_after_read=after_read['last_access'])
            return data

    def clock(self):
        coarse, precise = FileTime(), FileTime()
        self.coarse_time(C.byref(coarse))
        self.precise_time(C.byref(precise))
        return {'coarse_filetime_100ns': coarse.ticks, 'precise_filetime_100ns': precise.ticks,
                'monotonic_ns': time.perf_counter_ns()}

    def set_times(self, path, last_write, change_time):
        info = BasicInfo(0, 0, last_write, change_time, 0)
        with self.handle(path, WRITE_ATTRIBUTES) as h:
            self.check(self.set_info(h, 0, C.byref(info), C.sizeof(info)))


def stat_record(st):
    return {name: getattr(st, name, None) for name in
            ('st_size', 'st_ino', 'st_dev', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns', 'st_birthtime_ns')}


def app_capture(native, path):
    obs = attempt(lambda: native.capture(path))
    if obs['ok']:
        proof = obs['value']
        return proof, {'ok': True, 'proof': asdict(proof)}
    return None, obs


APP_NATIVE_COMMON = ('filesystem', 'drive_type', 'volume_guid', 'volume_serial', 'file_id', 'size',
                     'last_write', 'change_time', 'creation_time', 'links', 'attributes', 'delete_pending',
                     'final_path', 'directory')
OBJECT_FIELDS = ('volume_guid', 'volume_serial', 'file_id', 'creation_time', 'directory')


def verify_app_agreement(proof, win):
    require(proof is not None, 'The app could not capture a closed ordinary fixture')
    for key in APP_NATIVE_COMMON:
        actual = getattr(proof.leaf, key)
        if key == 'file_id':
            actual = actual.hex()
        require(actual == win[key], f'Application vs. independent native field {key}: {actual!r} != {win[key]!r}')


def record_baseline(row, api, native, path, *, marker=False):
    row['clocks'] = {'create_start': api.clock()}
    require(path.write_bytes(BASELINE) == len(BASELINE), 'Incomplete baseline write')
    row['clocks']['create_writer_closed'] = api.clock()
    if marker:
        row['marker_set'] = attempt(lambda: api.set_times(path, MARKER_WRITE, MARKER_CHANGE))
    row['before_native'] = api.observe(path)
    before, row['before_app'] = app_capture(native, path)
    st = path.stat()
    row['before_stat'] = stat_record(st)
    require(row['before_native']['sha256'] == sha(BASELINE), 'Baseline SHA-256 did not match fixture')
    verify_app_agreement(before, row['before_native'])
    if marker:
        row['marker_persisted'] = (row['before_native']['last_write'], row['before_native']['change_time']) == (MARKER_WRITE, MARKER_CHANGE)
    return before, st


def record_end(row, api, native, path, before, after, post, *, same_object, expected_bytes, app_obs):
    row['after_app'] = app_obs
    row['after_stat'] = stat_record(post)
    row['after_native'] = end = api.observe(path)
    start = row['before_native']
    row['same_material'] = native.same_material(before, after) if after is not None else None
    row['bytes_changed'] = start['sha256'] != end['sha256']
    row['same_object'] = all(start[k] == end[k] for k in OBJECT_FIELDS)
    row['same_volume_file_id'] = all(start[k] == end[k] for k in ('volume_guid', 'volume_serial', 'file_id'))
    row['same_size'] = start['size'] == end['size']
    row['same_mtime_ns'] = row['before_stat']['st_mtime_ns'] == post.st_mtime_ns
    row['last_write_delta_100ns'] = end['last_write'] - start['last_write']
    row['change_time_delta_100ns'] = end['change_time'] - start['change_time']
    row['creation_time_delta_100ns'] = end['creation_time'] - start['creation_time']
    row['changed_native_fields'] = [k for k in APP_NATIVE_COMMON if start[k] != end[k]]
    row['changed_app_leaf_fields'] = [k for k, v in asdict(before.leaf).items() if v != getattr(after.leaf, k)] if after else None
    row['same_app_ancestors'] = before.ancestors == after.ancestors if after else None
    row['data_collision'] = row['bytes_changed'] and row['same_material'] is True
    verify_app_agreement(after, end)
    require(end['sha256'] == sha(expected_bytes), 'Independent SHA-256 did not match expected fixture bytes')
    require(row['same_volume_file_id'] is same_object, 'Independent file ID did not match the intended mutation')
    require(row['same_size'], 'The fixture did not remain the same size')


def exact_case(row, api, native, path, kind, *, marker=False):
    before, st = record_baseline(row, api, native, path, marker=marker)
    row['clocks']['mutation_start'] = api.clock()
    if kind != 'unchanged':
        written = path.write_bytes(EDITED)  # Path.write_bytes closes its writer before returning, as in pytest.
        row['clocks']['mutation_writer_closed'] = api.clock()
        require(written == len(EDITED), 'Incomplete mutation write')
        if kind == 'restored-mtime':
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
            row['clocks']['os_utime_returned'] = api.clock()
    after, app_obs = app_capture(native, path)
    row['clocks']['app_capture_returned'] = api.clock()
    post = path.stat()
    record_end(row, api, native, path, before, after, post, same_object=True,
               expected_bytes=BASELINE if kind == 'unchanged' else EDITED, app_obs=app_obs)
    if kind == 'restored-mtime':
        require(row['same_mtime_ns'] and row['last_write_delta_100ns'] == 0,
                'os.utime did not restore the exact Python and native mtime')


def phased_case(row, api, native, path):
    import msvcrt

    before, st = record_baseline(row, api, native, path)
    row['open_phases'] = {}
    row['clocks']['mutation_start'] = api.clock()
    # Read/write mode also gives the writer handle FILE_READ_ATTRIBUTES, needed
    # for the independent metadata query. Truncation still matches write_bytes.
    with path.open('w+b') as writer:
        h = msvcrt.get_osfhandle(writer.fileno())
        require(writer.write(EDITED) == len(EDITED), 'Incomplete phased write')
        writer.flush()
        for phase in ('flushed', 'fsynced'):
            if phase == 'fsynced':
                os.fsync(writer.fileno())
            row['clocks'][phase] = api.clock()
            writer_info = api.metadata(h)
            readback = api.observe(path)
            _, capture = app_capture(native, path)
            row['open_phases'][phase] = {'writer_handle_native': writer_info, 'independent_reader': readback,
                                         'app_capture': capture, 'writer_closed': writer.closed}
            require(all(writer_info[k] == readback[k] == row['before_native'][k]
                        for k in ('volume_serial', 'file_id')), 'Writer, reader and baseline file IDs disagree')
            require(readback['sha256'] == sha(EDITED), 'Edited data not readable after writing on the same file ID')
    row['clocks']['mutation_writer_closed'] = api.clock()
    row['writer_closed'] = writer.closed
    closed, row['closed_app'] = app_capture(native, path)
    row['closed_native'] = api.observe(path)
    row['same_material_after_close_before_restore'] = native.same_material(before, closed) if closed is not None else None
    verify_app_agreement(closed, row['closed_native'])
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    row['clocks']['os_utime_returned'] = api.clock()
    after, app_obs = app_capture(native, path)
    post = path.stat()
    record_end(row, api, native, path, before, after, post, same_object=True, expected_bytes=EDITED, app_obs=app_obs)
    require(row['same_mtime_ns'] and row['last_write_delta_100ns'] == 0,
            'Phased os.utime did not restore the exact Python and native mtime')
    row['capture_refused_open_writer_win32_32'] = all(
        not p['app_capture']['ok'] and p['app_capture']['error']['winerror'] == ERROR_SHARING_VIOLATION
        for p in row['open_phases'].values())


def replacement_case(row, api, native, path, *, keep_original):
    before, st = record_baseline(row, api, native, path)
    replacement = path.with_name('replacement.bin')
    require(replacement.write_bytes(BASELINE) == len(BASELINE), 'Incomplete replacement write')
    os.utime(replacement, ns=(st.st_atime_ns, st.st_mtime_ns))
    row['replacement_before_move'] = api.observe(replacement)
    if keep_original:
        original = path.with_name('original-held.bin')
        path.rename(original)
    os.replace(replacement, path)
    after, app_obs = app_capture(native, path)
    record_end(row, api, native, path, before, after, path.stat(), same_object=False,
               expected_bytes=BASELINE, app_obs=app_obs)
    for field in ('volume_serial', 'file_id'):
        require(row['replacement_before_move'][field] == row['after_native'][field], 'Replacement moved a different physical file')
    if keep_original:
        row['original_after_move'] = api.observe(original)
        for field in ('volume_serial', 'file_id'):
            require(row['before_native'][field] == row['original_after_move'][field], 'Original object was not kept under its new name')
    require(row['same_mtime_ns'] and row['last_write_delta_100ns'] == 0,
            'Replacement control did not preserve exact mtime')


def rollback_case(row, api, native, path):
    """Separate explicit metadata rollback from ordinary close / os.utime."""
    before, _ = record_baseline(row, api, native, path, marker=True)
    require(path.write_bytes(EDITED) == len(EDITED), 'Incomplete rollback-control write')
    row['native_after_write_before_rollback'] = api.observe(path)
    base = row['before_native']
    row['rollback_attempt'] = attempt(lambda: api.set_times(path, base['last_write'], base['change_time']))
    after, app_obs = app_capture(native, path)
    record_end(row, api, native, path, before, after, path.stat(), same_object=True,
               expected_bytes=EDITED, app_obs=app_obs)
    row['rollback_persisted'] = row['last_write_delta_100ns'] == row['change_time_delta_100ns'] == 0


def lease_case(row, api, native, acquire_lease, path):
    source, target, replacement = (path.with_name(s) for s in ('source.mp3', 'managed.mp3', 'replacement.mp3'))
    for item, payload in ((source, BASELINE), (target, BASELINE), (replacement, EDITED)):
        require(item.write_bytes(payload) == len(payload), 'Incomplete lease fixture write')
    row['before_native'] = api.observe(target)
    row['source_native'] = api.observe(source)
    row['replacement_native'] = api.observe(replacement)
    lease = acquire_lease(source, target)
    before = lease.material[1]
    row['lease_proofs'] = [asdict(p) for p in lease.material]
    try:
        row['active_for_pair'] = lease.active_for((str(source), str(target)), lease.material)
        row['owned_handles_active'] = lease.owned_count

        def native_write_open():
            with api.handle(target, GENERIC_WRITE):
                return True

        row['native_writer_open_while_active'] = attempt(native_write_open)
        row['replacement_while_active'] = attempt(lambda: os.replace(replacement, target))
        if row['replacement_while_active']['ok']:
            require(replacement.write_bytes(EDITED) == len(EDITED), 'Incomplete replacement control recreation')
        # The independent reader shares everything; it can coexist with the held lease.
        row['while_active_native'] = api.observe(target)
    finally:
        lease.close()
    row['active_after_close'] = lease.active
    row['owned_handles_after_close'] = lease.owned_count
    row['native_writer_open_after_release'] = attempt(native_write_open)
    row['replacement_after_release'] = attempt(lambda: os.replace(replacement, target))
    after, row['after_app'] = app_capture(native, target)
    row['after_native'] = api.observe(target)
    row['same_material_after_release_replace'] = native.same_material(before, after) if after is not None else None
    verify_app_agreement(after, row['after_native'])
    row['protected_refused_mutation'] = (
        not row['native_writer_open_while_active']['ok']
        and row['native_writer_open_while_active']['error']['winerror'] == ERROR_SHARING_VIOLATION
        and not row['replacement_while_active']['ok']
        and row['replacement_while_active']['error']['winerror'] in (5, ERROR_SHARING_VIOLATION)
        and row['while_active_native']['sha256'] == sha(BASELINE)
        and row['while_active_native']['file_id'] == row['before_native']['file_id'])
    row['postrelease_control_succeeded'] = (row['native_writer_open_after_release']['ok']
        and row['replacement_after_release']['ok'] and row['after_native']['sha256'] == sha(EDITED)
        and row['after_native']['file_id'] != row['before_native']['file_id'])
    require(row['postrelease_control_succeeded'], 'Mutation control after lease release did not work')


def run(args, report):
    require(args.iterations >= 2, 'At least two iterations are required to vary probe order')
    api = IndependentWin32()
    from audio_library_organizer.safety import windows_file_identity as native
    from audio_library_organizer.safety.windows_output_lease import acquire_output_lease

    report.update(python=sys.version, executable=sys.executable, platform=platform.platform(), pid=os.getpid(),
                  native_module=native.__file__, native_module_sha256=sha(Path(native.__file__).read_bytes()),
                  fixture_sha256={'baseline': sha(BASELINE), 'edited': sha(EDITED)},
                  marker={'last_write': MARKER_WRITE, 'change_time': MARKER_CHANGE}, temp=str(args.temp),
                  iterations=args.iterations)
    require(args.temp.is_absolute() and re.fullmatch(r'[A-Za-z]:\\', args.temp.anchor) is not None,
            '--temp must be a new absolute path on a local DOS drive')
    require(api.get_drive(args.temp.anchor) == 3, '--temp must be on a local fixed drive')
    args.temp.mkdir(parents=False, exist_ok=False)
    require(args.temp == args.temp.resolve(), '--temp must use the canonical local path')

    def case(kind, index, exercise):
        directory = args.temp / f'{len(report["cases"]):03d}-{kind}'
        row = {'kind': kind, 'iteration': index, 'directory': str(directory)}
        report['cases'].append(row)
        try:
            directory.mkdir()
            exercise(row, directory / 'only-synthetic.bin')
        except Exception as exc:
            row['diagnostic_error'] = error_data(exc)
            row['traceback'] = traceback.format_exc()

    for index in range(args.iterations):
        kinds = ('same-size', 'restored-mtime') if index % 2 == 0 else ('restored-mtime', 'same-size')
        for kind in kinds:
            case(kind, index, lambda row, path: exact_case(row, api, native, path, kind))
    for index in range(min(args.iterations, 4)):
        for kind in ('same-size', 'restored-mtime'):
            case('marker-' + kind, index, lambda row, path: exact_case(row, api, native, path, kind, marker=True))
        case('writer-phases', index, lambda row, path: phased_case(row, api, native, path))
    case('unchanged', 0, lambda row, path: exact_case(row, api, native, path, 'unchanged'))
    case('replace', 0, lambda row, path: replacement_case(row, api, native, path, keep_original=False))
    case('rename-replace', 0, lambda row, path: replacement_case(row, api, native, path, keep_original=True))
    case('explicit-native-metadata-rollback', 0, lambda row, path: rollback_case(row, api, native, path))
    case('output-lease', 0, lambda row, path: lease_case(row, api, native, acquire_output_lease, path))

    report['summary'] = {}
    for kind in sorted({row['kind'] for row in report['cases']}):
        group = [row for row in report['cases'] if row['kind'] == kind]
        report['summary'][kind] = dict(Counter(
            'diagnostic_error' if 'diagnostic_error' in row else
            'same_material_true' if row.get('same_material') is True else
            'same_material_false' if row.get('same_material') is False else 'recorded'
            for row in group))
        report['summary'][kind]['byte_collisions'] = sum(row.get('data_collision', False) for row in group)
    return int(any('diagnostic_error' in row for row in report['cases']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp', type=Path, required=True, help='new absolute folder on the local fixed NTFS volume')
    parser.add_argument('--output', type=Path, required=True, help='absolute path of the JSON result')
    parser.add_argument('--iterations', type=int, default=12, help='repeat count per ordinary mutation case')
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error('--output must be absolute')
    report = {'schema': 1, 'cases': []}
    try:
        code = run(args, report)
    except Exception as exc:
        code = 1
        report.update(fatal_error=error_data(exc), traceback=traceback.format_exc())
    report['exit_code'] = code
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=serializable) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(args.output), 'exit_code': code, 'summary': report.get('summary')}, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
