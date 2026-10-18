"""Darwin volume locality. ABI: apple-oss-distributions/xnu/bsd/sys/mount.h."""
import ctypes as C
import os
from pathlib import Path

class StatFS64(C.Structure):
    _fields_ = [('f_bsize', C.c_uint32), ('f_iosize', C.c_int32),
                ('f_blocks', C.c_uint64), ('f_bfree', C.c_uint64), ('f_bavail', C.c_uint64),
                ('f_files', C.c_uint64), ('f_ffree', C.c_uint64), ('f_fsid', C.c_int32 * 2),
                ('f_owner', C.c_uint32), ('f_type', C.c_uint32), ('f_flags', C.c_uint32),
                ('f_fssubtype', C.c_uint32), ('f_fstypename', C.c_char * 16),
                ('f_mntonname', C.c_char * 1024), ('f_mntfromname', C.c_char * 1024),
                ('f_flags_ext', C.c_uint32), ('f_reserved', C.c_uint32 * 7)]


def is_local(path: Path, library=None) -> bool:
    library = library if library is not None else C.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    statfs = getattr(library, 'statfs$INODE64', None) or getattr(library, 'statfs64', None)
    if statfs is None:
        raise OSError('Darwin statfs64 ABI unavailable')
    statfs.argtypes = [C.c_char_p, C.POINTER(StatFS64)]
    statfs.restype = C.c_int
    existing = path
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    result = StatFS64()
    if statfs(os.fsencode(existing), C.byref(result)) != 0:
        raise OSError(C.get_errno(), 'Cannot identify local volume')
    return bool(result.f_flags & 0x00001000)
