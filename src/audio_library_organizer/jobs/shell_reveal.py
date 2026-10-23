"""Select one already-authorized file, without a command line or shell script.

Called only by MenuWork off the GUI thread: SHParseDisplayName can perform I/O.
The guard revalidates cancellation, library context and material after parsing.
"""
import ctypes
import ntpath


def reveal_file(path, *, guard):
    name = str(path)
    if not ntpath.isabs(name) or not ntpath.splitdrive(name)[0] or '\x00' in name:
        raise ValueError('Explorer selection requires an absolute verified file path')
    # Restrict native dependencies to the Windows system directory.
    shell = ctypes.WinDLL('shell32.dll', winmode=0x00000800)
    ole = ctypes.WinDLL('ole32.dll', winmode=0x00000800)
    pointer = ctypes.c_void_p
    hresult = ctypes.c_int32
    ole.CoInitializeEx.argtypes = [pointer, ctypes.c_uint32]
    ole.CoInitializeEx.restype = hresult
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [pointer]
    ole.CoTaskMemFree.restype = None
    shell.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, pointer, ctypes.POINTER(pointer),
                                         ctypes.c_uint32, pointer]
    shell.SHParseDisplayName.restype = hresult
    shell.SHOpenFolderAndSelectItems.argtypes = [pointer, ctypes.c_uint32, pointer, ctypes.c_uint32]
    shell.SHOpenFolderAndSelectItems.restype = hresult
    if ole.CoInitializeEx(None, 2) < 0:
        raise OSError('Could not initialize Explorer selection')
    pidl = pointer()
    try:
        guard()
        if shell.SHParseDisplayName(name, None, ctypes.byref(pidl), 0, None) < 0 or not pidl:
            raise OSError('Could not resolve verified file for Explorer selection')
        guard()
        # cidl=0: the absolute PIDL identifies the item; Windows opens its parent
        # and selects that exact item. Do not pass only the parent directory.
        if shell.SHOpenFolderAndSelectItems(pidl, 0, None, 0) < 0:
            raise OSError('Could not select verified file in Explorer')
    finally:
        if pidl:
            ole.CoTaskMemFree(pidl)
        ole.CoUninitialize()
