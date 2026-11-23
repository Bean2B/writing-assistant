"""Find versioned manuscript scenes and account for the source text shown."""
from collections import Counter
import math
from pathlib import Path
import re
import unicodedata

from .. import book


COMMANDS = {"scene"}
SCHEMA = """
CREATE TABLE scene_index (
    chapter INTEGER NOT NULL, revision INTEGER NOT NULL, scene INTEGER NOT NULL,
    lo INTEGER NOT NULL, hi INTEGER NOT NULL,
    PRIMARY KEY(chapter,revision,scene), FOREIGN KEY(chapter,revision) REFERENCES chapters
);
CREATE TABLE scene_terms (
    term TEXT NOT NULL, chapter INTEGER NOT NULL, revision INTEGER NOT NULL, scene INTEGER NOT NULL,
    PRIMARY KEY(term,chapter,revision,scene), FOREIGN KEY(chapter,revision,scene) REFERENCES scene_index
);
CREATE TABLE scene_aliases (
    chapter INTEGER NOT NULL, revision INTEGER NOT NULL, scene INTEGER NOT NULL, phrase TEXT NOT NULL,
    PRIMARY KEY(chapter,revision,scene,phrase), FOREIGN KEY(chapter,revision,scene) REFERENCES scene_index
);
CREATE TABLE scene_sessions (id TEXT PRIMARY KEY, before_chapter INTEGER NOT NULL);
CREATE TABLE scene_calls (
    id INTEGER PRIMARY KEY, session TEXT NOT NULL REFERENCES scene_sessions(id), action TEXT NOT NULL,
    query TEXT NOT NULL
);
CREATE INDEX scene_calls_session ON scene_calls(session);
CREATE TABLE scene_displays (
    call INTEGER NOT NULL REFERENCES scene_calls(id), chapter INTEGER NOT NULL, revision INTEGER NOT NULL,
    scene INTEGER NOT NULL, lo INTEGER NOT NULL, hi INTEGER NOT NULL, bytes INTEGER NOT NULL,
    FOREIGN KEY(chapter,revision,scene) REFERENCES scene_index
);
"""


def register(subs):
    p = subs.add_parser("scene", help="find earlier scenes, check retrospective claims and measure rereading")
    group = p.add_subparsers(dest="scene_action", required=True)
    for action in ("find", "open", "alias", "check", "usage"):
        p = group.add_parser(action)
        if action in {"find", "open", "check", "usage"}:
            p.add_argument("--session", required=True, help="a stable id for this writing or review session")
        if action in {"find", "open", "check"}:
            p.add_argument("--before", type=int, required=True, help="exclude this and later chapters")
        if action in {"open", "alias"}:
            p.add_argument("--chapter", type=int, required=True)
            p.add_argument("--revision", type=int, required=True)
            p.add_argument("--scene", type=int, required=True)
        if action == "alias":
            p.add_argument("phrase", help="an alternative description to locate this scene")
        if action == "find":
            p.add_argument("query")
        if action in {"find", "check"}:
            p.add_argument("--limit", type=int, default=3, help="number of suggestions per question")
        if action == "check":
            p.add_argument("--draft", type=Path, required=True)
            p.add_argument("--claim", action="append", default=[], help="additional exact draft sentence to check")


def writable(args):
    return args.scene_action != "usage"


HEADING = re.compile(r"^(?:#{1,6}\s+\S.*|[零一二三四五六七八九十百廿卅]+|[0-9]+|[*-](?:\s*[*-]){2,}|[◇◆※]{1,3})$")
# Bigram indexes support Chinese questions without a mandatory tokenizer or network model.
WORDS = re.compile(r"[\u3400-\u9fff\U00020000-\U0002ffff]+|[^\W_]+", re.UNICODE)


def _terms(text):
    result = set()
    for word in WORDS.findall(unicodedata.normalize("NFKC", text).casefold()):
        if "\u3400" <= word[0] <= "\u9fff" or "\U00020000" <= word[0] <= "\U0002ffff":
            result.update(word)
            result.update(word[i:i+2] for i in range(len(word)-1))
        else:
            result.add(word)
    return result


def sections(text):
    cut = [0]
    position = 0
    content = False
    for line in text.splitlines(keepends=True):
        label = line.strip()
        if HEADING.fullmatch(label):
            if content:
                cut.append(position)
                content = False
        elif label:
            content = True
        position += len(line)
    for lo, hi in zip(cut, cut[1:]+[len(text)]):
        if hi > lo:
            yield lo, hi


def _index(db, row):
    key = (row["number"], row["revision"])
    if db.execute("SELECT 1 FROM scene_index WHERE chapter=? AND revision=? LIMIT 1", key).fetchone():
        return
    text = row["body"].decode("utf-8")
    for scene, (lo, hi) in enumerate(sections(text), 1):
        anchor = (*key, scene)
        db.execute("INSERT INTO scene_index VALUES(?,?,?,?,?)", (*anchor, lo, hi))
        db.executemany("INSERT INTO scene_terms VALUES(?,?,?,?)",
                       ((term, *anchor) for term in sorted(_terms(text[lo:hi]))))


def _selected(db, before):
    choices = db.execute("""
        SELECT c.number, coalesce(a.revision,max(c.revision)) AS revision
        FROM chapters c LEFT JOIN adopted a ON a.number=c.number
        WHERE c.number < ? GROUP BY c.number, a.revision ORDER BY c.number
    """, (before,))
    selected = {}
    for number, revision in choices:
        selected[number] = revision
        if not db.execute("SELECT 1 FROM scene_index WHERE chapter=? AND revision=? LIMIT 1", (number, revision)).fetchone():
            _index(db, book.chapter(db, number, revision))
    return selected


def _call(db, session, before, action, query):
    if not session.strip() or not 0 < before <= 2**63-1:
        raise ValueError("Supply a session id and a positive chapter boundary.")
    db.execute("INSERT OR IGNORE INTO scene_sessions VALUES(?,?)", (session, before))
    if db.execute("SELECT before_chapter FROM scene_sessions WHERE id=?", (session,)).fetchone()[0] != before:
        raise ValueError("Session is bound to another chapter. Use the correct session id.")
    return db.execute("INSERT INTO scene_calls(session,action,query) VALUES(?,?,?)",
                      (session, action, query)).lastrowid


def _scores(db, selected, query):
    terms = _terms(query)
    if not terms:
        raise ValueError("Enter a question with searchable text.")
    counts = Counter()
    # A common individual character in a longer Chinese question can match nearly every scene.
    # Use bigrams or complete words when available. One-character names still work on their own.
    matching_terms = {term for term in terms if len(term) > 1} or terms
    for word in sorted(matching_terms):
        hits = [(ch, rev, idx) for ch, rev, idx in db.execute(
            "SELECT chapter,revision,scene FROM scene_terms WHERE term=?", (word,)) if selected.get(ch) == rev]
        # Rare terms and adjacent Chinese characters discriminate better than single common characters.
        weight = (2.5 if len(word) > 1 else 0.25) / math.sqrt(max(1, len(hits)))
        for key in hits:
            counts[key] += weight
    folded = unicodedata.normalize("NFKC", query).casefold()
    for ch, rev, idx, phrase in db.execute("SELECT chapter,revision,scene,phrase FROM scene_aliases"):
        if selected.get(ch) != rev:
            continue
        phrase = unicodedata.normalize("NFKC", phrase).casefold()
        alias_terms = _terms(phrase)
        if phrase in folded or folded in phrase:
            counts[ch, rev, idx] += 2 + len(terms)
        elif alias_terms & matching_terms:
            overlap = alias_terms & matching_terms
            counts[ch, rev, idx] += sum(1 if len(t) > 1 else .1 for t in overlap) / math.sqrt(len(alias_terms))
    return counts


def _show(db, key, call, query=None):
    ch, rev, idx = key
    anchor = db.execute("SELECT lo,hi FROM scene_index WHERE chapter=? AND revision=? AND scene=?", key).fetchone()
    if anchor is None:
        raise ValueError("Scene not found in this revision.")
    lo, hi = anchor
    row = book.chapter(db, ch, rev)
    body = row["body"].decode("utf-8")
    if query is not None:
        # Prefer a preview near a matching expression, even when a scene spans the whole chapter.
        words = sorted(_terms(query), key=lambda t: (-len(t), t))
        source = body[lo:hi]
        literal = re.search(re.escape(query.strip()), source, re.IGNORECASE)
        if literal is None:
            for word in words:
                literal = re.search(re.escape(word), source, re.IGNORECASE)
                if literal:
                    break
        focus = lo + (literal.start() if literal else 0)
        lo = max(lo, focus - 35)
        hi = min(hi, lo + 100)
    text = body[lo:hi]
    size = len(text.encode("utf-8"))
    db.execute("INSERT INTO scene_displays VALUES(?,?,?,?,?,?,?)", (call, *key, lo, hi, size))
    return {"chapter": ch, "revision": rev, "scene": idx, "sha256": row["digest"],
            "status": "adopted" if row["adopted"] else "draft", "range": [lo, hi], "text": text}


def _find(db, selected, query, limit, call):
    if limit < 1:
        raise ValueError("A suggestion count must be positive.")
    scores = _scores(db, selected, query)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return [_show(db, key, call, query) for key in ordered[:limit]]


def _usage(db, session):
    meta = db.execute("SELECT before_chapter FROM scene_sessions WHERE id=?", (session,)).fetchone()
    if meta is None:
        raise ValueError("Scene session not found.")
    calls = [dict(row) for row in db.execute(
        "SELECT id,action,query FROM scene_calls WHERE session=? ORDER BY id", (session,))]
    by_call = {call["id"]: call for call in calls}
    for call in calls:
        call["returns"] = []
    spans = {}
    chars = size = 0
    for call_id, ch, rev, idx, lo, hi, bytes_ in db.execute("""
        SELECT d.call,chapter,revision,scene,lo,hi,bytes FROM scene_displays d JOIN scene_calls c ON c.id=d.call
        WHERE c.session=? ORDER BY chapter,revision,lo,hi
    """, (session,)):
        by_call[call_id]["returns"].append({"chapter": ch, "revision": rev, "scene": idx,
                                           "range": [lo, hi], "utf8_bytes": bytes_})
        chars += hi - lo
        size += bytes_
        ranges = spans.setdefault((ch, rev), [])
        if ranges and lo <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], hi)
        else:
            ranges.append([lo, hi])
    details = []
    unique_chars = unique_bytes = 0
    for (ch, rev), ranges in spans.items():
        row = book.chapter(db, ch, rev)
        body = row["body"].decode("utf-8")
        unique_chars += sum(hi-lo for lo, hi in ranges)
        unique_bytes += sum(len(body[lo:hi].encode("utf-8")) for lo, hi in ranges)
        details.append({"chapter": ch, "revision": rev, "sha256": row["digest"], "ranges": ranges})
    return {"session": session, "before": meta[0], "calls": calls, "source_ranges": details,
            "returned_characters": chars, "returned_utf8_bytes": size, "distinct_characters": unique_chars,
            "distinct_utf8_bytes": unique_bytes, "provider_tokens": None}


RETROSPECT = re.compile(
    r"昨[夜天日]|前[夜日天]|上回|当初|先前|那[时晚天年回次]|原先|从前|曾[经在把说见答]|记得|早已|上次|"
    r"(?:白天|清晨|午后|黄昏|早上).{0,20}?(?:挖出|捡到|拿到|取来|换得|交给|塞进)|"
    r"从.{1,16}?(?:捡来|拿出来|取出|挖出)的|"
    r"[一二三四五六七八九十几数百千万\d]+[天日月年]前|答应过|见过|拿过|"
    r"\b(?:yesterday|formerly|remember(?:ed|s)?|previously|used to|had once|last (?:night|week|year))\b",
    re.IGNORECASE,
)


def run(db, args):
    action = args.scene_action
    if action == "usage":
        return _usage(db, args.session)
    if action == "alias":
        row = book.chapter(db, args.chapter, args.revision)
        _index(db, row)
        key = (args.chapter, args.revision, args.scene)
        if not _terms(args.phrase) or not db.execute(
                "SELECT 1 FROM scene_index WHERE chapter=? AND revision=? AND scene=?", key).fetchone():
            raise ValueError("Select an existing scene and provide a searchable description.")
        db.execute("INSERT OR IGNORE INTO scene_aliases VALUES(?,?,?,?)", (*key, args.phrase.strip()))
        return {"chapter": key[0], "revision": key[1], "scene": key[2], "alias": args.phrase.strip()}
    if action == "open":
        call = _call(db, args.session, args.before, action, f"{args.chapter}/{args.revision}/{args.scene}")
        if args.chapter >= args.before:
            raise ValueError("Select an earlier chapter.")
        row = book.chapter(db, args.chapter)
        if row["revision"] != args.revision:
            raise ValueError("Scene belongs to a stale revision. Run the search again.")
        _index(db, row)
        return _show(db, (args.chapter, args.revision, args.scene), call)
    if action == "find":
        call = _call(db, args.session, args.before, action, args.query)
        return {"suggestions": _find(db, _selected(db, args.before), args.query, args.limit, call)}
    draft = args.draft.read_bytes().decode("utf-8")
    claims = [match.group().strip() for match in re.finditer(r"[^。！？.!?\r\n]+[。！？.!?]?", draft)
              if RETROSPECT.search(match.group())]
    for explicit in args.claim:
        if not explicit.strip() or explicit not in draft:
            raise ValueError("Additional claim must be an exact passage of this draft.")
        claims.append(explicit)
    call = _call(db, args.session, args.before, action, "check draft claims")
    selected = _selected(db, args.before)
    return {"status": "for-author-review", "claims": [
        {"claim": claim, "candidate_sources": _find(db, selected, claim, args.limit, call)}
        for claim in dict.fromkeys(claims)]}
