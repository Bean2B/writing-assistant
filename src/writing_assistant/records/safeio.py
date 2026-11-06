"""Bounded, handle-relative local I/O. See docs/privacy.md.

Windows supports local NTFS only. POSIX requires a stable ancestor namespace;
directory fds are not an OS sandbox against arbitrary same-uid renames/writes.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
import stat
import time
import uuid
import tempfile
from contextlib import contextmanager

CONTROL_LIMIT = 2 * 1024 * 1024
LOTUS_PUBLICATION_PROTOCOL = 1
FILE_LIMIT = 64 * 1024 * 1024
CHUNK = 1024 * 1024
LIMITATION = ("Authenticated local I/O, not an OS access sandbox: POSIX requires stable "
              "ancestor names; arbitrary same-privilege inode/namespace changes are not excluded.")


class HashMismatch(ValueError):
    """Preserve the guard's public hash-mismatch diagnostic without exposing bytes."""


class Budget:
    def __init__(self, *, file_bytes=FILE_LIMIT, input_bytes=256 * 1024 * 1024,
                 read_bytes=1024 * 1024 * 1024, control_bytes=8 * 1024 * 1024, seconds=120):
        self.file_bytes, self.input_bytes = file_bytes, input_bytes
        self.read_limit, self.control_limit = read_bytes, control_bytes
        self.deadline = time.monotonic() + seconds
        self.bytes_read = 0
        self._versions, self._controls = {}, {}

    def tick(self):
        if time.monotonic() > self.deadline:
            raise ValueError("local I/O deadline exceeded")

    def reserve(self, name, expected, size, control):
        self.tick()
        versions = self._controls if control else self._versions
        key = (name, expected)
        versions[key] = max(size, versions.get(key, 0))
        if sum(versions.values()) > (self.control_limit if control else self.input_bytes):
            raise ValueError("local I/O declared byte budget exceeded")

    def consume(self, count):
        self.tick()
        self.bytes_read += count
        if self.bytes_read > self.read_limit:
            raise ValueError("local I/O read budget exceeded")


def logical_root(root):
    path = Path(root)
    if ".." in path.parts:
        raise ValueError("root traversal is forbidden")
    return Path(os.path.abspath(path))


_UNSAFE_RELATIVE = re.compile(r'[\\:*?\[\]\x00-\x1f"<>|]')


def relative_name(root, value):
    path = Path(value)
    if path.is_absolute():
        path = path.relative_to(root)
    value = path.as_posix()
    parts = value.split("/")
    if (not value or len(value) > 4096 or _UNSAFE_RELATIVE.search(value) is not None
            or any(p in {"", ".", ".."} or p.endswith((" ", ".")) for p in parts)):
        raise ValueError("explicit portable relative path required")
    return tuple(parts)


if os.name == "nt":
    import ctypes
    from ctypes import wintypes as w

    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _n = ctypes.WinDLL("ntdll", use_last_error=True)

    class _U(ctypes.Structure):
        _fields_ = [("Length", w.USHORT), ("MaximumLength", w.USHORT), ("Buffer", w.LPWSTR)]

    class _OA(ctypes.Structure):
        _fields_ = [("Length", w.ULONG), ("RootDirectory", w.HANDLE), ("ObjectName", ctypes.POINTER(_U)),
                    ("Attributes", w.ULONG), ("SecurityDescriptor", w.LPVOID), ("SecurityQualityOfService", w.LPVOID)]

    class _Status(ctypes.Union):
        _fields_ = [("Status", w.LONG), ("Pointer", w.LPVOID)]

    class _IOS(ctypes.Structure):
        _fields_ = [("u", _Status), ("Information", ctypes.c_size_t)]

    class _Info(ctypes.Structure):
        _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME), ("accessed", w.FILETIME),
                    ("written", w.FILETIME), ("volume", w.DWORD), ("size_high", w.DWORD),
                    ("size_low", w.DWORD), ("links", w.DWORD), ("index_high", w.DWORD), ("index_low", w.DWORD)]

    class _Rename(ctypes.Structure):
        _fields_ = [("replace", w.BOOL), ("parent", w.HANDLE), ("length", w.DWORD), ("name", w.WCHAR * 1)]

    for _name, _args, _result in [
        ("CreateFileW", [w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE], w.HANDLE),
        ("CloseHandle", [w.HANDLE], w.BOOL),
        ("GetFileType", [w.HANDLE], w.DWORD),
        ("GetFileInformationByHandle", [w.HANDLE,ctypes.POINTER(_Info)], w.BOOL),
        ("GetFinalPathNameByHandleW", [w.HANDLE,w.LPWSTR,w.DWORD,w.DWORD], w.DWORD),
        ("ReadFile", [w.HANDLE,w.LPVOID,w.DWORD,ctypes.POINTER(w.DWORD),w.LPVOID], w.BOOL),
        ("WriteFile", [w.HANDLE,w.LPCVOID,w.DWORD,ctypes.POINTER(w.DWORD),w.LPVOID], w.BOOL),
        ("FlushFileBuffers", [w.HANDLE], w.BOOL),
        ("SetFileInformationByHandle", [w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD], w.BOOL),
        ("GetVolumeInformationByHandleW", [w.HANDLE,w.LPWSTR,w.DWORD,ctypes.POINTER(w.DWORD),
                                          ctypes.POINTER(w.DWORD),ctypes.POINTER(w.DWORD),w.LPWSTR,w.DWORD], w.BOOL),
    ]:
        _fn = getattr(_k, _name)
        _fn.argtypes, _fn.restype = _args, _result
    _n.NtCreateFile.argtypes = [ctypes.POINTER(w.HANDLE),w.ULONG,ctypes.POINTER(_OA),ctypes.POINTER(_IOS),
                               w.LPVOID,w.ULONG,w.ULONG,w.ULONG,w.ULONG,w.LPVOID,w.ULONG]
    _n.NtCreateFile.restype = w.LONG
    _n.NtSetInformationFile.argtypes = [w.HANDLE, ctypes.POINTER(_IOS), w.LPVOID, w.ULONG, w.ULONG]
    _n.NtSetInformationFile.restype = w.LONG


def _close(handle):
    if os.name == "nt":
        if not _k.CloseHandle(handle):
            raise OSError("closing local I/O handle failed")
    else:
        os.close(handle)


def _open_child(parent, name, *, directory=False, create=False, write=False, delete=False):
    if os.name == "nt":
        raw = name.encode("utf-16-le")
        buf = ctypes.create_unicode_buffer(name)
        value = _U(len(raw), len(raw) + 2, ctypes.cast(buf, w.LPWSTR))
        oa = _OA(ctypes.sizeof(_OA), parent, ctypes.pointer(value), 0x1040, None, None)
        ios, handle = _IOS(), w.HANDLE()
        access = (0x120196 if write else 0x120089) | (0x10000 if delete else 0)
        status = _n.NtCreateFile(ctypes.byref(handle), access, ctypes.byref(oa), ctypes.byref(ios),
                                None, 0x10 if directory else 0x80, 3 if directory else 1, 2 if create else 1,
                                (1 if directory else 0x40) | 0x20 | 0x200000, None, 0)
        if status < 0:
            if status & 0xffffffff == 0xc0000034:
                raise FileNotFoundError("local I/O component missing")
            if status & 0xffffffff == 0xc0000035:
                raise FileExistsError("local I/O component already exists")
            raise OSError("native relative open refused: " + hex(status & 0xffffffff))
        if create and ios.Information != 2:
            _close(handle.value)
            raise OSError("exclusive native creation did not create a new object")
        return handle.value
    flags = os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_WRONLY if write else os.O_RDONLY)
    if directory:
        flags |= os.O_DIRECTORY
        if create:
            os.mkdir(name, mode=0o700, dir_fd=parent)
    elif create:
        flags |= os.O_CREAT | os.O_EXCL
    return os.open(name, flags, mode=0o600, dir_fd=parent)


def _state(handle, expected, directory):
    """Authenticate before read/write; no file contents are inspected here."""
    if os.name == "nt":
        row = _Info()
        if (_k.GetFileType(handle) != 1 or not _k.GetFileInformationByHandle(handle, ctypes.byref(row))
                or bool(row.attributes & 0x10) != directory or row.attributes & 0x400
                or (not directory and row.links != 1)):
            raise ValueError("local I/O requires a non-reparse ordinary single-link file or directory")
        buf = ctypes.create_unicode_buffer(32768)
        size = _k.GetFinalPathNameByHandleW(handle, buf, len(buf), 0)
        if not 0 < size < len(buf) or not buf.value.startswith("\\\\?\\"):
            raise ValueError("native final path is unavailable or unsupported")
        actual = buf.value[4:]
        if os.path.normcase(actual).rstrip("\\") != os.path.normcase(str(expected)).rstrip("\\"):
            raise ValueError("native final path differs from the logical path")
        identity = (row.volume, row.index_high, row.index_low)
        return identity, (row.size_high << 32) | row.size_low, (row.written.dwHighDateTime, row.written.dwLowDateTime)
    row = os.fstat(handle)
    if (not (stat.S_ISDIR(row.st_mode) if directory else stat.S_ISREG(row.st_mode))
            or (not directory and row.st_nlink != 1)):
        raise ValueError("local I/O requires ordinary single-link files")
    return (row.st_dev, row.st_ino), row.st_size, (row.st_mtime_ns, row.st_ctime_ns)


def _read_chunk(handle, count):
    if os.name == "nt":
        buf, received = ctypes.create_string_buffer(count), w.DWORD()
        if not _k.ReadFile(handle, buf, count, ctypes.byref(received), None):
            raise OSError("native read failed")
        return buf.raw[:received.value]
    return os.read(handle, count)


def _write_chunk(handle, raw):
    if os.name == "nt":
        count = w.DWORD()
        if not _k.WriteFile(handle, raw, len(raw), ctypes.byref(count), None):
            raise OSError("native write failed")
        return count.value
    return os.write(handle, raw)


class SafeSession:
    def __init__(self, root, budget=None):
        self.root = logical_root(root)
        self.budget = budget if budget is not None else Budget()
        self._anchors, self._dirs = [], {}
        self._root_anchors, self._dir_anchors = (), {}

    def __enter__(self):
        try:
            if os.name == "nt":
                if len(self.root.drive) != 2 or self.root.drive[1] != ":":
                    raise ValueError("only local drive paths are supported")
                cursor = Path(self.root.anchor)
                handle = _k.CreateFileW(str(cursor), 0x80000000, 3, None, 3, 0x02200000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise OSError("native volume root open failed")
                self._register(cursor, handle)
                fs = ctypes.create_unicode_buffer(32)
                if not _k.GetVolumeInformationByHandleW(handle, None, 0, None, None, None, fs, len(fs)) or fs.value != "NTFS":
                    raise ValueError("safe Windows output currently requires local NTFS")
            else:
                if (not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
                        or any(fn not in os.supports_dir_fd for fn in (os.open, os.mkdir, os.stat, os.link, os.unlink))):
                    raise ValueError("required handle-relative POSIX capabilities unavailable")
                cursor = Path(self.root.anchor)
                handle = os.open(str(cursor), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self._register(cursor, handle)
            for component in self.root.parts[1:]:
                self._verify_dirs()
                handle = _open_child(handle, component, directory=True)
                cursor /= component
                self._register(cursor, handle)
            self._dirs[()] = handle
            self._root_anchors = tuple(self._anchors)
            return self
        except BaseException:
            self.close()
            raise

    def _register(self, path, handle):
        try:
            identity = _state(handle, path, True)[0]
        except BaseException:
            _close(handle)
            raise
        self._anchors.append((path, handle, identity))

    def _verify_dirs(self, parts=None):
        self.budget.tick()
        # All handles remain pinned until close. A read must reauthenticate its
        # actual ancestors, not every unrelated directory ever visited by a DAG.
        anchors = self._anchors if parts is None else list(self._root_anchors) + [
            self._dir_anchors[tuple(parts[:index])]
            for index in range(1, len(parts) + 1) if tuple(parts[:index]) in self._dir_anchors]
        for path, handle, identity in anchors:
            if _state(handle, path, True)[0] != identity:
                raise ValueError("held directory identity changed")
            if os.name != "nt":
                row = os.stat(path, follow_symlinks=False)
                if not stat.S_ISDIR(row.st_mode) or (row.st_dev, row.st_ino) != identity:
                    raise ValueError("POSIX ancestor namespace changed")

    def directory(self, parts, *, create=False, exclusive=False):
        key = tuple(parts)
        if key in self._dirs:
            self._verify_dirs(parts)
            if exclusive and parts:
                raise FileExistsError("directory already exists")
            return self._dirs[key]
        parent = self._dirs[()]
        for index, name in enumerate(parts):
            key = tuple(parts[:index + 1])
            self._verify_dirs(parts[:index])
            if key in self._dirs:
                if exclusive and index == len(parts) - 1:
                    raise FileExistsError("directory already exists")
                parent = self._dirs[key]
                continue
            new = exclusive and index == len(parts) - 1
            try:
                child = _open_child(parent, name, directory=True, create=new)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    child = _open_child(parent, name, directory=True, create=True)
                except FileExistsError:
                    if new:
                        raise
                    # A concurrent session may create a reusable common parent.
                    # Reopen from the same held parent and authenticate below;
                    # an exclusive leaf must never take this reuse path.
                    self._verify_dirs(parts[:index])
                    child = _open_child(parent, name, directory=True)
            self._register(self.root.joinpath(*key), child)
            self._dir_anchors[key] = self._anchors[-1]
            self._dirs[key], parent = child, child
        return parent

    def mkdir(self, path, *, exclusive=False):
        self.directory(relative_name(self.root, path), create=True, exclusive=exclusive)

    def _read(self, path, expected, limit, collect, control, private_sink=None):
        if expected is not None:
            expected = expected.lower()
        parts = relative_name(self.root, path)
        parent = self.directory(parts[:-1])
        self._verify_dirs(parts[:-1])
        handle = _open_child(parent, parts[-1])
        try:
            logical = self.root.joinpath(*parts)
            initial = _state(handle, logical, False)
            size = initial[1]
            if size > limit:
                raise ValueError("local I/O file exceeds byte limit")
            self.budget.reserve("/".join(parts), expected, size, control)
            digest, raw, total = hashlib.sha256(), bytearray() if collect else None, 0
            while True:
                self._verify_dirs(parts[:-1])
                if _state(handle, logical, False) != initial:
                    raise ValueError("input identity or metadata changed during read")
                block = _read_chunk(handle, min(CHUNK, limit - total + 1))
                self.budget.consume(len(block))
                if not block:
                    break
                total += len(block)
                if total > limit or total > size:
                    raise ValueError("input grew beyond authenticated size")
                digest.update(block)
                if collect:
                    raw.extend(block)
                if private_sink is not None:
                    account = getattr(self.budget, "disk", None)
                    if account is not None:
                        account(len(block))
                    private_sink.write(block)
            if total != size or _state(handle, logical, False) != initial:
                raise ValueError("input was truncated or changed")
            actual = digest.hexdigest()
            if expected is not None and actual != expected.lower():
                raise HashMismatch("input SHA-256 differs from declared version")
            return bytes(raw) if collect else actual
        finally:
            _close(handle)

    def read_bytes(self, path, expected_sha256=None, *, limit=None, control=False):
        return self._read(path, expected_sha256, self.budget.file_bytes if limit is None else limit, True, control)

    def hash_file(self, path, expected_sha256=None):
        return self._read(path, expected_sha256, self.budget.file_bytes, False, False)

    @contextmanager
    def authenticated_stream(self, path, expected_sha256, *, limit=None):
        """Yield a private seekable stream only after complete native/hash checks.

        Bytes never reach a caller-supplied sink before authentication. The
        bounded disk store avoids retaining a large source in process memory.
        """
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise ValueError("authenticated stream requires an exact SHA-256")
        with tempfile.TemporaryFile(mode="w+b") as private:
            self._read(path, expected_sha256, self.budget.file_bytes if limit is None else limit,
                       False, False, private_sink=private)
            private.seek(0)
            yield private

    def inspect_file(self, path):
        """Check current native identity/ancestors; this is not a content receipt."""
        parts = relative_name(self.root, path)
        parent = self.directory(parts[:-1])
        self._verify_dirs(parts[:-1])
        handle = _open_child(parent, parts[-1])
        try:
            state = _state(handle, self.root.joinpath(*parts), False)
            self._verify_dirs(parts[:-1])
            return state
        finally:
            _close(handle)

    def _write(self, path, raw, marker=False):
        if not isinstance(raw, bytes) or len(raw) > (CONTROL_LIMIT if marker else self.budget.file_bytes):
            raise ValueError("bounded immutable output bytes required")
        parts = relative_name(self.root, path)
        parent = self.directory(parts[:-1])
        self._verify_dirs(parts[:-1])
        name = ".run.pending-" + uuid.uuid4().hex if marker else parts[-1]
        handle = _open_child(parent, name, create=True, write=True, delete=marker)
        logical = self.root.joinpath(*parts[:-1], name)
        try:
            identity = _state(handle, logical, False)[0]
            position = 0
            while position < len(raw):
                self._verify_dirs(parts[:-1])
                if _state(handle, logical, False)[0] != identity:
                    raise ValueError("output identity changed")
                block = raw[position:position + CHUNK]
                count = _write_chunk(handle, block)
                if not 0 < count <= len(block):
                    raise OSError("output short write made no progress")
                position += count
            self._verify_dirs(parts[:-1])
            _state(handle, logical, False)
            if os.name == "nt":
                if not _k.FlushFileBuffers(handle):
                    raise OSError("output flush failed")
            else:
                os.fsync(handle)
            if marker:
                self._publish(parent, handle, logical, parts[-1], identity)
        finally:
            _close(handle)

    def _publish(self, parent, handle, logical, name, identity):
        self._verify_dirs(relative_name(self.root, logical)[:-1])
        if _state(handle, logical, False)[0] != identity:
            raise ValueError("pending marker identity changed")
        if os.name == "nt":
            encoded = name.encode("utf-16-le")
            # Native FILE_RENAME_INFORMATION requires sizeof(struct) plus the
            # filename bytes, including the platform's trailing padding.
            size = ctypes.sizeof(_Rename) + len(encoded)
            buf = ctypes.create_string_buffer(size)
            row = _Rename.from_buffer(buf)
            row.replace, row.parent, row.length = False, parent, len(encoded)
            ctypes.memmove(ctypes.addressof(buf) + _Rename.name.offset, encoded, len(encoded))
            ios = _IOS()
            status = _n.NtSetInformationFile(handle, ctypes.byref(ios), buf, size, 10)
            if status < 0:
                raise OSError("atomic no-replace marker publication failed: " + hex(status & 0xffffffff))
        else:
            row = os.stat(logical.name, dir_fd=parent, follow_symlinks=False)
            if (row.st_dev, row.st_ino) != identity:
                raise ValueError("pending marker name changed")
            os.link(logical.name, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            os.unlink(logical.name, dir_fd=parent)

    def write_new(self, path, authenticated_bytes):
        self._write(path, authenticated_bytes)

    def receive_private_file(self, path, producer, size, expected_sha256, expected_git_sha, *, mode="100644"):
        """Receive into private quarantine; publish only authenticated exact bytes.

        Only a private publication EvidenceStore may call this. Unlike actor
        write_new, the random pending file is unauthenticated and must remain
        inaccessible to any consumer until the no-replace commit completes.
        Failure leaves quarantine for the owning store's whole-operation cleanup.
        """
        if not isinstance(size, int) or not 0 <= size <= self.budget.file_bytes:
            raise ValueError("private input exceeds its byte budget")
        parts = relative_name(self.root, path)
        parent = self.directory(parts[:-1], create=True)
        self._verify_dirs(parts[:-1])
        pending = ".publication.pending-" + uuid.uuid4().hex
        logical = self.root.joinpath(*parts[:-1], pending)
        handle = _open_child(parent, pending, create=True, write=True, delete=True)
        total, digest = 0, hashlib.sha256()
        git = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")
        try:
            identity = _state(handle, logical, False)[0]
            def accept(block):
                nonlocal total
                if not isinstance(block, bytes) or len(block) > CHUNK:
                    raise ValueError("private input requires bounded byte chunks")
                total += len(block)
                if total > size:
                    raise ValueError("private input exceeded its fixed size")
                digest.update(block)
                git.update(block)
                position = 0
                while position < len(block):
                    self._verify_dirs(parts[:-1])
                    if _state(handle, logical, False)[0] != identity:
                        raise ValueError("private staging file identity changed")
                    count = _write_chunk(handle, block[position:])
                    if not 0 < count <= len(block) - position:
                        raise OSError("private staging write made no progress")
                    position += count
            producer(accept)
            if total != size or digest.hexdigest() != expected_sha256 or git.hexdigest() != expected_git_sha:
                raise HashMismatch("private staged blob differs from its fixed digests")
            self._verify_dirs(parts[:-1])
            if _state(handle, logical, False)[1] != size:
                raise ValueError("private staging size changed")
            if os.name == "nt":
                if not _k.FlushFileBuffers(handle):
                    raise OSError("private staging flush failed")
            else:
                os.fsync(handle)
            if os.name != "nt":
                os.fchmod(handle, 0o755 if mode == "100755" else 0o644)
            self._publish(parent, handle, logical, parts[-1], identity)
            self._verify_dirs(parts[:-1])
            committed = _state(handle, self.root.joinpath(*parts), False)
            if committed[0] != identity or committed[1] != size:
                raise ValueError("private committed object changed")
        finally:
            _close(handle)

    def publish_record(self, path, bounded_record_bytes):
        self._write(path, bounded_record_bytes, marker=True)

    def close(self):
        failure = None
        while self._anchors:
            _, handle, _ = self._anchors.pop()
            try:
                _close(handle)
            except OSError as exc:
                failure = exc
        self._dirs.clear()
        self._dir_anchors.clear()
        self._root_anchors = ()
        if failure is not None:
            raise failure

    def __exit__(self, *exc):
        self.close()
