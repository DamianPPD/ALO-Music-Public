"""Reproduce the published manual_input failure with the measured Win/CPython stat shape."""
import os
from pathlib import Path
import platform
import tempfile
from types import SimpleNamespace
import traceback
from unittest.mock import patch

from PIL import Image

from audio_library_organizer.jobs import created_output

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'unchanged.png'
    Image.new('RGB', (12, 12), (255, 0, 0)).save(path)
    before = path.read_bytes()
    use_native = os.name == 'nt'
    if use_native:
        original = path.stat()
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
    path_stat = path.stat()
    real_fstat = os.fstat
    print('Python:', platform.python_version())

    class ObservedOS:
        def __getattr__(self, name):
            return getattr(os, name)

        def fstat(self, fd):
            stat = real_fstat(fd)
            fields = {name: getattr(stat, name) for name in dir(stat) if name.startswith('st_')}
            if not use_native:
                # Reproduce the previously measured Windows ChangeTime / CreationTime split.
                fields['st_birthtime_ns'] = path_stat.st_ctime_ns
                fields['st_ctime_ns'] = path_stat.st_ctime_ns + 50_795_100
            print('fd token:', created_output.stat_identity(SimpleNamespace(**fields)))
            return SimpleNamespace(**fields)

    print('mode:', 'native Windows' if use_native else 'Linux, measured Windows ctime split modeled')
    print('path token:', created_output.stat_identity(path_stat))
    try:
        with patch.object(created_output, 'os', ObservedOS()):
            print('manual_input:', created_output.ProducerOperation.manual_input(
                SimpleNamespace(manual_cover_path=str(path))))
    except ValueError as exc:
        if str(exc) != 'Manual cover changed while reading.':
            raise
        traceback.print_exc()
    assert before == path.read_bytes()
    print('cover bytes unchanged:', len(before))
