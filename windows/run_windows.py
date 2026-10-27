"""Small native validation runner; uses an existing pinned Windows environment.

No downloads, installation, admin rights or access to an existing library.
Not a bundled Windows runtime. Diagnostic gate overrides live only in tests.
"""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import hashlib,importlib.metadata,json,os,platform,shutil,subprocess,sys,zipfile
import xml.etree.ElementTree as ET


def sha(data):return hashlib.sha256(data).hexdigest()


def tree_id(files):
    nodes={}
    for f in files:
        cur=nodes;parts=f['path'].split('/')
        for part in parts[:-1]:cur=cur.setdefault(part,{})
        cur[parts[-1]]=f
    def digest(node):
        rows=[]
        for name,value in node.items():
            isdir=not isinstance(value.get('blob'),str)
            mode,blob=('40000',digest(value)) if isdir else (value['mode'],value['blob'])
            rows.append((name.encode()+ (b'/' if isdir else b''),mode.encode()+b' '+name.encode()+b'\0'+bytes.fromhex(blob)))
        raw=b''.join(row for _,row in sorted(rows))
        return hashlib.sha1(b'tree '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    return digest(nodes)


def verify(root,manifest):
    for f in manifest['files']:
        p=root/f['path'];raw=p.read_bytes()
        assert sha(raw)==f['sha256'],f['path']
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==f['blob'],f['path']
    assert tree_id(manifest['files'])==manifest['tree']


def main():
    package=Path(__file__).resolve().parent.parent
    result=package/('ALO-62D-Windows-wyniki-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    result.mkdir(exist_ok=False)
    status={'status':'STOP','native_windows':sys.platform=='win32','cases':[],
        'platform':platform.platform(),'python':sys.version,'positive_production_gate':'OFF',
        'diagnostic_positive_tests':'test-only in-memory gate override; real native APIs and GUI guards',
        'missing_native_scope':['second physical volume','real non-NTFS filesystem','native access DACL denial','forced native API failure','full two-process GUI restart','explicit WAL rotation'],
        'source_integrity_before':False,'source_integrity_after':False}
    code=2;source=result/'isolated-source';manifest=None
    try:
        assert sys.platform=='win32','Native Windows required; no Linux/Wine substitution'
        assert sys.version_info[:3]==(3,11,9),'Use existing CPython3.11.9 x64, not a system installation change'
        import struct
        assert struct.calcsize('P')==8,'Windows x64 required'
        for name,wanted in [('PySide6','6.10.3'),('shiboken6','6.10.3'),('mutagen','1.47.0'),('pytest','8.4.2')]:
            actual=importlib.metadata.version(name);status.setdefault('versions',{})[name]=actual
            assert actual==wanted,(name,actual,wanted)
        for name in ('Pillow','requests','numpy','soundfile'):status.setdefault('versions',{})[name]=importlib.metadata.version(name)
        exe=shutil.which('ffmpeg');assert exe,'Verified FFmpeg must be available in this environment PATH'
        assert Path(exe).is_file();status['ffmpeg']={'sha256':sha(Path(exe).read_bytes()),'name':Path(exe).name}
        manifest=json.loads((package/'candidate/SOURCE-MANIFEST.json').read_text())
        source.mkdir()
        with zipfile.ZipFile(package/'candidate/sources.zip') as z:
            assert z.testzip() is None
            assert sorted(z.namelist())==sorted(f['path'] for f in manifest['files'])
            for f in manifest['files']:
                assert not Path(f['path']).is_absolute() and '..' not in Path(f['path']).parts
                p=source/f['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(f['path']))
        verify(source,manifest);status['source_integrity_before']=True;status['tree']=manifest['tree']
        env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='windows',PYTHONUNBUFFERED='1')
        env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        # Existing fixtures use explicit synthetic LibraryPaths and INI QSettings.
        collect=[sys.executable,'-B','-m','pytest','tests/test_windows_output_native_v0427.py','--collect-only','-q']
        run=subprocess.run(collect,cwd=source,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        (result/'collect.stdout.log').write_bytes(run.stdout);(result/'collect.stderr.log').write_bytes(run.stderr)
        assert run.returncode==0,'Collection failed'
        cases=[line for line in run.stdout.decode('utf-8','replace').splitlines() if line.startswith('tests/test_windows_output_native_v0427.py::')]
        assert len(cases)==42,('Native case list changed',len(cases))
        status['planned_cases']=cases
        for i,case in enumerate(cases,1):
            directory=result/(f'{i:02d}-case');directory.mkdir()
            childenv=dict(env,ALO_62D_EVIDENCE=str(directory),STAGE62C_EVIDENCE=str(directory))
            cmd=[sys.executable,'-B','-m','pytest',case,'-v','--junitxml='+str(directory/'result.xml'),'--basetemp='+str(directory/'synthetic')]
            print(f'{i}/42 {case}',flush=True)
            with (directory/'stdout.log').open('wb') as out,(directory/'stderr.log').open('wb') as err:
                try:exitcode=subprocess.run(cmd,cwd=source,env=childenv,stdout=out,stderr=err,timeout=120).returncode
                except subprocess.TimeoutExpired:exitcode=124
            (directory/'exit.txt').write_text(str(exitcode))
            entry={'case':case,'exit':exitcode,'status':'STOP'};status['cases'].append(entry)
            if not (directory/'result.xml').is_file():raise RuntimeError('Missing XML, crash or timeout')
            xml=ET.parse(directory/'result.xml');tests=list(xml.iter('testcase'))
            bad=[n.tag for node in tests for n in node if n.tag in ('failure','error','skipped')]
            if exitcode!=0 or len(tests)!=1 or bad:raise RuntimeError('Case did not pass completely; '+str(entry)+' XML='+str(bad))
            verify(source,manifest);entry['status']='PASS'
        status['status']='NATIVE_TARGETED_PASS_REVIEW_REQUIRED';code=0
        # Scope gaps listed above still require separate evidence: this is not
        # permission to edit the production gate or publish the candidate.
    except Exception as exc:
        status['error']=type(exc).__name__+': '+str(exc)
    finally:
        if manifest is not None and source.exists():
            try:verify(source,manifest);status['source_integrity_after']=True
            except Exception as exc:status['status']='STOP';status['integrity_error']=str(exc);code=2
        status['exit']=code;status['tests_executed']=len(status['cases']);status['accepted_cases']=sum(c['status']=='PASS' for c in status['cases'])
        (result/'run.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
        # Keep logs, JSON, XML and screenshots. Synthetic audio/DB stay in their
        # own folder; the result ZIP need not copy thousands of temporary bytes.
        payload=[p for p in result.rglob('*') if p.is_file() and 'isolated-source' not in p.parts and 'synthetic' not in p.parts]
        records=[{'path':p.relative_to(result).as_posix(),'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in payload]
        (result/'MANIFEST.json').write_text(json.dumps(records,indent=2))
        output=Path(str(result)+'.zip')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for p in [*payload,result/'MANIFEST.json']:z.write(p,p.relative_to(result).as_posix())
        with zipfile.ZipFile(output) as z:
            assert z.testzip() is None
            for f in records:assert sha(z.read(f['path']))==f['sha256']
        Path(str(output)+'.sha256.txt').write_text(sha(output.read_bytes())+'  '+output.name+'\n')
        print(status['status']+' — '+str(output),flush=True)
    return code


if __name__=='__main__':sys.exit(main())
