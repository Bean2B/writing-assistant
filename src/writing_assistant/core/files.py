"""Descriptor-relative file access; symlink traversal is rejected on macOS/POSIX."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path, PurePosixPath
import secrets
import stat

from .errors import AssistantError, require
from .jsonio import MAX_BYTES


def relative(value):
    require(type(value) is str and bool(value) and "\\" not in value
            and "\0" not in value, "unsafe_path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and all(p not in ("", ".", "..") for p in path.parts), "unsafe_path")
    return path.parts


@contextmanager
def directory_chain(path, create=False):
    """Pin every existing ancestor, including the root, without resolving links."""
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    info = os.fstat(fd)
    identities = [(info.st_dev, info.st_ino)]
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            identities.append((info.st_dev, info.st_ino))
        yield fd, identities
    finally:
        os.close(fd)


@contextmanager
def directory(path, create=False):
    with directory_chain(path, create=create) as (fd, _identities):
        yield fd


@contextmanager
def parent(root, name, create=False):
    parts = relative(name)
    with directory(root) as root_fd:
        fd = os.dup(root_fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, parts[-1]
        finally:
            os.close(fd)


def read(root, name, limit=MAX_BYTES):
    with parent(root, name) as (fd, leaf):
        source = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(source)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "invalid_file")
            chunks, total = [], 0
            while True:
                chunk = os.read(source, min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                require(total <= limit, "input_limit")
            after = os.fstat(source)
            require((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "file_changed")
            return b"".join(chunks)
        finally:
            os.close(source)


def atomic(root, name, raw, *, exclusive=False, limit=MAX_BYTES):
    require(type(raw) is bytes and len(raw) <= limit, "input_limit")
    with parent(root, name, create=True) as (fd, leaf):
        temporary = ".pending-" + secrets.token_hex(16)
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        published = False
        try:
            with os.fdopen(out, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if exclusive:
                os.link(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                published = True
                os.unlink(temporary, dir_fd=fd)
            else:
                try:
                    info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                    require(stat.S_ISREG(info.st_mode), "invalid_file")
                except FileNotFoundError:
                    pass
                os.replace(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd)
                published = True
            os.fsync(fd)
        except OSError:
            if published:
                raise AssistantError("outcome_unknown") from None
            raise
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass


@contextmanager
def lock(root, name="lock"):
    with parent(root, name, create=True) as (fd, leaf):
        handle = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            require(stat.S_ISREG(os.fstat(handle).st_mode), "invalid_file")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        except BlockingIOError:
            raise AssistantError("busy") from None
        finally:
            os.close(handle)
