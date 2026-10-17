"""Stdlib-only integrity, isolation, native identity and bounded logging."""
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import struct
import subprocess
import sys
import time
import uuid

EXPECTED_TREE='7fbf8626aa56f61e283656fd38c601f5d73d4480'
EXPECTED_HEAD='7fff914a1f0275977455f634da05e220c9df54b5'

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def relative_path(name):
    path=PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe manifest path: '+name)
    return Path(*path.parts)

def git_hash(kind,data):
    return hashlib.sha1(kind.encode()+b' '+str(len(data)).encode()+b'\0'+data).hexdigest()

def tree_hash(rows):
    root={}
    for row in rows:
        node=root;parts=PurePosixPath(row['path']).parts
        for part in parts[:-1]:node=node.setdefault(part,{})
        if parts[-1] in node:raise ValueError('Duplicate source path')
        node[parts[-1]]=(row['mode'],row['git_blob'])
    def encode(node):
        payload=b''
        for name,value in sorted(node.items(),key=lambda x:(x[0]+('/' if isinstance(x[1],dict) else '')).encode()):
            mode,blob=('40000',encode(value)) if isinstance(value,dict) else value
            payload+=mode.encode()+b' '+name.encode()+b'\0'+bytes.fromhex(blob)
        return git_hash('tree',payload)
    return encode(root)

def classify(code,timeout):
    if timeout:return 'TIMEOUT'
    if code==0:return 'PASS'
    if code is not None and (code<0 or code>=0x80000000):return 'NATIVE_CRASH'
    return 'FAIL'

def host_problem(version,implementation,bits,abi,windows_major):
    if tuple(version)!=(3,11) or implementation!='CPython' or bits!=64 or abi!='win-amd64':
        return 'Use private CPython 3.11.9 x64 (win-amd64); ARM64 and 32-bit interpreters are outside this kit.'
    if windows_major!=10:return 'This kit is limited to Windows 10/11.'
    return None

def capture_auxiliary(directory,name,collector):
    try:
        write_json(directory/name,collector())
        return None
    except Exception as error:
        return dict(file=name,error=repr(error))

def isolated_environment(directory,base=None):
    environment=dict(os.environ if base is None else base)
    for key in list(environment):
        if key.startswith(('QT_','QML_','PYSIDE','ALO_','PYTEST_','PYTHON','IMAGEIO_')) or key in ('LD_PRELOAD','LD_LIBRARY_PATH'):
            del environment[key]
    for key,folder in [('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('USERPROFILE','home'),
                       ('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('TEMP','temp'),('TMP','temp')]:
        path=directory/folder;path.mkdir(parents=True,exist_ok=True);environment[key]=str(path.resolve())
    environment.update(QT_QPA_PLATFORM='offscreen',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        ALO_CRASH_DEBUG='1',ALO_CRASH_DEBUG_LOG=str((directory/'crash-debug.log').resolve()),PYTHONIOENCODING='utf-8')
    return environment

def pe_identity(data):
    if data[:2]!=b'MZ':return None
    offset=struct.unpack_from('<I',data,0x3c)[0]
    if data[offset:offset+4]!=b'PE\0\0':return None
    machine,sections,timestamp=struct.unpack_from('<HHI',data,offset+4)
    opt_size=struct.unpack_from('<H',data,offset+20)[0];opt=offset+24
    magic=struct.unpack_from('<H',data,opt)[0]
    result=dict(machine=hex(machine),timestamp=timestamp,image_size=struct.unpack_from('<I',data,opt+56)[0],pdb=[])
    directory=opt+(112 if magic==0x20b else 96)+6*8
    rva,size=struct.unpack_from('<II',data,directory)
    def file_offset(rva):
        for n in range(sections):
            virtual_size,address,raw_size,pointer=struct.unpack_from('<IIII',data,opt+opt_size+n*40+8)
            if address<=rva<address+max(virtual_size,raw_size):return pointer+rva-address
        return None
    debug=file_offset(rva)
    if debug is not None:
        for at in range(debug,debug+size,28):
            kind,length,address,pointer=struct.unpack_from('<IIII',data,at+12)
            block=data[pointer:pointer+length]
            if kind==2 and len(block)>=24 and block[:4]==b'RSDS':
                result['pdb'].append(dict(guid=str(uuid.UUID(bytes_le=block[4:20])),age=struct.unpack_from('<I',block,20)[0],
                    name=block[24:].split(b'\0')[0].decode('utf-8',errors='replace')))
    return result

def native_identity(path):
    record=dict(path=str(path.resolve()),size_bytes=path.stat().st_size,sha256=sha256(path))
    try:record['pe']=pe_identity(path.read_bytes())
    except (ValueError,struct.error,IndexError) as error:record['pe_error']=str(error)
    return record

def run_logged(command,directory,environment,limit,*,input_data=None,windows_job=False):
    directory.mkdir(parents=True,exist_ok=True);start=time.monotonic();timed_out=False
    record=dict(argv=list(map(str,command)),limit_seconds=limit,host=sys.platform)
    process=None;job=None
    try:
        if windows_job:
            from windows_job import Job
            job=Job()
        process=subprocess.Popen(command,env=environment,stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt')
        record['pid']=process.pid
        if job:job.assign(process)
        try:stdout,stderr=process.communicate(input_data,timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out=True
            if job:job.close();job=None
            elif os.name!='nt':os.killpg(process.pid,signal.SIGKILL)
            else:process.kill()
            stdout,stderr=process.communicate(timeout=5)
        record.update(exit_code=process.returncode,timeout=timed_out,outcome=classify(process.returncode,timed_out))
    except BaseException as error:
        if job:job.close();job=None
        if process and process.poll() is None:process.kill()
        if process:
            stdout,stderr=process.communicate(timeout=5)
        else:stdout,stderr=b'',b''
        record.update(exit_code=process.returncode if process else None,timeout=timed_out,
                      outcome='INTERRUPTED' if isinstance(error,KeyboardInterrupt) else 'INFRASTRUCTURE_STOP',error=repr(error))
    finally:
        if job:job.close()
    record['seconds']=time.monotonic()-start
    (directory/'stdout.log').write_bytes(stdout);(directory/'stderr.log').write_bytes(stderr)
    write_json(directory/'process.json',record)
    return record
