"""Windows-only owner of one test-process tree. No application synchronization."""
import ctypes
from ctypes import wintypes
import os

class BasicLimits(ctypes.Structure):
    _fields_=[('ProcessUserTime',ctypes.c_int64),('JobUserTime',ctypes.c_int64),
        ('Flags',wintypes.DWORD),('MinimumWorkingSet',ctypes.c_size_t),('MaximumWorkingSet',ctypes.c_size_t),
        ('ActiveProcesses',wintypes.DWORD),('Affinity',ctypes.c_size_t),
        ('Priority',wintypes.DWORD),('Scheduling',wintypes.DWORD)]

class Counters(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint64) for name in ('Reads','Writes','Others','ReadBytes','WriteBytes','OtherBytes')]

class ExtendedLimits(ctypes.Structure):
    _fields_=[('Basic',BasicLimits),('IO',Counters),('ProcessMemory',ctypes.c_size_t),
        ('JobMemory',ctypes.c_size_t),('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]

class Job:
    def __init__(self):
        if os.name!='nt':raise RuntimeError('Windows Job Object requires Windows')
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype=wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.api.SetInformationJobObject.restype=wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype=wintypes.BOOL
        self.api.CloseHandle.argtypes=[wintypes.HANDLE];self.api.CloseHandle.restype=wintypes.BOOL
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        info=ExtendedLimits();info.Basic.Flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error

    def assign(self,process):
        # CPython's Windows Popen owns this process handle. The child blocks
        # on stdin before Qt/decoder import, until assignment succeeds.
        if not self.api.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle);self.handle=None
