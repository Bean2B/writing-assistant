# 创作记录 / Creative records

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

Creative Records 为灵感、片段、设定、草稿、创作决定和反馈保存准确版本。Agent 可以找回原文、追踪修改历史，并为下一次写作留下选定版本和问题。保存与检索在本地完成，不调用模型。

本文使用已安装的 `writing-assistant` CLI 和已初始化的 `../demo-project`（project ID 为 `demo`）。初始化见[安装指南](install.md#中文)，JSON 结果与错误处理见 [Agent 接入](agent-usage.md#中文)。

### 保存原文，再保存修改

准备好 UTF-8 文件 `fragment.txt` 后：

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id first --kind fragment --title "First idea" > first.json
writing-assistant records --project ../demo-project read first.json --output original.txt
writing-assistant records --project ../demo-project show --ref first.json --raw
```

`first.json` 含有这个准确版本的 `ref`，请与稿件一起保留。`read` 将原始 bytes 写入一个尚不存在的新文件；`show --raw` 输出同样的 bytes，不加 JSON 包装或换行。原文的换行、emoji 和 UTF-8 BOM 均会保留。默认 `show` 返回 metadata 和 `body_base64`。

把修改写入 `revised.txt`，通过 `--parent-ref` 接续旧版本：

```sh
writing-assistant records --project ../demo-project save revised.txt --operation-id second --parent-ref first.json --kind draft --title "Revised idea" > second.json
```

新版本使用新的 `--operation-id`；同一个 ID 只可重试完全相同的内容和保存信息，否则返回 `operation_conflict`。旧版本保留。`--kind` 可选 `idea`、`fragment`、`draft`、`setting`、`decision`、`feedback`、`prose`；`--work` 可把相关记录归于同一个作品标识，`--authorship` 与 `--origin` 可记录来源说明。

### 找到需要的版本

```sh
writing-assistant records --project ../demo-project list --limit 20 --scan-limit 100
writing-assistant records --project ../demo-project recent --limit 20
writing-assistant records --project ../demo-project search idea --ignore-case --scan-limit 100
writing-assistant records --project ../demo-project history --record RECORD_ID --limit 20
```

| 操作 | 返回什么 |
| --- | --- |
| `list` | 按 `version_id` 升序排列的版本 metadata。 |
| `recent` | 按接收时间倒序排列的最新版本；`--all-versions` 可包含旧版本。 |
| `search` | 各已保存版本标题和正文的字面匹配预览；支持 `--ignore-case`。 |
| `history` | 一条记录从初稿到最新版本的线性修改历史。 |

`RECORD_ID` 从保存结果的 `ref.record_id` 或列表项取得。要使用完整原文，再按返回的准确 `ref` 调用 `read` 或 `show --raw`。`recent` 和 `search` 支持 `--work`。

分页时，原样传回 `next_cursor`，直到它为 `null`：

```sh
writing-assistant records --project ../demo-project search idea --ignore-case --scan-limit 100 --cursor 'RETURNED_CURSOR'
```

将 `RETURNED_CURSOR` 换成上一页返回值，保留同一查询和范围。即使 `items` 为空，也要继续使用非空 cursor。`range` 是这次遍历累计返回条目的半开区间；`originals_truncated: false` 表示原文未截断，不能据此认定当前页包含全部匹配项。

### 为下次写作保存书签

书签固定选中一个准确版本，还可以保存下次要处理的问题、决定和相关材料。以下例子在前面的 `first.json` 上留下一个问题：

```sh
python3.12 - <<'BOOKMARK'
import json
from pathlib import Path
selected = json.loads(Path("first.json").read_bytes())["ref"]
selection = {
    "selected": selected,
    "questions": [{"text": "What changes next?", "source": selected}]
}
Path("selection.json").write_text(json.dumps(selection), encoding="utf-8")
BOOKMARK
writing-assistant records --project ../demo-project bookmark --operation-id selected-draft --request selection.json > bookmark.json
writing-assistant records --project ../demo-project context --bookmark bookmark.json
```

`context` 返回接续材料，不生成新正文。每个准确版本和选定范围只在 `pieces` 中出现一次；`uses` 保留全部用途，`question_source` 的 `question_index` 从零开始对应 `questions`。兼容字段 `purpose` 保留第一个用途。不同版本或范围分别保留，即使文字相同。

找不到先前的 bookmark reference 文件时，完整 project owner 可查最近书签：

```sh
writing-assistant records --project ../demo-project bookmarks --limit 20 --max-bytes 32768
writing-assistant records --project ../demo-project context --latest-bookmark --max-bytes 262144
```

`bookmarks` 只返回准确 `bookmark`、`selected`、保存时间、operation ID、`stop`、`baseline`、`total` 和 `more_available`，不带正文或问题文字。`--latest-bookmark` 按书签原保存时间选择，同一时间按 bookmark ID 排序；重试旧 operation 不会把它变成最新书签。新稿也不会替换已选版本。

`context` 必须且只能指定 `--bookmark FILE` 或 `--latest-bookmark`。后者及 `bookmarks` 仅供完整 owner 使用；受限 record subset 或其他 audience 使用确切 bookmark。原书签含有 baseline 时，仍须提供匹配的 `--baseline`。

### 分页、大小与恢复

| 参数或结果 | 如何处理 |
| --- | --- |
| `--limit` | 四项查询为 1–200，默认 20；`bookmarks` 为 1–200。实际页可更短。 |
| `--max-bytes` | 完整紧凑 UTF-8 JSON 及最后换行的上限；查询与 `bookmarks` 默认 32768，`context` 默认 262144，最大 16777216。 |
| `--scan-limit` | `list`、`search` 每次检查 1–2000 个源版本，默认 100，包含未匹配和无读取权限的项。 |
| `context_budget_exceeded` | 返回数值 `required_bytes`、`allowed_bytes`。提高 byte 上限后重用同一个 cursor；第一页仍省略 cursor。失败不会跳项或推进 cursor。 |
| `stale_cursor` | 保存或移除版本、更换数据目录、查询或读取范围后，从第一页重新开始。 |
| `scan_limit_exceeded` | 查询的版本 namespace 超过 10000 个名称。使用另行获准的较小数据集合；减少 page limit 不能绕过此上限。 |

`search` 按版本 ID 升序检查各版本，不是只查最新稿。`list`、`search` 的 `total` 始终为 `null`；`scan.scanned` 计算源版本条目，不等于底层读取次数，`scan.complete` 只表示本页已到枚举末尾。当前页未检查的来源，不能据此认定完整或未损坏。

`recent`、`history` 都需要完整 metadata 检查，`total` 来自该检查。`history` 校验准确 parent reference 的线性关系；`history.latest_stored` 表示 metadata 链中的最新版本，本次只读取并校验返回页的正文。

查询还受 local I/O 上限约束：metadata envelope 1 MiB、单份原文 16 MiB、声明输入 512 MiB、实际读取 1 GiB、deadline 120 秒。增量查询超过 I/O 预算时减少 `--scan-limit`；完整 `recent` 检查放不下时，可用 `list` 逐页查找。Byte 上限不等于源读取工作量上限。搜索预览 offset 使用 Unicode code points，task material range 使用 bytes。

`context` 和书签列表会先校验读取权限与来源完整性，再报告 byte 预算不足。提高上限或另存选取范围更小的书签；应用不会截短原文或以摘要替换。旧书签、准确版本和 Python 完整查询 API 保持兼容，并受相同 namespace 与 I/O 上限约束。

### 备份与外部材料

停止写入后备份整个配置的数据目录，并保留版本引用。引用外部文件的记录还需要原文件及其读取权限。`import-writer`、`import-actor` 可登记明确提供的 producer 结果而不复制正文；读取时须显式提供匹配的 `--artifacts-root` 和 `--bindings`。参数见 `writing-assistant records --help` 与相应子命令 `--help`。

索引损坏时运行 `writing-assistant records --project ../demo-project rebuild-index`。它只重建索引；原文丢失或损坏会报错，请从备份恢复原件。保存记录、选作任务材料和采用到稿件是各自明确的操作。

继续阅读：[Story state](story-state.md#中文) · [Story context](story-context.md#中文) · [任务与恢复](tasks.md#中文) · [隐私](privacy.md#中文)。机器可读结果由 `capabilities --schema core-results` 提供。

## English

Creative Records keeps exact versions of ideas, fragments, settings, drafts, decisions, and feedback. An Agent can retrieve originals, follow revision history, and bookmark a selected version with questions for the next writing session. Saving and searching run locally without a model call.

This guide uses the installed `writing-assistant` CLI and an initialized `../demo-project` with project ID `demo`. See [installation](install.md#english) for setup and the [Agent interface](agent-usage.md#english) for JSON results and error handling.

### Save an original and a revision

Create a UTF-8 file named `fragment.txt`, then run:

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id first --kind fragment --title "First idea" > first.json
writing-assistant records --project ../demo-project read first.json --output original.txt
writing-assistant records --project ../demo-project show --ref first.json --raw
```

Keep `first.json`: its `ref` identifies this exact version. `read` writes original bytes to a new file that must not already exist. `show --raw` writes those bytes without a JSON wrapper or added newline. Line endings, emoji, and a UTF-8 BOM are preserved. Default `show` returns metadata and `body_base64`.

Write your changes to `revised.txt` and link the new version to the original:

```sh
writing-assistant records --project ../demo-project save revised.txt --operation-id second --parent-ref first.json --kind draft --title "Revised idea" > second.json
```

Use a new `--operation-id` for a new save. Repeating an ID retries exactly the same text and save metadata; different inputs return `operation_conflict`. Earlier versions remain available. `--kind` accepts `idea`, `fragment`, `draft`, `setting`, `decision`, `feedback`, or `prose`. `--work` groups related records under a work identifier; `--authorship` and `--origin` record source information.

### Find the version you need

```sh
writing-assistant records --project ../demo-project list --limit 20 --scan-limit 100
writing-assistant records --project ../demo-project recent --limit 20
writing-assistant records --project ../demo-project search idea --ignore-case --scan-limit 100
writing-assistant records --project ../demo-project history --record RECORD_ID --limit 20
```

| Operation | Result |
| --- | --- |
| `list` | Version metadata in ascending `version_id` order. |
| `recent` | Latest versions in descending receive-time order; `--all-versions` includes older versions. |
| `search` | Literal matching previews from titles and bodies across stored versions; supports `--ignore-case`. |
| `history` | One record's linear revision history from root to latest. |

Read `RECORD_ID` from `ref.record_id` in a save result or listing. Use the returned exact `ref` with `read` or `show --raw` for complete original text. `recent` and `search` accept `--work`.

For more results, return `next_cursor` unchanged until it is `null`:

```sh
writing-assistant records --project ../demo-project search idea --ignore-case --scan-limit 100 --cursor 'RETURNED_CURSOR'
```

Replace `RETURNED_CURSOR` with the previous result and keep the same query and scope. Continue after an empty `items` page when its cursor is non-null. `range` is the half-open interval of items returned so far in this traversal. `originals_truncated: false` describes intact originals, not complete coverage of all matches.

### Bookmark a draft for later

A bookmark fixes an exact version and can retain questions, decisions, and related material. This example adds a question to the version in `first.json`:

```sh
python3.12 - <<'BOOKMARK'
import json
from pathlib import Path
selected = json.loads(Path("first.json").read_bytes())["ref"]
selection = {
    "selected": selected,
    "questions": [{"text": "What changes next?", "source": selected}]
}
Path("selection.json").write_text(json.dumps(selection), encoding="utf-8")
BOOKMARK
writing-assistant records --project ../demo-project bookmark --operation-id selected-draft --request selection.json > bookmark.json
writing-assistant records --project ../demo-project context --bookmark bookmark.json
```

`context` returns continuation material without generating prose. Each exact version and selected range appears once in `pieces`; `uses` retains all purposes. A `question_source` uses a zero-based `question_index` into `questions`. The compatibility field `purpose` retains the first use. Different versions or ranges stay separate even when their text matches.

When you cannot locate an earlier bookmark reference file, a full project owner can inspect recent bookmarks:

```sh
writing-assistant records --project ../demo-project bookmarks --limit 20 --max-bytes 32768
writing-assistant records --project ../demo-project context --latest-bookmark --max-bytes 262144
```

`bookmarks` returns exact `bookmark` and `selected` references, save time, operation ID, `stop`, `baseline`, `total`, and `more_available`, without prose or question text. `--latest-bookmark` selects by the original save timestamp, with bookmark ID breaking ties. Retrying an old operation does not make it newest. A newer draft does not replace the selected version.

`context` requires exactly one of `--bookmark FILE` and `--latest-bookmark`. Discovery and latest selection require full-owner access; restricted record subsets and other audiences use an explicit exact bookmark. Supply the matching `--baseline` when the saved bookmark contains one.

### Pagination, bounds, and recovery

| Parameter or result | What to do |
| --- | --- |
| `--limit` | Queries accept 1–200, default 20; `bookmarks` accepts 1–200. A page may contain fewer items. |
| `--max-bytes` | Bounds complete compact UTF-8 JSON including its final newline. Default 32768 for queries and `bookmarks`, 262144 for `context`; maximum 16777216. |
| `--scan-limit` | `list` and `search` inspect 1–2000 source versions per call, default 100, including denied and nonmatching entries. |
| `context_budget_exceeded` | Reports numeric `required_bytes` and `allowed_bytes`. Increase the byte bound and reuse the same cursor; omit it again for the first page. Failure does not advance or skip an item. |
| `stale_cursor` | Restart without a cursor after saving/removing a version, replacing the data root, or changing the query or scope. |
| `scan_limit_exceeded` | The queried version namespace exceeds 10000 names. Use a smaller separately authorized data collection; a smaller page limit does not bypass this cap. |

`search` scans stored versions in ascending version ID order, rather than selecting latest drafts. `list` and `search` always report `total: null`. `scan.scanned` counts source entries, not all low-level reads; `scan.complete` means this page reached the enumerated namespace's end. A page cannot establish the integrity or completeness of sources it has not checked.

`recent` and `history` require a complete metadata pass and derive `total` from that pass. `history` validates the exact linear parent chain. `history.latest_stored` identifies its latest stored version; only bodies on the returned page are read and verified on this call.

Local I/O limits also apply: 1 MiB metadata envelopes, 16 MiB per original, 512 MiB declared input, 1 GiB bytes read, and a 120-second deadline. Reduce `--scan-limit` when an incremental query exceeds its I/O budget. Use `list` for paged discovery when a complete `recent` pass cannot fit. Output size does not bound source work. Search preview offsets use Unicode code points; task material ranges use bytes.

`context` and bookmark discovery check access and source integrity before reporting a byte-budget error. Increase the permitted bound or save a smaller explicit selection. Originals are never shortened or replaced with summaries. Existing bookmarks, exact references, and complete-query Python APIs remain compatible under the same namespace and I/O caps.

### Back up and retain external material

Back up the complete configured data directory while no writer is active, and retain version references. Externally referenced records also need their original files and read permissions. `import-writer` and `import-actor` register explicitly supplied producer results without copying their bodies. Reference reads require matching explicit `--artifacts-root` and `--bindings`; see `writing-assistant records --help` and each subcommand's `--help`.

For a damaged index, run `writing-assistant records --project ../demo-project rebuild-index`. It rebuilds the index only. Missing or damaged originals are reported as errors and need recovery from backup. Saving a record, selecting task material, and adopting writing content are separate explicit operations.

Continue with [story state](story-state.md#english), [story context](story-context.md#english), [tasks and recovery](tasks.md#english), or [privacy](privacy.md#english). Machine-readable JSON results are available through `capabilities --schema core-results`.
