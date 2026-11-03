"""Native test of the built ZIP and exact CMD; not a Windows11 Desktop claim."""
from pathlib import Path
import os,sys,zipfile,json,subprocess,hashlib,shutil
TEMP=Path(os.environ['RUNNER_TEMP']);OUT=TEMP/'portable-delivery';ZIP=OUT/'ALO-Music-v0427-Windows11-FINAL-TEST.zip'
def clean_env():
    names={'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','SYSTEMDRIVE','PROGRAMFILES','PROGRAMFILES(X86)','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS'}
    return {k:v for k,v in os.environ.items()if k.upper()in names}
def audit_results(path,expected,code):
    with zipfile.ZipFile(path)as z:
        assert z.testzip()is None
        for f in json.loads(z.read('MANIFEST.json')):
            b=z.read(f['path']);assert len(b)==f['bytes']and hashlib.sha256(b).hexdigest()==f['sha256']
        state=json.loads(z.read('final-summary.json'))
        assert state['status']==expected and state['gate']is False,state
        if expected=='PASS':
            assert state['counts']['PASS']==145 and state['executed']==145 and state['source_before']and state['source_after']
            import xml.etree.ElementTree as E
            names=[n for n in z.namelist()if n.endswith('/result.xml')];assert len(names)==145
            for name in names:
                root=E.fromstring(z.read(name));assert len(root.findall('.//testcase'))==1 and not root.findall('.//failure')+root.findall('.//error')+root.findall('.//skipped')
        else:assert state['executed']==0
    assert Path(str(path)+'.sha256.txt').read_text().split()[0]==hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(status=state['status'],exit=code,counts=state['counts'],executed=state['executed'])
def trial(name,corrupt=False):
    root=TEMP/'Portable path with spaces'/name;root.mkdir(parents=True)
    with zipfile.ZipFile(ZIP)as z:z.extractall(root)
    if corrupt:
        p=root/'app/src/audio_library_organizer/audio/identity.py';p.write_bytes(p.read_bytes()+b'\n# deliberate integrity refusal probe\n')
    env=dict(clean_env(),ALO_PACKAGE_CI_SMOKE='1');cmd=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
    with (OUT/(name+'.stdout.log')).open('wb')as out,(OUT/(name+'.stderr.log')).open('wb')as err:
        p=subprocess.run([str(cmd),'/d','/c',str(root/'URUCHOM-TESTY.cmd')],cwd=root,env=env,stdout=out,stderr=err,timeout=1800)
    results=list((root/'wyniki').rglob('*.zip'));assert len(results)==1,results
    for file in(results[0],Path(str(results[0])+'.sha256.txt')):shutil.copy2(file,OUT/(name+'-'+file.name))
    assert p.returncode==(2 if corrupt else 0),(name,p.returncode)
    report=audit_results(results[0],'STOP'if corrupt else'PASS',p.returncode)
    return report

def failure_proof():
    # A real intentionally failing pytest solely tests infrastructure classification
    # and archive creation. It is not an ALO test and is not included in the ZIP.
    root=TEMP/'Portable path with spaces'/'good';script=TEMP/'only-CI-failure-proof.py'
    script.write_text('''from pathlib import Path
import sys,os,json,io
p=Path(sys.argv[1]);sys.path.insert(0,str(p/'app/.ci/62d'))
import portable_run as adapter
n=adapter.load();w=n.base.ci.EVIDENCE.parent
f=w/'only_harness_failure.py'
case=str(f)+'::test_expected_failure'
if len(sys.argv)>2:
    n.base.CASES.append(case)
    raise SystemExit(n.base.child(case,Path(sys.argv[2])))
f.write_text('def test_expected_failure():\\n    assert False, "intentional infrastructure failure"\\n')
folder=n.base.OUT/'999-case';folder.mkdir();(folder/'profile').mkdir()
env=n.base.old.child_environment(p/'runtime/python.exe',p/'tools')
env.update(ALO_62D_EVIDENCE=str(folder),APPDATA=str(folder/'profile'),LOCALAPPDATA=str(folder/'profile'),USERPROFILE=str(folder/'profile'))
code=n.base.bounded_child([str(p/'runtime/python.exe'),'-I','-B',__file__,str(p),str(folder)],env,folder)
(folder/'exit.txt').write_text(str(code))
assert code==1 and n.base.classify(folder,code)=='FAIL'
result=adapter.archive_results(w,w,{'status':'EXPECTED_INFRASTRUCTURE_FAIL','case':'only harness, NOT ALO','exit':code,'accepted_cases':0},[])
print(json.dumps({'classification':'FAIL','accepted_cases':0,'archive':str(result)}))
''')
    work=TEMP/'private-failure-proof';work.mkdir();env=dict(clean_env(),RUNNER_TEMP=str(work));p=subprocess.run([str(root/'runtime/python.exe'),'-I','-B',str(script),str(root)],env=env,capture_output=True,text=True,timeout=120)
    (OUT/'intentional-failure.stdout.log').write_text(p.stdout);(OUT/'intentional-failure.stderr.log').write_text(p.stderr);assert p.returncode==0,p.stderr
    return {'real_pytest_failure':'classified FAIL, accepted0, results archive created','proof_exit':p.returncode}
if __name__=='__main__':
    result={'scope':'Native Windows Server2022; NOT Windows11Desktop','zip_sha256':hashlib.sha256(ZIP.read_bytes()).hexdigest()}
    try:
        result['good_CMD']=trial('good');result['corrupted_CMD']=trial('corrupted',True);result['actual_failure_archive']=failure_proof();result['status']='PACKAGED_CMD_PASS_SERVER2022'
    finally:(OUT/'package-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
