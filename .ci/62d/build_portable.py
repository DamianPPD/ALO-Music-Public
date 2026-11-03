"""Assemble a standalone offline test package on the existing native CI host."""
from pathlib import Path,PurePosixPath
import os,sys,json,hashlib,shutil,urllib.request,zipfile,subprocess,importlib.util,struct
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];TEMP=Path(os.environ['RUNNER_TEMP']);OUT=TEMP/'portable-delivery';OUT.mkdir(exist_ok=True)
TREE='bea8fc4fbc128fbfd99f2c6c1a3d0b62493844ee'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def pe(path):
 b=path.read_bytes();assert b[:2]==b'MZ';offset=struct.unpack_from('<I',b,60)[0];assert b[offset:offset+4]==b'PE\0\0';assert struct.unpack_from('<H',b,offset+4)[0]==0x8664,path

def signatures(paths):
 ps=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
 names=','.join("'"+str(p).replace("'","''")+"'"for p in paths)
 command='@('+names+') | ForEach-Object { $s=Get-AuthenticodeSignature -LiteralPath $_; $v=(Get-Item -LiteralPath $_).VersionInfo; [pscustomobject]@{name=[IO.Path]::GetFileName($_);status=[string]$s.Status;subject=[string]$s.SignerCertificate.Subject;company=$v.CompanyName;original=$v.OriginalFilename;version=$v.FileVersion} } | ConvertTo-Json -Compress'
 p=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,check=True)
 rows=json.loads(p.stdout);rows=rows if isinstance(rows,list)else[rows]
 for row in rows:assert row['status']=='Valid'and ('Python Software Foundation'in row['subject']or'Microsoft'in row['subject']),row
 return rows

def main():
 assert sys.platform=='win32'and sys.version_info[:3]==(3,11,9)and struct.calcsize('P')==8
 spec=importlib.util.spec_from_file_location('ci',HERE/'ci.py');ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(ci);ci.materialize_inputs();source=ci.verify_sources();assert source['tree']==TREE
 package=OUT/'ALO-Music-v0427-Windows11-FINAL-TEST';package.mkdir(exist_ok=False);app=package/'app';app.mkdir();runtime=package/'runtime';runtime.mkdir();tools=package/'tools';tools.mkdir()
 for f in source['files']:
  p=app/f['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/f['path']).read_bytes())
 for p in HERE.iterdir():
  if p.is_file()and p.name not in('build_portable.py','smoke_portable.py','test_portable_contract.py'):
   d=app/'.ci/62d'/p.name;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,d)
 for name in('windows/run_windows.py','windows/URUCHOM-TEST.cmd','candidate/SOURCE-MANIFEST.json'):
  p=app/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
 lock=json.loads((HERE/'python-embed.json').read_text());embed=TEMP/'python-3.11.9-embed-amd64.zip'
 urllib.request.urlretrieve(lock['url'],embed);raw=embed.read_bytes();assert len(raw)==lock['size']and sha(raw)==lock['sha256']
 with zipfile.ZipFile(embed)as z:
  assert z.testzip()is None
  for name in z.namelist():
   q=PurePosixPath(name);assert not q.is_absolute()and'..'not in q.parts and ':'not in name
  z.extractall(runtime)
 for name in('python.exe','python311.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll'):pe(runtime/name)
 provenance={'python_embed':lock,'python_signatures':signatures([runtime/n for n in('python.exe','python311.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll')]),'wheels':[],'crt':[]}
 wheels=TEMP/'portable-wheels';wheels.mkdir(exist_ok=False);site=runtime/'Lib/site-packages';site.mkdir(parents=True)
 for f in json.loads((HERE/'wheels.json').read_text()):
  assert f['url'].startswith('https://files.pythonhosted.org/')
  p=wheels/f['filename'];urllib.request.urlretrieve(f['url'],p);raw=p.read_bytes();assert len(raw)==f['size']and sha(raw)==f['sha256'];records=ci.verify_wheel(p)
  with zipfile.ZipFile(p)as z:
   for name in z.namelist():
    if name.endswith('/'):continue
    q=PurePosixPath(name);assert not q.is_absolute()and'..'not in q.parts and ':'not in name and not any(part.endswith('.data')for part in q.parts)
    d=site/name;d.parent.mkdir(parents=True,exist_ok=True);b=z.read(name)
    if d.exists():assert d.read_bytes()==b
    else:d.write_bytes(b)
   if f['name']=='imageio-ffmpeg':
    b=z.read(f['executable_entry']);assert sha(b)==f['executable_sha256'];(tools/'ffmpeg.exe').write_bytes(b)
  provenance['wheels'].append(dict(name=f['name'],version=f['version'],sha256=f['sha256'],RECORD_files=records))
 # Application-local, signed Microsoft runtime; no redistributable installer.
 crt_names=('msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','msvcp140_atomic_wait.dll','concrt140.dll','vcomp140.dll')
 for name in crt_names:
  src=Path(os.environ['SystemRoot'])/'System32'/name
  if not src.exists():
   if name=='msvcp140.dll':raise RuntimeError('Required application-local MSVC runtime missing on build host')
   continue
  pe(src);row=signatures([src])[0];assert'Microsoft'in row['subject']and row['company']=='Microsoft Corporation'and row['original'].lower()==name.lower(),row
  shutil.copy2(src,runtime/name);row.update(sha256=sha(src.read_bytes()),origin='Official Microsoft Windows2022 CI image /System32; exact signed runtime file, no directory allowlist');provenance['crt'].append(row)
 (runtime/'python311._pth').write_text('python311.zip\n.\nLib/site-packages\n../app/.ci/62d\nimport site\n')
 (site/'sitecustomize.py').write_text('''import os,sys
from pathlib import Path
p=Path(__file__).resolve().parents[3]
w=os.environ.get('ALO_PORTABLE_WORK')
if w:
    sys.path[:0]=[str(p/'app/src'),str(p/'app/tests'),str(p/'app/.ci/62d')]
    from portable_policy import install
    profile=os.environ.get('ALO_PORTABLE_PROFILE')if Path(sys.argv[0]).name in ('portable_run.py','n2final_restart.py')else None
    install(p,Path(w),profile=profile)
''')
 for source_name,dest in [('URUCHOM-TESTY.cmd','URUCHOM-TESTY.cmd'),('README.txt','README.txt')]:shutil.copy2(HERE/source_name,package/dest)
 # Native CMD line endings without changing any product file.
 p=package/'URUCHOM-TESTY.cmd';p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
 write(package/'PROVENANCE.json',provenance)
 (package/'PACKAGE-VALIDATION.txt').write_text('Portable package assembled from BEA8. Native packaged-CMD validation is reported in the separately delivered README. Windows11 Desktop execution remains NOT RUN until the user runs it. Product gate OFF.\n')
 manifest=[dict(path=p.relative_to(package).as_posix(),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))for p in sorted(package.rglob('*'))if p.is_file()]
 write(package/'PACKAGE-MANIFEST.json',manifest)
 path=OUT/'ALO-Music-v0427-Windows11-FINAL-TEST.zip'
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED)as z:
  for p in sorted(package.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(package).as_posix())
 with zipfile.ZipFile(path)as z:assert z.testzip()is None
 Path(str(path)+'.sha256.txt').write_text(sha(path.read_bytes())+'  '+path.name+'\n')
 write(OUT/'build.json',dict(tree=TREE,source_files=425,package_bytes=path.stat().st_size,sha256=sha(path.read_bytes()),manifest_files=len(manifest),gate=False))
 print('BUILT',path.name,path.stat().st_size,sha(path.read_bytes()),flush=True)
if __name__=='__main__':main()
