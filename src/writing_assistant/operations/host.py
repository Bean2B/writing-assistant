"""User-owned local runtime registry and verified release switching for local installations."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile

from ..filesystem import exclusive_file, file_identity, linked


def register(subs):
    p = subs.add_parser("host", help="manage a private local runtime installation")
    p.add_argument("--root", type=Path, required=True)
    group = p.add_subparsers(dest="host_action", required=True)
    group.add_parser("enroll", help="create a new host registry")
    group.add_parser("status")
    p = group.add_parser("stage", help="unpack a release matching the supplied digest")
    p.add_argument("archive", type=Path)
    p.add_argument("--sha256", required=True)
    for op in ("qualify", "activate"):
        p = group.add_parser(op)
        p.add_argument("digest")
    p = group.add_parser("rollback")
    p.add_argument("--from", dest="from_digest", required=True)


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def check_dir(path):
    if linked(path) or not path.is_dir():
        raise ValueError("Host directory must be a regular directory.")
    if os.name == "nt":
        # Inspect actual Windows owner and access rules. chmod mode bits do not represent a DACL.
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        check = """
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.SecurityIdentifier]
$user = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$acl = Get-Acl -LiteralPath $env:WA_REGISTRY_ROOT
if ($acl.GetOwner($sid).Value -ne $user) { exit 1 }
# CPython grants OWNER RIGHTS when mkdir creates a protected directory.
$allowed = @($user, 'S-1-3-4', 'S-1-5-18', 'S-1-5-32-544')
$rules = @($acl.GetAccessRules($true, $true, $sid) | Where-Object { $_.AccessControlType -eq 'Allow' })
if (!$rules.Count) { exit 1 }
foreach ($rule in $rules) { if ($rule.IdentityReference.Value -notin $allowed) { exit 1 } }
"""
        checked = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", check],
                                 env={**os.environ, "WA_REGISTRY_ROOT": str(path)}, capture_output=True, timeout=20)
        if checked.returncode:
            raise ValueError("Host directory must be owned by you and accessible only to you, SYSTEM and Administrators.")
    else:
        st = path.stat()
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError("Host directory must be private and owned by the current user.")


@contextmanager
def registry(root):
    check_dir(root)
    if linked(root / "runtimes"):
        raise ValueError("Unexpected runtime directory.")
    lock = root / "registry.lock"
    with exclusive_file(lock):
        path = root / "registry.sqlite3"
        if linked(path) or not path.is_file():
            raise ValueError("Unregistered host.")
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                info = db.execute("SELECT * FROM identity").fetchone()
                if (info["device"], info["inode"]) != file_identity(root):
                    raise ValueError("Host registry belongs to a different directory.")
                yield db, info
        finally:
            db.close()


def enroll(root):
    if os.name == "nt" and sys.version_info < (3, 13):
        raise ValueError("Windows host enrollment requires Python 3.13+ for private directory creation.")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    check_dir(root)
    (root / "runtimes").mkdir(mode=0o700)
    ident = uuid.uuid4().hex
    conn = sqlite3.connect(root / "registry.sqlite3")
    try:
        conn.executescript("""
            CREATE TABLE identity (id TEXT,device INTEGER,inode INTEGER,active TEXT,previous TEXT);
            CREATE TABLE runtimes (digest TEXT PRIMARY KEY,manifest TEXT,qualified INTEGER DEFAULT 0);
        """)
        with conn:
            conn.execute("INSERT INTO identity VALUES(?,?,?,NULL,NULL)", (ident, *file_identity(root)))
    finally:
        conn.close()
    return {"host": ident}


def windows_reserved(part):
    # Device names remain special even when they have an extension.
    return part.split(".", 1)[0].rstrip(" ").upper() in WINDOWS_DEVICES


WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
}


def manifest_from(archive):
    names = archive.namelist()
    if (len(names) > 384 or len(set(names)) != len(names) or "runtime-manifest.json" not in names
            or sum(x.file_size for x in archive.infolist()) > 16 * 1024 * 1024):
        raise ValueError("Invalid release archive.")
    m = json.loads(archive.read("runtime-manifest.json"))
    if not isinstance(m, dict) or m.get("format") != "writing-assistant/runtime/1" or not isinstance(m.get("files"), dict):
        raise ValueError("Unexpected runtime manifest.")
    if set(names) != set(m["files"]) | {"runtime-manifest.json"} or "scripts/writing-assistant" not in m["files"]:
        raise ValueError("Manifest and archive contents disagree.")
    spelling = {"runtime-manifest.json": "runtime-manifest.json"}
    for name, checksum in m["files"].items():
        path = PurePosixPath(name)
        for i, part in enumerate(path.parts, 1):
            prefix = "/".join(path.parts[:i])
            if (re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((" ", "."))
                    or windows_reserved(part) or spelling.setdefault(prefix.casefold(), prefix) != prefix):
                raise ValueError("Release paths must be distinct portable filenames.")
        if (not path.parts or path.is_absolute() or str(path) != name or ".." in path.parts or "\\" in name
                or not isinstance(checksum, str) or not re.fullmatch("[0-9a-f]{64}", checksum)):
            raise ValueError("Invalid release member.")
    file_names = set(names)
    if any(str(parent) in file_names for name in m["files"] for parent in PurePosixPath(name).parents):
        raise ValueError("A release file cannot also be a directory.")
    return m


def verify(folder, manifest):
    actual = set()
    for path in folder.rglob("*"):
        if linked(path):
            raise ValueError("Unexpected runtime symlink.")
        if path.is_file():
            name = path.relative_to(folder).as_posix()
            actual.add(name)
            if name not in manifest["files"] or hash_bytes(path.read_bytes()) != manifest["files"][name]:
                raise ValueError("Installed file differs from the recorded release.")
    if actual != set(manifest["files"]):
        raise ValueError("Installed runtime is incomplete.")


def installed(root, db, digest):
    row = db.execute("SELECT * FROM runtimes WHERE digest=?", (digest,)).fetchone()
    if not row:
        raise ValueError("Unknown runtime digest.")
    manifest = json.loads(row["manifest"])
    folder = root / "runtimes" / digest
    if linked(folder):
        raise ValueError("Unexpected runtime directory.")
    verify(folder, manifest)
    return row, manifest, folder


def probe(folder, manifest):
    env = {"PATH": os.defpath}
    if os.name == "nt":
        env.update({k: v for k, v in os.environ.items() if k in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}})
    result = subprocess.run([sys.executable, "-I", "-B", str(folder / "scripts/writing-assistant"), "doctor"],
                            cwd=folder, capture_output=True, timeout=20, env=env)
    if result.returncode:
        raise ValueError("Fresh runtime process failed.")
    info = json.loads(result.stdout)
    if not isinstance(info, dict) or info.get("product") != "Writing Assistant" or info.get("version") != manifest["version"]:
        raise ValueError("Fresh runtime identity differs from the package.")
    return info


def execute(args):
    root = args.root.absolute()
    op = args.host_action
    if op == "enroll":
        return enroll(root)
    with registry(root) as (db, info):
        if op == "status":
            if info["active"]:
                installed(root, db, info["active"])
            return {"host": info["id"], "active": info["active"], "previous": info["previous"],
                    "runtimes": [dict(r) for r in db.execute("SELECT digest,qualified FROM runtimes ORDER BY digest")]}
        if op == "stage":
            with args.archive.open("rb") as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            digest = hash_bytes(raw)
            if digest != args.sha256 or len(raw) > 16 * 1024 * 1024:
                raise ValueError("Release digest or size mismatch.")
            dest = root / "runtimes" / digest
            with zipfile.ZipFile(io.BytesIO(raw)) as z, tempfile.TemporaryDirectory(dir=root) as temp:
                manifest = manifest_from(z)
                candidate = Path(temp) / "files"
                candidate.mkdir()
                for name, expected in manifest["files"].items():
                    data = z.read(name)
                    if hash_bytes(data) != expected:
                        raise ValueError("Release payload digest mismatch.")
                    path = candidate / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    if name in {"scripts/writing-assistant", "scripts/writing-assistant-provider"}:
                        path.chmod(0o700)
                if linked(dest):
                    raise ValueError("Unexpected runtime directory.")
                if dest.exists():
                    verify(dest, manifest)
                else:
                    candidate.rename(dest)
            db.execute("INSERT OR IGNORE INTO runtimes(digest,manifest) VALUES(?,?)",
                       (digest, json.dumps(manifest, sort_keys=True)))
            return {"staged": digest, "version": manifest["version"]}
        if op == "rollback":
            if info["active"] != args.from_digest or not info["previous"]:
                raise ValueError("Rollback does not match the active and previous installations.")
            target = info["previous"]
        else:
            target = args.digest
        row, manifest, folder = installed(root, db, target)
        if op == "qualify":
            observed = probe(folder, manifest)
            db.execute("UPDATE runtimes SET qualified=1 WHERE digest=?", (target,))
            return {"qualified": target, "observation": observed}
        if not row["qualified"]:
            raise ValueError("Qualify the release in a fresh process before activation.")
        probe(folder, manifest)
        if target != info["active"]:
            db.execute("UPDATE identity SET previous=active,active=?", (target,))
        launcher = folder / "scripts/writing-assistant"
        if os.name == "nt" and "scripts/writing-assistant.cmd" in manifest["files"]:
            launcher = launcher.with_suffix(".cmd")
        return {"active": target, "launcher": str(launcher)}
