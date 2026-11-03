"""Reuse the exact verified offline runtime, without rebuilding or installing."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,zipfile,subprocess,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import ci
SHA='cc632bd47bfd84fe114e5deeda722bb510ef9228ca95f07b53ef07ceafb6cdb6'
def main():
 ci.materialize_inputs();ci.verify_sources()
 temp=Path(os.environ['RUNNER_TEMP']);archive=temp/'portable-base/ALO-Music-v0427-Windows11-FINAL-TEST.zip';root=temp/'activation-private';root.mkdir()
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==SHA
 runtime=[]
 with zipfile.ZipFile(archive)as z:
  assert z.testzip()is None
  rows=json.loads(z.read('PACKAGE-MANIFEST.json'));names=set()
  for f in rows:
   n=f['path'];p=PurePosixPath(n)
   assert n and not p.is_absolute()and '..'not in p.parts and ':'not in n and '\\'not in n and n.casefold()not in names
   names.add(n.casefold());data=z.read(n);assert len(data)==f['bytes']and hashlib.sha256(data).hexdigest()==f['sha256']
   if p.parts[0]in('runtime','tools'):
    dest=root.joinpath(*p.parts);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);runtime.append(f)
  assert {n for n in z.namelist()if not n.endswith('/')and n!='PACKAGE-MANIFEST.json'}=={f['path']for f in rows}
 assert len(runtime)==5578
 ci.write('runtime-manifest.json',runtime)
 ci.write('runtime-reuse.json',{'package_sha256':SHA,'runtime_files':len(runtime),'all_package_hashes_verified':len(rows),'new_installations':0})
 python=root/'runtime/python.exe';bins=root/'tools';env=ci.safe_environment(python,bins);env['RUNNER_TEMP']=str(temp)
 ci.write('prepared.json',{'python':str(python),'bin':str(bins),'runtime_root':str(root),'candidate_tree':ci.TREE})
 # Probe in a separate -I process before adding any product/test search path.
 probe="import importlib.util,pathlib,json,sys;s=importlib.util.spec_from_file_location('verified_probe',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);d=m.probe(pathlib.Path(sys.argv[2]));d.update(candidate_tree=sys.argv[3],product_gate=True,scope='Native Windows Server 2022; NOT Windows11 activation run');pathlib.Path(sys.argv[4]).write_text(json.dumps(d,indent=2))"
 ci.execute([python,'-I','-B','-c',probe,HERE/'portable_launch.py',root,ci.TREE,ci.EVIDENCE/'environment.json'],'private-runtime-probe',env=env,timeout=60)
 code=subprocess.run([str(python),'-I','-B',str(HERE/'activation_run.py'),'run'],cwd=ci.ROOT,env=env).returncode
 return code
if __name__=='__main__':sys.exit(main())
