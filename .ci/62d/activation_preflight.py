"""Provenance check for the existing BEA8 offline runtime layout, not a rebuild."""
from pathlib import Path
import ctypes as C,importlib,importlib.util,importlib.metadata as M,json,struct,sys
root=Path(sys.argv[1]).resolve();runtime=root/'runtime';tree=sys.argv[2];out=Path(sys.argv[3])
assert sys.platform=='win32'and sys.version_info[:3]==(3,11,9)and struct.calcsize('P')==8 and sys.flags.isolated
assert Path(sys.executable).resolve()==runtime/'python.exe'and Path(sys.prefix).resolve()==runtime
# This exact optional test-helper entry is declared by the verified python311._pth.
# It was not extracted, cannot contain code, and is not a directory allowlist.
helper=root/'app/.ci/62d';assert not helper.exists()
for item in sys.path:
 p=Path(item).resolve();assert p.is_relative_to(runtime)or p==helper,('External Python search path',item)
assert importlib.util.find_spec('pip')is None
versions={'PySide6':'6.10.3','PySide6_Essentials':'6.10.3','PySide6_Addons':'6.10.3','shiboken6':'6.10.3','pytest':'8.4.2','mutagen':'1.47.0','Pillow':'11.3.0','requests':'2.32.5','numpy':'2.2.6','soundfile':'0.13.1','cffi':'1.17.1'}
origins={}
for name,want in versions.items():
 dist=M.distribution(name);assert dist.version==want and Path(dist.locate_file('')).resolve().is_relative_to(runtime)
for name in('PySide6.QtCore','PySide6.QtWidgets','PySide6.QtMultimedia','shiboken6','pytest','mutagen','PIL','requests','numpy','soundfile','_cffi_backend'):
 m=importlib.import_module(name);p=Path(m.__file__).resolve();assert p.is_relative_to(runtime);origins[name]=str(p.relative_to(root))
from PySide6.QtCore import qVersion
assert qVersion()=='6.10.3'
k=C.WinDLL('kernel32',use_last_error=True)
k.GetModuleHandleW.argtypes=[C.c_wchar_p];k.GetModuleHandleW.restype=C.c_void_p
k.GetModuleFileNameW.argtypes=[C.c_void_p,C.c_wchar_p,C.c_uint32];k.GetModuleFileNameW.restype=C.c_uint32
modules={}
for name in('Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6Multimedia.dll'):
 handle=k.GetModuleHandleW(name);buf=C.create_unicode_buffer(32768)
 assert handle and k.GetModuleFileNameW(handle,buf,len(buf));p=Path(buf.value).resolve();assert p.is_relative_to(runtime)
 modules[name]=str(p.relative_to(root))
# Reuse the existing runner's actual RtlGetVersion + volume-information probe.
spec=importlib.util.spec_from_file_location('existing_environment',Path(__file__).with_name('portable_run.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e);data=e.environment(root)
assert data['windows']['product_type']!=1 and data['windows']['build']==20348 and data['filesystem']=='NTFS'
data.update(candidate_tree=tree,tree=tree,product_gate=True,scope='Native Windows Server 2022; NOT Windows11 activation run',product_type=data['windows']['product_type'],versions=versions,origins=origins,native_modules=modules,isolated=True,pip_available=False,optional_helper_path_absent=True)
out.write_text(json.dumps(data,indent=2)+'\n')
