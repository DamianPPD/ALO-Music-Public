"""Reuse byte-identical, already-verified Windows runtime; update test infrastructure only."""
from pathlib import Path
import hashlib,json,os,zipfile
HERE=Path(__file__).resolve().parent;TEMP=Path(os.environ['RUNNER_TEMP']);OUT=TEMP/'timeout39-delivery'
SHA='cc632bd47bfd84fe114e5deeda722bb510ef9228ca95f07b53ef07ceafb6cdb6';TREE='bea8fc4fbc128fbfd99f2c6c1a3d0b62493844ee'
def digest(b):return hashlib.sha256(b).hexdigest()
def main():
 OUT.mkdir(exist_ok=True);base=TEMP/'portable-base/ALO-Music-v0427-Windows11-FINAL-TEST.zip';assert digest(base.read_bytes())==SHA
 replacements={}
 for n in ('portable_run.py','contract_run.py','timeout39_observer.py','history38.json'):
  replacements['app/.ci/62d/'+n]=(HERE/n).read_bytes().replace(b'\r\n',b'\n')
 for n in ('README.txt','URUCHOM-TESTY.cmd'):
  b=(HERE/n).read_bytes()
  if n.endswith('.cmd'):b=b.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
  replacements[n]=b;replacements['app/.ci/62d/'+n]=b
 replacements['PACKAGE-VALIDATION.txt']=b'Exact BEA8. Continuation selects EN39 plus106, not first38. Diagnostic native Server PL/EN and timeout transport evidence is reported separately. Windows11 timeout root cause remains unconfirmed. Gate OFF.\n'
 path=OUT/'ALO-Music-Windows11-FINAL-KONTYNUACJA.zip';records=[];unchanged_runtime=0
 with zipfile.ZipFile(base)as old,zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED)as new:
  assert old.testzip()is None
  mf=json.loads(old.read('PACKAGE-MANIFEST.json'))
  for f in mf:
   b=old.read(f['path']);assert len(b)==f['bytes']and digest(b)==f['sha256']
  src=json.loads(old.read('app/candidate/SOURCE-MANIFEST.json'));assert src['tree']==TREE and len(src['files'])==425
  protected={'app/'+f['path']for f in src['files']};assert not protected.intersection(replacements)
  for n in old.namelist():
   if n in replacements or n=='PACKAGE-MANIFEST.json':continue
   b=old.read(n);new.writestr(n,b);records.append(dict(path=n,bytes=len(b),sha256=digest(b)))
   if n.startswith(('runtime/','tools/')):unchanged_runtime+=1
  for n,b in replacements.items():
   new.writestr(n,b);records.append(dict(path=n,bytes=len(b),sha256=digest(b)))
  new.writestr('PACKAGE-MANIFEST.json',json.dumps(records,indent=2)+'\n')
 with zipfile.ZipFile(path)as z:
  assert z.testzip()is None
  for f in records:assert digest(z.read(f['path']))==f['sha256']
  for f in src['files']:assert digest(z.read('app/'+f['path']))==f['sha256']
 Path(str(path)+'.sha256.txt').write_text(digest(path.read_bytes())+'  '+path.name+'\n')
 (OUT/'build.json').write_text(json.dumps(dict(tree=TREE,source_files=425,package_bytes=path.stat().st_size,sha256=digest(path.read_bytes()),manifest_files=len(records),unchanged_runtime_files=unchanged_runtime,selected=107,historical_not_rerun=38,gate=False),indent=2))
 print('REPACKED',path.name,digest(path.read_bytes()),flush=True)
if __name__=='__main__':main()
