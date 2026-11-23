"""Author-maintained chapter data bound to an immutable manuscript revision."""
import json

from .. import book
from . import records, scenes


SCHEMA = """
CREATE TABLE IF NOT EXISTS chapter_cards (
    number INTEGER NOT NULL, revision INTEGER NOT NULL, version INTEGER NOT NULL,
    body TEXT NOT NULL, PRIMARY KEY(number, revision, version),
    FOREIGN KEY(number, revision) REFERENCES chapters
)
"""
TEXT_FIELDS = {"summary", "title", "volume", "place", "time"}
LIST_FIELDS = {"characters", "interpretations", "intentions", "open_questions", "held_back", "materials"}


def validate(db, card, manuscript):
    if not isinstance(card, dict) or set(card) - (TEXT_FIELDS | LIST_FIELDS | {"events"}):
        raise ValueError("Expected a chapter card object with supported fields.")
    if "summary" not in card:
        raise ValueError("Include the author's chapter summary.")
    for key in TEXT_FIELDS.intersection(card):
        records.nonempty(card[key])
    for key in LIST_FIELDS.intersection(card):
        if not isinstance(card[key], list):
            raise ValueError(f"{key} must be a list of strings.")
        for item in card[key]:
            records.nonempty(item)
    for ref in card.get("materials", []):
        records.metadata(db, ref)
    events = card.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Include an event or observation with an exact manuscript quote.")
    for event in events:
        if not isinstance(event, dict) or set(event) != {"detail", "quote"}:
            raise ValueError("Each event needs a detail and an exact quote.")
        records.nonempty(event["detail"])
        if records.nonempty(event["quote"]) not in manuscript:
            raise ValueError("Chapter card quote does not occur in this manuscript revision.")


def store(db, number, revision, card, parent):
    manuscript = book.chapter(db, number, revision)["body"].decode("utf-8")
    validate(db, card, manuscript)
    body = json.dumps(card, ensure_ascii=False, sort_keys=True)
    row = db.execute("""SELECT version,body FROM chapter_cards WHERE number=? AND revision=?
                        ORDER BY version DESC LIMIT 1""", (number, revision)).fetchone()
    if row and row["body"] == body:
        return row["version"]
    current = row["version"] if row else None
    if parent != current:
        raise ValueError("Supply the current card version as --parent-version to update it.")
    version = (current or 0) + 1
    db.execute("INSERT INTO chapter_cards VALUES(?,?,?,?)", (number, revision, version, body))
    return version


def overview(db, number, revision, version=None):
    row = book.chapter(db, number, revision)
    key = (number, row["revision"])
    schema = db.execute("PRAGMA user_version").fetchone()[0]
    card = None
    if schema >= 4:
        card = db.execute("""SELECT version,body FROM chapter_cards WHERE number=? AND revision=?
                            AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1""",
                          (*key, version, version)).fetchone()
    if version is not None and card is None:
        raise ValueError("Card version not found on this manuscript revision.")
    notes = db.execute("""SELECT id,kind,detail,quote,closed FROM notes WHERE number=? AND revision=?
                          ORDER BY id""", key)
    feedback = db.execute("SELECT reader,origin FROM feedback WHERE number=? AND revision=? ORDER BY reader", key)
    trials = []
    if schema >= 3:
        trials = [dict(r) for r in db.execute("""SELECT trial,arm,step FROM trial_plan
                  WHERE chapter=? AND revision=? ORDER BY trial,step""", key)]
    text = row["body"].decode("utf-8")
    locations = [{"scene": index, "range": [lo, hi], "preview": text[lo:min(hi, lo + 80)]}
                 for index, (lo, hi) in enumerate(scenes.sections(text), 1)]
    return {"number": number, "revision": row["revision"], "sha256": row["digest"],
            "adopted": bool(row["adopted"]), "text_characters": len(text), "scenes": locations,
            "card_status": "recorded" if card else "pending", "card_version": card["version"] if card else None,
            "card": json.loads(card["body"]) if card else None, "notes": [dict(r) for r in notes],
            "feedback": [dict(r) for r in feedback], "trials": trials}
