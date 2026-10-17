"""Pinned Qt6.10.3 native checks on real Windows; no emulation/offscreen acceptance."""
from importlib import metadata
from pathlib import Path
import sys

def check_native(catalog_path=None,catalog_sha=None,*,output=None):
    from private_runtime import verify_private_runtime
    from windows_modules import loaded_paths
    from native_provenance import installed_native_paths,path_problem,verify_installed_record,RUNTIME_NAMES,runtime_record_valid
    from runtime_catalog import make_catalog,read_catalog
    runtime=verify_private_runtime()
    from PIL import Image
    import charset_normalizer
    if catalog_path is None:
        identities=make_catalog(loaded_paths(),Path(output))
    else:identities=read_catalog(catalog_path,catalog_sha)
    from PySide6 import QtCore,QtGui,QtWidgets,QtMultimedia,QtNetwork
    import numpy,soundfile
    if QtCore.qVersion()!='6.10.3':raise ValueError('Wrong native Qt version')
    for name in ('PySide6','PySide6-Essentials','PySide6-Addons','shiboken6'):
        if metadata.version(name)!='6.10.3':raise ValueError('Wrong binding version')
    installed=installed_native_paths();loaded=loaded_paths()
    native=verify_installed_record()
    problem=path_problem(loaded,installed,sys.prefix,identities)
    if problem:raise ValueError(problem)
    for raw in loaded:
        path=Path(raw).resolve()
        if path.name.lower()in RUNTIME_NAMES and path not in installed and not runtime_record_valid(identities.get(str(path)),path):
            raise ValueError('Missing exact external CRT identity: '+str(path))
    return dict(status='PASS',private_runtime=runtime,Qt=QtCore.qVersion(),RECORD_native=native,
        loaded_native_modules=loaded,runtime_catalog=str(catalog_path or Path(output)/'trusted-runtime-catalog.json'))

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from contract import write_json
    if sys.platform!='win32':raise SystemExit('STOP: Windows native preflight NOT RUN')
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    write_json(output/'native.json',check_native(output=output))
