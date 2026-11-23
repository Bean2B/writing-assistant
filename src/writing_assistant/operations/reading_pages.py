"""Generate self-contained local book pages from committed manuscript revisions."""
from contextlib import closing
from html import escape
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.parse import quote

from .. import book
from . import shelf_index


PAGE = "目录.html"
SHELF = "书架.html"
GROUPS = ("创作作品", "学习样本")
MARK = b"<!doctype html>\n<!-- writing-assistant local reading view v1 -->\n"
PACKAGE = Path(__file__).resolve().parents[1]
CSS = PACKAGE / "resources/templates/book/reading.css"
if not CSS.is_file():
    CSS = PACKAGE.parents[1] / "templates/book/reading.css"
CHAPTER_HEADING = re.compile(r"^第\s*[零〇一二两三四五六七八九十百千万\d]+\s*[章回节](?:[\s·：:、.．—-]+.*)?$")


def document(title, header, body):
    html = f"""<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{CSS.read_text(encoding="utf-8")}</style></head>
<body><header>{header}</header>{body}</body></html>
"""
    return MARK + html.encode("utf-8")


def managed(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(len(MARK)) == MARK


def publish(path, data):
    if path.is_symlink() or (path.exists() and not managed(path)):
        raise ValueError(f"Reading page destination already in use: {path}")
    if managed(path) and path.read_bytes() == data:
        return
    with tempfile.TemporaryDirectory(dir=path.parent) as work:
        pending = Path(work) / "page"
        with pending.open("xb") as stream:
            pending.chmod(0o600)
            stream.write(data)
        if not path.exists():
            try:
                if os.name == "nt":
                    os.rename(pending, path)
                else:
                    os.link(pending, path)
                return
            except FileExistsError:
                if not managed(path):
                    raise ValueError(f"Reading page destination already in use: {path}") from None
        os.replace(pending, path)


def chapter_section(db, number, book_title, has_cards):
    row = book.chapter(db, number)
    rev = row["revision"]
    fallback = f"第 {number} 章"
    text = row["body"].decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    skip = 0
    title = None
    for i, line in enumerate(lines[:5]):
        first = line.strip().lstrip("#").strip()
        if not first or first == f"《{book_title}》":
            continue
        if len(first) <= 90 and CHAPTER_HEADING.fullmatch(first):
            title = first
            skip = i + 1
        break
    if has_cards:
        card = db.execute("""SELECT body FROM chapter_cards WHERE number=? AND revision=?
                             ORDER BY version DESC LIMIT 1""", (number, rev)).fetchone()
        if card:
            name = json.loads(card[0]).get("title")
            if name and not title:
                title = name if CHAPTER_HEADING.fullmatch(name) else f"{fallback}　{name}"
    state = "已采纳" if row["adopted"] else "草稿"
    prose = "".join(lines[skip:]).lstrip("\r\n") if skip else text
    return (f"chapter-{number}", title or fallback, f"第 {rev} 稿 · {state}",
            f'<div class="prose">{escape(prose)}</div>')


def study_text(text):
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        data = None
    questions = data.get("questions") if isinstance(data, dict) else None
    if isinstance(questions, list) and questions and all(
            isinstance(item, dict) and isinstance(item.get("question"), str) for item in questions):
        parts = ['<div class="study">']
        for key in ("scope", "use"):
            if isinstance(data.get(key), str):
                parts.append(f"<p>{escape(data[key])}</p>")
        parts.append("<h3>写作问题</h3><ol>")
        for item in questions:
            limit = item.get("limit")
            extra = f"<p>{escape(limit)}</p>" if isinstance(limit, str) else ""
            parts.append(f'<li><p>{escape(item["question"])}</p>{extra}</li>')
        return "".join(parts) + "</ol></div>"
    return f'<div class="prose">{escape(text)}</div>'


def study_sections(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='creative_records'").fetchone():
        return []
    # Only the latest revision of each author/reader research note belongs in the study view.
    labels = {}
    index = db.execute("SELECT body FROM creative_records WHERE name='book-materials' ORDER BY revision DESC LIMIT 1").fetchone()
    if index:
        try:
            catalog = json.loads(index[0])
        except (ValueError, RecursionError):
            catalog = None
        if isinstance(catalog, dict) and catalog.get("format") == "writing-assistant/book-materials/1":
            items = catalog.get("items")
            if isinstance(items, dict):
                labels = {v["record"]: v["label"] for v in items.values() if isinstance(v, dict)
                          and isinstance(v.get("record"), str) and isinstance(v.get("label"), str)}
    rows = db.execute("""SELECT sequence, ref, title, body FROM creative_records c
        WHERE category='research' AND audience IN ('author','reader') AND name!='book-materials'
        AND NOT EXISTS (SELECT 1 FROM creative_records n WHERE n.name=c.name AND n.revision>c.revision)
        ORDER BY sequence""")
    sections = []
    for seq, ref, title, raw in rows:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        sections.append((f"study-{seq}", labels.get(ref, title), "研读笔记", study_text(text)))
    return sections


def render(db, group, has_shelf):
    title = db.execute("SELECT title FROM book").fetchone()[0]
    has_cards = db.execute("PRAGMA user_version").fetchone()[0] >= 4
    numbers = db.execute("SELECT DISTINCT number FROM chapters ORDER BY number")
    chapters = [chapter_section(db, n, title, has_cards) for n, in numbers]
    notes = study_sections(db) if group == "学习样本" else []
    count = f"{len(chapters)} 章" if chapters or group != "学习样本" else "未收录原著正文"
    if notes:
        count += f" · {len(notes)} 篇研读笔记"
    home = f'<a class="home" href="../../{SHELF}">← 本机书架</a>' if has_shelf else ""
    header = f'{home}<h1>{escape(title)}</h1><div class="meta">{count}</div>'
    items, articles = [], []
    for anchor, name, meta, body in chapters + notes:
        label = escape(name)
        items.append(f'<li><a href="#{anchor}">{label}</a></li>')
        articles.append(f'<article id="{anchor}"><div class="meta">{meta}</div><h2>{label}</h2>{body}'
                        '<footer><a class="back" href="#contents">↑ 返回目录</a></footer></article>')
    if not items:
        message = "这本书还没有可读的研读笔记。" if group == "学习样本" else "第一章保存后会显示在这里。"
        return document(title, header, f"<main><p>{message}</p></main>")
    nav = '<nav id="contents" aria-label="目录"><h2>目录</h2><ol>' + "".join(items) + "</ol></nav>"
    return document(title, header, '<div class="layout">' + nav + "<main>" + "".join(articles) + "</main></div>")


def book_page(directory, has_shelf=False):
    path = directory / PAGE
    with closing(book.connect(directory)) as db:
        # In WAL mode another writer can commit while a snapshot is being rendered.
        while True:
            before = db.execute("PRAGMA data_version").fetchone()[0]
            publish(path, render(db, directory.parent.name, has_shelf))
            db.commit()
            if db.execute("PRAGMA data_version").fetchone()[0] == before:
                return path
            db.execute("BEGIN")


def titles(root, group):
    parent = root / group
    if not parent.is_dir() or parent.is_symlink():
        return []
    return sorted(path for path in parent.iterdir() if not path.is_symlink() and (path / "book.sqlite3").is_file())


def shelf_members(root):
    return {group: [p for p in titles(root, group) if managed(p / PAGE)] for group in GROUPS}


def shelf_page(root):
    path = root / SHELF
    while True:
        groups = shelf_members(root)
        sections = []
        for name, books in groups.items():
            links = []
            for entry in books:
                href = quote((entry / PAGE).relative_to(root).as_posix())
                links.append(f'<li><a href="{href}">{escape(entry.name)}</a></li>')
            listing = "<ul>" + "".join(links) + "</ul>" if links else "<p>暂无书籍</p>"
            sections.append(f'<section><h2>{name} <small class="meta">{len(books)} 本</small></h2>{listing}</section>')
        publish(path, document("本机书架", "<h1>本机书架</h1>", '<main class="shelf">' + "".join(sections) + "</main>"))
        if groups == shelf_members(root):
            return path


def refresh(directory, *, index_book=True):
    root = directory.parent.parent
    group = directory.parent.name
    listed = group in GROUPS and managed(root / SHELF)
    path = book_page(directory, listed)
    if index_book and group in GROUPS:
        shelf_index.update(root, {group: [directory]}, PAGE)
    if listed:
        shelf_page(root)
    return {"path": str(path)}


def build_shelf(root):
    if not root.is_dir():
        raise ValueError("Select an existing book shelf directory.")
    groups = {group: titles(root, group) for group in GROUPS}
    for directories in groups.values():
        for directory in directories:
            book_page(directory, has_shelf=True)
    shelf_index.update(root, groups, PAGE)
    return {"path": str(shelf_page(root)), "books": sum(map(len, groups.values()))}


def refresh_after_write(args, result):
    cmd = args.command
    changed = (cmd in {"init", "restore", "save", "adopt", "import-chapter", "import-test"}
               or cmd == "chapter" and args.card is not None
               or cmd == "trial" and args.trial_action == "adopt"
               or cmd == "task" and args.task_action in {"execute", "receive", "recover"}
               and result["state"] == "completed" and result["role"] == "writer")
    if args.book and args.book.resolve().parent.name == "学习样本":
        changed |= (cmd == "records" and args.records_action == "save" or cmd == "import-record"
                    or cmd == "library" and args.operation == "attach")
    if changed:
        try:
            refresh(args.book.resolve(), index_book=cmd in {"init", "restore", "import-chapter", "import-test"})
        except (OSError, ValueError, sqlite3.Error) as error:
            # The database operation has already committed and retains its normal receipt.
            print(f"Book saved. Reading page or shelf refresh failed: {error}. Retry with --book DIR reading-page.", file=sys.stderr)
