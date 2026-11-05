"""Measure the same bytes and the same native object across both stat APIs."""
from dataclasses import asdict
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image
from audio_library_organizer.jobs import created_output
from audio_library_organizer.safety import windows_file_identity as native

stage = sys.argv[1]
observations = []
with tempfile.TemporaryDirectory() as folder:
    for extension in ('jpg', 'png'):
        path = Path(folder) / ('unchanged.' + extension)
        Image.new('RGB', (12, 12), (255, 0, 0)).save(path)
        original = path.stat()
        original_bytes = path.read_bytes()
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
        path_stat = path.stat()
        proof = native.capture(path)
        with path.open('rb') as stream:
            fd_stat = os.fstat(stream.fileno())
            actual = native._WinAPI().query(msvcrt.get_osfhandle(stream.fileno()))
            assert stream.read() == original_bytes
        assert actual == proof.leaf and actual.filesystem == 'NTFS'
        track = SimpleNamespace(manual_cover_path=str(path), track_id='synthetic',
                                title=extension, artist='Synthetic', path=path)
        error = None
        try:
            result = created_output.ProducerOperation.manual_input(track)
            if stage == 'candidate':
                _, read_bytes = result
                assert read_bytes == original_bytes
        except ValueError as exc:
            error = f'{type(exc).__name__}: {exc}'
            if stage == 'base':
                assert str(exc) == 'Manual cover changed while reading.', error
        assert path.read_bytes() == original_bytes and native.capture(path).leaf == actual
        fields = ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_birthtime_ns', 'st_nlink']
        observations.append(dict(ext=extension, error=error, sha256=hashlib.sha256(original_bytes).hexdigest(),
                                 unchanged=True,
                                 stat={key:getattr(path_stat,key,None) for key in fields},
                                 fstat={key:getattr(fd_stat,key,None) for key in fields},
                                 leaf=asdict(actual)))
out = json.dumps(observations, default=lambda value: value.hex(), indent=2)
(Path(os.environ['ALO_EVIDENCE']) / (stage + '-native-probe.json')).write_text(out, encoding='utf-8')
print(out, flush=True)
if stage == 'candidate':
    assert all(row['error'] is None for row in observations)
