"""Only the pinned wheel's RECORD-verified Windows executable; no fallback."""
import base64
import hashlib
from pathlib import Path
import shutil
from support import native_identity

def copy_bundled_ffmpeg(distribution,destination,venv):
    if distribution.version!='0.6.0':raise ValueError('Unexpected imageio-ffmpeg version')
    candidates=[f for f in distribution.files or [] if str(f).startswith('imageio_ffmpeg/binaries/') and str(f).endswith('.exe')]
    if len(candidates)!=1:raise ValueError('Expected one bundled Windows ffmpeg executable')
    item=candidates[0];source=Path(distribution.locate_file(item))
    if source.is_symlink() or not source.resolve().is_relative_to(Path(venv).resolve()):raise ValueError('Decoder outside fresh venv')
    source=source.resolve()
    content=source.read_bytes();digest=hashlib.sha256(content).digest()
    if item.hash is None or item.hash.mode!='sha256' or item.size!=len(content) or \
       base64.urlsafe_b64encode(digest).rstrip(b'=').decode()!=item.hash.value:
        raise ValueError('Bundled decoder RECORD mismatch')
    identity=native_identity(source)
    if identity.get('pe',{}).get('machine')!='0x8664':raise ValueError('Decoder is not AMD64 PE')
    destination=Path(destination).resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
    copied=native_identity(destination)
    if copied['sha256']!=identity['sha256']:raise ValueError('Copied decoder SHA mismatch')
    return dict(distribution='imageio-ffmpeg',version=distribution.version,RECORD_verified=True,source=identity,selected=copied)
