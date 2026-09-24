# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = []

for package in ('librosa', 'soundfile'):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden


assets = project_root / 'src' / 'audio_library_organizer' / 'assets'
if assets.exists():
    datas += [(str(path), r'audio_library_organizer\assets') for path in assets.iterdir() if path.is_file()]

chromaprint = project_root / 'tools' / 'chromaprint'
if chromaprint.exists():
    datas += [(str(path), r'tools\chromaprint') for path in chromaprint.iterdir() if path.is_file()]

analysis = Analysis(
    ['src/audio_library_organizer/__main__.py'],
    pathex=[str(project_root / 'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name='ALO-Music',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project_root / 'src' / 'audio_library_organizer' / 'assets' / 'alo.ico'),
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name='ALO-Music',
)
