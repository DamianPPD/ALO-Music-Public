/* Read-only self-process diagnostics, compiled against the installed Windows SDK.
   No OpenProcess, external PID, remote memory or arbitrary CloseHandle. */
#define _WIN32_WINNT 0x0603
#include <windows.h>
#include <processsnapshot.h>
#include <stdint.h>
#include <string.h>

typedef struct N1_ROW {
    uintptr_t value;
    DWORD flags;
    DWORD object_type;
    wchar_t type_name[128];
    wchar_t object_name[2048];
} N1_ROW;

__declspec(dllexport) DWORD n1_row_size(void) { return (DWORD)sizeof(N1_ROW); }
__declspec(dllexport) DWORD n1_count(DWORD *count) {
    return GetProcessHandleCount(GetCurrentProcess(), count) ? ERROR_SUCCESS : GetLastError();
}
__declspec(dllexport) DWORD n1_snapshot(N1_ROW *rows, DWORD capacity, DWORD *used) {
    HPSS snapshot = NULL;
    HPSSWALK marker = NULL;
    PSS_HANDLE_ENTRY entry;
    DWORD status, cleanup;
    *used = 0;
    status = PssCaptureSnapshot(GetCurrentProcess(),
        PSS_CAPTURE_HANDLES | PSS_CAPTURE_HANDLE_NAME_INFORMATION |
        PSS_CAPTURE_HANDLE_BASIC_INFORMATION | PSS_CAPTURE_HANDLE_TYPE_SPECIFIC_INFORMATION,
        0, &snapshot);
    if (status != ERROR_SUCCESS) return status;
    status = PssWalkMarkerCreate(NULL, &marker);
    if (status == ERROR_SUCCESS) {
        for (;;) {
            memset(&entry, 0, sizeof(entry));
            status = PssWalkSnapshot(snapshot, PSS_WALK_HANDLES, marker, &entry, (DWORD)sizeof(entry));
            if (status == ERROR_NO_MORE_ITEMS) { status = ERROR_SUCCESS; break; }
            if (status != ERROR_SUCCESS) break;
            if (*used >= capacity) { status = ERROR_INSUFFICIENT_BUFFER; break; }
            memset(&rows[*used], 0, sizeof(rows[*used]));
            rows[*used].value = (uintptr_t)entry.Handle;
            rows[*used].flags = (DWORD)entry.Flags;
            if (entry.Flags & PSS_HANDLE_HAVE_TYPE) {
                if (entry.TypeNameLength >= sizeof(rows[0].type_name) ||
                    entry.TypeNameLength % sizeof(wchar_t) || (entry.TypeNameLength && !entry.TypeName)) {
                    status = ERROR_INVALID_DATA; break;
                }
                rows[*used].object_type = (DWORD)entry.ObjectType;
                if (entry.TypeNameLength) memcpy(rows[*used].type_name, entry.TypeName, entry.TypeNameLength);
            }
            if (entry.Flags & PSS_HANDLE_HAVE_NAME) {
                if (entry.ObjectNameLength >= sizeof(rows[0].object_name) ||
                    entry.ObjectNameLength % sizeof(wchar_t) || (entry.ObjectNameLength && !entry.ObjectName)) {
                    status = ERROR_INVALID_DATA; break;
                }
                if (entry.ObjectNameLength) memcpy(rows[*used].object_name, entry.ObjectName, entry.ObjectNameLength);
            }
            ++*used;
        }
    }
    if (marker) {
        cleanup = PssWalkMarkerFree(marker);
        if (status == ERROR_SUCCESS) status = cleanup;
    }
    cleanup = PssFreeSnapshot(GetCurrentProcess(), snapshot);
    if (status == ERROR_SUCCESS) status = cleanup;
    return status;
}
