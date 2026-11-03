"""Only PL/EN targeted package checks + synthetic timeout proof. Never full145."""
from pathlib import Path
import os,sys,zipfile,json,subprocess,hashlib,shutil,xml.etree.ElementTree as E
TEMP=Path(os.environ['RUNNER_TEMP']);OUT=TEMP/'timeout39-delivery';ZIP=OUT/'ALO-Music-Windows11-FINAL-KONTYNUACJA.zip'
def env():
 names={'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','SYSTEMDRIVE','PROGRAMFILES','PROGRAMFILES(X86)','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','OS'}
 return {k:v for k,v in os.environ.items()if k.upper()in names}
def trial(language):
 root=TEMP/('Timeout39 path with spaces '+language);root.mkdir()
 with zipfile.ZipFile(ZIP)as z:z.extractall(root)
 e=dict(env(),ALO_PACKAGE_CI_SMOKE='1',ALO_TIMEOUT39_CI_TARGET=language);cmd=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
 with(OUT/(language+'.stdout.log')).open('wb')as out,(OUT/(language+'.stderr.log')).open('wb')as err:
  result=subprocess.run([str(cmd),'/d','/c',str(root/'URUCHOM-TESTY.cmd')],env=e,cwd=root,stdout=out,stderr=err,timeout=230)
 files=list((root/'wyniki').rglob('*.zip'));assert len(files)==1,files
 p=files[0]
 for f in(p,Path(str(p)+'.sha256.txt')):shutil.copy2(f,OUT/(language+'-'+f.name))
 if result.returncode:print((OUT/(language+'.stdout.log')).read_text(encoding='utf-8',errors='replace')[-8000:],flush=True)
 assert result.returncode==0,(language,result.returncode)
 with zipfile.ZipFile(p)as z:
  assert z.testzip()is None
  for f in json.loads(z.read('MANIFEST.json')):assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
  s=json.loads(z.read('final-summary.json'));assert s['status']=='PASS'and s['counts']['PASS']==s['executed']==s['planned']==1 and s['source_after']and s['package_after']and s['gate']is False
  xml=[n for n in z.namelist()if n.endswith('/result.xml')];assert len(xml)==1
  t=E.fromstring(z.read(xml[0]));assert not(t.findall('.//failure')+t.findall('.//error')+t.findall('.//skipped'))
  stages=[json.loads(line)['stage']for n in z.namelist()if n.endswith('/timeout39-checkpoints.jsonl')for line in z.read(n).decode().splitlines()]
  required={'call.begin','MainWindow.create.end','worker.created','worker.finished.signal','MainWindow.result.received.end','QThread.GUI-finished-slot.end','MainWindow.close.end','call.end','teardown.end','process.exit','test.statement'}
  assert required.issubset(stages),sorted(required-set(stages))
 return dict(language=language,status='PASS',executed=1,phase_count=3,gate=False,checkpoint_events=len(stages))
def timeout_proof():
 # Only infrastructure, not an ALO case. Real JobObject uses a shorter3s budget.
 root=TEMP/'Timeout39 path with spaces en';w=TEMP/'timeout39-owned-proof';w.mkdir()
 child=w/'blocked.py';child.write_text('import sys,faulthandler,threading\nassert sys.stdin.readline()=="GO\\n"\nf=open(sys.argv[1],"wb",buffering=0)\nfaulthandler.dump_traceback_later(1,file=f)\nthreading.Event().wait()\n')
 driver=w/'driver.py';driver.write_text('''from pathlib import Path
import sys,os,json
root=Path(sys.argv[1]);w=Path(sys.argv[2]);sys.path.insert(0,str(root/'app/.ci/62d'))
import contract_run as b
folder=b.OUT/'only-synthetic-timeout';folder.mkdir()
e=dict(os.environ);e['PATH']=str(root/'runtime')+os.pathsep+str(root/'tools')+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
code=b.bounded_child([str(root/'runtime/python.exe'),'-I','-B',str(w/'blocked.py'),str(folder/'python-stacks-before-timeout.log')],e,folder,timeout_seconds=3)
assert code==124
s=json.loads((folder/'process-final.json').read_text());assert s['job_closed']and s['process_reaped']and s['runner_exit']==124
assert (folder/'python-stacks-before-timeout.log').stat().st_size>0
p=json.loads((folder/'timeout-processes.json').read_text());assert p['complete']and len(p['active_process_ids_at_timeout'])==1
import portable_run as a
archive=a.archive_results(b.ci.EVIDENCE.parent,w,{'status':'EXPECTED_SYNTHETIC_TIMEOUT','runner_code':124,'product_cases':0,'proof':s},[])
print(json.dumps({'status':'PASS_INFRASTRUCTURE_ONLY','runner_code':124,'product_cases':0,'archive':str(archive)}))
''')
 e=dict(env(),RUNNER_TEMP=str(w))
 p=subprocess.run([str(root/'runtime/python.exe'),'-I','-B',str(driver),str(root),str(w)],env=e,capture_output=True,text=True,timeout=25)
 (OUT/'synthetic-timeout.stdout.log').write_text(p.stdout);(OUT/'synthetic-timeout.stderr.log').write_text(p.stderr)
 assert p.returncode==0,p.stderr
 for f in w.glob('*.zip*'):shutil.copy2(f,OUT/('synthetic-'+f.name))
 return {'status':'PASS_INFRASTRUCTURE_ONLY','process_timeout_seconds':3,'real_product_timeout_seconds':180,'product_cases':0,'real_stack_dump':True,'job_snapshot':True,'reaped':True}
if __name__=='__main__':
 s={'scope':'Windows Server2022 native package targets; NOT Windows11; remaining106 NOT RUN','zip_sha256':hashlib.sha256(ZIP.read_bytes()).hexdigest()}
 try:s['pl']=trial('pl');s['en']=trial('en');s['synthetic_timeout']=timeout_proof();s['status']='TARGETED_PACKAGE_VALIDATION_PASS'
 finally:(OUT/'timeout39-package-validation.json').write_text(json.dumps(s,indent=2)+'\n')
 print(json.dumps(s,indent=2))
