"""Portable contract tests of the Windows adapter, not native Windows PASS."""
import ctypes
from types import SimpleNamespace
import pytest

from audio_library_organizer.jobs import shell_reveal


def native_api(monkeypatch, *, init=0, parse=0, select=0, null=False):
    calls = []
    class Function:
        def __init__(self, name, callback):
            self.name, self.callback = name, callback
        def __call__(self, *args):
            calls.append((self.name, args))
            return self.callback(*args)
    def parse_path(name, context, output, attributes, result):
        if not null:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = 12345
        return parse
    shell = SimpleNamespace(SHParseDisplayName=Function('parse', parse_path),
                            SHOpenFolderAndSelectItems=Function('select', lambda *a: select))
    ole = SimpleNamespace(CoInitializeEx=Function('init', lambda *a: init),
                          CoUninitialize=Function('uninit', lambda: None),
                          CoTaskMemFree=Function('free', lambda *a: None))
    def load(name, *, winmode):
        assert winmode == 0x800
        assert name in ('shell32.dll', 'ole32.dll')
        return shell if name == 'shell32.dll' else ole
    monkeypatch.setattr(ctypes, 'WinDLL', load, raising=False)
    return calls


def test_exact_unicode_file_selected_without_command_line(monkeypatch):
    calls = native_api(monkeypatch)
    guards = []
    name = r'C:\synthetic\Muzyka, test & demo\Utwór (1).mp3'
    shell_reveal.reveal_file(name, guard=lambda: guards.append(True))
    assert len(guards) == 2
    assert next(args[0] for call, args in calls if call == 'parse') == name
    selected = next(args for call, args in calls if call == 'select')
    assert selected[0].value == 12345 and selected[1:] == (0, None, 0)
    assert [name for name, _ in calls] == ['init', 'parse', 'select', 'free', 'uninit']


@pytest.mark.parametrize('failure', ['init', 'parse', 'null', 'select', 'guard'])
def test_failure_is_not_success_and_native_resources_are_released(monkeypatch, failure):
    calls = native_api(monkeypatch, init=-1 if failure == 'init' else 1,
                       parse=-1 if failure == 'parse' else 0,
                       select=-1 if failure == 'select' else 0, null=failure == 'null')
    count = 0
    def guard():
        nonlocal count
        count += 1
        if count == 2 and failure == 'guard':
            raise InterruptedError('Synthetic context was cancelled')
    with pytest.raises(OSError):
        shell_reveal.reveal_file(r'C:\synthetic\one.mp3', guard=guard)
    names = [name for name, _ in calls]
    if failure != 'select':
        assert 'select' not in names
    if failure != 'init':
        assert names[-1] == 'uninit'
        assert ('free' in names) == (failure != 'null')


@pytest.mark.parametrize('path', ['', 'one.mp3', r'\relative.mp3', 'shell:Downloads', 'C:\\bad\x00.mp3'])
def test_non_absolute_or_invalid_path_refused_before_native_calls(monkeypatch, path):
    calls = native_api(monkeypatch)
    with pytest.raises(ValueError):
        shell_reveal.reveal_file(path, guard=lambda: None)
    assert calls == []
