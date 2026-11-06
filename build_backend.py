"""Dependency-free, deterministic PEP 517 builder using an explicit file list."""

import base64
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).parent
NAME = "writing_assistant"
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
VERSION = PROJECT["version"]
DESCRIPTION = PROJECT["description"]
DIST_INFO = f"{NAME}-{VERSION}.dist-info"
EXCLUDED_PREFIXES = ("tests/", ".github/workflows/", ".agents/", ".githooks/")
EXCLUDED_PATHS = frozenset({
    ".githooks/pre-push", ".github/pull_request_template.md", "agents.md",
    "contributing.md", "docs/maintenance.md", "scripts/public_preflight.py",
    "scripts/export_public.py",
})
# Keep distribution guards self-contained when maintenance tools are absent.
PRIVATE_PARTS = frozenset({
    "private", "private-data", "private_data", "personal", "corpus", "corpora",
    "manuscript", "manuscripts", "training", "training-data", "training_data",
    "dataset", "datasets", "credentials", "secrets", "telemetry", "logs",
    "runs", "outputs", ".ssh", ".aws", ".venv", "node_modules", "__pycache__",
})
BLOCKED_SUFFIXES = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".keystore", ".sqlite", ".sqlite3",
    ".db", ".jsonl", ".ndjson", ".csv", ".tsv", ".log", ".zip", ".gz",
    ".pdf", ".doc", ".docx", ".epub", ".png", ".jpg", ".jpeg", ".bin",
})


def files():
    manifest = json.loads((ROOT / "public-files.json").read_bytes())
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "files"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1):
        raise ValueError("invalid_public_manifest")
    entries = manifest["files"]
    if (not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries)
            or len(entries) != len(set(entries))):
        raise ValueError("invalid_public_manifest")
    validated = []
    for entry in entries:
        path = PurePosixPath(entry)
        lowered = entry.casefold()
        if (not path.parts or path.is_absolute() or path.as_posix() != entry
                or ".." in path.parts or "\\" in entry or ".git" in lowered.split("/")
                or any(ord(char) < 32 or ord(char) == 127 for char in entry)):
            raise ValueError("unsafe_public_path")
        if lowered in EXCLUDED_PATHS or lowered.startswith(EXCLUDED_PREFIXES):
            raise ValueError("maintenance_file_not_public")
        if (any(part in PRIVATE_PARTS or PurePosixPath(part).stem in PRIVATE_PARTS
                or part.startswith((".env", "id_rsa", "id_ed25519"))
                for part in lowered.split("/"))
                or path.suffix.casefold() in BLOCKED_SUFFIXES):
            raise ValueError("private_file_not_public")
        validated.append((entry, path))
    # Reject the complete manifest before opening any listed payload.
    result = {}
    for entry, path in validated:
        current = ROOT
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink_not_allowed")
        if not stat.S_ISREG(current.stat().st_mode):
            raise ValueError("regular_files_only")
        result[entry] = current.read_bytes()
    if "public-files.json" not in result:
        raise ValueError("manifest_not_included")
    return result


def metadata():
    if not isinstance(DESCRIPTION, str) or not DESCRIPTION or any(char in DESCRIPTION for char in "\r\n"):
        raise ValueError("invalid_project_description")
    return ("Metadata-Version: 2.4\nName: writing-assistant\nVersion: " + VERSION
            + "\nSummary: " + DESCRIPTION + "\nRequires-Python: >=3.12\n"
              "License-Expression: Apache-2.0\nLicense-File: LICENSE\n"
              "Description-Content-Type: text/plain\n\n" + DESCRIPTION + "\n").encode()


def _hash(raw):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    entries = {}
    source_files = files()
    for path, raw in source_files.items():
        if path.startswith("src/"):
            target = path[4:]
        else:
            target = f"{NAME}-{VERSION}.data/data/share/writing-assistant/{path}"
        entries[target] = raw
    entries[f"{DIST_INFO}/licenses/LICENSE"] = source_files["LICENSE"]
    entries[f"{DIST_INFO}/METADATA"] = metadata()
    entries[f"{DIST_INFO}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: writing-assistant\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    entries[f"{DIST_INFO}/entry_points.txt"] = b"[console_scripts]\nwriting-assistant = writing_assistant.cli:main\n"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for path, raw in sorted(entries.items()):
        writer.writerow((path, _hash(raw), len(raw)))
    record = f"{DIST_INFO}/RECORD"
    writer.writerow((record, "", ""))
    entries[record] = output.getvalue().encode()
    name = f"{NAME}-{VERSION}-py3-none-any.whl"
    Path(wheel_directory).mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(Path(wheel_directory) / name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return name


def build_sdist(sdist_directory, config_settings=None):
    name = f"{NAME}-{VERSION}.tar.gz"
    entries = files()
    entries["PKG-INFO"] = metadata()
    Path(sdist_directory).mkdir(parents=True, exist_ok=True)
    with (Path(sdist_directory) / name).open("wb") as file:
        with gzip.GzipFile(filename="", mode="wb", fileobj=file, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path, raw in sorted(entries.items()):
                    info = tarfile.TarInfo(f"{NAME}-{VERSION}/{path}")
                    info.size = len(raw)
                    info.mode = 0o644
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(raw))
    return name
