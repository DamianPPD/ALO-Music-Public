"""Native Windows-only builder and relocation check; not a new test suite."""
from pathlib import Path
import concurrent.futures
import ctypes
import hashlib
import html
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ci
import portable_launch as launch

ROOT=ci.ROOT
CONFIG=Path(__file__).resolve().parent
TEMP=Path(os.environ.get('RUNNER_TEMP',ROOT/'portable-temp'))/'alo-portable-build'
OUT=Path(os.environ.get('RUNNER_TEMP',ROOT/'portable-temp'))/'alo-portable-output'
NAME='ALO-Music-6.2D-Windows-TESTY'
INPUTS=[
 {'name':'python-3.11.9-embed-amd64.zip','url':'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip','sha256':'009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b'},
 {'name':'ffmpeg-7.1.tar.xz','url':'https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz','sha256':'40973d44970dbc83ef302b0609f2e74982be2d85916dd2ee7472d30678a7abe6'},
 {'name':'mingw-w64-x86_64-lame-3.100-3-any.pkg.tar.zst','url':'https://repo.msys2.org/mingw/mingw64/mingw-w64-x86_64-lame-3.100-3-any.pkg.tar.zst','sha256':'083e74a93c2fa764c26d73b5a21e2f5055242bc13997d8dbe6a6c2b4577d6b03'},
 {'name':'mingw-w64-lame-3.100-3.src.tar.zst','url':'https://mirror.msys2.org/mingw/sources/mingw-w64-lame-3.100-3.src.tar.zst','sha256':'dfd51143ea25aa0b67f5d355127b8a89a27379b1b128f0b2f9eed7c3327656ab'}]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def download(row,target):
    if not row['url'].startswith('https://'):raise ValueError('HTTPS required')
    with urllib.request.urlopen(row['url'],timeout=120) as response,target.open('wb') as out:shutil.copyfileobj(response,out)
    if launch.digest(target)!=row['sha256']:raise ValueError('Download SHA mismatch: '+target.name)
    return target


def extract_zip(path,target):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        seen=set()
        for item in z.infolist():
            if item.is_dir():continue
            rel=launch.relative(item.filename)
            if item.filename.casefold() in seen or ((item.external_attr>>16)&0o170000)==0o120000:raise ValueError('Duplicate or symlink ZIP entry')
            seen.add(item.filename.casefold());p=target/rel;p.parent.mkdir(parents=True,exist_ok=True)
            data=z.read(item)
            if p.exists() and p.read_bytes()!=data:raise ValueError('Wheel collision: '+str(rel))
            p.write_bytes(data)


def extract_tar(path,target):
    if path.suffix=='.zst':
        seven=Path(os.environ['ProgramFiles'])/'7-Zip/7z.exe'
        raw=subprocess.check_output([seven,'x',path,'-so'])
        source=tarfile.open(fileobj=io.BytesIO(raw))
    else:source=tarfile.open(path)
    with source as t:
        for item in t:
            name=item.name.removeprefix('./').rstrip('/')
            if not name:continue
            rel=launch.relative(name);p=target/rel
            if item.isdir():p.mkdir(parents=True,exist_ok=True)
            elif item.isfile():
                p.parent.mkdir(parents=True,exist_ok=True)
                with t.extractfile(item) as inp,p.open('wb') as out:shutil.copyfileobj(inp,out)
            else:raise ValueError('Unsupported source archive link')


def signatures(files):
    lines=[]
    for p in files:
        literal=str(p).replace("'","''")
        lines.append("$p='"+literal+"';$s=Get-AuthenticodeSignature -LiteralPath $p; $v=(Get-Item -LiteralPath $p).VersionInfo; [pscustomobject]@{path=$p;status=[string]$s.Status;signer=[string]$s.SignerCertificate.Subject;company=$v.CompanyName;version=$v.FileVersion;original=$v.OriginalFilename}")
    powershell=Path(os.environ['ProgramFiles'])/'PowerShell/7/pwsh.exe'
    module=powershell.parent/'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1'
    if not powershell.is_file() or not module.is_file():raise ValueError('Official runner PowerShell7 signature module unavailable')
    module_literal=str(module).replace("'","''")
    command="$ErrorActionPreference='Stop'; Import-Module -Name '"+module_literal+"' -ErrorAction Stop; @("+';'.join(lines)+') | ConvertTo-Json -Depth 4'
    data=json.loads(subprocess.check_output([powershell,'-NoProfile','-NonInteractive','-Command',command],text=True,encoding='utf-8-sig',env=dict(os.environ,PSModulePath=str(powershell.parent/'Modules'))))
    if isinstance(data,dict):data=[data]
    for row in data:
        if row['status']!='Valid':raise ValueError('Invalid native signature: '+row['path'])
    return data


def crt(package):
    vswhere=Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    vs=Path(subprocess.check_output([vswhere,'-latest','-products','*','-property','installationPath'],text=True).strip())
    folders=list((vs/'VC/Redist/MSVC').glob('*/x64/Microsoft.VC143.CRT'))
    if not folders:raise ValueError('Licensed Visual Studio release REDIST unavailable')
    source=max(folders,key=lambda p:tuple(int(x) for x in p.parents[1].name.split('.')))
    names={'concrt140.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','vccorlib140.dll','vcruntime140.dll','vcruntime140_1.dll','vcruntime140_threads.dll'}
    files=[p for p in source.glob('*.dll') if p.name.lower() in names]
    if not {'msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}.issubset({p.name.lower() for p in files}):raise ValueError('Incomplete MSVC release redist')
    rows=signatures(files)
    for row in rows:
        if 'Microsoft' not in row['signer'] or 'Microsoft' not in row['company'] or row['original'].lower()!=Path(row['path']).name.lower():raise ValueError('Unverified MSVC publisher')
        p=Path(row['path']);raw=p.read_bytes();offset=struct.unpack_from('<I',raw,0x3c)[0]
        if raw[offset:offset+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,offset+4)[0]!=0x8664:raise ValueError('MSVC architecture mismatch')
        # Only these explicit release CRT names may replace CPython's bundled CRT.
        shutil.copyfile(p,package/'runtime'/p.name);row['sha256']=launch.digest(p)
    return rows


def build_ffmpeg(inputs,package):
    work=TEMP/'ffmpeg-build';work.mkdir()
    extract_tar(inputs/'ffmpeg-7.1.tar.xz',work)
    extract_tar(inputs/'mingw-w64-x86_64-lame-3.100-3-any.pkg.tar.zst',work/'lame-dev')
    # Explicit static linking; never fall back to a LAME DLL from the host.
    (work/'lame-dev/mingw64/lib/libmp3lame.dll.a').unlink()
    gcc=Path(shutil.which('gcc') or '')
    if not gcc.is_file():raise ValueError('Official runner MinGW GCC unavailable')
    make=next((p for p in [gcc.parent/'mingw32-make.exe',Path(shutil.which('make') or '')] if p.is_file()),None)
    if make is None:raise ValueError('Official runner GNU make unavailable')
    bash=Path(os.environ['ProgramFiles'])/'Git/bin/bash.exe'
    script=work/'build.sh'
    text='''#!/usr/bin/env bash
set -euo pipefail
export PATH="$(cygpath -u "$ALO_GCCDIR"):/usr/bin:$PATH"
MAKE="$(cygpath -u "$ALO_MAKE")"
cd "$(cygpath -u "$ALO_FFBUILD")/ffmpeg-7.1"
DEP="$(pwd)/../lame-dev/mingw64"
gcc --version
gcc -dumpmachine
"$MAKE" --version
./configure --target-os=mingw32 --arch=x86_64 --cc=gcc --cxx=g++ --ar=ar --ranlib=ranlib --nm=nm \\
 --disable-autodetect --disable-gpl --disable-nonfree --disable-network --disable-doc --disable-debug \\
 --disable-shared --enable-static --disable-x86asm --disable-pthreads --enable-w32threads \\
 --disable-everything --disable-programs --enable-ffmpeg --enable-libmp3lame \\
 --enable-demuxer=mp3,wav,flac --enable-muxer=mp3,wav,s16le,f32le,null,flac \\
 --enable-encoder=libmp3lame,pcm_s16le,pcm_f32le,flac \\
 --enable-decoder=mp3,mp3float,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,flac \\
 --enable-parser=mpegaudio,flac --enable-protocol=file,pipe \\
 --enable-filter=aformat,anull,aresample,atrim \\
 --pkg-config=false --extra-cflags="-I$DEP/include" --extra-ldflags="-static -L$DEP/lib"
"$MAKE" -j4 ffmpeg.exe
./ffmpeg.exe -version
./ffmpeg.exe -L
objdump -p ffmpeg.exe
'''
    script.write_text(text,encoding='utf-8',newline='\n')
    env=dict(os.environ,ALO_GCCDIR=str(gcc.parent),ALO_MAKE=str(make),ALO_FFBUILD=str(work))
    with (OUT/'ffmpeg-build.log').open('wb') as log:
        run=subprocess.run([bash,'--noprofile','--norc',script],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    if run.returncode:raise RuntimeError('Native FFmpeg source build failed; see ffmpeg-build.log')
    exe=work/'ffmpeg-7.1/ffmpeg.exe'
    version=subprocess.check_output([exe,'-version'],text=True)
    license_text=subprocess.check_output([exe,'-L'],stderr=subprocess.STDOUT,text=True)
    if '--enable-gpl ' in version or '--enable-nonfree ' in version or 'Lesser General Public' not in license_text:raise ValueError('Unexpected FFmpeg license')
    imports=subprocess.check_output([gcc.parent/'objdump.exe','-p',exe],text=True)
    names=re.findall(r'DLL Name:\s*(\S+)',imports)
    allowed={'kernel32.dll','msvcrt.dll','advapi32.dll','user32.dll','shell32.dll','ole32.dll','ws2_32.dll','bcrypt.dll','secur32.dll'}
    if any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-') for n in names):raise ValueError('FFmpeg has an external runtime DLL dependency: '+str(names))
    target=package/'narzedzia/ffmpeg/ffmpeg.exe';target.parent.mkdir(parents=True);shutil.copyfile(exe,target)
    sources=package/'licencje/FFmpeg-LAME-source';sources.mkdir(parents=True)
    for name in ('ffmpeg-7.1.tar.xz','mingw-w64-lame-3.100-3.src.tar.zst'):shutil.copyfile(inputs/name,sources/name)
    extract_tar(inputs/'mingw-w64-lame-3.100-3.src.tar.zst',work/'lame-source')
    with tarfile.open(work/'lame-source/mingw-w64-lame/lame-3.100.tar.gz') as t:
        for n in ('COPYING','LICENSE'):
            (sources/('LAME-'+n+'.txt')).write_bytes(t.extractfile('lame-3.100/'+n).read())
    shutil.copyfile(script,sources/'build.sh');shutil.copyfile(OUT/'ffmpeg-build.log',sources/'build.log')
    for name in ('COPYING.LGPLv2.1','COPYING.LGPLv3','COPYING.GPLv3','LICENSE.md'):
        shutil.copyfile(work/'ffmpeg-7.1'/name,sources/name)
    return {'version':version,'license':license_text,'sha256':launch.digest(target),'native_imports':names,'scope':'Small native Windows LGPL build, only file/pipe, MP3/WAV/FLAC; source and relink recipe included. Not the prior Gyan GPL composite.'}


def notices(package,wheels,lock):
    checks=[]
    rows=json.loads((CONFIG/'licenses.json').read_text())
    def one(row):
        raw=urllib.request.urlopen(row['url'],timeout=60).read()
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if len(raw)!=row['size'] or blob!=row['blob']:raise ValueError('Upstream license blob mismatch')
        path=package/'licencje'/row['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(one,rows))
    for item in lock:
        if item['name']=='imageio-ffmpeg':continue
        with zipfile.ZipFile(wheels/item['filename']) as z:
            for name in z.namelist():
                if not name.endswith('/') and any(k in name.lower() for k in ('license','copying','notice')):
                    out=package/'licencje/wheels'/item['name']/launch.relative(name);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(name))
        checks.append({'name':item['name'],'version':item['version'],'wheel':item['filename'],'sha256':item['sha256'],'source':item['url']})
    # Clear equivalent source access; no invented three-year written offer.
    text='''ALO Music: GPL-3.0-or-later. Exact 421 source files in testy/candidate/sources.zip.
No prohibition on reverse engineering or replacement of LGPL components is imposed.
The dependency hash manifest describes this distributed build; a modified local copy must rebuild its manifest before running the safety checks.

CPython3.11.9: PSF license, runtime/LICENSE.txt; source https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz
Qt6.10.3: LGPL3/GPL3 as applicable, license texts in licencje/Qt; dynamically loaded replaceable DLLs in runtime/Lib/site-packages/PySide6.
Exact Qt6.10.3 complete source: https://download.qt.io/official_releases/qt/6.10/6.10.3/single/qt-everywhere-src-6.10.3.tar.xz
PySide/Shiboken6.10.3 source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.3-src/pyside-setup-everywhere-src-6.10.3.tar.xz
Qt build controls: https://github.com/qt/qt5/tree/v6.10.3/coin/provisioning
Qt's SEPARATE FFmpeg DLLs are7.1.3, LGPL2.1-or-later, shared MSVC build with zlib1.3.1.
Exact FFmpeg source used by Qt: https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n7.1.3.tar.gz
Qt FFmpeg build configuration: https://github.com/qt/qt5/blob/v6.10.3/coin/provisioning/common/windows/install-ffmpeg.ps1
zlib1.3.1: https://zlib.net/fossils/zlib-1.3.1.tar.gz and https://github.com/qt/qt5/blob/v6.10.3/coin/provisioning/common/windows/zlib.ps1
Qt third-party FFmpeg notices are in licencje/Qt-FFmpeg; other components in Qt complete source and package license files.

Standalone narzedzia/ffmpeg is FFmpeg7.1 LGPL2.1+ with static LAME3.100 LGPL2.0+.
Its complete FFmpeg source, exact MSYS2 LAME source package/patches and build/relink recipe are INCLUDED in licencje/FFmpeg-LAME-source.
LAME source package: https://mirror.msys2.org/mingw/sources/mingw-w64-lame-3.100-3.src.tar.zst
Build tools (not distributed): GNU GCC14.2 / MinGW-w64 from official GitHub Windows image.
GCC runtime exception: https://gcc.gnu.org/onlinedocs/libstdc++/manual/license.html ; GCC source https://ftp.gnu.org/gnu/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz
Microsoft release CRT: official licensed VisualStudio2022 VC/Redist/MSVC/x64/Microsoft.VC143.CRT, unmodified signed files; see MSVC terms and REDIST link.
UCRT and OS DLLs are components of supported Windows10/11/Server; no OS installation is performed.
SoundFile0.13.1 ships libsndfile1.2.2 (LGPL2.1+), not a system DLL.
Exact bundled DLL/build controls: https://github.com/bastibe/libsndfile-binaries/tree/a3e6f9769d0c7e91d2d036cf0fdbe5b4bbf18b87
Windows recipe: same commit .github/workflows/build-libs.yml and triplets/x64-windows-custom.cmake (vcpkg).
DLL SHA25622518c16f9d13eda5ae5adf999c4740d7d16cc2d6b178b36dd4ac2f759a38559, matches Gitblob698263ffc2d2b3fee0c68973d35c057459688228.
libsndfile1.2.2 source: https://github.com/libsndfile/libsndfile/releases/download/1.2.2/libsndfile-1.2.2.tar.xz
MPG1231.32.9 LGPL2.1+ source: https://sourceforge.net/projects/mpg123/files/mpg123/1.32.9/mpg123-1.32.9.tar.bz2
LAME3.100 LGPL2+: original source included within FFmpeg-LAME-source/mingw-w64-lame-3.100-3.src.tar.zst.
Relevant vcpkg source/patch/relink controls: https://github.com/microsoft/vcpkg/tree/80d54ff62d528339c626a6fbc3489a7f25956ade/ports (libsndfile, mpg123, mp3lame).
The Windows vcpkg global checkout was not pinned by upstream; it is NOT claimed as a fully reproducible third-party build.
Permissive codec notices: FLAC1.4.3, Vorbis1.3.7, Opus1.5.2, Ogg1.3.5 are retained in licencje/SoundFile.
All other Python package license notices are retained in licencje/wheels and runtime .dist-info; exact wheel versions/hashes/sources are in THIRD-PARTY.json.
'''
    (package/'licencje/SOURCES.txt').write_text(text,encoding='utf-8')
    urls={
      
      'MSVC-REDIST.txt':'https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution',
      'GCC-RUNTIME-EXCEPTION.txt':'https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-14.2.0/COPYING.RUNTIME',
      'MinGW-COPYING.txt':'https://raw.githubusercontent.com/mingw-w64/mingw-w64/v12.0.0/COPYING'}
    for name,url in urls.items():
        raw=urllib.request.urlopen(url,timeout=60).read().decode('utf-8')
        if '<html' in raw.lower():raw=html.unescape(re.sub('<[^>]+>',' ',re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',raw,flags=re.S|re.I)))
        (package/'licencje'/name).write_text(raw,encoding='utf-8')
    terms_url='https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx'
    raw=urllib.request.urlopen(terms_url,timeout=60).read()
    if hashlib.sha256(raw).hexdigest()!='f1e3d56ceb2ad68aae0711b910375009e651ac5530fa0760f0dea6e81e54fae1':raise ValueError('MSVC terms hash mismatch')
    (package/'licencje/MSVC-LICENSE.docx').write_bytes(raw)
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        document=ET.fromstring(z.read('word/document.xml'))
        terms='\n'.join(''.join(p.itertext()) for p in document.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
    (package/'licencje/MSVC-TERMS.txt').write_text(terms,encoding='utf-8')
    # Verify exact source endpoints are available; never download them on user launch.
    access=[]
    for url in re.findall(r'https://\S+(?:\.tar\.xz|\.tar\.gz)',text):
        with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=60) as r:
            access.append({'url':url,'status':r.status,'content_length':r.headers.get('Content-Length')})
    write(package/'licencje/SOURCE-ACCESS.json',access)
    write(package/'licencje/THIRD-PARTY.json',checks)


def build():
    if sys.platform!='win32' or sys.version_info[:3]!=(3,11,9) or struct.calcsize('P')!=8:raise ValueError('Build only on native Windows x64 CPython3.11.9')
    TEMP.mkdir(exist_ok=False);OUT.mkdir(exist_ok=True)
    ci.materialize_inputs();manifest=ci.verify_sources()
    inputs=TEMP/'inputs';inputs.mkdir()
    for row in INPUTS:download(row,inputs/row['name'])
    package=TEMP/NAME;package.mkdir();(package/'runtime').mkdir()
    extract_zip(inputs/INPUTS[0]['name'],package/'runtime')
    psf=signatures([package/'runtime'/n for n in ('python.exe','python311.dll','python3.dll')])
    if any('Python Software Foundation' not in r['signer'] for r in psf):raise ValueError('Embedded CPython PSF signature mismatch')
    runtime_crt=crt(package)
    wheels=TEMP/'wheels';wheels.mkdir()
    lock=json.loads((CONFIG/'wheels.json').read_text());wheel_checks=[]
    site=package/'runtime/Lib/site-packages';site.mkdir(parents=True)
    for row in lock:
        if row['name']=='imageio-ffmpeg':continue
        path=download(row,wheels/row['filename'])
        records=ci.verify_wheel(path);extract_zip(path,site)
        wheel_checks.append({'file':row['filename'],'sha256':row['sha256'],'record_files':records})
    (package/'runtime/python311._pth').write_text('python311.zip\n.\nLib/site-packages\nimport site\n',encoding='ascii',newline='\n')
    (site/'sitecustomize.py').write_text('''# Offline Python test environment, not product instrumentation.
import sys
def _offline(event,args):
    if event in {"socket.connect","socket.getaddrinfo","socket.gethostbyname","socket.gethostbyaddr","socket.sendto"}:
        raise PermissionError("Portable tests are offline; network denied")
sys.addaudithook(_offline)
sys._alo_portable_offline_audit=True
''',encoding='utf-8')
    ffmpeg=build_ffmpeg(inputs,package);notices(package,wheels,lock)
    testy=package/'testy';(testy/'candidate').mkdir(parents=True);(testy/'windows').mkdir()
    for name in ('candidate/SOURCE-MANIFEST.json','windows/run_windows.py','windows/URUCHOM-TEST.cmd'):shutil.copyfile(ROOT/name,testy/name)
    with zipfile.ZipFile(testy/'candidate/sources.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in manifest['files']:z.write(ROOT/f['path'],f['path'])
    shutil.copyfile(CONFIG/'portable_launch.py',package/'narzedzia/portable_launch.py')
    shutil.copyfile(ROOT/'LICENSE',package/'licencje/ALO-Music-GPL-3.0.txt')
    cmd=r'''@echo off
setlocal
chcp 65001 >nul
title ALO Music 6.2D - testy portable
cd /d "%~dp0"
echo Testy wylacznie na danych syntetycznych. Niczego nie instalujemy.
"%~dp0runtime\python.exe" -I -B "%~dp0narzedzia\portable_launch.py"
set "ALO_EXIT=%ERRORLEVEL%"
echo.
echo Kod zakonczenia: %ALO_EXIT%. Wynik niezaliczonego testu nie jest PASS.
echo Wyniki znajdziesz w folderze wyniki.
pause
exit /b %ALO_EXIT%
'''
    (package/'URUCHOM-TESTY.cmd').write_text(cmd,encoding='ascii',newline='\r\n')
    (package/'CZYTAJ-MNIE.txt').write_text('''ALO Music 6.2D — TESTY PORTABLE, nie wydanie aplikacji.
1. Rozpakuj caly ZIP do nowego zwyklego folderu na lokalnym NTFS (Windows10/11 x64, min. Windows10 1809).
2. Kliknij dwukrotnie URUCHOM-TESTY.cmd. Nie uruchamiaj jako administrator.
3. Poczekaj na koniec; okno pozostanie otwarte. Testy dotycza tylko syntetycznych plikow.
4. Przeslij ZIP i .zip.sha256.txt utworzone w folderze wyniki.

Nie trzeba instalowac Pythona, Qt, FFmpeg, wpisywac komend ani miec internetu.
Nie mieszaj tej paczki z instalacja ALO ani starszymi paczkami. Niczego nie kopiuj miedzy nimi.
Testy korzystaja z osobnego profilu, SQLite i plikow w wyniki/sesja-... . Nie wybieraja prywatnej Biblioteki.
Runner zatrzymuje sie na pierwszym FAIL/ERROR/SKIP/crash/timeout. To uczciwy wynik, nie powtarzaj testu dla uzyskania PASS.
Znany poprzedni wynik Server2022: 2 PASS/1 FAIL/39 NOT RUN, same-size. Nie poprawiono produktu ani asercji.
Bramka WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED pozostaje False. Diagnostyczne testy dodatnie maja jawny test-only override.
CPython3.11.9 x64, Qt/PySide/Shiboken6.10.3, pytest8.4.2, Mutagen1.47.0; inne komponenty i licencje: licencje/THIRD-PARTY.json i SOURCES.txt.
Paczka zawiera kod i skladniki open source; LGPL DLL mozna zastapic. Manifest nalezy wtedy odtworzyc dla lokalnej zmodyfikowanej kopii; taki wynik nie dotyczy zatwierdzonego kandydata.
Nie ma pip, instalatora, modyfikacji PATH/rejestru ani automatycznego pobierania.
''',encoding='utf-8')
    write(package/'licencje/BUILD-PROVENANCE.json',{'inputs':INPUTS,'psf_signatures':psf,'msvc_redist':runtime_crt,'wheels':wheel_checks,'ffmpeg':ffmpeg,'product_tree':ci.TREE,'product_gate':'OFF','builder_platform':sys.platform})
    records=[{'path':p.relative_to(package).as_posix(),'bytes':p.stat().st_size,'sha256':launch.digest(p)} for p in sorted(package.rglob('*')) if p.is_file()]
    write(package/'MANIFEST.json',{'candidate_tree':ci.TREE,'files':records})
    launch.verify_package(package);ci.verify_sources()
    output=TEMP/'build-container.zip'
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in package.rglob('*'):
            if p.is_file():z.write(p,NAME+'/'+p.relative_to(package).as_posix())
    Path(str(output)+'.sha256.txt').write_text(launch.digest(output)+'  '+output.name+'\n')
    write(OUT/'build.json',{'status':'BUILT_NOT_YET_RELOCATION_VERIFIED','zip':output.name,'bytes':output.stat().st_size,'sha256':launch.digest(output),'package_files':len(records)+1,'candidate_tree':ci.TREE,'gate':'OFF'})


def download_artifact(artifact_id):
    # Token is used ONLY for this read-only API request, never the test process.
    token=os.environ['GH_READ_TOKEN']
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):return None
    url='https://api.github.com/repos/DamianPPD/ALO-Music-Public/actions/artifacts/'+str(int(artifact_id))+'/zip'
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'}
    opener=urllib.request.build_opener(NoRedirect)
    output=OUT/(NAME+'-PORTABLE.zip')
    for attempt in range(6):
        try:
            with opener.open(urllib.request.Request(url,headers=headers),timeout=120) as response,output.open('xb') as f:shutil.copyfileobj(response,f)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (301,302,303,307,308):raise
            url=exc.headers['Location']
            if not url.startswith('https://'):raise ValueError('Non-HTTPS artifact redirect')
            headers={}  # Never forward GitHub credentials to artifact storage.
    else:raise ValueError('Too many artifact redirects')
    expected=launch.digest(output);Path(str(output)+'.sha256.txt').write_text(expected+'  '+output.name+'\n')
    return output,expected


def smoke():
    output,expected=download_artifact(sys.argv[2])
    if launch.digest(output)!=expected:raise ValueError('Finished ZIP SHA mismatch')
    # Remove the build location from consideration before launching the ZIP.
    (TEMP/NAME).rename(TEMP/'retired-build-location')
    relocated=Path(os.environ['RUNNER_TEMP'])/'ALO Relocated Space 62D';relocated.mkdir(exist_ok=False)
    extract_zip(output,relocated);package=relocated;launch.verify_package(package)
    win=Path(os.environ['SystemRoot'])
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','TEMP','TMP','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS','PROGRAMFILES','PROGRAMFILES(X86)'}}
    env.update(PATH=str(win/'System32')+';'+str(win),PYTHONHOME='C:\\deliberately-invalid-python-home',PYTHONPATH='C:\\deliberately-invalid-python-path',PIP_NO_INDEX='1')
    command=[str(win/'System32/cmd.exe'),'/d','/c','URUCHOM-TESTY.cmd']
    # Actual CMD including its pause; queued Enter is only input to the pause,
    # never an alternative runner or a mode that skips a test.
    with (OUT/'portable-CMD.stdout.log').open('wb') as log,(OUT/'portable-CMD.stderr.log').open('wb') as err:
        run=subprocess.Popen(command,cwd=package,env=env,stdin=subprocess.PIPE,stdout=log,stderr=err)
        job=launch.RunnerJob(run)
        try:run.communicate(b'\r\n',timeout=5700)
        except subprocess.TimeoutExpired:
            job.close();run.wait(timeout=20);raise RuntimeError('Portable CMD timeout; see preserved console logs')
        finally:job.close()
    results=list((package/'wyniki').glob('ALO-62D-Windows-wyniki-*.zip'))
    if len(results)!=1:raise ValueError('Portable CMD did not produce one result ZIP')
    result=results[0];checksum=Path(str(result)+'.sha256.txt')
    if launch.digest(result)!=checksum.read_text().split()[0]:raise ValueError('Portable result SHA mismatch')
    with zipfile.ZipFile(result) as z:
        if z.testzip() is not None:raise ValueError('Portable result CRC failure')
        for f in json.loads(z.read('MANIFEST.json')):
            raw=z.read(f['path'])
            if len(raw)!=f['bytes'] or hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('Portable result manifest mismatch')
        summary=json.loads(z.read('summary.json'));runtime=json.loads(z.read('environment.json'))
    if summary.get('error') or summary.get('integrity_error') or summary.get('status')=='STOP' or summary.get('preflight')!='PASS' or not summary.get('evidence_complete') or summary.get('package_after')!='PASS':raise ValueError('Portable environment/evidence incomplete: '+str(summary))
    if runtime['scope']!='Windows Server' or runtime['versions']['pytest']!='8.4.2' or not runtime['isolated'] or runtime['pip_available']:raise ValueError('Relocation runtime proof failed')
    if summary['collected']!=42 or summary['executed']<3 or summary['passed']<2 or summary['errors'] or summary['skipped']:raise ValueError('Native tests did not reach the required portable smoke scope')
    if run.returncode!=summary['exit'] or run.returncode not in (0,2):raise ValueError('CMD did not preserve runner outcome')
    launch.verify_package(package);ci.verify_sources()
    for f in (result,checksum):shutil.copyfile(f,OUT/f.name)
    write(OUT/'portable-verification.json',{'artifact_id':int(sys.argv[2]),'package_status':'READY','native_test_status':summary['status'],'portable_zip_sha256':expected,'zip_extracted_to_new_location_with_spaces':True,'build_location_retired':True,'actual_cmd_executed':True,'cmd_exit':run.returncode,'no_host_python_or_pip_in_PATH':True,'poisoned_PYTHONHOME_PATH_ignored':True,'runtime':runtime,'results':summary,'product_tree':ci.TREE,'product_gate':'OFF'})
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:
            f.write('## PORTABLE PACKAGE READY — native tests: '+summary['status']+'\n\n')
            f.write('Windows Server2022 relocation/CMD proof; NOT Windows10/11 acceptance. Gate OFF.\n\n')
            f.write('PASS '+str(summary['passed'])+' / FAIL '+str(summary['failed'])+' / NOT RUN '+str(summary['not_run'])+'\n')


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    try:{'build':build,'smoke':smoke}[sys.argv[1]]()
    except Exception as exc:
        write(OUT/(sys.argv[1]+'-STOP.json'),{'status':'STOP','error':type(exc).__name__+': '+str(exc),'gate':'OFF'})
        raise
