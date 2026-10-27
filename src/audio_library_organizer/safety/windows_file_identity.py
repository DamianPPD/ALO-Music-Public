"""Read-only, point-in-time local NTFS metadata proof (Windows x64).

Experimental until native tests are reviewed. No environment/config switch can
enable positive UI acceptance. No content reads, chmod, file writes or fallback
to Python ctime. This is NOT protection against a privileged hostile writer,
writable mappings, metadata rollback, or changes after the last observation.
"""
from dataclasses import dataclass
from pathlib import PureWindowsPath
import ctypes as C
import re
import sys


WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED = False


def on_windows():
    return sys.platform == 'win32'


def positive_acceptance_enabled():
    return on_windows() and WINDOWS_POSITIVE_ACCEPTANCE_VERIFIED


class FILE_BASIC_INFO(C.Structure):
    _fields_=[('CreationTime',C.c_int64),('LastAccessTime',C.c_int64),
              ('LastWriteTime',C.c_int64),('ChangeTime',C.c_int64),('FileAttributes',C.c_uint32)]


class FILE_STANDARD_INFO(C.Structure):
    _fields_=[('AllocationSize',C.c_int64),('EndOfFile',C.c_int64),
              ('NumberOfLinks',C.c_uint32),('DeletePending',C.c_ubyte),('Directory',C.c_ubyte)]


class FILE_ID_INFO(C.Structure):
    _fields_=[('VolumeSerialNumber',C.c_uint64),('FileId',C.c_ubyte*16)]


class FILE_ATTRIBUTE_TAG_INFO(C.Structure):
    _fields_=[('FileAttributes',C.c_uint32),('ReparseTag',C.c_uint32)]


@dataclass(frozen=True, slots=True)
class NativeNode:
    filesystem: str
    drive_type: int
    volume_guid: str
    volume_serial: int
    file_id: bytes
    size: int
    last_write: int
    change_time: int
    creation_time: int
    links: int
    attributes: int
    reparse_tag: int
    delete_pending: bool
    final_path: str
    directory: bool

    @property
    def object_identity(self):
        return (self.volume_guid,self.volume_serial,self.file_id,self.creation_time,self.directory)


@dataclass(frozen=True, slots=True)
class AncestorIdentity:
    path: str
    volume_guid: str
    volume_serial: int
    file_id: bytes
    creation_time: int


@dataclass(frozen=True, slots=True)
class NativePathProof:
    path: str
    ancestors: tuple
    leaf: NativeNode


def _lexical(path):
    raw=str(path)
    # Deliberately narrow DOS drive namespace. No UNC/device/ADS/relative names,
    # ambiguous trailing dots/spaces, DOS devices, dot components or shortnames.
    if not re.match(r'^[A-Za-z]:\\',raw) or '/' in raw or '\x00' in raw:
        raise ValueError('WINDOWS_PATH_NAMESPACE_UNSUPPORTED')
    parts=raw[3:].split('\\') if len(raw)>3 else []
    for part in parts:
        stem=part.split('.',1)[0].upper()
        if (not part or part in ('.','..') or part.endswith(('.', ' '))
                or any(c in part for c in ':*?<>|"~')
                or any(ord(c)<32 for c in part)
                or stem in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}):
            raise ValueError('WINDOWS_PATH_COMPONENT_UNSUPPORTED')
    return PureWindowsPath(raw)


def _capture(path, api, *, mutable=False):
    """Dependency seam for contract tests; public capture never injects an API.

    Hold all ancestors without share-delete until the entire observation is
    complete. Music handles also deny share-write: ordinary unclosed writers
    must cause refusal, because their timestamps may not yet be updated.
    """
    p=_lexical(path);handles=[];ancestors=[];volume=None
    paths=(*reversed(p.parents),p)
    try:
        for index,node_path in enumerate(paths):
            is_leaf=index==len(paths)-1
            h=api.open(str(node_path),mutable=(not is_leaf or mutable));handles.append(h)
            n=api.query(h)
            if (n.filesystem!='NTFS' or n.drive_type!=3 or not n.volume_guid
                    or not n.volume_serial or len(n.file_id)!=16 or not any(n.file_id)
                    # Refuse reparse, offline/recall and device
                    # objects; a local NTFS volume alone is not enough.
                    or n.reparse_tag or n.attributes & (0x400|0x1000|0x40000|0x400000|0x40) or n.delete_pending
                    or n.change_time<=0 or n.creation_time<=0
                    or str(PureWindowsPath(n.final_path)).casefold()!=str(node_path).casefold()
                    or (not is_leaf and not n.directory)
                    or (is_leaf and (n.directory or n.links!=1 or n.size<0))):
                raise ValueError('WINDOWS_OBJECT_UNSUPPORTED')
            current=(n.volume_guid,n.volume_serial)
            if volume is None:volume=current
            if current!=volume:raise ValueError('WINDOWS_VOLUME_BOUNDARY')
            if is_leaf:return NativePathProof(str(p),tuple(ancestors),n)
            ancestors.append(AncestorIdentity(str(node_path),n.volume_guid,n.volume_serial,n.file_id,n.creation_time))
        raise ValueError('WINDOWS_FILE_REQUIRED')
    finally:
        # Close every acquired handle even if another CloseHandle fails.
        failure=None
        for h in reversed(handles):
            try:api.close(h)
            except OSError as exc:failure=exc
        if failure is not None:raise failure


def same_material(before, after):
    return isinstance(before,NativePathProof) and before==after


def same_database(before, after):
    # Database content is re-read in an independent SQLite transaction. Cache
    # and WAL activity may change its size/times without changing its identity.
    return (isinstance(before,NativePathProof) and isinstance(after,NativePathProof)
        and before.path==after.path and before.ancestors==after.ancestors
        and before.leaf.object_identity==after.leaf.object_identity)


class _WinAPI:
    def __init__(self):
        if not on_windows() or C.sizeof(C.c_void_p)!=8:
            raise OSError('WINDOWS_X64_REQUIRED')
        self.k=C.WinDLL('kernel32',use_last_error=True)
        def bind(name,args,result):
            f=getattr(self.k,name);f.argtypes=args;f.restype=result;return f
        ptr=C.c_void_p;u32=C.c_uint32;wstr=C.c_wchar_p;boolean=C.c_int32
        self.create=bind('CreateFileW',[wstr,u32,u32,ptr,u32,u32,ptr],ptr)
        self.info=bind('GetFileInformationByHandleEx',[ptr,C.c_int32,ptr,u32],boolean)
        self.final=bind('GetFinalPathNameByHandleW',[ptr,wstr,u32,u32],u32)
        self.volume=bind('GetVolumeInformationByHandleW',[ptr,wstr,u32,C.POINTER(u32),C.POINTER(u32),C.POINTER(u32),wstr,u32],boolean)
        self.drive=bind('GetDriveTypeW',[wstr],u32)
        self.filetype=bind('GetFileType',[ptr],u32)
        self.close_handle=bind('CloseHandle',[ptr],boolean)

    def open(self,path,*,mutable):
        # FILE_READ_DATA (FILE_LIST_DIRECTORY for ancestors) | READ_ATTRIBUTES:
        # attributes-only access does not establish the required share denial.
        # No inheritable security attributes, OPEN_EXISTING,
        # BACKUP_SEMANTICS for directories + OPEN_REPARSE_POINT for the leaf.
        h=self.create(path,0x81,0x1|(0x2 if mutable else 0),None,3,0x02000000|0x00200000,None)
        if h is None or h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
        return h

    def close(self,h):
        if not self.close_handle(h):raise C.WinError(C.get_last_error())

    def _info(self,h,kind,cls):
        data=cls()
        if not self.info(h,kind,C.byref(data),C.sizeof(data)):raise C.WinError(C.get_last_error())
        return data

    def _final(self,h,flags):
        buf=C.create_unicode_buffer(32768);size=self.final(h,buf,len(buf),flags)
        if not size:raise C.WinError(C.get_last_error())
        if size>=len(buf):raise ValueError('WINDOWS_FINAL_PATH_TOO_LONG')
        return buf.value

    def query(self,h):
        if self.filetype(h)!=1:raise ValueError('WINDOWS_NOT_DISK_FILE')
        basic=self._info(h,0,FILE_BASIC_INFO);standard=self._info(h,1,FILE_STANDARD_INFO)
        ident=self._info(h,18,FILE_ID_INFO);tag=self._info(h,9,FILE_ATTRIBUTE_TAG_INFO)
        fs=C.create_unicode_buffer(64);flags=C.c_uint32()
        if not self.volume(h,None,0,None,None,C.byref(flags),fs,len(fs)):raise C.WinError(C.get_last_error())
        final=self._final(h,0);guid_path=self._final(h,1)
        match=re.match(r'^(\\\\\?\\Volume\{[0-9A-Fa-f-]+\}\\)',guid_path)
        if not match or not final.startswith('\\\\?\\'):
            raise ValueError('WINDOWS_VOLUME_GUID_REQUIRED')
        final=final[4:];p=_lexical(final)
        if basic.FileAttributes!=tag.FileAttributes or not flags.value & 0x8:
            raise ValueError('WINDOWS_METADATA_INCONSISTENT')
        # A second native read avoids assembling a token across an observed
        # change during querying. LastAccessTime is intentionally irrelevant.
        again=self._info(h,0,FILE_BASIC_INFO);std2=self._info(h,1,FILE_STANDARD_INFO)
        if ((basic.CreationTime,basic.LastWriteTime,basic.ChangeTime,basic.FileAttributes,
             standard.EndOfFile,standard.NumberOfLinks,standard.DeletePending,standard.Directory)
                !=(again.CreationTime,again.LastWriteTime,again.ChangeTime,again.FileAttributes,
                   std2.EndOfFile,std2.NumberOfLinks,std2.DeletePending,std2.Directory)):
            raise ValueError('WINDOWS_METADATA_CHANGED_DURING_QUERY')
        return NativeNode(fs.value,self.drive(str(p.anchor)),match[1].casefold(),ident.VolumeSerialNumber,
            bytes(ident.FileId),standard.EndOfFile,basic.LastWriteTime,basic.ChangeTime,basic.CreationTime,
            standard.NumberOfLinks,basic.FileAttributes,tag.ReparseTag,bool(standard.DeletePending),final,bool(standard.Directory))


def capture(path, *, mutable=False):
    """Raises on missing/unsupported/ambiguous state; no weaker fallback."""
    try:api=_WinAPI()
    except AttributeError as exc:raise OSError('WINDOWS_NATIVE_API_UNAVAILABLE') from exc
    return _capture(str(path),api,mutable=mutable)
