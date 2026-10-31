"""CI environment/provenance wrapper; invokes the unchanged 42-case runner.

No application test implementation and no product/gate edits live here.
"""
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse
from datetime import datetime,timezone
import base64,csv,hashlib,io,json,os,shutil,struct,subprocess,sys,urllib.request,zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
CONFIG=Path(__file__).resolve().parent
EVIDENCE=Path(os.environ.get('RUNNER_TEMP',str(ROOT)))/'alo-62d-evidence'
EVIDENCE.mkdir(parents=True,exist_ok=True)
TREE='13bd813e15ef85925e6b5da5cccde6edaf0807b8'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def write(name,data):
    (EVIDENCE/name).write_text(json.dumps(data,indent=2),encoding='utf-8')


def execute(cmd,name,*,env=None,timeout=300):
    with (EVIDENCE/(name+'.stdout.log')).open('wb') as out,(EVIDENCE/(name+'.stderr.log')).open('wb') as err:
        try:code=subprocess.run([str(x) for x in cmd],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=timeout).returncode
        except subprocess.TimeoutExpired:code=124
    (EVIDENCE/(name+'.exit.txt')).write_text(str(code))
    if code:raise RuntimeError(name+' failed, exit '+str(code))


def verify_sources():
    manifest=json.loads((ROOT/'candidate/SOURCE-MANIFEST.json').read_text())
    assert manifest['tree']==TREE and len(manifest['files'])==425
    for f in manifest['files']:
        raw=(ROOT/f['path']).read_bytes()
        assert sha(raw)==f['sha256'],f['path']
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==f['blob'],f['path']
    # Existing runner's pure TREE routine; it does not import ALO or Qt.
    import importlib.util
    spec=importlib.util.spec_from_file_location('original_runner',ROOT/'windows/run_windows.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    assert runner.tree_id(manifest['files'])==TREE
    assert 'WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED = False' in (ROOT/'src/audio_library_organizer/safety/windows_file_identity.py').read_text()
    for name,expected in json.loads((CONFIG/'original-hashes.json').read_text()).items():
        assert sha((ROOT/name).read_bytes())==expected,name
    return manifest


def materialize_inputs(ref='HEAD'):
    """Undo checkout EOL filters using exact Git blobs, before any validation.

    Never call this after tests: doing so would conceal test-time modifications.
    No Git commit/ref/index or product content is changed relative to the
    approved blob IDs; the CI working copy is restored to those original bytes.
    """
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
    raw=git('cat-file','blob',ref+':candidate/SOURCE-MANIFEST.json')
    hashes=json.loads((CONFIG/'original-hashes.json').read_text())
    assert sha(raw)==hashes['candidate/SOURCE-MANIFEST.json']
    manifest=json.loads(raw);assert manifest['tree']==TREE and len(manifest['files'])==425
    actual={}
    for line in git('ls-tree','-r','-z',ref).split(b'\0'):
        if line:
            info,path=line.split(b'\t');mode,kind,blob=info.decode().split();actual[path.decode()]=(mode,kind,blob)
    expected=list(manifest['files'])
    for path,hashvalue in hashes.items():
        if path not in {f['path'] for f in expected}:
            mode,kind,blob=actual[path];expected.append({'path':path,'mode':mode,'blob':blob,'sha256':hashvalue})
    for f in expected:
        assert actual[f['path']]==(f['mode'],'blob',f['blob']),f['path']
    batch=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,
        input=('\n'.join(f['blob'] for f in expected)+'\n').encode(),capture_output=True,check=True).stdout
    stream=io.BytesIO(batch)
    for f in expected:
        blob,kind,size=stream.readline().decode().strip().split();assert blob==f['blob'] and kind=='blob'
        data=stream.read(int(size));assert stream.read(1)==b'\n' and sha(data)==f['sha256'],f['path']
        path=ROOT/f['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    assert not stream.read()
    write('raw-source-materialization.json',{'candidate_tree':TREE,'source_files':425,
        'mechanism':'exact Git blobs; checkout text filters undone before tests','after_test_restore':False})


def verify_wheel(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        files=[n for n in z.namelist() if not n.endswith('/')]
        assert len(files)==len(set(files))
        records=[n for n in files if n.endswith('.dist-info/RECORD')];assert len(records)==1
        rows=list(csv.reader(io.StringIO(z.read(records[0]).decode())))
        assert {r[0] for r in rows}==set(files)
        for name,hashvalue,size in rows:
            p=PurePosixPath(name);assert not p.is_absolute() and '..' not in p.parts and ':' not in name
            if name==records[0]:continue
            raw=z.read(name);algorithm,encoded=hashvalue.split('=',1);assert algorithm=='sha256'
            assert base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')==encoded
            assert len(raw)==int(size)
        return len(files)


def prepare():
    assert sys.platform=='win32' and sys.version_info[:3]==(3,11,9) and struct.calcsize('P')==8
    materialize_inputs()
    osinfo=json.loads((EVIDENCE/'environment.json').read_text(encoding='utf-8-sig'))
    assert 'Windows Server 2022' in osinfo['caption'] and osinfo['architecture']=='64-bit'
    assert osinfo['filesystem']=='NTFS' and osinfo['drive_type']=='Fixed'
    assert osinfo['python_signature_status']=='Valid' and 'Python Software Foundation' in osinfo['python_signer']
    manifest=verify_sources()
    # This creates the container consumed by the original runner from the exact
    # 421 original bytes/modes; ZIP compression metadata is not the product TREE.
    with zipfile.ZipFile(ROOT/'candidate/sources.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in manifest['files']:z.write(ROOT/f['path'],f['path'])
    with zipfile.ZipFile(ROOT/'candidate/sources.zip') as z:assert z.testzip() is None
    lock=json.loads((CONFIG/'wheels.json').read_text());wheels=Path(os.environ['RUNNER_TEMP'])/'alo-62d-wheels';wheels.mkdir(exist_ok=False)
    checks=[]
    for f in lock:
        u=urlparse(f['url']);assert u.scheme=='https' and u.hostname=='files.pythonhosted.org'
        path=wheels/f['filename']
        with urllib.request.urlopen(f['url'],timeout=120) as response,path.open('wb') as out:shutil.copyfileobj(response,out)
        raw=path.read_bytes();assert len(raw)==f['size'] and sha(raw)==f['sha256'],f['filename']
        checks.append({'file':f['filename'],'sha256':f['sha256'],'record_files':verify_wheel(path),'source':f['url']})
    write('wheel-verification.json',checks)
    venv=Path(os.environ['RUNNER_TEMP'])/'alo-62d-venv'
    assert not venv.exists();execute([sys.executable,'-I','-m','venv',venv],'create-venv')
    python=venv/'Scripts/python.exe'
    execute([python,'-I','-m','pip','--isolated','install','--no-index','--find-links',wheels,'--only-binary=:all:','--no-deps','--require-hashes','-r',CONFIG/'requirements.lock'],'install',timeout=600)
    execute([python,'-I','-m','pip','check'],'pip-check')
    ff=next(f for f in lock if f['name']=='imageio-ffmpeg');binpath=Path(os.environ['RUNNER_TEMP'])/'alo-62d-bin';binpath.mkdir(exist_ok=False)
    with zipfile.ZipFile(wheels/ff['filename']) as z:
        raw=z.read(ff['executable_entry']);assert sha(raw)==ff['executable_sha256']
    exe=binpath/'ffmpeg.exe';exe.write_bytes(raw)
    clean=safe_environment(python,binpath)
    execute([exe,'-version'],'ffmpeg-version',env=clean)
    execute([exe,'-hide_banner','-encoders'],'ffmpeg-encoders',env=clean)
    assert 'libmp3lame' in (EVIDENCE/'ffmpeg-encoders.stdout.log').read_text()
    execute([python,'-I','-c',"import sys,platform,json,importlib.metadata as m;from PySide6.QtCore import qVersion;print(json.dumps({'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'qt':qVersion(),'versions':{n:m.version(n) for n in ['PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','pytest','mutagen','Pillow','requests','numpy','soundfile','cffi']}},indent=2))"],'runtime-versions',env=clean)
    write('prepared.json',{'python':str(python),'bin':str(binpath),'candidate_tree':TREE,
        'ffmpeg_sha256':ff['executable_sha256'],'product_gate':'OFF','scope':'Native Windows Server 2022; NOT Windows10/11 desktop'})


def safe_environment(python,binpath):
    # No GitHub, Actions runtime, PAT, SSH or user-secret variables reach tests.
    names={'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','HOMEDRIVE','HOMEPATH','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS','SYSTEMDRIVE','PROGRAMFILES','PROGRAMFILES(X86)','COMMONPROGRAMFILES','COMMONPROGRAMFILES(X86)','USERNAME','USERDOMAIN','PUBLIC','ALLUSERSPROFILE','PROGRAMDATA'}
    result={k:v for k,v in os.environ.items() if k.upper() in names}
    windows=Path(os.environ['SystemRoot'])
    result['PATH']=os.pathsep.join(map(str,[binpath,python.parent,windows/'System32',windows]))
    result.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',QT_QPA_PLATFORM='windows')
    return result


def run():
    data=json.loads((EVIDENCE/'prepared.json').read_text());verify_sources()
    execute([data['python'],'-B',ROOT/'windows/run_windows.py'],'native-runner',
        env=safe_environment(Path(data['python']),Path(data['bin'])),timeout=900)


def finish():
    summary={'scope':'Windows Server 2022, not Windows10/11 Desktop','candidate_tree':TREE,
        'product_gate':'OFF','classification':'CI_BLOCKED','prepared_cases':42,'executed':0,'passed':0,'failed':0,'errors':0,'skipped':0,'not_run':42}
    dirs=sorted(p for p in ROOT.glob('ALO-62D-Windows-wyniki-*') if p.is_dir())
    if dirs:
        assert len(dirs)==1
        directory=dirs[0]
        target=EVIDENCE/'results';target.mkdir(exist_ok=True)
        # A hard crash may precede run.json/ZIP. Preserve only evidence files,
        # never the restored source, synthetic music/SQLite or environment.
        for p in directory.rglob('*'):
            relative=p.relative_to(directory)
            if (p.is_file() and not any(x in relative.parts for x in ('isolated-source','synthetic'))
                    and p.suffix in {'.json','.jsonl','.log','.txt','.xml','.png'}):
                out=target/'expanded'/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
        try:status=json.loads((directory/'run.json').read_text())
        except (OSError,ValueError) as exc:
            status={'status':'INTERRUPTED_NO_RUN_JSON','tests_executed':0,'accepted_cases':0,'cases':[]}
            summary['execution_count_unknown']=True
            summary['completed_case_exits']=len(list(directory.glob('*-case/exit.txt')))
            summary['created_case_folders']=len([p for p in directory.glob('*-case') if p.is_dir()])
            summary['runner_summary_error']=str(exc)
        summary['runner']=status
        summary['executed']=status['tests_executed'];summary['passed']=status['accepted_cases'];summary['not_run']=42-summary['executed']
        if summary.get('execution_count_unknown'):
            summary['executed']=None;summary['not_run']=None
        for p in (Path(str(directory)+'.zip'),Path(str(directory)+'.zip.sha256.txt')):
            if p.exists():shutil.copy2(p,target/p.name)
        for case in status['cases']:
            index=status['cases'].index(case)+1;folder=directory/(f'{index:02d}-case');xml=folder/'result.xml'
            if xml.exists():
                for node in ET.parse(xml).iter('testcase'):
                    summary['failed']+=node.find('failure') is not None
                    summary['errors']+=node.find('error') is not None
                    summary['skipped']+=node.find('skipped') is not None
        if (target/(directory.name+'.zip')).exists():
            p=target/(directory.name+'.zip');expected=(target/(p.name+'.sha256.txt')).read_text().split()[0];assert sha(p.read_bytes())==expected
            with zipfile.ZipFile(p) as z:
                assert z.testzip() is None
                for f in json.loads(z.read('MANIFEST.json')):
                    raw=z.read(f['path']);assert sha(raw)==f['sha256'] and len(raw)==f['bytes']
                    q=PurePosixPath(f['path']);assert not q.is_absolute() and '..' not in q.parts
                    if q.suffix in {'.json','.jsonl','.log','.txt','.xml','.png'}:
                        out=target/'expanded'/f['path'];out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
        summary['classification']='WINDOWS_SERVER_42_PASS_REVIEW_REQUIRED' if status['status']=='NATIVE_TARGETED_PASS_REVIEW_REQUIRED' and summary['passed']==42 else ('CI_INTERRUPTED' if summary.get('execution_count_unknown') else 'NATIVE_NOT_PASS')
    try:verify_sources();summary['source_integrity']='PASS'
    except Exception as exc:summary['source_integrity']='FAIL';summary['integrity_error']=str(exc);summary['classification']='CI_BLOCKED'
    write('ci-summary.json',summary)
    entries=[{'path':p.relative_to(EVIDENCE).as_posix(),'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in EVIDENCE.rglob('*') if p.is_file() and p.name!='CI-MANIFEST.json']
    write('CI-MANIFEST.json',entries)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write('## ALO6.2D — '+summary['classification']+'\n\nNative Windows Server2022; NOT desktop certification. Product gate OFF.\n\n')
            out.write('|Executed|PASS|FAIL|ERROR|SKIP|NOT RUN|\n|---:|---:|---:|---:|---:|---:|\n')
            out.write('|'+ '|'.join(str(summary[k]) for k in ['executed','passed','failed','errors','skipped','not_run'])+'|\n')


if __name__=='__main__':
    action=sys.argv[1]
    try:{'prepare':prepare,'run':run,'finish':finish}[action]()
    except Exception as exc:
        write(action+'-error.json',{'error':type(exc).__name__,'message':str(exc),'time_utc':datetime.now(timezone.utc).isoformat(),'product_gate':'OFF'})
        raise

