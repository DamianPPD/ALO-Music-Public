"""Read OriginalFilename via system version.dll; never execute the inspected DLL."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct


def original_filenames(path):
    if os.name!='nt':raise RuntimeError('Version resource query requires Windows')
    api=ctypes.WinDLL(str(Path(os.environ['SystemRoot'])/'System32/version.dll'),use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype=wintypes.DWORD
    api.GetFileVersionInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID]
    api.GetFileVersionInfoW.restype=wintypes.BOOL
    api.VerQueryValueW.argtypes=[wintypes.LPCVOID,wintypes.LPCWSTR,ctypes.POINTER(wintypes.LPVOID),ctypes.POINTER(wintypes.UINT)]
    api.VerQueryValueW.restype=wintypes.BOOL
    unused=wintypes.DWORD();size=api.GetFileVersionInfoSizeW(str(path),ctypes.byref(unused))
    if not size:
        error=ctypes.get_last_error()
        if error in (0,1812,1813,1814,1815):return ()  # No version resource.
        raise ctypes.WinError(error)
    if size>16*1024*1024:raise ValueError('Unbounded version resource')
    data=ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path),0,size,data):raise ctypes.WinError(ctypes.get_last_error())
    def query(key,unit):
        pointer=wintypes.LPVOID();length=wintypes.UINT()
        if not api.VerQueryValueW(data,key,ctypes.byref(pointer),ctypes.byref(length)):return None,0
        start=ctypes.addressof(data);address=pointer.value
        if address is None or not start<=address<=start+size or address+length.value*unit>start+size:
            raise ValueError('Invalid version resource pointer/length')
        return address,length.value
    address,length=query(r'\VarFileInfo\Translation',1)
    if address is None:return ()
    if length%4:raise ValueError('Invalid version translation table')
    translations=struct.iter_unpack('<HH',ctypes.string_at(address,length));names=set()
    for language,codepage in translations:
        key='\\StringFileInfo\\%04x%04x\\OriginalFilename'%(language,codepage)
        address,length=query(key,ctypes.sizeof(ctypes.c_wchar))
        if address is not None and length:
            names.add(ctypes.wstring_at(address,length).rstrip('\0'))
    return tuple(sorted(names))
