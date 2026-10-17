"""Library4.1 acceptance: immutable source, complete evidence, no Qt import."""
from collections import Counter
from contextlib import closing
import base64,csv,io,hashlib,json,sqlite3,zipfile
from pathlib import Path,PurePosixPath
import xml.etree.ElementTree as ET

HEAD='7fff914a1f0275977455f634da05e220c9df54b5'
TREE='7fbf8626aa56f61e283656fd38c601f5d73d4480'
PATCH_SHA='ea46ded0aafe2cd325cadfc00835b189857c53a6c34fb68817e2e0b8a9b0cbd8'
CASES=['colors-100','colors-125','colors-150','filters','selection-icons',
       'menu-source','menu-managed','managed-offline','sha-conflict',
       'stale-menu','active-read-close','missing-local','slow-stat-model']

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def relative(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or p.as_posix()!=name or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe relative path')
    return Path(*p.parts)

def verify_source(root):
    m=read_json(root/'provenance/ALO-Music-v0427-Etap41-source-manifest.json');rows=[]
    if m['base_head']!=HEAD or m['candidate_tree']!=TREE or len(m['files'])!=385 or len(m['changed_files'])!=7:
        raise ValueError('Wrong candidate identity')
    for r in m['files']:
        p=root/'snapshot'/relative(r['path']);b=p.read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if p.is_symlink() or len(b)!=r['size'] or hashlib.sha256(b).hexdigest()!=r['sha256'] or blob!=r['blob']:
            raise ValueError('Source modified: '+r['path'])
        rows.append(dict(path=r['path'],mode=r['mode'],git_blob=blob))
    actual={p.relative_to(root/'snapshot').as_posix() for p in (root/'snapshot').rglob('*') if p.is_file()}
    if actual!={r['path'] for r in rows}:raise ValueError('Source inventory mismatch')
    from support import tree_hash
    if tree_hash(rows)!=TREE:raise ValueError('Git TREE mismatch')
    if sha256(root/'provenance/ALO-Music-v0427-Etap41.patch')!=PATCH_SHA:raise ValueError('Patch modified')
    return dict(status='PASS',tree=TREE,source_files=385,patch_sha256=PATCH_SHA)

def verify_kit(root):
    rows=read_json(root/'manifest-SHA256.json')['files']
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
            and p.relative_to(root).parts[0] not in ('work','results') and p.name!='manifest-SHA256.json'}
    if actual!=set(rows):raise ValueError('Kit inventory mismatch')
    for name,row in rows.items():
        p=root/relative(name)
        if p.is_symlink() or p.stat().st_size!=row['size_bytes'] or sha256(p)!=row['sha256']:
            raise ValueError('Kit file modified: '+name)
    return dict(status='PASS',files=len(rows),source=verify_source(root))

def archive_results(folder,parent):
    rows={p.relative_to(folder).as_posix():dict(size_bytes=p.stat().st_size,sha256=sha256(p))
          for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='SHA256.json'}
    write_json(folder/'SHA256.json',rows)
    p=parent/('ALO-Library41-wyniki-'+folder.name+'.zip')
    with zipfile.ZipFile(p,'x',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(folder).as_posix())
    p.with_suffix('.sha256.txt').write_text(sha256(p)+'  '+p.name+'\n',encoding='ascii')
    return p

def accept_case(folder,case,process):
    node='test_library41.py::test_native_library41['+case+']'
    if process.get('exit_code')!=0 or process.get('timeout')is not False or process.get('outcome')!='PASS':
        raise ValueError('FAIL/crash/timeout; no acceptance')
    for name in ('stdout.log','stderr.log','process.json','collection.json','phases.jsonl','results.xml','child.json','observations.json','gui.json','integrity.json','isolation.json','waveform-processes.json','desktop-services.json'):
        if not (folder/name).is_file():raise ValueError('Missing evidence '+name)
    if read_json(folder/'collection.json')!=[node]:raise ValueError('Wrong collection')
    phases=[json.loads(x) for x in (folder/'phases.jsonl').read_text().splitlines() if x.strip()]
    if len(phases)!=3 or Counter(x['phase']for x in phases)!=Counter(['setup','call','teardown']) or any(
            x['nodeid']!=node or x['outcome']!='passed' or x.get('wasxfail') for x in phases):
        raise ValueError('Incomplete/failed/skipped phases')
    xml=ET.parse(folder/'results.xml');suites=list(xml.iter('testsuite'));cases=list(xml.iter('testcase'))
    if len(suites)!=1 or any(suites[0].get(k)!=v for k,v in {'tests':'1','errors':'0','failures':'0','skipped':'0'}.items()):
        raise ValueError('Inconsistent XML totals or failure/error/skip')
    if len(cases)!=1 or cases[0].get('name')!=node.partition('::')[2] or any(cases[0].find(x)is not None for x in ('failure','error','skipped')):
        raise ValueError('Invalid XML')
    child=read_json(folder/'child.json');gui=read_json(folder/'gui.json');obs=read_json(folder/'observations.json')
    if child.get('status')!='PASS' or child.get('exit_code')!=0 or child.get('source_after',{}).get('tree')!=TREE:
        raise ValueError('Child integrity/status failure')
    if not gui.get('real_MainWindow') or gui.get('platform')!='windows' or not gui.get('interactive_desktop') or not gui.get('assertions_complete'):
        raise ValueError('Missing real interactive Windows GUI evidence')
    if not gui.get('protected_checks') or any(r.get('unchanged') is not True for r in gui['protected_checks']):
        raise ValueError('Missing/failed protected-data comparisons')
    teardown=[r for r in gui.get('evidence',[]) if r.get('name')=='teardown']
    if len(teardown)!=1 or not all(teardown[0].get(k) is True for k in ('MainWindow_destroyed','QApplication_destroyed')) or teardown[0].get('pool_active')!=0 or teardown[0].get('owned_threads_running')!=0:
        raise ValueError('Incomplete real Qt shutdown evidence')
    isolation=read_json(folder/'isolation.json');wave=read_json(folder/'waveform-processes.json');integrity=read_json(folder/'integrity.json')
    if isolation.get('attempts') or not isolation.get('Qt_guards_installed') or not isolation.get('INI_stores'):
        raise ValueError('Missing/violated GUI isolation')
    if wave.get('faults') or {r['child_pid']for r in wave['starts']}!={r['child_pid']for r in wave['reaped']} or any(r.get('exit_code')!=0 for r in wave['reaped']):
        raise ValueError('Waveform crash, missing exit, or timeout')
    required=case in ('menu-source','menu-managed','managed-offline')
    if required:
        requests=read_json(folder/'desktop-services.json')
        reads=[r for r in gui.get('evidence',[])if r.get('name')=='real-player-read']
        if len(reads)!=1 or len(requests)!=2:raise ValueError('Missing real open/reveal/read requests')
        expected=Path(reads[0]['path']);media,directory=requests
        if (media.get('kind')!='synthetic-media-request' or Path(media['path'])!=expected
                or media.get('real_dispatch')is not False or not media.get('status','').startswith('NOT RUN')
                or directory.get('kind')!='synthetic-folder' or Path(directory['path'])!=expected.parent
                or directory.get('real_dispatch')is not True or directory.get('result')is not True):
            raise ValueError('Wrong/failed synthetic open/reveal dispatch')
        names={r['function']for r in obs.get('operations',[])if r.get('event')=='call'}
        if not {'read_material','resolve_read_path','recheck_read_path'}<=names or not wave['starts']:
            raise ValueError('Missing real backend read/waveform execution')
    if not integrity.get('databases') or not integrity.get('audio'):
        raise ValueError('Missing actual SQLite/audio integrity evidence')
    if obs['errors'] or obs['violations'] or integrity.get('status')!='PASS':
        raise ValueError('Safety/data integrity failure')
    return dict(status='PASS',case=case,phases=3,XML=1)


def verify_wheel(path, row):
    path=Path(path)
    if path.name!=row['name'] or path.is_symlink() or path.stat().st_size!=row['size_bytes'] or sha256(path)!=row['sha256']:
        raise ValueError('Pinned wheel SHA mismatch: '+path.name)
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist(); names=[entry.filename for entry in entries if not entry.is_dir()]
        if archive.testzip() or len(names)!=len(set(name.casefold() for name in names)):
            raise ValueError('Wheel CRC/duplicate failure')
        for entry in entries:
            name=entry.filename.rstrip('/') if entry.is_dir() else entry.filename
            relative(name)
            if (entry.external_attr>>16)&0o170000==0o120000: raise ValueError('Wheel symlink')
        records=[name for name in names if name.endswith('.dist-info/RECORD')]
        if len(records)!=1: raise ValueError('Wheel RECORD missing/ambiguous')
        seen=set()
        for name,digest,size in csv.reader(io.StringIO(archive.read(records[0]).decode('utf-8'))):
            if name in seen or name not in names: raise ValueError('Invalid RECORD inventory')
            seen.add(name)
            if name==records[0]:
                if digest or size: raise ValueError('Invalid RECORD self entry')
            else:
                data=archive.read(name)
                actual='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
                if digest!=actual or size!=str(len(data)): raise ValueError('Wheel RECORD mismatch: '+name)
        if seen!=set(names): raise ValueError('Incomplete RECORD')
    return dict(file=path.name,sha256=row['sha256'],RECORD='PASS')

def data_state(directory, *, protected=False):
    directory=Path(directory); dbs=[]; audio=[]
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.is_symlink(): continue
        if path.suffix.lower() in ('.mp3','.wav'):
            audio.append(dict(path=str(path),size_bytes=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns,sha256=sha256(path)))
        if path.suffix.lower() in ('.sqlite3','.sqlite','.db'):
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
                integrity=conn.execute('PRAGMA integrity_check').fetchall(); fk=conn.execute('PRAGMA foreign_key_check').fetchall()
                if integrity!=[('ok',)] or fk: raise ValueError('SQLite integrity/FK failure: '+str(path))
                names=[r[0]for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
                tables={name:conn.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY 1').fetchall()
                        for name in names if not protected or name!='file_state_cache'}
                dbs.append(dict(path=str(path),user_version=conn.execute('PRAGMA user_version').fetchone()[0],
                    schema=conn.execute('SELECT * FROM sqlite_schema ORDER BY name').fetchall(),tables=tables,
                    integrity_check='ok',foreign_key_check=[]))
    return dict(status='PASS',databases=dbs,audio=audio,cache_excluded=protected)
