# 写作上下文 / Story context

[中文](#中文) · [English](#english)

## 中文

Story context 把选定的 Story state、近期章节和较早原文整理成一份有大小上限的写作材料。Agent 可以明确指定本次续写需要哪些版本，并检查哪些材料因预算或标签匹配被排除。

这是 Python API。`story_context.build` 保存选材记录并返回可交给 `tasks.prepare` 的材料；两者都不调用模型。需要固定单篇草稿和待续问题时，也可使用[创作记录书签](records.md#中文)。

### 从准确版本准备一次续写

先按[安装指南](install.md#中文)初始化 `../demo-project`（project ID 为 `demo`），按[Story state](story-state.md#中文)创建 `journey`。将虚构章节和开篇片段保存到记录中：

```sh
writing-assistant records --project ../demo-project save chapter-1.txt --operation-id chapter-1 --kind prose --title "Chapter 1" > chapter-1.json
writing-assistant records --project ../demo-project save opening.txt --operation-id opening --kind fragment --title "Opening detail" > opening.json
```

在应用的 Python 环境中运行：

```python
import json
from pathlib import Path
from writing_assistant import story_context, story_state, tasks

project = "../demo-project"
state = story_state.inspect(project, "journey")
chapter_1 = json.loads(Path("chapter-1.json").read_bytes())["ref"]
opening = json.loads(Path("opening.json").read_bytes())["ref"]

context = story_context.build(project, {
    "schema_version": "writing-assistant-story-context-request/1",
    "context_id": "journey-chapter-2-draft",
    "project_id": "demo",
    "state": {"ref": state["reference"], "entry_ids": ["chapter-purpose"]},
    "recent_chapters": [{"ref": chapter_1, "chapter": 1}],
    "earlier_prose": [{
        "ref": opening,
        "reason": "Keep the original crossing detail available.",
        "tags": ["river"]
    }],
    "tags": ["river"],
    "max_bytes": 262144,
    "max_items": 24
})

request = {
    "schema_version": "writing-assistant-request/1",
    "request_id": "journey-chapter-2-draft",
    "project_id": "demo",
    "kind": "writing", "phase": "draft",
    "request": "Write the next chapter using the selected context.",
    "materials": context["materials"]
}
prepared = tasks.prepare(
    project, request, bindings=context["bindings"], ranges=context["ranges"],
)
```

先检查 `context["packet"]` 的 `selected` 和 `excluded`，再执行已准备的任务。`prepared` 是已保存但尚未执行的 task；执行方法与恢复见[持久任务](tasks.md#中文)。[持久 workflow](workflows.md#中文)也可以直接使用它保存的章节索引准备上下文。

### 如何选择材料

选择顺序为：选定 state → 明确索引中较新的 recent chapter → 按输入顺序排列的 earlier prose。应用只考虑请求中的准确引用，不搜索资料库或隐式挑选“最新章节”。

| 请求字段 | 用途 |
| --- | --- |
| `state` | `{ref, entry_ids?, tags?}` 选择一个当前准确 snapshot；省略或 `null` 表示不选 state。 |
| `recent_chapters` | `{ref, chapter}` 选择完整章节原文；chapter 唯一，范围 1–20000。 |
| `earlier_prose` | `{ref, reason, tags?, span?}` 选择较早原文，注明选用理由。 |
| `tags` | 与 earlier prose 的明确 tags 匹配，不做语义推断。 |
| `max_bytes` | 材料与完整选材记录 JSON 的总预算，默认及最大 262144 bytes。 |
| `max_items` | 材料数量，包含选材记录本身，默认及最大 24。 |

原文 kind 必须为 `prose`、`draft` 或 `fragment`，所有引用属于同一 project。每个来源列表最多 64 项，合计最多 96 项。带 tags 的 earlier prose 没有匹配时，在 metadata 或正文读取前排除；不带 tags 的项目按明确给定的 reason 参与选择。

只需片段时，在 earlier prose 上指定 `span: {"start": START, "end": END, "sha256": DIGEST}`。起止为原文半开 byte 范围，digest 对应选中片段，边界须能完整解码为 UTF-8。完整原文 reference 保留，用于核对版本。

### 检查输出与排除原因

| 结果字段 | 如何使用 |
| --- | --- |
| `reference` | 保存的准确选材记录引用，供恢复和检查。 |
| `packet.state` | 选定条目及其准确 state reference。 |
| `packet.selected` | 原始 `ref`、`category`、`start`、`end`、片段 `sha256` 和 `reason`；近期章节还含 `chapter`，标签匹配含 `matched_tags`。 |
| `packet.excluded` | 原始 reference、category、reason 与已知 byte 数，不包含排除的正文。 |
| `material_bytes` | 本次选中材料的准确总大小。 |
| `materials`, `bindings`, `ranges` | 一起传给 `tasks.prepare`，保留准确原件与可见范围。 |

排除原因包括 `budget`、`item-limit`、`unmatched-tags`、`duplicate`。预算不足时从最低优先级原文开始排除；预算排除的正文不会被打开。State 不被悄悄裁短。即使不含原文，完整选材记录仍放不下时，返回 `story_context_budget_exceeded`；缩小明确 state 选择，或在允许上限内增加预算。

选材记录本身作为 `request-material` 占用 bytes 和一个 item；选中原文作为 `prior-prose`。完整原文 reference 不允许模型引用未显示的 bytes，审读引用也应使用同样的可见范围。材料发送给 Codex 的边界见[隐私说明](privacy.md#中文)。

### 恢复准确选择

`story_context.inspect(project, context["reference"])` 重新读取已保存选择。已有 `RecordStore` 与 live `Scope` 的调用方可使用 `build_in_store`。

| 情况 | 如何处理 |
| --- | --- |
| 同一个 `context_id`、相同输入 | 重新校验 state 与原文，返回原来准确选材记录。 |
| `story_context_operation_conflict` | 同 ID 的输入已改变；新选择使用新的 context ID。 |
| `stale_story_state` | 查看当前 state，为新选择创建新的 context 操作和 task；已有 task 不会自动改指新状态。 |
| 原件丢失、digest 或 UTF-8 边界不符 | 恢复准确原件或修正明确范围，再重新准备。失败不能当作已完成覆盖。 |

备份选材记录、state 和原件时，保留完整静止的数据目录；恢复到新目录身份后重新获取 scope。字段定义见 [story-context schema](../schemas/story-context-v1.schema.json)。

## English

Story context assembles selected story state, recent chapters, and earlier original prose within an explicit size budget. An Agent chooses the exact versions for a writing task and can inspect material omitted for budget or tag matching.

This is a Python API. `story_context.build` saves a selection receipt and returns material for `tasks.prepare`; neither operation calls a model. For a single selected draft and continuation questions, [Creative Records bookmarks](records.md#english) are another entry point.

### Prepare a continuation from exact versions

Initialize `../demo-project` with project ID `demo` using [installation](install.md#english), and create `journey` using the [story-state guide](story-state.md#english). Save a fictional chapter and opening fragment:

```sh
writing-assistant records --project ../demo-project save chapter-1.txt --operation-id chapter-1 --kind prose --title "Chapter 1" > chapter-1.json
writing-assistant records --project ../demo-project save opening.txt --operation-id opening --kind fragment --title "Opening detail" > opening.json
```

Run this in the application's Python environment:

```python
import json
from pathlib import Path
from writing_assistant import story_context, story_state, tasks

project = "../demo-project"
state = story_state.inspect(project, "journey")
chapter_1 = json.loads(Path("chapter-1.json").read_bytes())["ref"]
opening = json.loads(Path("opening.json").read_bytes())["ref"]

context = story_context.build(project, {
    "schema_version": "writing-assistant-story-context-request/1",
    "context_id": "journey-chapter-2-draft",
    "project_id": "demo",
    "state": {"ref": state["reference"], "entry_ids": ["chapter-purpose"]},
    "recent_chapters": [{"ref": chapter_1, "chapter": 1}],
    "earlier_prose": [{
        "ref": opening,
        "reason": "Keep the original crossing detail available.",
        "tags": ["river"]
    }],
    "tags": ["river"],
    "max_bytes": 262144,
    "max_items": 24
})

request = {
    "schema_version": "writing-assistant-request/1",
    "request_id": "journey-chapter-2-draft",
    "project_id": "demo",
    "kind": "writing", "phase": "draft",
    "request": "Write the next chapter using the selected context.",
    "materials": context["materials"]
}
prepared = tasks.prepare(
    project, request, bindings=context["bindings"], ranges=context["ranges"],
)
```

Inspect `selected` and `excluded` in `context["packet"]` before execution. `prepared` is a saved, unexecuted task; see [durable tasks](tasks.md#english) for execution and recovery. A [durable workflow](workflows.md#english) can also provide its saved chapter index directly.

### How material is selected

Priority is selected state, then newest explicitly indexed recent chapters, then earlier prose in input order. Only references in the request are considered. The application does not scan a library or discover an implicit latest chapter.

| Request field | Purpose |
| --- | --- |
| `state` | `{ref, entry_ids?, tags?}` selects one exact current snapshot; omit it or use `null` for no state. |
| `recent_chapters` | `{ref, chapter}` selects complete chapter originals; chapter numbers are unique, 1–20000. |
| `earlier_prose` | `{ref, reason, tags?, span?}` selects earlier originals with a reason for each. |
| `tags` | Matches declared earlier-prose tags, without semantic inference. |
| `max_bytes` | Total material budget including the complete receipt JSON; default and maximum 262144 bytes. |
| `max_items` | Material count including the receipt itself; default and maximum 24. |

Original records must have kind `prose`, `draft`, or `fragment`, and all references belong to the same project. Each source list accepts up to 64 items, with at most 96 combined. Tagged earlier prose with no matching tag is excluded before metadata or body reads. Untagged earlier prose remains an explicit choice with its supplied reason.

For an excerpt, add `span: {"start": START, "end": END, "sha256": DIGEST}` to an earlier-prose entry. This is a half-open original byte range with the selected slice's digest; boundaries must decode as complete UTF-8. The full original reference remains intact for version checks.

### Inspect results and exclusions

| Result field | How to use it |
| --- | --- |
| `reference` | Exact saved selection receipt for recovery and inspection. |
| `packet.state` | Selected entries and their exact state reference. |
| `packet.selected` | Original `ref`, `category`, `start`, `end`, selected `sha256`, and `reason`; recent chapters add `chapter`, tag matches add `matched_tags`. |
| `packet.excluded` | Original reference, category, reason, and known byte count, without excluded prose. |
| `material_bytes` | Exact total size of selected material. |
| `materials`, `bindings`, `ranges` | Pass these together to `tasks.prepare` to retain exact originals and visible ranges. |

Exclusion reasons are `budget`, `item-limit`, `unmatched-tags`, and `duplicate`. Lowest-priority prose is removed until the packet fits; budget-excluded bodies are not opened. State is never silently shortened. If the complete receipt cannot fit even without prose, `story_context_budget_exceeded` requires a smaller explicit state selection or a larger budget within the ceiling.

The receipt is a `request-material`, counting toward bytes and one item; selected originals are `prior-prose`. A full original reference does not authorize a model to cite unseen bytes. Review evidence must use the same visible ranges. See [privacy](privacy.md#english) for what selected material can be sent to Codex.

### Recover the exact selection

`story_context.inspect(project, context["reference"])` rereads the saved selection. Callers with an existing `RecordStore` and live `Scope` can use `build_in_store`.

| Situation | What to do |
| --- | --- |
| Same `context_id` and inputs | Revalidates state and originals, then returns the same exact receipt. |
| `story_context_operation_conflict` | Inputs changed under an existing ID. Use a new context ID for a new selection. |
| `stale_story_state` | Inspect current state and create a new explicit context operation and task. A saved task is never silently retargeted. |
| Lost originals, invalid digests, or UTF-8 boundaries | Restore exact originals or correct the explicit range, then prepare again. Failure is not completed coverage. |

Back up receipts, state, and originals together in the complete data directory while writes are stopped. Obtain a fresh scope after restoring to a new directory identity. See the [story-context schema](../schemas/story-context-v1.schema.json) for complete fields.
