"""Real filesystem prerequisites for alias tests; never replace an alias by a file."""
from pathlib import Path
import sys
import tempfile

import pytest


def require_symlink(parent, *, directory=False):
    """Probe the same volume before a fixture unlinks or renames owned data.

    Only Windows' explicit missing-privilege error is an unavailable capability.
    Such a skip is unverified security coverage, not a passing protection test.
    Other errors remain failures, including unexpected failures after this probe.
    """
    with tempfile.TemporaryDirectory(prefix='symlink-capability-', dir=parent) as name:
        root = Path(name)
        target, link = root / 'target', root / 'link'
        if directory:
            target.mkdir()
        else:
            target.write_bytes(b'synthetic capability probe')
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as error:
            if sys.platform == 'win32' and getattr(error, 'winerror', None) == 1314:
                pytest.skip('UNVERIFIED: Windows denies symlink creation (WinError 1314); '
                            'this alias protection requires the missing capability.')
            raise
        assert link.is_symlink() and link.resolve() == target.resolve()


def replace_directory_with_symlink(directory, held):
    """Fixture-only swap: restore the real database directory if setup fails."""
    directory.rename(held)
    try:
        directory.symlink_to(held, target_is_directory=True)
    except BaseException:
        held.rename(directory)
        raise
