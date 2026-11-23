"""Add missing book links to the shelf README while retaining editorial notes."""
from contextlib import closing
from html import escape
import os
from pathlib import Path
import re
from shutil import copymode
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote

from .. import book
from ..filesystem import exclusive_file, linked


TABLE = "| 书名 | 已有内容 |"
DIVIDER = "| --- | --- |"
BOOK_LINK = re.compile(r"^\s*\|\s*\[.*?\]\((.+?)\)\s*\|")


def append_rows(lines, group, directories, page, newline):
    heading = f"## {group}"
    start = next((i for i, line in enumerate(lines) if line.rstrip() == heading), len(lines))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,2}\s", lines[i])), len(lines))
    section = lines[start:end]
    targets = set()
    for line in section:
        match = BOOK_LINK.match(line)
        if match:
            targets.add(Path(unquote(match[1].strip("<>"))).as_posix())
    rows = []
    for directory in directories:
        relative = f"{group}/{directory.name}"
        target = f"{relative}/{page}"
        if relative in targets or target in targets:
            continue
        with closing(book.connect(directory)) as db:
            title = db.execute("SELECT title FROM book").fetchone()[0]
        label = escape(" ".join(title.splitlines()), quote=False)
        label = re.sub(r"[\\|`*_\[\]~]", lambda m: f"&#{ord(m[0])};", label)
        rows.append(f"| [{label}]({quote(target)}) | |")
    if not rows:
        return

    table = next((i for i, line in enumerate(section[:-1])
                  if line.strip() == TABLE and section[i + 1].strip() == DIVIDER), None)
    if table is None:
        insert = end if not section else start + 1
        block = (["", heading] if not section else []) + ["", TABLE, DIVIDER] + rows + [""]
    else:
        insert = start + table + 2
        while insert < end and lines[insert].lstrip().startswith("|"):
            insert += 1
        block = rows
    if insert and not lines[insert - 1].endswith(("\n", "\r")):
        block.insert(0, "")
    lines[insert:insert] = [line + newline for line in block]


def update(root, groups, page):
    path = root / "README.md"
    with exclusive_file(root / ".bookshelf.lock"):
        if linked(path) or (path.exists() and not path.is_file()):
            raise ValueError(f"Shelf README must be a regular file: {path}")
        original = path.read_bytes() if path.exists() else None
        text = original.decode("utf-8-sig") if original is not None else "# 本机书架\n"
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        for group, directories in groups.items():
            append_rows(lines, group, directories, page, newline)
        encoding = "utf-8-sig" if original and original.startswith(b"\xef\xbb\xbf") else "utf-8"
        data = "".join(lines).encode(encoding)
        if data == original:
            return
        with TemporaryDirectory(dir=root) as work:
            pending = Path(work) / "README.md"
            pending.write_bytes(data)
            if original is None:
                pending.chmod(0o600)
            else:
                copymode(path, pending)
            os.replace(pending, path)
