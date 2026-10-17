"""Use the original private bootstrap/guards for six technical Windows checks only."""
from pathlib import Path
from datetime import datetime,timezone
import os,shutil,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from contract import read_json,write_json,sha256,verify_wheel,archive_results
from support import isolated_environment,run_logged
def main():
    token='ci-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(4).hex()
    out=ROOT/'results'/token;out.mkdir(parents=True);bootstrap=Path(os.environ['I7_311_BOOTSTRAP_DIR'])
    receipt=dict(status='STOP',scope='TECHNICAL_WINDOWS_CI_NOT_INTERACTIVE_GUI',stage='runtime',cases=0,phases=0,XML=0);code=2
    try:
        from private_runtime import verify_private_runtime
        receipt['private_runtime']=verify_private_runtime()
        env=isolated_environment(out/'sandbox');env.update(I7_311_PACKAGE_ROOT=str(ROOT),I7_311_RUNTIME_DIR=os.environ['I7_311_RUNTIME_DIR'])
        python=Path(sys.executable).resolve();site=python.parent/'Lib/site-packages'
        def step(name,argv,limit=90,extra=None):
            record=run_logged(argv,out/name,extra or env,limit,windows_job=True,input_data=b'SMOKE-GO\n');write_json(out/(name+'.json'),record)
            if record['outcome']!='PASS':raise RuntimeError(name+': '+str(record))
            return record
        write_json(out/'wheel-RECORD.json',[verify_wheel(ROOT/'wheels'/r['name'],r)for r in read_json(ROOT/'requirements/wheels.json')])
        pip=[str(python),'-I','-B','-X','utf8','-m','pip','--isolated','--disable-pip-version-check']
        receipt['stage']='install'
        step('install',pip+['install','--no-index','--find-links',str(ROOT/'wheels'),'--target',str(site),'--no-compile','--no-deps',
            '--require-hashes','--only-binary=:all:','--no-cache-dir','-r',str(ROOT/'requirements/windows-hashed.txt')],240)
        step('pip-check',pip+['check'],30)
        from importlib import metadata
        from native_tools import copy_bundled_ffmpeg
        selected=copy_bundled_ffmpeg(metadata.distribution('imageio-ffmpeg'),ROOT/'work'/token/'tools/ffmpeg/ffmpeg.exe',Path(sys.prefix))
        write_json(out/'ffmpeg-identity.json',selected);ffmpeg=Path(selected['selected']['path'])
        from observe import _windows_directories
        systems=_windows_directories()
        env.update(I7_FFMPEG_EXE=str(ffmpeg),I7_FFMPEG_SHA256=sha256(ffmpeg))
        env['PATH']=os.pathsep.join(map(str,[ffmpeg.parent,python.parent,systems[0],systems[-1]]))
        write_json(out/'parent-path.json',dict(PATH=env['PATH'],roles=['pinned_ffmpeg','private_python','WindowsSystem','Windows']))
        step('ffmpeg-version',[str(ffmpeg),'-version'],30)
        receipt['stage']='native'
        step('native',[str(python),'-I','-B','-X','utf8',str(ROOT/'scripts/native_probe.py'),str(out/'native')],120)
        catalog=out/'native/trusted-runtime-catalog.json';env.update(L41_RUNTIME_CATALOG=str(catalog),L41_RUNTIME_CATALOG_SHA256=sha256(catalog))
        for mode in ('RED','GREEN'):
            receipt['stage']=mode
            folder=out/mode;folder.mkdir();childenv=isolated_environment(folder/'sandbox',base=env)
            childenv.update(PATH=env['PATH'],QT_QPA_PLATFORM='offscreen',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
            record=run_logged([str(python),'-I','-B','-X','utf8',str(ROOT/'scripts/smoke_worker.py'),str(folder),mode],
                folder,childenv,150,windows_job=True,input_data=b'SMOKE-GO\n')
            receipt[mode]=record;write_json(out/'run.json',receipt)
            data=read_json(folder/'child.json')
            if mode=='RED':
                if data.get('pytest_exit')!=1 or 'Unverified subprocess PATH'not in (folder/'stdout.log').read_text(encoding='utf-8'):
                    raise ValueError('Original PATH failure not reproduced exactly')
            else:
                if record['outcome']!='PASS'or data.get('status')!='PASS':raise ValueError('Windows technical GREEN failed')
                receipt.update(cases=data['cases'],phases=data['phases'],XML=data['XML'])
        receipt.update(status='WINDOWS CI SMOKE VERIFIED',stage='complete');code=0
    except BaseException as error:
        receipt['error']=repr(error);(out/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        shutil.copytree(bootstrap,out/'bootstrap')
        receipt['exit_code']=code;write_json(out/'run.json',receipt)
        archive=archive_results(out,ROOT/'results')
        write_json(bootstrap/'runner-receipt.json',dict(archive=str(archive),sha256=sha256(archive),exit_code=code,status=receipt['status']))
        print(receipt['status'],archive,flush=True)
    return code
if __name__=='__main__':raise SystemExit(main())
