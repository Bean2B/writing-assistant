"""Import a manuscript and its recorded reading evidence into the selected book."""
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path

from . import book
from .story import records


def field(obj, key, expected=str):
    value = obj.get(key) if isinstance(obj, dict) else None
    if type(value) is not expected or (expected is str and not value.strip()):
        raise ValueError(f"Invalid writing-test field: {key}")
    return value


def asset(root, spec):
    name = Path(field(spec, "path"))
    path = (root / name).resolve()
    if name.is_absolute() or not path.is_relative_to(root):
        raise ValueError("Writing-test assets must be inside the case directory.")
    raw = book.text_bytes(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != field(spec, "sha256"):
        raise ValueError(f"Writing-test asset differs from its recorded digest: {name}")
    return raw


def line_range(spec, key):
    span = field(spec, key, list)
    if (len(span) != 2 or any(type(n) is not int for n in span)
            or not 1 <= span[0] <= span[1]):
        raise ValueError(f"Invalid inclusive line range: {key}")
    return span


def reading_evidence(root, case, number, raw, manuscript):
    assessment = field(case, "assessment", dict)
    evidence = [("assessment", assessment, asset(root, assessment))]
    for comparison in field(case, "comparisons", list):
        _, last = line_range(comparison, "target_lines")
        if last > len(raw.splitlines()):
            raise ValueError("Comparison points outside the manuscript.")
        prior = field(comparison, "prior_passage", dict)
        excerpt = asset(root, prior)
        start, end = line_range(prior, "source_lines")
        if (not 1 <= field(prior, "source_chapter", int) < number
                or len(excerpt.splitlines()) != end - start + 1):
            raise ValueError("Prior passage and its source range disagree.")
        evidence.append((f"comparison-{len(evidence)}", comparison, excerpt))
    responses = {}
    for response in field(case, "responses", list):
        name = field(response, "reader")
        if name in responses or field(response, "manuscript_sha256") != manuscript["sha256"]:
            raise ValueError("Duplicate reader or response linked to another manuscript.")
        responses[name] = asset(root, field(response, "body", dict))
    return responses, evidence


@contextmanager
def destination(directory, title, number, source):
    if not (directory / "book.sqlite3").exists():
        with book.new_book(directory, title, number, source) as db:
            yield db
        return
    with closing(book.connect(directory, writable=True)) as db, db:
        current_title, first = db.execute("SELECT title,first_chapter FROM book").fetchone()
        if current_title != title:
            raise ValueError("The manuscript belongs to a different book.")
        if number == first - 1 or not db.execute("SELECT 1 FROM chapters LIMIT 1").fetchone():
            db.execute("UPDATE book SET first_chapter=?", (number,))
        yield db


def load(directory, manifest, manuscript_only=False):
    manifest_bytes = manifest.read_bytes()
    case = json.loads(manifest_bytes)
    if field(case, "format") != "writing-assistant/writing-test/1":
        raise ValueError("Unsupported writing-test format.")
    root = manifest.resolve().parent
    case_id = field(case, "id")
    source_commit = field(field(case, "source", dict), "commit")
    title = field(case, "book")
    ch = field(case, "chapter", dict)
    number = field(ch, "number", int)
    if not 1 <= number <= 2**63 - 1:
        raise ValueError("Invalid source chapter number.")
    manuscript = field(ch, "body", dict)
    raw = asset(root, manuscript)
    responses, evidence = ({}, []) if manuscript_only else reading_evidence(root, case, number, raw, manuscript)
    with destination(directory, title, number, f"{case_id}@{source_commit}") as db:
        saved = book.save(db, number, raw)
        for name, reply in responses.items():
            db.execute("INSERT OR IGNORE INTO readers(name) VALUES(?)", (name,))
            book.add_response(db, number, saved["revision"], name, reply, "historical")
        if not manuscript_only:
            evidence.append(("manifest", {"sha256": hashlib.sha256(manifest_bytes).hexdigest()}, manifest_bytes))
        for label, spec, content in evidence:
            name = f"readings/{case_id}/{saved['sha256']}/{label}"
            records.put_record(db, name=name, body=content, operation=name,
                               title=f"{case_id} {label}", category="research", audience="owner",
                               authorship="unknown", origin="historical import", parent=None,
                               source=json.dumps({"source": case["source"], "evidence": spec, "chapter": saved},
                                                 ensure_ascii=False, sort_keys=True))
    return dict(case=case_id, chapter=saved, historical_responses=len(responses))
