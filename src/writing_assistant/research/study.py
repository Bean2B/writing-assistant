"""Book-local, source-bound literary study with frozen observations and review."""
import codecs
import hashlib
from pathlib import Path
import uuid


COMMANDS = {"study"}
SCHEMA = """
CREATE TABLE study_sources (
    id TEXT PRIMARY KEY, genre TEXT NOT NULL, title TEXT NOT NULL, edition TEXT NOT NULL,
    question TEXT NOT NULL, source_digest TEXT NOT NULL, lo INTEGER NOT NULL, hi INTEGER NOT NULL,
    source_span TEXT NOT NULL, first_analyst TEXT NOT NULL, second_analyst TEXT NOT NULL,
    first_reviewer TEXT NOT NULL, second_reviewer TEXT NOT NULL
);
CREATE TABLE study_windows (
    id TEXT PRIMARY KEY, study TEXT NOT NULL REFERENCES study_sources(id), actor TEXT NOT NULL,
    lo INTEGER NOT NULL, hi INTEGER NOT NULL, digest TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE study_observations (
    study TEXT NOT NULL REFERENCES study_sources(id), actor TEXT NOT NULL, body TEXT NOT NULL,
    at_char INTEGER NOT NULL, quotation TEXT NOT NULL, PRIMARY KEY(study,actor)
);
CREATE TABLE study_profiles (
    study TEXT NOT NULL REFERENCES study_sources(id), kind TEXT NOT NULL, revision INTEGER NOT NULL,
    body TEXT NOT NULL, adopted TEXT, PRIMARY KEY(study,kind,revision)
);
CREATE TABLE study_reviews (
    study TEXT NOT NULL, kind TEXT NOT NULL, revision INTEGER NOT NULL, reviewer TEXT NOT NULL,
    verdict TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(study,kind,revision,reviewer),
    FOREIGN KEY(study,kind,revision) REFERENCES study_profiles
);
"""


def register(subs):
    group = subs.add_parser("study", help="read and review an explicitly scoped source").add_subparsers(
        dest="study_action", required=True)
    p = group.add_parser("create", help="bind a research question and an authorized UTF-8 character range")
    p.add_argument("study")
    for name in ("genre", "title", "edition", "question", "sha256"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--file", type=Path, required=True)
    for name in ("analyst", "reviewer"):
        p.add_argument("--" + name, action="append", required=True, help="give two distinct host identities")
    for name in ("start", "end"):
        p.add_argument("--" + name, type=int, required=True)
    group.add_parser("catalog", help="list study versions and authorized ranges")
    for name in ("window", "ack", "coverage", "observe", "exchange", "synthesize",
                 "review", "adopt", "profile"):
        p = group.add_parser(name)
        p.add_argument("study")
        if name in {"window", "ack", "observe", "review"}:
            p.add_argument("--actor", required=True)
        if name == "window":
            p.add_argument("--start", type=int, required=True)
            p.add_argument("--end", type=int, required=True)
        if name == "ack":
            p.add_argument("--window", required=True)
            p.add_argument("--sha256", required=True)
        if name in {"observe", "synthesize", "review"}:
            p.add_argument("--file", type=Path, required=True, help="original UTF-8 response")
        if name == "observe":
            p.add_argument("--quote", required=True)
            p.add_argument("--at", required=True, type=int)
        if name in {"synthesize", "review", "adopt", "profile"}:
            p.add_argument("--kind", choices=["technique", "style"], required=True)
        if name in {"review", "adopt", "profile"}:
            p.add_argument("--revision", type=int, required=True)
        if name == "review":
            p.add_argument("--verdict", choices=["accept", "revise"], required=True)
        if name == "adopt":
            p.add_argument("--decision", required=True, help="user's decision reference")


def writable(args):
    return args.study_action not in {"catalog", "coverage", "exchange", "profile"}


def _span(path, start, end, expected):
    if not 0 <= start < end <= 2**63 - 1:
        raise ValueError("Invalid source character range.")
    digest = hashlib.sha256()
    decode = codecs.getincrementaldecoder("utf-8-sig")()
    position, pieces = 0, []
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            digest.update(chunk)
            text = decode.decode(chunk, final=not chunk)
            count = len(text)
            if position < end and position + count > start:
                pieces.append(text[max(0, start-position):end-position])
            position += count
            if not chunk:
                break
    if position < end or digest.hexdigest() != expected:
        raise ValueError("Source digest or authorized range does not match the selected edition.")
    return "".join(pieces)


def _create(db, args):
    analysts = [name.strip() for name in args.analyst]
    reviewers = [name.strip() for name in args.reviewer]
    people = analysts + reviewers
    metadata = [args.study, args.genre, args.title, args.edition, args.question]
    if len(analysts) != 2 or len(reviewers) != 2 or len(set(people)) != 4 or not all(people):
        raise ValueError("Assign two independent analysts and two different reviewers.")
    if not all(s.strip() for s in metadata):
        raise ValueError("Study metadata must be nonempty.")
    span = _span(args.file, args.start, args.end, args.sha256)
    values = (*metadata, args.sha256, args.start, args.end, span, *people)
    existing = db.execute("SELECT * FROM study_sources WHERE id=?", (args.study,)).fetchone()
    if existing is None:
        db.execute("INSERT INTO study_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
    elif tuple(existing) != values:
        raise ValueError("This study id is already bound to a different source, scope or team.")
    return {"study": args.study, "source_sha256": args.sha256, "range": [args.start, args.end]}


def _union(ranges):
    result = []
    for lo, hi in sorted(ranges):
        if result and result[-1][1] >= lo:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return result


def _coverage(db, source):
    actors = {source[key]: [] for key in ("first_analyst", "second_analyst", "first_reviewer", "second_reviewer")}
    windows = db.execute("SELECT actor,lo,hi,acknowledged FROM study_windows WHERE study=?", (source["id"],))
    delivered = []
    for actor, lo, hi, acknowledged in windows:
        delivered.append((lo, hi))
        if acknowledged:
            actors[actor].append((lo, hi))
    unique = _union(actors[source["first_analyst"]] + actors[source["second_analyst"]])
    return {"source_sha256": source["source_digest"], "authorized": [source["lo"], source["hi"]],
            "returned_distinct_ranges": _union(delivered), "acknowledged_by": {k: _union(v) for k, v in actors.items()},
            "analyst_acknowledged_ranges": unique,
            "analyst_acknowledged_characters": sum(hi-lo for lo, hi in unique)}


def _body(path):
    text = path.read_bytes().decode("utf-8")
    if not text.strip():
        raise ValueError("An original response must contain text.")
    return text


def _observations(db, study):
    rows = db.execute("SELECT actor,at_char,quotation,body FROM study_observations WHERE study=? ORDER BY actor", (study,))
    items = [dict(row) for row in rows]
    if len(items) != 2:
        raise ValueError("Exchange opens after both analysts freeze their independent observations.")
    return items


def run(db, args):
    action = args.study_action
    if action == "create":
        return _create(db, args)
    if action == "catalog":
        rows = db.execute("SELECT id,genre,title,edition,question,source_digest,lo,hi FROM study_sources ORDER BY id")
        return [dict(row) for row in rows]
    study = args.study
    source = db.execute("SELECT * FROM study_sources WHERE id=?", (study,)).fetchone()
    if source is None:
        raise ValueError("Study not found.")
    analysts = (source["first_analyst"], source["second_analyst"])
    reviewers = (source["first_reviewer"], source["second_reviewer"])
    if action in {"window", "ack", "observe", "review"}:
        actor = args.actor.strip()
        if actor not in analysts + reviewers:
            raise ValueError("Actor is outside this study.")
    if action == "window":
        lo, hi = args.start, args.end
        if not source["lo"] <= lo < hi <= source["hi"]:
            raise ValueError("Window falls outside the authorized study range.")
        text = source["source_span"][lo-source["lo"]:hi-source["lo"]]
        digest = hashlib.sha256(text.encode()).hexdigest()
        window = uuid.uuid4().hex
        db.execute("INSERT INTO study_windows(id,study,actor,lo,hi,digest) VALUES(?,?,?,?,?,?)",
                   (window, study, actor, lo, hi, digest))
        return {"window": window, "study": study, "actor": actor, "source_sha256": source["source_digest"],
                "range": [lo, hi], "window_sha256": digest, "text": text}
    if action == "ack":
        updated = db.execute("UPDATE study_windows SET acknowledged=1 WHERE id=? AND study=? AND actor=? AND digest=?",
                             (args.window, study, actor, args.sha256))
        if not updated.rowcount:
            raise ValueError("Acknowledgement does not match this actor's window and digest.")
        return {"acknowledged": args.window}
    if action == "coverage":
        return _coverage(db, source)
    if action == "observe":
        if actor not in analysts:
            raise ValueError("Only an assigned analyst can freeze a first observation.")
        quote, at = args.quote, args.at
        spans = _coverage(db, source)["acknowledged_by"][actor]
        if (not quote.strip() or not any(lo <= at and at+len(quote) <= hi for lo, hi in spans)
                or source["source_span"][at-source["lo"]:at-source["lo"]+len(quote)] != quote):
            raise ValueError("Cite an exact quote within this analyst's acknowledged ranges.")
        body = _body(args.file)
        previous = db.execute("SELECT body,at_char,quotation FROM study_observations WHERE study=? AND actor=?",
                              (study, actor)).fetchone()
        if previous and tuple(previous) != (body, at, quote):
            raise ValueError("The first observation is frozen.")
        if previous is None:
            db.execute("INSERT INTO study_observations VALUES(?,?,?,?,?)", (study, actor, body, at, quote))
        return {"frozen": actor}
    if action == "exchange":
        return {"source_sha256": source["source_digest"], "observations": _observations(db, study)}
    if action == "synthesize":
        _observations(db, study)
        kind, body = args.kind, _body(args.file)
        previous = db.execute("SELECT revision,body FROM study_profiles WHERE study=? AND kind=? ORDER BY revision DESC LIMIT 1",
                              (study, kind)).fetchone()
        revision = previous["revision"] if previous else 0
        if previous is None or previous["body"] != body:
            revision += 1
            db.execute("INSERT INTO study_profiles(study,kind,revision,body) VALUES(?,?,?,?)",
                       (study, kind, revision, body))
        return {"study": study, "kind": kind, "revision": revision}
    key = (study, args.kind, args.revision)
    profile = db.execute("SELECT * FROM study_profiles WHERE study=? AND kind=? AND revision=?", key).fetchone()
    if profile is None:
        raise ValueError("Profile revision not found.")
    if action == "review":
        if actor not in reviewers or not _coverage(db, source)["acknowledged_by"][actor]:
            raise ValueError("The reviewer must independently acknowledge a source window.")
        body = _body(args.file)
        previous = db.execute("SELECT verdict,response FROM study_reviews WHERE study=? AND kind=? AND revision=? AND reviewer=?",
                              (*key, actor)).fetchone()
        if previous and tuple(previous) != (args.verdict, body):
            raise ValueError("This review is frozen. Revise the profile to open another round.")
        if previous is None:
            db.execute("INSERT INTO study_reviews VALUES(?,?,?,?,?,?)", (*key, actor, args.verdict, body))
        return {"reviewer": actor, "verdict": args.verdict}
    reviews = [dict(row) for row in db.execute(
        "SELECT reviewer,verdict,response FROM study_reviews WHERE study=? AND kind=? AND revision=? ORDER BY reviewer", key)]
    if action == "adopt":
        if not args.decision.strip() or len(reviews) != 2 or any(r["verdict"] != "accept" for r in reviews):
            raise ValueError("Adoption needs both accepting reviews and the user's decision reference.")
        if profile["adopted"] and profile["adopted"] != args.decision:
            raise ValueError("This profile already has a recorded adoption decision.")
        db.execute("UPDATE study_profiles SET adopted=? WHERE study=? AND kind=? AND revision=?", (args.decision, *key))
        return {"adopted": args.decision, "revision": args.revision}
    # A reviewer can receive the profile without seeing the other first verdict.
    return {"profile": dict(profile), "source_sha256": source["source_digest"],
            "reviews": reviews if len(reviews) == 2 else [], "review_count": len(reviews)}
