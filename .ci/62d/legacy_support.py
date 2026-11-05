"""Exact product content verification for the focused legacy adoption run."""
from pathlib import Path
import hashlib,importlib.util,io,json,subprocess
import ci
ROOT=ci.ROOT
MANIFEST=ROOT/'candidate/SOURCE-MANIFEST.json'
# This file itself is a committed diagnostic blob; product roots stay separate.
def original_manifest():
    raw=MANIFEST.read_text(encoding='utf-8').encode('utf-8')
    assert hashlib.sha256(raw).hexdigest()=='1d34868cc1dea87ba368533287772a14fe43ee73d617015c45e0e0f5a99c6945'
    return json.loads(raw)
ci.TREE=original_manifest()['tree']
def verify_sources():
    manifest=original_manifest()
    assert manifest['tree']==ci.TREE and len(manifest['files'])==428
    for f in manifest['files']:
        raw=(ROOT/f['path']).read_bytes()
        assert len(raw)==f['bytes'] and hashlib.sha256(raw).hexdigest()==f['sha256'],f['path']
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==f['blob'],f['path']
    spec=importlib.util.spec_from_file_location('tree_runner',ROOT/'windows/run_windows.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    assert runner.tree_id(manifest['files'])==ci.TREE
    for name,want in json.loads((ci.CONFIG/'original-hashes.json').read_text()).items():
        if name!='candidate/SOURCE-MANIFEST.json':
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==want,name
    return manifest
ci.verify_sources=verify_sources
def materialize():
    # Only before tests: undo Windows checkout EOL filters with exact Git blobs.
    manifest=original_manifest();files=list(manifest['files'])
    present={f['path'] for f in files}
    hashes=json.loads((ci.CONFIG/'original-hashes.json').read_text())
    for name,want in hashes.items():
        if name in present or name=='candidate/SOURCE-MANIFEST.json':continue
        blob=subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=ROOT).decode().strip()
        files.append({'path':name,'blob':blob,'sha256':want})
    batch=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,
        input=('\n'.join(f['blob'] for f in files)+'\n').encode(),capture_output=True,check=True).stdout
    stream=io.BytesIO(batch)
    for f in files:
        sha,kind,size=stream.readline().decode().split()
        assert sha==f['blob'] and kind=='blob'
        raw=stream.read(int(size));assert stream.read(1)==b'\n'
        assert hashlib.sha256(raw).hexdigest()==f['sha256']
        (ROOT/f['path']).write_bytes(raw)
    assert not stream.read()
    ci.write('raw-source-materialization.json',{'tree':ci.TREE,'files':len(files),'after_test_restore':False})
