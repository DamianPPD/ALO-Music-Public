"""Download only exact pinned official inputs; no ALO candidate or local environment."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,ssl,urllib.parse,urllib.request
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def download(row,folder):
    url=row.get('url',row.get('source_url'));parsed=urllib.parse.urlsplit(url)
    assert parsed.scheme=='https'and parsed.hostname in ('files.pythonhosted.org','www.python.org')
    name=row.get('name',row.get('filename'));assert Path(name).name==name
    target=ROOT/folder/name;target.parent.mkdir(exist_ok=True,parents=True)
    with urllib.request.urlopen(url,timeout=120,context=ssl.create_default_context())as response:
        assert urllib.parse.urlsplit(response.url).hostname==parsed.hostname
        data=response.read()
    assert len(data)==row['size_bytes']and hashlib.sha256(data).hexdigest()==row['sha256'],name
    target.write_bytes(data);return name
rows=read(ROOT/'requirements/wheels.json');assert len(rows)==23
with ThreadPoolExecutor(max_workers=4)as pool:list(pool.map(lambda row:download(row,'wheels'),rows))
catalog=read(ROOT/'metadata/environment-catalog.json')
download(catalog['python_embed'],'runtime-source');download(catalog['pip'],'runtime-source')
files={p.relative_to(ROOT).as_posix():dict(size_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
       for p in ROOT.rglob('*')if p.is_file()and p.name!='manifest-SHA256.json'and p.relative_to(ROOT).parts[0]not in ('work','results')}
(ROOT/'manifest-SHA256.json').write_text(json.dumps(dict(schema_version=1,scope='TECHNICAL_CI_NO_UNPUBLISHED_PRODUCT',files=files),indent=2))
print('Exact official inputs prepared:',len(files),'manifest entries; no product candidate')
