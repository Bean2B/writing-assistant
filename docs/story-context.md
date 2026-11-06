# 故事上下文

[中文](#中文) · [English](#english)

## 中文

故事上下文从明确给出的准确原文引用和当前 state 选择有上限的材料。它不扫描私人资料库、不隐式寻找最新章节，也不以摘要替代旧原文。

### 请求与选择

`story_context.build(project, request)` 保存 selection receipt，不调用模型；`build_in_store(store, scope, request)` 复用已有 live scope/resolver。Schema 为 `writing-assistant-story-context-request/1`，要求 `context_id`、`project_id`。

| 可选字段 | 用途 |
| --- | --- |
| `state` | `{ref, entry_ids?, tags?}`；null 表示不选 state |
| `recent_chapters` | 明确 `{ref, chapter}`，选择完整章节原文 |
| `earlier_prose` | `{ref, reason, tags?, span?}`；span 为原文 `{start, end, sha256}` |
| `tags` | 对明确旧原文索引的相关性标签 |
| `max_bytes` | 材料连同完整 receipt JSON 的总上限，默认/最大 262144 |
| `max_items` | 包含 receipt 本身的项目数，默认/最大 24 |

每个来源列表最多 64 项，合计最多 96 项；recent chapter 号唯一且为 1–20000。原文 kind 为 `prose`、`draft` 或 `fragment`，引用属于同一项目。Span 使用半开 byte 范围、独立 digest 和 UTF-8 边界；完整原文引用保留。选定 state 和证据必须仍可访问且 current。

选定 state 优先，其次为明确索引中较新的 recent chapter，再按输入顺序考虑旧原文。带 tags 的旧原文不匹配时，在 metadata/body 读取前排除；没有 tags 的项目仍是有 reason 的明确选择。标签不等于语义或文学质量判断。

预算不足时从最低优先级原文排除，receipt 写明 `budget`、`item-limit`、`unmatched-tags` 或 `duplicate`。预算排除的正文不被读取。State 不被裁短；即使不含原文，receipt 仍放不下时返回 `story_context_budget_exceeded`。Receipt 自身占预算和一个 item。

结果包含准确 `reference`、`packet`、`material_bytes`，以及供 task preparation 使用的 `materials`、`bindings`、`ranges`。所选 state、原文 ref、片段起止、digest、选择理由与排除项都可核对。完整原文 ref 不代表允许向模型显示或引用未选中的 bytes。

### 恢复

相同 `context_id` 与输入重用准确 receipt，并重核 state 和原文；不同输入为 `story_context_operation_conflict`。`inspect(project, reference)` 重读准确保存的选择。State 过时为 `stale_story_state`；原件丢失或 span digest 不符时失败，不报告已完成覆盖。

这些材料可交给 `tasks.prepare`，它仍不执行模型。新 state 的使用必须是新的明确 context 操作，不能把已保存 task 隐式改指其他版本。备份和恢复使用既有完整数据目录；新目录身份需要新的 scope。详见 [story-context schema](../schemas/story-context-v1.schema.json) 和 [task](tasks.md)。

## English

Story context selects bounded exact original prose alongside an explicitly
selected current story-state snapshot. Its only source index is the request's
exact references. It never scans an unrelated private library, discovers an
implicit latest chapter, or replaces an earlier original with a summary.

### Request

`story_context.build(project, request)` writes a selection receipt in Creative
Records and dispatches no model. `build_in_store(store, scope, request)` uses an
existing live scope and resolver. A workflow can supply its saved chapter index
directly without asking the calling Agent to reconstruct chapter history.

The request's `schema_version` is `writing-assistant-story-context-request/1`.
`context_id` and `project_id` are required. Optional fields are:

| Field | Meaning |
| --- | --- |
| `state` | `{ref, entry_ids?, tags?}` selecting one current exact story-state snapshot; `null` selects no state |
| `recent_chapters` | Explicit `{ref, chapter}` entries; complete original chapter bodies |
| `earlier_prose` | Explicit `{ref, reason, tags?, span?}` entries; a span is `{start, end, sha256}` over original bytes |
| `tags` | Declared relevance tags for the earlier source index |
| `max_bytes` | Total selected material bytes including the complete receipt JSON; default and ceiling 262144 |
| `max_items` | Material count including the receipt itself; default and ceiling 24 |

At most 64 entries in each source list and 96 combined are accepted. Recent
chapter numbers are unique and range from 1 to 20000. Prose records must have
kind `prose`, `draft` or `fragment`. All references belong to the selected project.
An earlier span is a half-open range, with its own digest; its full original
reference stays intact. UTF-8 decoding must succeed at the selected boundaries.
The saved state and selected evidence must still be available and current.

```python
from writing_assistant import story_context, tasks

context = story_context.build(project, {
    "schema_version": "writing-assistant-story-context-request/1",
    "context_id": "journey-chapter-2-draft",
    "project_id": "example",
    "state": {"ref": state_reference},
    "recent_chapters": [{"ref": chapter_1_reference, "chapter": 1}],
    "earlier_prose": [{"ref": opening_reference,
                       "reason": "Original crossing detail", "tags": ["river"],
                       "span": {"start": byte_start, "end": byte_end,
                                "sha256": selected_span_digest}}],
    "tags": ["river"]
})

request = {
    "schema_version": "writing-assistant-request/1",
    "request_id": "journey-chapter-2-draft",
    "project_id": "example", "kind": "writing", "phase": "draft",
    "request": "Write the next chapter using the selected context.",
    "materials": context["materials"]
}
prepared = tasks.prepare(project, request, bindings=context["bindings"],
                         ranges=context["ranges"])
```

`tasks.prepare` remains an unexecuted saved task. Only the existing explicit task
execution operation dispatches a model.

### Selection and exclusions

The application keeps selected state first, then gives newest explicitly indexed
recent chapters priority, then considers earlier prose in the supplied order.
An earlier indexed item with declared tags that do not intersect the requested
tags is excluded before metadata or original reads. An untagged earlier item is
an explicit selection with its supplied reason. No semantic relevance or literary
quality is inferred from the presence of a tag.

The complete receipt and all selected original bytes must fit both bounds.
Lowest-priority prose items are excluded until the actual packet fits. State
is never silently trimmed to fit: a receipt too large even without prose fails
with `story_context_budget_exceeded`. A smaller explicit state selection or larger
permitted budget is necessary. Receipt overhead counts even when no prose fits.

`packet.state` contains the selected state and its exact source reference.
`packet.selected` contains `category`, original `ref`, `start`, `end`, selected
`sha256` and the selection `reason`; recent items also have `chapter`, and tag
matches record `matched_tags`. `packet.excluded` reports only original reference,
category, `reason` (`budget`, `item-limit`, `unmatched-tags` or `duplicate`) and
known byte count. Excluded original prose is never included in the receipt or
returned result. Budget-excluded originals are not opened for body reads.

The result provides the receipt `reference`, `packet`, precise `material_bytes`,
and arrays `materials`, `bindings` and `ranges` for durable task preparation.
The receipt is a `request-material`; exact selected originals are `prior-prose`
materials. Material hashes authenticate selected byte ranges while each binding
retains the complete immutable original reference. Evidence review must use the
same visible ranges; a full original reference does not authorize citing unseen
bytes from that original.

### Exact recovery

`context_id` names an immutable selection operation. Retrying identical inputs
authenticates the saved state and selected originals and returns the same receipt.
Changing inputs under the same ID fails with `story_context_operation_conflict`.
`inspect(project, reference)` rereads the exact receipt and original selected
bytes. Changed current state fails with `stale_story_state`; lost originals or
invalid span digests fail rather than returning successful coverage. Selecting
newer state is an explicit new context operation, not implicit retargeting of a
saved task.

Selection receipts, state and originals use the existing data directory and
RecordStore. A complete quiesced file backup retains them together; reading a
copy-back requires a fresh scope bound to the restored directory identity.
These operations do not adopt generated content, update formal World facts or
provide a literary correctness judgment.

See `schemas/story-context-v1.schema.json`, [story state](story-state.md) and
[durable tasks](tasks.md) for the supported contracts.
