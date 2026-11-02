import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audio_adoption_fixtures import mp3_samples, copy_audio


def test_windows_stderr_quota_refuses_large_real_producer(monkeypatch, windows_transport):
    """Real bounded CPython producer, not evidence of FFmpeg output volume."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    import tempfile
    api = importlib.import_module('audio_library_organizer.audio.identity')
    temporary_sizes = []
    actual = tempfile.TemporaryFile
    @contextmanager
    def observed_tempfile(*args, **kwargs):
        with actual(*args, **kwargs) as stream:
            try:
                yield stream
            finally:
                temporary_sizes.append(os.fstat(stream.fileno()).st_size)
    # Keep the old path observable too: this same test must fail before the fix.
    monkeypatch.setattr(api, 'tempfile', SimpleNamespace(TemporaryFile=observed_tempfile), raising=False)
    processes = []
    popen = subprocess.Popen
    def observed_process(*args, **kwargs):
        p = popen(*args, **kwargs); processes.append(p); return p
    monkeypatch.setattr(api, 'subprocess', SimpleNamespace(Popen=observed_process,
        DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    with pytest.raises(ValueError) as error:
        api._decode_windows([sys.executable, '-I', '-c',
            'import os;os.write(2,b"E"*(2*1024*1024))'], lambda: False)
    evidence = {'producer': 'controlled CPython, NOT FFmpeg', 'offered_bytes': 2097152,
        'temporary_stderr_bytes': temporary_sizes, 'error': str(error.value),
        'reaped': all(p.poll() is not None for p in processes)}
    print(json.dumps(evidence))
    folder = os.environ.get('ALO_62D_EVIDENCE')
    if folder:
        (Path(folder)/'stderr-quota.json').write_text(json.dumps(evidence, indent=2))
    assert evidence['reaped'] and processes
    assert 'stderr exceeded 65536-byte transport limit' in str(error.value)
    assert temporary_sizes == [], 'No stderr disk spool is permitted'


@pytest.fixture
def windows_transport(monkeypatch):
    """Linux tests model only the availability query, using a real POSIX pipe.

    On Windows no adapter is installed: actual PeekNamedPipe runs unchanged.
    """
    api = importlib.import_module('audio_library_organizer.audio.identity')
    if os.name != 'nt':
        import array, fcntl, termios
        def probe(stream):
            def available():
                count = array.array('i', [0])
                fcntl.ioctl(stream.fileno(), termios.FIONREAD, count, True)
                return count[0]
            return available
        monkeypatch.setattr(api, '_windows_stderr_probe', probe)
    return api


def identity(path, **kwargs):
    name = 'audio_library_organizer.audio.identity'
    assert importlib.util.find_spec(name) is not None, 'Missing versioned audio identity contract'
    api = importlib.import_module(name)
    return api.inspect_audio(path, **kwargs)


@pytest.mark.parametrize('version', [3, 4])
def test_tag_and_cover_changes_keep_audio_identity(tmp_path, mp3_samples, version):
    source = copy_audio(mp3_samples['original'], tmp_path/'source.mp3')
    target = copy_audio(source, tmp_path/'target.mp3', title='Changed tags', cover=True, id3_version=version)
    before, after = identity(source), identity(target)
    assert before.status == after.status == 'VALID'
    assert before.full_sha256 != after.full_sha256
    assert before.audio_digest == after.audio_digest
    assert before.algorithm == after.algorithm == 'mp3-layer3-frames-sha256/v1'
    assert after.tag_snapshot['title'] == 'Changed tags'
    assert after.tag_snapshot['cover_sha256']


def test_changed_audio_and_tail_with_same_filename_are_rejected(tmp_path, mp3_samples):
    a = copy_audio(mp3_samples['original'], tmp_path/'a'/'same.mp3')
    b = copy_audio(mp3_samples['different_tail'], tmp_path/'b'/'same.mp3')
    assert identity(a).audio_digest != identity(b).audio_digest


def test_identical_copies_have_same_audio_digest_but_not_ownership(tmp_path, mp3_samples):
    a = copy_audio(mp3_samples['original'], tmp_path/'a.mp3')
    b = copy_audio(a, tmp_path/'b.mp3')
    left, right = identity(a), identity(b)
    assert left.status == right.status == 'VALID'
    assert left.audio_digest == right.audio_digest
    assert left.full_sha256 == right.full_sha256 == hashlib.sha256(a.read_bytes()).hexdigest()
    assert left.stat_identity != right.stat_identity
    assert not hasattr(left, 'owner_track_id')


@pytest.mark.parametrize('cut', [1, 137, 418, 16000])
def test_truncated_mp3_never_has_valid_audio_identity(tmp_path, mp3_samples, cut):
    path = tmp_path/'truncated.mp3'
    path.write_bytes(mp3_samples['original'].read_bytes()[:-cut])
    result = identity(path)
    assert result.status == 'ERROR'
    assert result.audio_digest is None


def test_corrupted_mp3_is_error(tmp_path):
    path = tmp_path/'broken.mp3'; path.write_bytes(b'not an MP3 stream')
    result = identity(path)
    assert result.status == 'ERROR' and result.audio_digest is None


def test_missing_decoder_never_claims_validation(tmp_path, mp3_samples):
    result = identity(mp3_samples['original'], decoder=tmp_path/'no-decoder')
    assert result.status == 'UNAVAILABLE' and result.audio_digest is None


def test_other_format_is_explicitly_unsupported(tmp_path):
    path = tmp_path/'other.flac'; path.write_bytes(b'fLaC')
    result = identity(path)
    assert result.status == 'UNSUPPORTED' and result.audio_digest is None


def test_cancelled_identity_is_not_a_proof(mp3_samples):
    result = identity(mp3_samples['original'], cancelled=lambda: True)
    assert result.status == 'CANCELLED' and result.audio_digest is None


def test_identity_is_read_only_and_deterministic(mp3_samples):
    path = mp3_samples['original']; before = path.read_bytes(); stat = path.stat()
    a, b = identity(path), identity(path)
    assert a.audio_digest == b.audio_digest and a.full_sha256 == b.full_sha256
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stat.st_mtime_ns


def test_failed_tag_analysis_is_error_not_a_partial_proof(mp3_samples,monkeypatch):
    api=importlib.import_module('audio_library_organizer.audio.identity')
    from mutagen import MutagenError
    def unavailable(*args,**kwargs):
        raise MutagenError('ID3 analysis unavailable')
    monkeypatch.setattr(api,'ID3',unavailable)
    result=identity(mp3_samples['original'])
    assert result.status=='ERROR' and result.audio_digest is None


def _observed_spawn(api, monkeypatch):
    """Keep real children for assertions; never replace process behavior."""
    from types import SimpleNamespace
    processes = []
    actual = subprocess.Popen
    def spawn(*args, **kwargs):
        p = actual(*args, **kwargs); processes.append(p); return p
    monkeypatch.setattr(api, 'subprocess', SimpleNamespace(Popen=spawn,
        DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    return processes


def test_windows_decode_transport_uses_real_ffmpeg_and_preserves_source(mp3_samples, monkeypatch, windows_transport):
    import shutil
    api = windows_transport
    path = mp3_samples['original']; before = path.read_bytes()
    processes = _observed_spawn(api, monkeypatch)
    api._decode_windows([shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path), '-f', 'null', '-'], lambda: False)
    assert path.read_bytes() == before and processes
    assert all(p.poll() == 0 and p.stderr.closed for p in processes)


@pytest.mark.parametrize('mode', ['stderr', 'cancel', 'timeout', 'spawn-error', 'probe-error'])
def test_windows_decode_transport_failure_reaps_and_closes(monkeypatch, mode):
    """Negative protocol models, separately labelled from real process tests."""
    from types import SimpleNamespace
    import io
    api = importlib.import_module('audio_library_organizer.audio.identity')
    events = []; streams = []
    class Process:
        returncode = None
        stderr = None
        def poll(self): return self.returncode
        def kill(self): events.append('kill'); self.returncode = -1
        def wait(self, timeout=None):
            events.append(('wait', timeout)); self.returncode = 0
        def communicate(self, *a, **kw): raise AssertionError('No Windows reader threads')
    def popen(command, *, stdout, stderr, bufsize):
        events.append('spawn')
        assert stdout is subprocess.DEVNULL and stderr is subprocess.PIPE and bufsize == 0
        if mode == 'spawn-error': raise FileNotFoundError('synthetic spawn refusal')
        p = Process(); p.stderr = io.BytesIO(); streams.append(p.stderr); return p
    reads = []
    def probe(stream):
        if mode == 'probe-error': raise OSError('synthetic Peek failure')
        return lambda: 1 if mode == 'stderr' and not reads else 0
    def read(fd, size): reads.append(size); return b'X'
    # BytesIO has no fileno, so only the model supplies a dummy descriptor.
    class Pipe(io.BytesIO):
        def fileno(self): return 123
    def model_popen(*a, **kw):
        p = popen(*a, **kw); p.stderr.close(); p.stderr = Pipe(); streams.append(p.stderr); return p
    monkeypatch.setattr(api, 'subprocess', SimpleNamespace(Popen=model_popen,
        DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(api, '_windows_stderr_probe', probe)
    monkeypatch.setattr(api, 'os', SimpleNamespace(read=read))
    calls = []
    def clock(): calls.append(None); return 0 if len(calls) == 1 else 121
    if mode == 'timeout': monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=clock))
    expected = {'stderr': ValueError, 'cancel': InterruptedError, 'timeout': TimeoutError,
        'spawn-error': FileNotFoundError, 'probe-error': OSError}[mode]
    with pytest.raises(expected) as error:
        api._decode_windows(['synthetic-negative-model'], lambda: mode == 'cancel')
    assert all(stream.closed for stream in streams)
    if mode in ('cancel', 'timeout', 'probe-error'):
        assert events.count('kill') == 1 and ('wait', None) in events
    if mode == 'stderr': assert str(error.value) == 'Full MP3 decoding failed: X'
    if mode == 'probe-error': assert 'stderr transport failed' in str(error.value)


@pytest.mark.parametrize('stop', ['cancel', 'deadline'])
def test_windows_decode_transport_reaps_real_child_on_stop(mp3_samples, monkeypatch, stop, windows_transport):
    import shutil
    api = windows_transport; processes = _observed_spawn(api, monkeypatch)
    if stop == 'deadline': monkeypatch.setattr(api, 'DECODE_SECONDS', -1.0)
    path = mp3_samples['original']; before = path.read_bytes()
    with pytest.raises(InterruptedError if stop == 'cancel' else TimeoutError):
        api._decode_windows([shutil.which('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(path), '-f', 'null', '-'], lambda: stop == 'cancel')
    assert processes and all(p.poll() is not None and p.stderr.closed for p in processes)
    assert path.read_bytes() == before


@pytest.mark.parametrize('mode', ['empty', 'small', 'limit', 'overflow', 'continuous', 'closed-stderr', 'exit-error'])
def test_windows_stderr_real_stream_boundaries(monkeypatch, windows_transport, mode):
    """Real synthetic producer, never represented as the FFmpeg decoder."""
    api = windows_transport; processes = _observed_spawn(api, monkeypatch)
    code = {
        'empty': 'pass', 'small': 'import os;os.write(2,b"small diagnostic")',
        'limit': 'import os;os.write(2,b"X"*65536)',
        'overflow': 'import os;os.write(2,b"X"*65537)',
        'continuous': 'import os\nwhile True: os.write(2,b"X"*4096)',
        'closed-stderr': 'import os;os.close(2)',
        'exit-error': 'raise SystemExit(7)',
    }[mode]
    reads = []; actual = os.read
    from types import SimpleNamespace
    def read(fd, count):
        b = actual(fd, count); reads.append((count, len(b))); return b
    monkeypatch.setattr(api, 'os', SimpleNamespace(read=read))
    if mode in ('empty', 'closed-stderr'):
        api._decode_windows([sys.executable, '-I', '-c', code], lambda: False)
    else:
        with pytest.raises(ValueError) as error:
            api._decode_windows([sys.executable, '-I', '-c', code], lambda: False)
        message = str(error.value)
        if mode in ('overflow', 'continuous'):
            assert message == 'Decoder stderr exceeded 65536-byte transport limit.'
            assert sum(n for _, n in reads) == 65537
        else:
            assert message.startswith('Full MP3 decoding failed: ')
        if mode == 'small': assert message.endswith('small diagnostic')
        if mode == 'limit': assert message == 'Full MP3 decoding failed: ' + 'X'*4096
    assert all(count <= 4096 for count, _ in reads)
    assert sum(n for _, n in reads) <= 65537
    assert processes and all(p.poll() is not None and p.stderr.closed for p in processes)


@pytest.mark.parametrize('failure', ['cancel', 'timeout', 'read', 'peek'])
def test_windows_stderr_active_child_is_reaped(monkeypatch, windows_transport, failure):
    from types import SimpleNamespace
    api = windows_transport; processes = _observed_spawn(api, monkeypatch)
    actual_read = os.read; actual_probe = api._windows_stderr_probe
    read_seen = []
    def read(fd, count):
        if failure == 'read': raise OSError('injected read I/O refusal')
        b = actual_read(fd, count); read_seen.append(len(b)); return b
    def probe(stream):
        peek = actual_probe(stream)
        def available():
            count = peek()
            if count and failure == 'peek': raise OSError('injected PeekNamedPipe refusal')
            return count
        return available
    monkeypatch.setattr(api, 'os', SimpleNamespace(read=read))
    monkeypatch.setattr(api, '_windows_stderr_probe', probe)
    if failure == 'timeout':
        monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda: 121.0 if read_seen else 0.0))
    expected = InterruptedError if failure == 'cancel' else TimeoutError if failure == 'timeout' else OSError
    with pytest.raises(expected) as error:
        api._decode_windows([sys.executable, '-I', '-c', 'import os;os.write(2,b"ready")\nwhile True: pass'],
            lambda: failure == 'cancel' and bool(read_seen))
    if failure in ('read', 'peek'): assert 'stderr transport failed' in str(error.value)
    else: assert read_seen, 'Stop must occur during real work, after observed input'
    assert processes and all(p.poll() is not None and p.stderr.closed for p in processes)


def test_windows_stderr_closed_before_child_exit_keeps_deadline(monkeypatch):
    """EOF alone is not successful process completion; deterministic protocol."""
    from types import SimpleNamespace
    import io
    api = importlib.import_module('audio_library_organizer.audio.identity')
    events = []
    class Process:
        returncode = None
        stderr = io.BytesIO()
        def poll(self): return self.returncode
        def wait(self, timeout=None):
            events.append(('wait', timeout))
            if timeout is not None: raise subprocess.TimeoutExpired('model', timeout)
            return self.returncode
        def kill(self): events.append('kill'); self.returncode = -1
    process = Process(); times = iter([0.0, 0.0, 121.0])
    monkeypatch.setattr(api, 'subprocess', SimpleNamespace(Popen=lambda *a, **kw: process,
        DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(api, '_windows_stderr_probe', lambda stream: lambda: 0)
    monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda: next(times)))
    with pytest.raises(TimeoutError): api._decode_windows(['model'], lambda: False)
    assert events == [('wait', 0.1), 'kill', ('wait', None)] and process.stderr.closed


def test_windows_stderr_exit_between_probe_and_poll_is_not_lost(monkeypatch):
    """Child writes and exits after an empty peek but before poll returns."""
    from types import SimpleNamespace
    import io
    api = importlib.import_module('audio_library_organizer.audio.identity')
    state = {'exited': False, 'read': False}
    class Pipe(io.BytesIO):
        def fileno(self): return 123
    class Process:
        returncode = None
        stderr = Pipe()
        def poll(self):
            state['exited'] = True; self.returncode = 0; return 0
        def wait(self, timeout=None): return 0
        def kill(self): raise AssertionError('Already exited')
    p = Process()
    def read(fd, count): state['read'] = True; return b'X'
    monkeypatch.setattr(api, 'subprocess', SimpleNamespace(Popen=lambda *a, **kw: p,
        DEVNULL=subprocess.DEVNULL, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired))
    monkeypatch.setattr(api, '_windows_stderr_probe', lambda stream:
        lambda: int(state['exited'] and not state['read']))
    monkeypatch.setattr(api, 'os', SimpleNamespace(read=read))
    with pytest.raises(ValueError, match='Full MP3 decoding failed: X'):
        api._decode_windows(['model'], lambda: False)
    assert state['read'] and p.stderr.closed
