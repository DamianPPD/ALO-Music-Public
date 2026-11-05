"""26 targeted producer integration cases; reuse established per-process N2 runner."""
from pathlib import Path
import hashlib,json,os,sys,traceback
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[1]/'src'),str(HERE.parents[1]/'tests')]
import contract_run as base
import legacy_support
CASES=json.loads((HERE/'legacy-cases.json').read_text())['selected']
assert len(CASES)==len(set(CASES))==40
base.CASES=CASES

def run():
 base.old.windows_required();base.ci.verify_sources();native=base.old.load_product()
 assert native.positive_acceptance_enabled()
 p=json.loads((base.ci.EVIDENCE/'prepared.json').read_text())
 environment=json.loads((base.ci.EVIDENCE/'environment.json').read_text())
 assert environment['candidate_tree']==base.ci.TREE and environment['product_gate']is True
 assert environment['scope'].startswith('Native Windows Server')and environment['product_type']!=1
 base.ci.write('environment.json',environment)
 status={'tree':base.ci.TREE,'gate':True,'selected':len(CASES),'executed':0,'cases':[],
  'status':'STOP','source_before':True,'source_after':False,'runtime_after':False,'full145_rerun':False}
 try:
  for i,case in enumerate(CASES,1):
   folder=base.OUT/('%02d-case'%i);folder.mkdir()
   profile=folder/'profile';profile.mkdir()
   env=base.old.child_environment(Path(p['python']),Path(p['bin']))
   env.update(ALO_ADOPTION_MEASURE=str(folder/'performance.json'),ALO_62D_EVIDENCE=str(folder),STAGE62C_EVIDENCE=str(folder),APPDATA=str(profile),LOCALAPPDATA=str(profile),USERPROFILE=str(profile),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
   code=base.bounded_child([p['python'],'-I','-B',str(Path(__file__).resolve()),'pytest-wait',case,str(folder)],env,folder)
   (folder/'exit.txt').write_text(str(code));outcome=base.classify(folder,code)
   status['cases'].append({'case':case,'exit':code,'outcome':outcome,'category':'SQLite-contract'if 'test_library_reconciliation' in case else 'native-Qt-real-audio'})
   status['executed']=len(status['cases']);base.write(base.OUT/'run.json',status);base.ci.verify_sources()
   print(str(i)+'/'+str(len(CASES))+' '+outcome+' '+case,flush=True)
   if outcome!='PASS':raise RuntimeError('STOP '+case+' / '+outcome)
   base.audit_synthetic(folder)
  assert status['executed']==status['selected']==40 and all(c['outcome']=='PASS'and c['exit']==0 for c in status['cases'])
  status['status']='LEGACY_ADOPTION_PASS'
 finally:
  base.ci.verify_sources();status['source_after']=True
  root=Path(p['runtime_root'])
  for f in json.loads((base.ci.EVIDENCE/'runtime-manifest.json').read_text()):
   raw=(root/f['path']).read_bytes();assert len(raw)==f['bytes']and hashlib.sha256(raw).hexdigest()==f['sha256']
  status['runtime_after']=True;base.write(base.OUT/'run.json',status)
 return 0
if __name__=='__main__':
 try:
  if sys.argv[1]=='pytest-wait':code=base.child(sys.argv[2],Path(sys.argv[3]))
  else:code=run()
 except BaseException:
  (base.OUT/'activation-exception.log').write_text(traceback.format_exc());raise
 sys.exit(code)
