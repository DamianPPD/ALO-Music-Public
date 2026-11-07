"""Same restart program with ordinary MP3s supported by both trees."""

import json
import os
from pathlib import Path
import subprocess
import sys

from audio_adoption_fixtures import mp3_samples
from test_adopted_output_spec_v0427 import approve
from test_legacy_adoption_v0427 import library


def test_id3_restart_compatible_with_both_trees(library):
    repo, root, track, output = library
    binding = approve(library)
    before = track.path.read_bytes(), output.read_bytes(), repo.list_managed_bindings()
    script = Path(os.environ['ALO_EXACT_CHILD_SCRIPT']).read_text(encoding='utf-8')
    result = subprocess.run([sys.executable, '-c', script, str(root), 'gui'],
                            capture_output=True, text=True, timeout=45,
                            env={'QT_QPA_PLATFORM': 'offscreen', **os.environ,
                                 'PYTHONPATH': str(Path.cwd() / 'src')})
    assert result.returncode == 0, (result.stdout, result.stderr)
    value = json.loads(result.stdout)
    assert value['pid'] != os.getpid()
    assert value['reason'] == 'CONFIRMED_FIELD_DIFFERENCE' and value['confirmed'] is True
    assert (value['library_id'], value['track_id'], value['binding_id']) == (
        binding.library_id, binding.track_id, binding.binding_id)
    assert (track.path.read_bytes(), output.read_bytes(), repo.list_managed_bindings()) == before
