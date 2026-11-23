# World Sandbox, Creative Records and writing preparation

All commands follow `scripts/writing-assistant --book BOOK`. They use the selected book's database. The coordinator owns that directory. Actors and readers receive selected payloads through their host sessions. Filesystem access to the entire book gives a caller owner access.

## Chapter dossiers

`chapter N` opens the selected manuscript revision (adopted, otherwise latest). Use `--revision R` for an exact draft. Each dossier reports the digest, adoption state, character count including headings and whitespace, scene locations with short previews, existing source-linked notes, readers who submitted feedback, and trial references. Use `read N --revision R` for the full prose, `reviews N --revision R` for original chapter responses, and `trial results ID` for a closed comparative reading.

Write the card in the book's language. Include a short `summary` and at least one `events` entry with a `detail` and an exact `quote` from that revision. The author judges whether the quote supports the observation. Optional fields include `volume`, `title`, `time`, `place`, lists of `characters`, `interpretations`, `intentions`, `open_questions`, `held_back` and book-local Creative Record refs in `materials`. Include what matters for this chapter.

```json
{
  "title": "还钥匙",
  "summary": "周嫂收回船钥匙。阿棠没有问她缘由。",
  "characters": ["周嫂", "阿棠"],
  "events": [{"detail": "船钥匙回到周嫂手里。", "quote": "她从阿棠手心拈走了船钥匙。"}],
  "interpretations": ["阿棠以为周嫂不肯再借船。"],
  "held_back": ["周嫂为何收回钥匙，暂缓说明。"]
}
```

Use `save N --file manuscript.md --card card.json` for an atomic save. Use `--card -` to supply JSON on stdin. After a prose-only save, `chapter N --revision R --card -` attaches it. Keep working inputs temporary. Amend a card with its current `--parent-version V` and retrieve an earlier one with `--card-version V`. Each manuscript revision has its own card history. Missing cards appear as `pending`, with a null `card_version` in `status`. The normal author handoff gives the preceding revision's card version. Open other dossiers on demand. Blind reader packets carry manuscript text only.

## Records and writing context

For a supplied setting sheet or explanation, read it in place, then write the synthesized material directly with `records save NAME --stdin --title TITLE --category setting --audience author --authorship mixed --operation ID`. Standard input contains only the prepared record. Use the latest `--parent REF` to update an existing outline or character record. Keep tentative suggestions distinguishable from settled decisions. The research workflow below preserves original text when needed for literary study or fact-checking.

Use `records save field-notes --file notes.md --title "Kiln walls" --category research --authorship user --origin interview --source "Page 14" --audience author --operation notes-first`. Save keeps the exact UTF-8 bytes and returns an opaque version ref, digest and attribution. Use a fresh operation and the current `--parent REF` to revise a named record. Reusing an operation with identical input returns the original receipt. Origin and source describe provenance supplied by the caller.

`records read REF` writes the original bytes. `records history NAME`, `records recent --category research` and `records search TERM` help locate material. Search covers titles and text across versions using Unicode case folding. Recent results select the latest version of each named record. Page from the returned sequence with `--after N`. An owner bookmark pins exact refs in caller-supplied order. `--stop` measures Unicode characters in the final selected record, preserving the full bytes when reopened. A bookmark with a producer `--baseline TOKEN` requires the same current token on reopening. A trusted host can use the `scoped_read(db, ref, permit)` API to enforce its current book/ref grant before content access.

```sh
"$wa" --book "$book" records bookmark crossing --ref "$ref" --stop 20
"$wa" --book "$book" records context crossing --max-bytes 40960
"$wa" --book "$book" config --writing-mode direct --world-sandbox off
"$wa" --book "$book" prepare "Continue the crossing" --target 5 --prior 4 1 --material "$ref"
"$wa" --book "$book" prepare "What stayed with you?" --phase reader-review --chapter 5 1 --prior 4 1
```

Writing mode and sandbox are independently configurable per book. They default to Lotus and on. Preparation selects only explicit chapter revisions and record refs, performs no dispatch and fails if the complete packet exceeds its byte budget. Each packet binds this book’s persistent ID and can pin an intended chapter with `--target N`. A selected current draft also pins its chapter. The packet digest covers compact key-sorted UTF-8 JSON with its own digest omitted. Direct draft packets carry an empty framework instruction list. Reader review accepts the current manuscript and selected earlier chapters. Continuity review also accepts selected author-visible setting records. Revision requires Lotus mode, the current draft and selected feedback. Book notes stay in the separate author handoff.

## Model a turn

This small world has two participants. At minute 12 the ferryman sees the lantern. The keeper learns only information explicitly routed to the keeper or made public.

```json
{
  "actors": {
    "ferryman": {
      "profile": "Collects the last toll before dusk.",
      "knowledge": {"debt": "six pennies"},
      "actions": {
        "leave": {"label": "Cast off", "effects": [{"to": "public", "facts": {"boat": "gone"}}]}
      }
    },
    "keeper": {"profile": "Tends the bridge."}
  },
  "public": {"boat": "moored"},
  "schedule": [{"at": 12, "effects": [{"to": "ferryman", "facts": {"lamp": "lit"}}]}],
  "request_limit": 12
}
```

```sh
"$wa" --book "$book" world --run ferry create ferry.json
"$wa" --book "$book" world --run ferry advance-time --target 12 --expect 0
"$wa" --book "$book" world --run ferry checkpoint dusk
"$wa" --book "$book" world --run ferry fork alternative --checkpoint dusk
"$wa" --book "$book" world --run ferry --branch alternative projection --actor ferryman --field knowledge.lamp
"$wa" --book "$book" world --run ferry capture lantern --actor ferryman --field knowledge.lamp --operation dusk-note
```

An action may declare `"requires": {"knowledge.lamp": "lit"}`. Its key and label appear only while that actor can satisfy the condition. Actor projections include their own settled choices and support a historical `--revision N`. Each branch has its own revision and narrative clock. Time moves only by an explicit advance. Forks retain their parent's exact revision and digest. Replay walks the ancestry, checks persisted event hashes and derives the saved world state. Capturing explicitly selected scalar fields produces an immutable author-visible setting record usable by `prepare`. A source digest detects changes to the saved representation. The interface trusts the local coordinator to choose an appropriate actor, fields and audience.

For an actor decision, call `world --run ferry request --actor ferryman --expect 1 --id turn-one`. Send only the returned `packet` to the actor. It contains the actor's observations and offered action keys and labels. Before an authorized host dispatch mark `dispatching --id turn-one`. Record the actual choice with `result --id turn-one --choice leave` and apply it with `settle --id turn-one`. These subcommands live under the same world and branch. Repeating settlement returns the saved receipt. An unresolved dispatch blocks further branch changes until a result is established. Outstanding requests consume a shared run budget. Switching the sandbox off blocks new decisions and time advancement while preserving reads and settlement of a previously recorded result.

This implementation provides deterministic authored schedules and choices. It uses a new per-book journal format. Earlier World/RunStore bundles, external token-based record permissions and native decision-provider observations have their own compatibility and live-validation requirements.

## Try a fictional world

Use the [market town](../data/worlds/market-town/scenario.json) with `world --run town create data/worlds/market-town/scenario.json`. Run `world --run town projection --actor keeper` to inspect what the keeper can see. The sample contains two fictional actors.
