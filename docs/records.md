# 创作记录 / Creative records

[中文](#中文) · [English](#english)

## 中文

Agent 通过 `records` CLI 保存 user 的灵感、片段、设定、草稿、创作决定和反馈。
每个版本保留原文。Agent 可以检索获准使用的记录、读取准确版本，并准备选定草稿的
接续材料。这些操作都在本地完成，不调用模型；数据归 user 所有，内容采用由 user 决定。

下方英文参考中的例子使用 Agent 执行环境里已安装的 `writing-assistant` CLI；从 source checkout
根目录调用时，使用 `PYTHONPATH=src python3.12 -B -m writing_assistant` 代替它。
结果处理见 [Agent 接入说明](agent-usage.md)。

#### 保存与回看

准备好 `fragment.txt` 后，`save` 会保存内容，并把版本引用写入 `first.json`。
保留这份引用，之后就能准确找回这个版本。`read` 把原文写入新的 `original.txt`，
`show --raw` 则直接输出原文，不追加换行。原文的换行、emoji 和 UTF-8 BOM 均会保留。
输出文件必须是尚不存在的新文件。

修改时，将新内容写入 `revised.txt`，再按下方英文参考中的例子使用新的 `--operation-id`，
通过 `--parent-ref first.json` 指向旧版本。旧稿会保留。同一个操作 ID 只能用于
内容和保存信息完全相同的重复保存。

#### 查找旧内容

`list` 按 `version_id` 升序分页返回版本 metadata；`recent` 列出最近的版本；
`search` 在各版本的标题和正文里查找文字，可用
`--ignore-case` 忽略大小写；`history --record RECORD_ID` 查看一条记录的修改历史。
`RECORD_ID` 来自保存结果或列表。搜索结果是预览，需要完整原文时用 `read` 或
`show --raw`。

四项查询默认都分页，支持 `--limit`（默认 20，1–200）、`--cursor` 和 `--max-bytes`。
`--max-bytes` 默认 32768，最大 16777216，限制包含最后换行的
完整紧凑 UTF-8 JSON。每个返回项保持完整；byte bound 可能让当前页少于 `--limit` 条。
`range` 是本次遍历累计已返回条目的半开区间；沿用返回的 `next_cursor`
查询下一页，直到它为 `null`。`originals_truncated: false` 说明原文未被截断，不代表所有
匹配项都在当前页。

`list` 和 `search` 的 `--scan-limit` 默认 100，范围 1–2000，限制每次检查的源版本
条目数，包含权限拒绝和不匹配条目。`search` 按版本 ID 升序检查所有版本，不声称它们是
最新版本。`scan.scanned` 是实际检查的 namespace 条目数；每次 metadata projection 仍可
额外校验最多 64 个 related reference。搜索会校验两次 relation projection，并在读取正文前
重新校验准确版本，每个源条目最多触发 130 次 metadata 读取。
`scan.complete` 只说明当前页已经到达所枚举 namespace 的末尾。即使 `items` 为空，
也要继续使用非空 `next_cursor`。`total` 始终为 `null`，最后一页也不把未重新校验的
前页或未读取资料宣称为完整总数。

`recent` 保留最新版本筛选和接收时间倒序。`history` 先完整校验可见 metadata 及准确
parent reference 的线性关系，再从初稿向最新版本分页，当前调用只读取并校验本页正文。
两者仍有 O(N) metadata 工作，`total` 来自这次完整 metadata 检查。
`history.latest_stored` 仅表示已检查 metadata 链中的最新存储版本，不表示已校验未返回页正文。

四项查询在排序前都枚举现有 flat version namespace，最多访问 10001 个条目；超过
10000 个名称就返回 `scan_limit_exceeded`，不先无限量 `listdir`，也不读取源 metadata。
此时应使用另行获准的较小资料集合，调小 page limit 不能绕过 namespace 上限。
现有每个 session 的 local I/O 预算继续生效：metadata 最多 1 MiB，原文最多 16 MiB，
声明输入最多 512 MiB，实际读取最多 1 GiB，deadline 为 120 秒。增量查询超出 I/O 预算时
可减少 `--scan-limit`；完整 `recent` metadata 检查无法完成时可用 `list` 逐页查找。

单个下一项也放不下时，`context_budget_exceeded` 仅返回数值 `required_bytes` 和
`allowed_bytes`。提高 `--max-bytes` 后重用同一个 cursor；第一页仍省略 cursor。失败不会
推进 cursor 或跳项，标题、引用和预览也不会被裁短。页大小和 scan bound 可以调整。
cursor 绑定实际 data root、project、audience、record subset、查询及 namespace generation；
保存或移除版本、更换 data root 或查询范围后，旧 cursor 返回 `stale_cursor`，需从第一页重启。
原版本按 immutable storage 契约保留；直接破坏已有 metadata 或正文时，在检查到该来源时
报错，前一页不保证未访问来源没有损坏。读取期间的 namespace 变化也会拒绝本页。
搜索预览的 offset 以 Unicode code points 计数，task material range 仍使用 bytes。
Python library 的旧完整 `history()`、`RecordStore.metadata()` 和 `list_records()` 调用保持
兼容，但也受上述 namespace 和 I/O 上限约束。

#### 为下次创作留下书签

书签选定一个具体版本，还可以记下下次要处理的问题、创作决定和相关材料。下方英文参考中的
Python 例子从 `first.json` 取出版本引用，写入一个带有待解决问题的 `selection.json`；
随后用 `bookmark` 保存书签，再用 `context` 准备接续材料。

准备材料不会生成正文，也不会自动发起下一项任务。同一个准确版本和选定范围的正文
只在 `pieces` 中出现一次，`uses` 保留全部用途；`question_source` 通过从零开始的
`question_index` 对应 `questions`。原有 `purpose` 字段保留第一个用途，旧书签仍可读取。
不同版本或范围分别保留，即使文字相同也不会合并。

找不到先前保存的 bookmark reference 文件时，完整 project owner 可用 `bookmarks`
查看最近的选择，再显式使用 `context --latest-bookmark`。列表只返回确切 bookmark 和
selected ref、保存时间、operation ID、stop、baseline，以及 `total` 和
`more_available`，不返回正文或问题文字。`--limit` 为 1–200；完整扫描受既有 I/O 和
deadline 预算约束，遇到损坏或扫描未完成就报错，不把部分结果当作最新选择。

`--latest-bookmark` 与 `--bookmark FILE` 必须且只能选一个。最新选择按 bookmark
原保存时间确定，同一时间用 bookmark ID 稳定排序；重复旧 operation 不会改写保存时间。
结果仍返回确切 bookmark 和原先选定的 record version，新稿不会自动替换它。
该便利入口仅供完整 owner 使用；record subset 和其他 audience 继续使用确切 bookmark。
保存时有 baseline 的，仍须提供匹配的 `--baseline`。这些读取不会自动创作、采用内容或
恢复暂停任务。

`--max-bytes` 限制完整紧凑 UTF-8 JSON 响应的 byte 数，包括最后一个换行。超过限制时，
`context` 和 `bookmarks` 的 `context_budget_exceeded` 只返回 `required_bytes` 和
`allowed_bytes`，且先完成读取权限与完整性检查。可把限制提高到至少 `required_bytes`
（上限为 16777216），或另存一个
选择范围更小的书签。系统不会悄悄截断或用摘要代替原文。之后保存新稿，也不会替换
书签选中的旧版本。

#### 备份与恢复

停止写入后，备份整个数据目录，并保留版本引用。引用外部文件的材料还需要原文件及
读取权限；引用本身不能代替原文。

索引损坏时，可以用 `records rebuild-index` 重建，不要删除原文。原文损坏会报错，
不会生成一份替代文字。

保存、选用和正式写进故事是不同的操作。AI 任务及中断后的处理方法见[使用与恢复](usage.md)。

## English

Agents use the `records` CLI to preserve the user's ideas, fragments, settings,
drafts, decisions, and feedback. Each saved version keeps its original text.
An Agent can search permitted records, retrieve an exact version, or prepare a
selected draft for further work. These operations run locally without calling
a model. The user retains ownership and decides content adoption.

The examples use the installed `writing-assistant` CLI from the Agent's execution
environment. From a source checkout root, use
`PYTHONPATH=src python3.12 -B -m writing_assistant` in its place.
See the [Agent interface guide](agent-usage.md) for result handling.

#### Save and read a version

Create `fragment.txt`, then run:

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id first --title "First idea" > first.json
writing-assistant records --project ../demo-project read first.json --output original.txt
writing-assistant records --project ../demo-project show --ref first.json --raw
```

Keep `first.json`: it identifies this exact saved version. `read` writes the
original bytes to a new file, and `show --raw` sends them to standard output
without adding a newline. Line endings, emoji, and a UTF-8 BOM are preserved.
The output file must not already exist.

To save an edit, create `revised.txt` and link it to the earlier version:

```sh
writing-assistant records --project ../demo-project save revised.txt --operation-id second --parent-ref first.json --title "Revised idea" > second.json
```

Use a new operation ID for a new save. Repeating an earlier ID only works for
the same text and metadata. The earlier version remains available.

#### Find earlier writing

```sh
writing-assistant records --project ../demo-project list --limit 20 --scan-limit 100
writing-assistant records --project ../demo-project recent --limit 20
writing-assistant records --project ../demo-project search idea --ignore-case --scan-limit 100
writing-assistant records --project ../demo-project history --record RECORD_ID --limit 20
```

Replace `RECORD_ID` with the record ID returned by a save or listing.
`recent` shows the latest versions; `search` finds matching text in titles and
bodies across stored versions. Search results show previews. Use `read` or
`show --raw` when you need the complete original.

`list`, `recent`, `search`, and `history` return pages by default. They accept
`--limit` (1–200, default 20), `--cursor`, and `--max-bytes` (default 32768,
maximum 16777216).
The bound includes the complete compact UTF-8 JSON response and its final newline.
Each item remains complete; a byte bound can return fewer items than `--limit`.
`range` is the half-open interval of returned items accumulated in this traversal.
Pass the returned `next_cursor` unchanged to the same query until it is `null`.
A page never skips a matching entry. The existing
`originals_truncated: false` describes the stored originals, not whether every
matching entry is on this page.

`list` returns version metadata in ascending `version_id` order. `search` scans
all stored versions in that same order and returns matching previews; this is
not a chronological latest-version selection. Both accept `--scan-limit` (1–2000,
default 100), which bounds the number of source version entries inspected on
each call, including denied and nonmatching entries. Related-reference checks
remain required and may read up to 64 additional envelopes per metadata
projection. Search performs two such projections and rechecks its exact source
metadata before reading its body (up to 130 metadata reads per source entry).
`scan.scanned` reports inspected namespace entries, not all low-level I/O calls.
`scan.complete` means this page reached the end of the enumerated namespace.
An empty match page can have a `next_cursor`; continue until it is `null`.
`total` remains `null`, including on the last page: a page does not revalidate
earlier pages or claim the integrity or number of unseen records.

`recent` keeps its latest-version selection and descending receive-time order.
`history` checks the complete visible metadata and exact linear parent chain,
then pages versions from root to latest. Their `total` is derived from that
complete metadata pass. `history.latest_stored` identifies the latest stored
version in the checked metadata chain; only the returned page's original bodies
are read and verified on this call. These operations still perform O(N) metadata
work; they do not silently return a partial global latest result.

All four queries enumerate the existing flat version namespace before sorting.
Enumeration visits at most 10001 entries and fails with `scan_limit_exceeded`
when more than 10000 names exist, before source-envelope reads. This caps name
enumeration and allocation; it does not make traversal O(1). Use a narrower
separately authorized data collection when that namespace exceeds the cap;
changing a page limit does not bypass it. Existing per-session local I/O limits
also apply: 1 MiB metadata envelopes, 16 MiB original bodies, 512 MiB declared
input, 1 GiB bytes read, and a 120-second deadline. Reduce `--scan-limit` when an
incremental query exceeds its I/O budget. Prefer `list` for bounded discovery
when a complete `recent` metadata pass cannot fit.

If even one next item cannot fit, `context_budget_exceeded` reports only safe
`required_bytes` and `allowed_bytes`. Increase `--max-bytes` and reuse the same
cursor (or omit it again for the first page); the failed read does not advance it.
Page and scan bounds may change between pages. Cursors bind the physical data
root, project, audience, record subset, query and version namespace generation.
Saving or removing a version, changing scope/query, or replacing the data root
rejects the old cursor as `stale_cursor`; restart without it. Original versions
are immutable. Direct damage to an existing envelope or body is detected when
that source is checked, rather than certified absent from unvisited pages.
Namespace changes during a read also refuse the result. Titles, references, relation metadata and search
previews are not trimmed to make a page fit. Search preview offsets use Unicode
code points; task material ranges continue to use bytes. Library callers that
omit the new pagination argument retain the complete `history()` behavior;
`RecordStore.metadata()` and legacy `list_records()` keep their complete-scan
semantics under the same namespace and I/O caps.

#### Leave a bookmark for later

A bookmark selects a particular version and can keep the questions, decisions,
and material you want to return to. A newer draft does not replace that selection.
After the first save above, create a selection file:

```sh
python3.12 - <<'BOOKMARK'
import json
from pathlib import Path
selected = json.loads(Path("first.json").read_bytes())["ref"]
selection = {"selected": selected,
             "questions": [{"text": "What changes next?", "source": selected}]}
Path("selection.json").write_text(json.dumps(selection), encoding="utf-8")
BOOKMARK
writing-assistant records --project ../demo-project bookmark --operation-id selected-draft --request selection.json > bookmark.json
writing-assistant records --project ../demo-project context --bookmark bookmark.json
```

`context` prepares the selected material for continuation. It does not write new
prose or automatically start another task. Each exact version and selected range
appears once in `pieces`; different versions and ranges stay separate even when
their text matches. Each piece's `uses` preserves every purpose and uses a
zero-based `question_index` to link a `question_source` to `questions`. The legacy
`purpose` field retains the first use. Existing saved bookmarks remain readable.

To find a saved selection without locating an earlier reference file, the full
project owner can inspect recent bookmark metadata and explicitly use the latest
saved bookmark:

```sh
writing-assistant records --project ../demo-project bookmarks --limit 20 --max-bytes 32768
writing-assistant records --project ../demo-project context --latest-bookmark --max-bytes 262144
```

`bookmarks` returns exact `bookmark` and `selected` references, save time,
operation ID, stop and baseline, with `total` and `more_available`. It returns no
prose or question text. `--limit` selects the newest 1–200 entries; `--max-bytes`
bounds the complete UTF-8 JSON including its newline. The complete owner-bookmark
scan verifies sources under the existing I/O and deadline bounds. An incomplete
or corrupt scan fails; it does not return a partial latest selection.

`context` requires exactly one of `--bookmark FILE` and `--latest-bookmark`.
The convenience entrypoint chooses the most recently saved bookmark by its save
timestamp (bookmark ID breaks ties), then returns and revalidates that exact
bookmark and its selected version. A newer record version does not change it.
Repeating an existing bookmark operation does not change its original save time.
Discovery and latest selection require full-owner authority; record subsets and
other audiences continue to use an explicit exact bookmark. If the bookmark has
a baseline, supply the matching `--baseline` as with the explicit entrypoint.
These reads do not generate writing, adopt content or resume a paused task.

`--max-bytes` bounds the complete compact UTF-8 JSON response, including its final
newline, for both `context` and `bookmarks`. A `context_budget_exceeded` error
reports only `required_bytes` and `allowed_bytes`, after source access and
integrity checks. Increase the bound to
at least `required_bytes` (up to 16777216), or save a bookmark with a smaller
explicit selection. Context is never silently summarized or cut off.

#### Read machine-checkable results

`capabilities --schema core-results` exposes result definitions for every records
JSON operation. Each operation's discovery entry links its definition, including
exact record/bookmark references, nullable selections, metadata, pagination,
continuation ranges, pieces and omissions. The CLI checks these fields before
publishing JSON. Source authorization, hashes and version consistency remain
RecordStore checks; a result schema grants no authority or adoption.

`show --raw` retains the exact original byte stream, with no newline or JSON
wrapper added. Discovery names this separate byte branch and its body-size bound;
the default `show` returns checked metadata and `body_base64`. Paginated `list`,
`search` and `history` results have machine-checkable page envelopes. Source
scan limits, namespace caps and complete metadata passes have the distinct
meanings described above; a byte bound alone does not constrain source work.

#### Keep versions recoverable

Back up the whole data directory while no writer is active. Keep saved references
with it. Material stored outside that directory also needs its original files
and permissions; a reference cannot replace a missing original.

Do not delete saved text to repair a search index. `records rebuild-index`
rebuilds only the navigation index. A damaged original is reported as an error,
rather than replaced with generated text.

Saving text is separate from choosing it for a writing task or adopting it into
the story. See [usage and recovery](usage.md) for AI tasks and interrupted work.
