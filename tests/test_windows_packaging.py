from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_bootstrap_and_launcher_are_present():
    launcher = ROOT / 'run_audio_library_organizer.bat'
    bootstrap = ROOT / 'scripts' / 'bootstrap_windows.ps1'
    assert launcher.exists()
    assert bootstrap.exists()
    text = bootstrap.read_text(encoding='utf-8')
    assert 'chromaprint-fpcalc-1.6.1-windows-x86_64.zip' in text
    assert '735d6182b38e9f364b84ce6f4ccd682c75e2851de89735711d6b762d12b92a4e' in text
    assert '.[gui,analysis]' in text


def test_pyinstaller_build_files_are_present():
    spec = ROOT / 'audio_library_organizer.spec'
    build = ROOT / 'scripts' / 'build_windows.ps1'
    assert spec.exists()
    assert build.exists()
    assert "tools\\chromaprint" in spec.read_text(encoding='utf-8')
    assert 'PyInstaller' in build.read_text(encoding='utf-8')


def test_public_windows_binary_uses_alo_music_name():
    spec = (ROOT / 'audio_library_organizer.spec').read_text(encoding='utf-8')
    build = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert "name='ALO-Music'" in spec
    assert "$DistDir = Join-Path $Root 'dist\\ALO-Music'" in build
    assert "$Exe = Join-Path $DistDir 'ALO-Music.exe'" in build


def test_pyinstaller_entrypoint_uses_absolute_package_import():
    entrypoint = (ROOT / 'src' / 'audio_library_organizer' / '__main__.py').read_text(encoding='utf-8')
    assert 'from audio_library_organizer.main import main' in entrypoint
    assert 'from .main import main' not in entrypoint


def test_windows_build_script_is_fail_fast():
    build = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert 'Remove-Item $DistDir' in build
    assert 'Instalacja/aktualizacja PyInstaller nie powiodla sie.' in build
    assert 'Build PyInstaller nie powiodl sie.' in build
    assert 'if (-not (Test-Path $Exe))' in build


def test_inno_setup_is_per_user_and_never_requires_admin():
    installer = ROOT / 'installer' / 'ALO-Music.iss'
    assert installer.exists()
    text = installer.read_text(encoding='utf-8')
    assert 'PrivilegesRequired=lowest' in text
    assert r'DefaultDirName={localappdata}\Programs\ALO Music' in text
    assert 'ALO-Music.exe' in text
    assert 'desktopicon' in text
    assert r'{autoprograms}\ALO Music' in text


def test_release_script_builds_portable_installer_and_hashes():
    script = ROOT / 'scripts' / 'build_release_windows.ps1'
    assert script.exists()
    text = script.read_text(encoding='utf-8')
    assert 'build_windows.ps1' in text
    assert '--smoke-test' in text
    assert 'Compress-Archive' in text
    assert 'ISCC.exe' in text
    assert 'Get-FileHash' in text
    assert 'SHA256SUMS.txt' in text
    assert 'ALO-Music-v$Version-Windows-Portable.zip' in text
    assert 'ALO-Music-v$Version-Setup.exe' in text
    assert "__version__\\s*=\\s*[''\"]([^''\"]+)[''\"]" in text


def test_release_script_delimits_version_before_colon():
    text = (ROOT / 'scripts' / 'build_release_windows.ps1').read_text(encoding='utf-8')
    assert 'v${Version}:' in text
    assert 'v$Version:' not in text


def test_release_script_waits_for_smoke_test_and_retries_archive_when_files_are_locked():
    text = (ROOT / 'scripts' / 'build_release_windows.ps1').read_text(encoding='utf-8')
    assert 'Start-Process -FilePath $Exe' in text
    assert "-ArgumentList '--smoke-test'" in text
    assert '-Wait -PassThru' in text
    assert '$SmokeProcess.ExitCode' in text
    assert '$MaxArchiveAttempts = 6' in text
    assert 'Compress-Archive' in text
    assert 'Start-Sleep -Seconds 2' in text
    assert 'Remove-Item $Portable -Force -ErrorAction SilentlyContinue' in text


def test_generated_release_directory_is_gitignored():
    ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'release/' in ignore


def test_windows_docs_describe_public_release_build():
    readme = ROOT / 'README.md'
    windows_doc = ROOT / 'WINDOWS.md'
    build_script = ROOT / 'scripts' / 'build_windows.ps1'
    release_script = ROOT / 'scripts' / 'build_release_windows.ps1'
    spec = ROOT / 'audio_library_organizer.spec'
    installer = ROOT / 'installer' / 'ALO-Music.iss'
    for path in (readme, windows_doc, build_script, release_script, spec, installer):
        assert path.is_file(), f'Missing public build file: {path.name}'

    readme_text = readme.read_text(encoding='utf-8')
    windows = windows_doc.read_text(encoding='utf-8')
    assert '## Publiczna wersja dla Windows' in readme_text
    assert '## Build developerski EXE' in windows
    assert '## Pełne wydanie Windows' in windows
    assert r'.\scripts\build_windows.ps1' in windows
    assert r'.\scripts\build_release_windows.ps1' in windows
    assert 'Inno Setup 6' in windows
    assert r'dist\ALO-Music\ALO-Music.exe' in windows
    assert 'Portable ZIP' in windows
    assert 'instalator per-user' in windows
    assert 'fpcalc' in windows
    assert 'SHA256SUMS.txt' in windows
    assert 'audio_library_organizer.spec' in build_script.read_text(encoding='utf-8')
    assert r'installer\ALO-Music.iss' in release_script.read_text(encoding='utf-8')
    assert 'release-checklist' not in (readme_text + windows).lower()
