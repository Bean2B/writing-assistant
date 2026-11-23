"""Browse the separately installed local research library by category."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
from importlib.resources import files as package_files

from .. import book
from ..story import records
from ..writing_test import field

ROOT = Path(str(package_files("writing_assistant"))) / "resources/data"
if not ROOT.is_dir():
    ROOT = Path(__file__).resolve().parents[3] / "data"


def register(subs):
    p = subs.add_parser("library", help="browse curated local material")
    p.add_argument("--root", type=Path, default=ROOT, help="directory containing catalog.json")
    commands = p.add_subparsers(dest="operation", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--category", choices=("planning", "writing-tests", "benchmarks", "worlds"))
    reading = commands.add_parser("read")
    reading.add_argument("id")
    commands.add_parser("attach", help="save one selected planning or evaluation record to this book").add_argument("id")


def execute(args):
    root = args.root.resolve()
    if not (root / "catalog.json").is_file():
        raise ValueError("No local research library at this location. Pass library --root DIR.")
    catalog = json.loads((root / "catalog.json").read_bytes())
    if field(catalog, "format") != "writing-assistant/library/1":
        raise ValueError("Unsupported library format.")
    entries = field(catalog, "items", list)
    if args.operation == "list":
        return [e for e in entries if args.category is None or e["category"] == args.category]
    matches = [e for e in entries if e["id"] == args.id]
    if len(matches) != 1:
        raise ValueError("Expected one matching catalog entry.")
    spec = matches[0]
    path = (root / spec["path"]).resolve()
    category = field(spec, "category")
    if category not in ("planning", "writing-tests", "benchmarks", "worlds") or not path.is_relative_to(root / category):
        raise ValueError("Library asset outside its category.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("Library asset digest mismatch.")
    if args.operation == "read":
        return raw
    if args.book is None:
        raise ValueError("Select the destination book with --book DIR.")
    if category == "writing-tests":
        raise ValueError("Use import-chapter with the matching book to load a historical manuscript.")
    if category == "worlds":
        raise ValueError("Use world create with the selected scenario to start a simulation.")
    source = field(spec, "source", dict)
    source_ref = json.dumps({"catalog_id": args.id, "source": source, "asset_sha256": spec["sha256"]},
                            ensure_ascii=False, sort_keys=True)
    with closing(book.connect(args.book, writable=True)) as db, db:
        return records.put_record(db, name="library/" + args.id, body=raw,
                                  operation="library/" + args.id + "/" + spec["sha256"], title=spec["label"],
                                  category="research", audience="author" if category == "planning" else "owner",
                                  authorship=spec.get("authorship", "unknown"), origin=spec.get("origin", ""),
                                  source=source_ref, parent=None)
