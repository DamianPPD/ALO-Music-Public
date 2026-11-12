"""Capture only after the original timeout has already expired."""
import json
import os
from pathlib import Path
import subprocess
import time

def collect(pid, directory):
    started = time.monotonic()
    result = {'pid': pid, 'collection_started_after_timeout': True}
    dump = directory / f'hung-{pid}.dmp'
    procdump = os.environ.get('ALO_PROCDUMP_EXE')
    if procdump:
        try:
            with (directory / 'procdump.log').open('wb') as log:
                p = subprocess.run([procdump, '-accepteula', '-mm', str(pid), str(dump)],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=35)
            result['procdump_exit'] = p.returncode
        except Exception as exc:
            result['procdump_error'] = repr(exc)
    result['dump_exists'] = dump.exists()
    result['capture_seconds'] = time.monotonic() - started
    (directory / 'native-capture.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

def analyze(directory):
    cdb = os.environ.get('ALO_CDB_EXE')
    if not cdb:
        return
    for dump in directory.glob('hung-*.dmp'):
        symbols = os.environ.get('ALO_PYTHON_PDB_DIR','')
        symbols += ';srv*' + str(directory / 'symbols') + '*https://msdl.microsoft.com/download/symbols'
        command = '.symopt+ 0x10000000; .reload; ~*kp; !locks; !runaway; lmv; q'
        try:
            with dump.with_suffix('.cdb.log').open('wb') as log:
                r = subprocess.run([cdb, '-z', str(dump), '-y', symbols, '-c', command],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=150)
            result = {'exit_code':r.returncode}
        except Exception as exc:
            result = {'error':repr(exc)}
        dump.with_suffix('.analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
