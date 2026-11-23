"""Local filesystem operations whose ownership or atomicity is platform-specific."""
from contextlib import contextmanager
import os
import stat
import time


def linked(path):
    try:
        st = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def publish_new(source, destination):
    # Both paths are on the same filesystem. Windows rename refuses replacement.
    if os.name == "nt":
        os.rename(source, destination)
    else:
        os.link(source, destination)


def file_identity(path):
    st = path.stat()
    # NTFS file IDs can exceed SQLite's signed 64-bit integer range.
    return tuple(i if i < 2**63 else "id:" + str(i) for i in (st.st_dev, st.st_ino))


@contextmanager
def exclusive_file(path, *, wait=True):
    """Yield an open descriptor (POSIX) or handle (Windows) suitable for inheritance."""
    if os.name == "nt":
        import _winapi
        import msvcrt
        while True:
            try:
                # No share flags: duplicates inherited by a worker retain this exclusion.
                # OPEN_ALWAYS and FILE_FLAG_OPEN_REPARSE_POINT open the link itself.
                handle = _winapi.CreateFile(str(path), 0xC0000000, 0, 0, 4, 0x00200000, 0)
                break
            except OSError as exc:
                if exc.winerror != 32:
                    raise
                if not wait:
                    raise BlockingIOError("File is locked.") from exc
                time.sleep(0.05)
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("A lock must be a regular file.")
            yield handle
        finally:
            os.close(fd)
    else:
        import fcntl
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield fd
        finally:
            os.close(fd)
