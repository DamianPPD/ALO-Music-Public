import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from time import monotonic

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import soundfile as sf
import pytest

from audio_library_organizer.ui import waveform


def test_waveform_never_opens_native_decoder_in_gui_process(tmp_path, monkeypatch):
    path = tmp_path / 'levels.wav'
    sf.write(path, np.repeat([0.0, 0.25, -0.5, 1.0], 100), 8000, subtype='FLOAT')

    def forbidden(*args, **kwargs):
        raise AssertionError('SoundFile.read must be isolated from the GUI process')

    monkeypatch.setattr(sf, 'SoundFile', forbidden)
    assert waveform.read_waveform(path, bins=4) == [0.0, 0.25, 0.5, 1.0]


def test_cancelled_waveform_never_enters_native_decoder(tmp_path, monkeypatch):
    path = tmp_path / 'cancelled.wav'
    sf.write(path, np.zeros(400), 8000)
    cancel = Event()
    cancel.set()
    calls = []
    original = sf.SoundFile

    def opened(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(sf, 'SoundFile', opened)
    assert waveform.read_waveform(path, cancel=cancel) == []
    assert calls == []


def _native_crash_command(*arguments):
    # A real native fault in the child, rather than a caught Python exception.
    code = ('import ctypes, sys; '
            'exec("if sys.platform != \'win32\':\\n import resource\\n resource.setrlimit(resource.RLIMIT_CORE, (0, 0))"); '
            'ctypes.string_at(0)')
    return [sys.executable, '-X', 'faulthandler', '-c', code]


def test_native_decoder_access_violation_cannot_kill_caller(tmp_path, monkeypatch, caplog):
    path = tmp_path / 'problematic.mp3'
    path.write_bytes(b'ID3 truncated MP3')
    monkeypatch.setattr(waveform, '_waveform_command', _native_crash_command)
    parent_pid = os.getpid()
    assert waveform.read_waveform(path, generation=17) == []
    assert os.getpid() == parent_pid
    assert 'waveform decoder failed' in caplog.text
    assert 'generation=17' in caplog.text
    assert 'Fatal Python error' in caplog.text or 'Windows fatal exception' in caplog.text


@pytest.mark.parametrize('extension,subtype', [('wav', 'PCM_16'), ('flac', 'PCM_16'), ('mp3', None)])
def test_formats_decode_sequentially_without_gui(tmp_path, extension, subtype):
    path = tmp_path / f'levels.{extension}'
    sf.write(path, np.sin(np.arange(8000) * .1) * .5, 44100, subtype=subtype)
    for _ in range(3):
        peaks = waveform.read_waveform(path, bins=8)
        assert len(peaks) == 8
        assert all(0 <= peak <= 1 for peak in peaks)
        assert max(peaks) > .4


def test_m4a_and_truncated_mp3_have_safe_seek_fallback(tmp_path):
    import shutil
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('No M4A test encoder is available')
    wav = tmp_path / 'source.wav'
    sf.write(wav, np.sin(np.arange(8000) * .1) * .5, 44100)
    m4a = tmp_path / 'source.m4a'
    subprocess.run([ffmpeg, '-v', 'error', '-i', str(wav), '-c:a', 'aac', str(m4a)],
                   check=True, timeout=10)
    result = waveform.read_waveform(m4a, bins=8)
    assert result == [] or len(result) == 8
    broken = tmp_path / 'broken.mp3'
    broken.write_bytes(b'ID3\x04\x00\x00\x00\x00\x00\x7f' + b'\xff\xfb\x90\x00' * 7)
    assert waveform.read_waveform(broken) == []


def test_cancel_kills_and_reaps_decoder_before_next_request(tmp_path, monkeypatch):
    path = tmp_path / 'slow.wav'
    path.write_bytes(b'audio')
    started = tmp_path / 'started'
    cancel = Event()
    processes = []
    original_popen = subprocess.Popen

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(waveform.subprocess, 'Popen', popen)
    monkeypatch.setattr(waveform, '_waveform_command', lambda *args: [
        sys.executable, '-c', 'from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30)', str(started)])
    results = []
    thread = Thread(target=lambda: results.append(waveform.read_waveform(path, cancel=cancel)))
    thread.start()
    deadline = monotonic() + 3
    while not started.exists() and monotonic() < deadline:
        Event().wait(.01)
    assert started.exists()
    cancel.set()
    thread.join(timeout=3)
    assert not thread.is_alive() and results == [[]]
    assert processes[0].poll() is not None


def test_hung_decoder_timeout_is_bounded(tmp_path, monkeypatch):
    path = tmp_path / 'hung.wav'
    path.write_bytes(b'audio')
    monkeypatch.setattr(waveform, '_DECODER_TIMEOUT', .1)
    monkeypatch.setattr(waveform, '_waveform_command', lambda *args: [sys.executable, '-c', 'import time; time.sleep(30)'])
    before = monotonic()
    assert waveform.read_waveform(path) == []
    assert monotonic() - before < 2


def test_worker_entrypoint_decodes_without_starting_gui(tmp_path):
    path = tmp_path / 'levels.wav'
    sf.write(path, np.ones(400) * .5, 8000)
    output, trace = tmp_path / 'peaks.json', tmp_path / 'decoder.log'
    result = subprocess.run([sys.executable, '-m', 'audio_library_organizer', '--waveform-worker',
                             str(path), '4', str(output), str(trace), '21'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    import json
    assert json.loads(output.read_text()) == [.5] * 4
    log = trace.read_text()
    assert 'generation=21' in log and 'audio.read.enter' in log and 'audio.read.leave' in log
    assert 'SoundFile.enter' in log and 'SoundFile.opened' in log


def test_frozen_exe_uses_worker_dispatch_instead_of_starting_another_gui(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    command = waveform._waveform_command(tmp_path / 'a.mp3', 4, tmp_path / 'output', tmp_path / 'trace', 19)
    assert command[:2] == [sys.executable, '--waveform-worker']
    assert command[-1] == '19'


def test_two_requests_never_overlap_native_decoders(tmp_path, monkeypatch):
    slow, next_path = tmp_path / 'slow.wav', tmp_path / 'next.wav'
    slow.write_bytes(b'audio')
    sf.write(next_path, np.ones(400) * .5, 8000)
    started = tmp_path / 'started'
    original_command, original_popen = waveform._waveform_command, subprocess.Popen
    active_at_spawn, processes = [], []

    def command(path, *args):
        if path == slow:
            return [sys.executable, '-c', 'from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30)', str(started)]
        return original_command(path, *args)

    def popen(*args, **kwargs):
        active_at_spawn.append(sum(process.poll() is None for process in processes))
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(waveform, '_waveform_command', command)
    monkeypatch.setattr(waveform.subprocess, 'Popen', popen)
    cancel = Event()
    first_result, last_result = [], []
    first = Thread(target=lambda: first_result.append(waveform.read_waveform(slow, cancel=cancel)))
    last = Thread(target=lambda: last_result.append(waveform.read_waveform(next_path, bins=4)))
    first.start()
    try:
        deadline = monotonic() + 3
        while not started.exists() and monotonic() < deadline:
            Event().wait(.01)
        assert started.exists()
        last.start()
        cancel.set()
        first.join(timeout=3); last.join(timeout=3)
        assert not first.is_alive() and not last.is_alive()
        assert first_result == [[]] and last_result == [[.5] * 4]
        assert active_at_spawn == [0, 0]
        assert all(process.poll() is not None for process in processes)
    finally:
        cancel.set()
        first.join(timeout=3)
