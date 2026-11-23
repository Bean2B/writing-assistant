# Import a prior Creative Records version

The previous public CLI can export one readable version as an owner-scoped `creative-records/1` document. Select its exact ref or the original save receipt. Preserve the source project and the exported file. The following example uses `old-wa` for the previous installed launcher and performs no model calls.

```sh
old-wa records --project "$old_project" show --ref selected.json > selected-export.json
shasum -a 256 selected-export.json
./scripts/writing-assistant --book "$book" import-record \
    --selection selected.json --export selected-export.json \
    --export-sha256 "$approved_export_sha256" --category research
```

Supply the approved digest of the complete export and select the destination book and category. The new audience defaults to owner. An explicit `--audience` must also be visible under the original owner export. The importer reads just the selection and the one exported object. It verifies its old contract, project, record, version, operation binding, body size and SHA-256. It also checks the complete export digest, which covers the supplied attribution. A ref alone does not prove transfer permission. Use only a version authorized for this book, category and audience.

The returned new ref works with `records read REF` for exact bytes and the Creative Records navigation commands. The metadata retains the original ref, projected parent/relations, original audience, timestamps, source attribution and export digest. Each selected old version is an independent destination record. Repeating the identical import is idempotent. The previous store stays independent, and only the exact version named in the selection is materialized. A binary record can be read as original bytes. Text preparation requires UTF-8.

Source records backed by a live producer require its authorization on every read. This importer accepts inline originals. An unaccompanied `saved-original` receipt and raw file omit the original audience and attribution. Obtain the complete `records show` export for that exact version.
