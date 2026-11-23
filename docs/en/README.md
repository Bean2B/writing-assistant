# Writing Assistant

[中文指南](../../README.md)

Writing Assistant is a local long-fiction application developed by Codex for Agents. Each book stores its chapter drafts, author cards, continuity notes and reader feedback in SQLite. A card links observations to exact quotes in a revision. A blind reader receives the selected manuscript.

## Install and start

Use Python 3.12 on Apple Silicon macOS. Download the wheel from the [release](https://github.com/Bean2B/writing-assistant/releases/tag/v0.3.1), compare its digest with the published SHA256SUMS and install it in a virtual environment.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps ./writing_assistant-0.3.1-py3-none-any.whl
writing-assistant --book books/example init Example
writing-assistant --book books/example prepare 'Plan three opening chapters' --phase plan-book
```

From a source checkout use `./scripts/writing-assistant`. The optional writing skill can be registered with your chosen harness. See [installation](../operations.md#install-a-skill), [chapter dossiers](../world-and-records.md#chapter-dossiers), [source recall](../study-and-recall.md), [reader trials](../reader-trials.md) and [model tasks](../task-runtime.md). For the wheel installation, the skill, its installer and manuals live under `share/writing-assistant/` in the virtual environment. Activate the environment before using its scripts.

### Windows source checkout

Use Python 3.13 or newer and open PowerShell in the root of this branch.

```powershell
$wa = '.\scripts\writing-assistant.cmd'
& $wa doctor
& $wa --book 'books\example' init 'Example'
```

The published v0.3.1 downloads predate these changes. Native Windows validation is pending. See [Windows book files and skills](../operations.md#windows-book-files-and-skills).

### Reading pages and shelf index

In this branch, creating or restoring a book under `books/创作作品/` or `books/学习样本/` registers its reading link in the corresponding section of `books/README.md`. Open the book’s `目录.html` to read its adopted chapter revisions offline. Chapters with no adopted revision show their latest draft.

Run `writing-assistant bookshelf books` to add missing entries, retain hand-written descriptions and build `books/书架.html`. Use `writing-assistant --book DIR reading-page` to refresh one book.

Version 0.3.1 changes the CLI and storage format from public 0.1.x. Keep the old installation and a backup when moving work. The [record importer](../prior-creative-records.md) transfers an explicitly selected prior Creative Record.
