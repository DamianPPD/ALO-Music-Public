"""Observe the existing restart subprocess and retain evidence on timeout."""

import json
import os
from pathlib import Path
import subprocess
import threading
import time

import pytest

TARGETS = {'test_unchanged_ape_binary_tag_adoption_survives_main_window_restart',
           'test_id3_restart_compatible_with_both_trees'}


def record(directory, stage, **detail):
    with (directory / 'parent.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'stage': stage, 'monotonic_ns': time.monotonic_ns(),
                                 'pid': os.getpid(), 'thread': threading.get_ident(), **detail}) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def output(directory, name, value):
    if value is not None:
        value = value.encode('utf-8', errors='replace') if isinstance(value, str) else value
        (directory / name).write_bytes(value)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    if item.originalname not in TARGETS:
        return (yield)
    directory = Path(os.environ['ALO_TIMEOUT_ATTEMPT'])
    directory.mkdir(parents=True, exist_ok=True)
    original_run, original_popen = subprocess.run, subprocess.Popen

    class ObservedProcess(original_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            record(directory, 'child-spawned', child_pid=self.pid)

        def communicate(self, *args, **kwargs):
            try:
                return super().communicate(*args, **kwargs)
            except subprocess.TimeoutExpired as exc:
                record(directory, 'communicate-timeout', child_pid=self.pid,
                       child_poll=self.poll(), timeout=exc.timeout)
                output(directory, 'partial-stdout.txt', exc.stdout)
                output(directory, 'partial-stderr.txt', exc.stderr)
                subprocess.Popen = original_popen
                try:
                    from native_dump import collect
                    collect(self.pid, directory)
                finally:
                    subprocess.Popen = ObservedProcess
                raise

        def kill(self):
            record(directory, 'child-kill', child_pid=self.pid, child_poll=self.poll())
            return super().kill()

    def run(command, *args, **kwargs):
        if not (isinstance(command, list) and len(command) == 5 and command[1] == '-c'
                and 'window.review_btn.click()' in command[2] and command[-1] == 'gui'):
            return original_run(command, *args, **kwargs)
        assert kwargs['timeout'] == 45 and kwargs['capture_output'] and kwargs['text']
        tracing = os.environ.get('ALO_TRACE_CHILD') == '1'
        record(directory, 'restart-start', tracing=tracing, timeout=45)
        if tracing:
            env = kwargs['env'].copy()
            env['PYTHONPATH'] = os.pathsep.join((str(Path(__file__).parent), env['PYTHONPATH']))
            env['ALO_RESTART_TRACE_DIR'] = str(directory)
            env['ALO_RESTART_CHILD_SCRIPT'] = os.environ['ALO_EXACT_CHILD_SCRIPT']
            kwargs['env'] = env
        subprocess.Popen = ObservedProcess
        try:
            result = original_run(command, *args, **kwargs)
        except subprocess.TimeoutExpired as exc:
            output(directory, 'final-stdout.txt', exc.stdout)
            output(directory, 'final-stderr.txt', exc.stderr)
            record(directory, 'restart-end', result='TIMEOUT')
            raise
        else:
            output(directory, 'final-stdout.txt', result.stdout)
            output(directory, 'final-stderr.txt', result.stderr)
            record(directory, 'restart-end', result='EXIT', returncode=result.returncode)
            return result
        finally:
            subprocess.Popen = original_popen

    subprocess.run = run
    try:
        return (yield)
    finally:
        subprocess.run = original_run
