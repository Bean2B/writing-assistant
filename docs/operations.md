# Local operations

Run `./scripts/writing-assistant doctor` to see the installed version, schema and Python runtime. For a selected book, `diagnostics` reports integrity, foreign-key errors, revision count and exchange state. This projection uses fixed fields so that book titles, material, session handles and credentials stay out of diagnostics.

## Install a skill

The `skills/` directory contains the skills included in your edition. Use the skill folder directly if your harness supports registering a local folder. For a harness that discovers installed skills in a directory, run the optional installer from the checkout or unpacked runtime. Choose one destination and one skill for each invocation.

For example, to register the writing skill in a particular Claude Code project:

```sh
python3 scripts/install-skill.py writing-assistant --to "/path/to/your/project/.claude/skills"
```

For a personal Claude Code installation, choose `~/.claude/skills`. For a Codex-only personal installation, choose `~/.codex/skills`. Use `.agents/skills` in a project or `~/.agents/skills` at user scope when you want discovery shared with other compatible harnesses. The installer creates a link to the selected source folder. Running it again with the same source and destination reuses the link. Keep the source folder in place for as long as you use that registration. To unregister, remove the individual link in the harness directory.

## Moving a book

The CLI snapshot covers `book.sqlite3`, including saved research records and registered study passages. If the book also has original files in `资料/`, carry that directory alongside the snapshot and restore it under the same book. Carry any older attachment paths used by saved records as well. Preserve their relative paths so that notes still locate their supporting files.

Use `--book BOOK backup SNAPSHOT.sqlite3`. Keep the returned SHA-256 separately. To restore, run `--book UNUSED_DIR restore SNAPSHOT.sqlite3 --sha256 SHA`. Both operations reject an existing destination. A consistent backup includes chapters, source notes, reader responses, settings and workflow records. Finish or reconcile outstanding tasks before taking a snapshot. The snapshot contains private book material and belongs with the owner. An older book upgrades in one transaction on its first write, or explicitly with `--book BOOK upgrade`.

## Manual exchange

`exchange reader --packet ID` prepares an unsent request containing only the fixed manuscript. `exchange source-window --window ID --actor NAME` exports the exact previously assigned study span. For an engineering exchange, use `exchange engineering --repo DIR --commit FULL_OID --input PATH --response-name NAME`; give each selected tracked file explicitly. These are local owner commands. The coordinator supplies the request and its digest to the intended recipient.

The recipient returns a JSON object with `format` set to `writing-assistant/return/1`, the original `id`, `request_sha256`, assigned response `name`, UTF-8 `text` and the text's `sha256`. Run `exchange receive ID --file RETURN.json` to validate and quarantine it. Inspect `exchange result ID`. Then use `exchange accept ID --return-sha256 SHA` to accept that exact return. A reader return records feedback on the original revision. Other kinds remain available as returned material for the owning workflow. A malformed or misbound return can be corrected and resubmitted. No operation executes received material or writes an engineering candidate into a checkout.

## Runtime installation

The GitHub release contains a wheel and a source distribution. The `host` commands manage a separate runtime ZIP format. Use the wheel or source installation instructions in the [project guide](../README.md) for these downloads.
