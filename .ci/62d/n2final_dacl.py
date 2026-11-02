"""Temporary DACL on one owned synthetic file, restored by exact descriptor.

No icacls, administrator, system settings or recursive path operations.
"""
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path

@contextmanager
def deny(path, mask):
    path=Path(path).resolve()
    allowed=Path(os.environ['ALO_62D_EVIDENCE']).resolve()/'synthetic'
    assert path.is_relative_to(allowed) and path.is_file() and not path.is_symlink()
    k=C.WinDLL('kernel32',use_last_error=True);a=C.WinDLL('advapi32',use_last_error=True)
    ptr=C.c_void_p;u32=C.c_uint32
    def bind(lib,name,args,ret):
        f=getattr(lib,name);f.argtypes=args;f.restype=ret;return f
    current=bind(k,'GetCurrentProcess',[],ptr)
    close=bind(k,'CloseHandle',[ptr],W.BOOL)
    free=bind(k,'LocalFree',[ptr],ptr)
    token=ptr()
    op=bind(a,'OpenProcessToken',[ptr,u32,C.POINTER(ptr)],W.BOOL)
    info=bind(a,'GetTokenInformation',[ptr,u32,ptr,u32,C.POINTER(u32)],W.BOOL)
    sidtext=bind(a,'ConvertSidToStringSidW',[ptr,C.POINTER(ptr)],W.BOOL)
    get=bind(a,'GetNamedSecurityInfoW',[W.LPWSTR,u32,u32,ptr,ptr,C.POINTER(ptr),ptr,C.POINTER(ptr)],u32)
    set_=bind(a,'SetNamedSecurityInfoW',[W.LPWSTR,u32,u32,ptr,ptr,ptr,ptr],u32)
    convert=bind(a,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[W.LPCWSTR,u32,C.POINTER(ptr),ptr],W.BOOL)
    getdacl=bind(a,'GetSecurityDescriptorDacl',[ptr,C.POINTER(W.BOOL),C.POINTER(ptr),C.POINTER(W.BOOL)],W.BOOL)
    control=bind(a,'GetSecurityDescriptorControl',[ptr,C.POINTER(C.c_uint16),C.POINTER(u32)],W.BOOL)
    old=ptr();dacl=ptr();new=ptr();text=ptr();changed=False
    try:
        if not op(current(),8,C.byref(token)):raise C.WinError(C.get_last_error())
        size=u32();info(token,1,None,0,C.byref(size));buf=C.create_string_buffer(size.value)
        if not info(token,1,buf,size,C.byref(size)):raise C.WinError(C.get_last_error())
        sid=C.cast(buf,C.POINTER(ptr))[0]
        if not sidtext(sid,C.byref(text)):raise C.WinError(C.get_last_error())
        sid=C.wstring_at(text)
        error=get(str(path),1,4,None,None,C.byref(dacl),None,C.byref(old))
        if error:raise C.WinError(error)
        ctl=C.c_uint16();rev=u32()
        if not control(old,C.byref(ctl),C.byref(rev)):raise C.WinError(C.get_last_error())
        sddl=f'D:P(D;;0x{mask:x};;;{sid})(A;;FA;;;{sid})'
        if not convert(sddl,1,C.byref(new),None):raise C.WinError(C.get_last_error())
        present=W.BOOL();default=W.BOOL();newdacl=ptr()
        if not getdacl(new,C.byref(present),C.byref(newdacl),C.byref(default)):raise C.WinError(C.get_last_error())
        error=set_(str(path),1,4|0x80000000,None,None,newdacl,None)
        if error:raise C.WinError(error)
        changed=True
        yield {'mask':mask,'synthetic_only':True,'origin':'real SetNamedSecurityInfoW / current-user DACL'}
    finally:
        try:
            if changed:
                error=set_(str(path),1,4|(0x80000000 if ctl.value&0x1000 else 0x20000000),None,None,dacl,None)
                if error:raise C.WinError(error)
        finally:
            for p in (new,old,text):
                if p:free(p)
            if token and not close(token):raise C.WinError(C.get_last_error())
