"""Add the external observer to sys.path without touching measured files."""
import sys
from pathlib import Path
root, diagnostics, *arguments = sys.argv[1:]
sys.path[:0] = [str(Path(root)/'src'), diagnostics]
import pytest
raise SystemExit(pytest.main(arguments))
