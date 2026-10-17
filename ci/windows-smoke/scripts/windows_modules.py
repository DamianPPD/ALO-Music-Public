"""Read actual loaded-module paths in this Windows process only."""
import ctypes
from ctypes import wintypes
import os

def loaded_paths():
    if os.name!='nt':raise RuntimeError('Loaded Windows modules require Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    psapi.EnumProcessModulesEx.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.DWORD]
    psapi.EnumProcessModulesEx.restype=wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes=[wintypes.HANDLE,wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
    psapi.GetModuleFileNameExW.restype=wintypes.DWORD
    process=kernel.GetCurrentProcess();needed=wintypes.DWORD();modules=(wintypes.HMODULE*2048)()
    if not psapi.EnumProcessModulesEx(process,modules,ctypes.sizeof(modules),ctypes.byref(needed),3):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value>ctypes.sizeof(modules):raise RuntimeError('Module list exceeded bounded buffer')
    paths=[]
    for module in modules[:needed.value//ctypes.sizeof(wintypes.HMODULE)]:
        buffer=ctypes.create_unicode_buffer(32768)
        if not psapi.GetModuleFileNameExW(process,module,buffer,len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        paths.append(buffer.value)
    return paths
