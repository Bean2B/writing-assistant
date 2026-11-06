# 故事状态

[中文](#中文) · [English](#english)

## 中文

故事状态在 Creative Records 保存有版本的知识、地点、时间、资源、关系、开放问题和章节目的。每个 snapshot 都有准确引用，旧 snapshot、原始修改请求和证据范围继续保留。它不直接修改 World authority，也不自动采用稿件内容。

### 条目与证据

条目包含 `id`、`kind`、`subject`、`value`、`status`、`origin`、`evidence`、`tags`。同一 subject 使用一致拼写；应用不推断别名或判断陈述真假。

| kind | value |
| --- | --- |
| `knowledge` | `holder`, `topic`, `claim` |
| `location` | `entity`, `place` |
| `time` | `event`, `position` |
| `resource` | `holder`, `resource`, integer `amount`, `unit` |
| `relationship` | `source`, `target`, `relation` |
| `open-question` | `question`, `options`, nullable `resolution` |
| `purpose` | `chapter`, `aim`, `open_choices` |

Resource amount 为 -1000000000–1000000000；负数可表示明确代价。Time 保留明确文字，不虚构日历。Purpose 的 chapter 为 0–20000（0 表示整体目的），options/open choices 最多八项。目的可以变化，不规定结局。

`status` 为 `user_constraint`、`proposal`、`adopted_fact`。`origin=generated` 只能为 proposal；即使确认 user 授权，生成提取仍不自动成为事实。另一次已获授权的本地 user 操作可以用 `origin=user` 记录采用决定，并保留旧 proposal。

Evidence 为准确 `{ref, start, end, sha256}`，使用原文半开 byte 范围与片段 digest。每条最多四个 span，每个最多 1 MiB；constraint/adopted fact 必须有证据。原件不明、hash 改变或 scope 不符时拒绝。

### 本地 API 与恢复

`story_state.create` 创建完整初始集，`revise` 以 `expected_ref` 绑定当前 snapshot，并提供 `operation_id`、`upsert`、`remove`、`reason`、`evidence`。每次修改保存新版本，不删除旧条目历史。

创建、修改或移除已建立的 constraint/adopted fact 要求可信本地 API 参数 `user_authorized=True`；它只确认调用方已有授权，不能从 JSON 输入获得，不是远端认证凭据。修改还要求 update-level evidence。普通 proposal 更新不新增审批。

`inspect(project, state_id)` 查看当前 snapshot；明确 reference 可选历史版本。`select` 在该 snapshot 内按 entry IDs/tags 选择，默认 `require_current=True`。受限 scope 无法证明没有隐藏后继版本时返回 `story_state_current_unavailable`；明确历史读取可用 `require_current=False`，其 `current` 可以为 null。

相同 operation 与内容幂等，包括中断和后续修改之后；相同 ID 的不同内容为 `story_state_operation_conflict`，过时更新为 `stale_story_state`。同一 typed slot 的已建立事实冲突为 `conflicting_story_fact`；不同 proposal 可以并存。

每 snapshot 最多 128 条、131072 canonical entry bytes、48 个不同证据版本；每 state 最多 256 个 snapshot。读取 lineage 不扫描其他故事正文。备份整个静止的数据目录，恢复后重新获取与目录身份绑定的 owner scope。完整 schema 见 [story-state](../schemas/story-state-v1.schema.json)。

## English

Story state stores explicitly selected local knowledge, locations, time positions,
resource amounts/costs, relationships, unresolved questions and chapter purposes.
Every snapshot is an immutable Creative Records version with an exact reference.
The previous snapshot, original update request and evidence spans remain available.
These records do not change a World authority or adopt manuscript content.

### Entry contract

An entry has `id`, `kind`, `subject`, `value`, `status`, `origin`, `evidence` and
`tags`. IDs and tags are bounded identifiers. `subject` names the tracked subject;
use a consistent spelling when referring to the same subject. The application
does not infer aliases or judge the truth of a claim.

| Kind | Value fields |
| --- | --- |
| `knowledge` | `holder`, `topic`, `claim` |
| `location` | `entity`, `place` |
| `time` | `event`, `position` |
| `resource` | `holder`, `resource`, integer `amount`, `unit` |
| `relationship` | `source`, `target`, `relation` |
| `open-question` | `question`, `options`, nullable `resolution` |
| `purpose` | `chapter`, `aim`, `open_choices` |

Resource amounts range from -1000000000 to 1000000000; a negative amount can
represent a declared cost. Time positions remain explicit text, without an
invented calendar. `chapter` ranges from 0 (overall purpose) to 20000. Options
and open choices contain at most eight distinct strings. A purpose is an evolving
aim, not a required ending or a demand that a character take a predetermined path.

`status` distinguishes `user_constraint`, `proposal` and `adopted_fact`.
`origin=generated` is allowed only with `status=proposal`, even when the caller
acknowledges user authorization. Extraction from generated prose must therefore
remain a proposal. A separate, already authorized local user operation may record
an adopted fact with `origin=user`; that operation preserves the earlier proposal.
An adopted fact here records the user's local story decision, not an update to
formal World data.

Evidence is a list of `{ref, start, end, sha256}`. `ref` is the exact complete
Creative Records reference; the offsets are a half-open byte range in its intact
original body, and `sha256` authenticates that range. At most four spans per entry
are accepted, each at most 1 MiB. User constraints and adopted facts require
evidence. Selected evidence is reread through the same live scope and validated;
missing originals, changed hashes and unauthorized references fail.

### Local operations

The Python API accepts an initialized project. The `_in_store` variants accept an
existing `RecordStore` and `Scope`, preserving that caller's authority and resolver.
Reading or writing state dispatches no model.

```python
from writing_assistant import story_state

created = story_state.create(project, {
    "schema_version": "writing-assistant-story-state-request/1",
    "state_id": "journey",
    "project_id": "example",
    "operation_id": "initial-purpose",
    "entries": [{
        "id": "chapter-purpose",
        "kind": "purpose",
        "subject": "journey",
        "value": {"chapter": 1, "aim": "Expose the cost of waiting",
                  "open_choices": ["wait", "seek another crossing"]},
        "status": "proposal",
        "origin": "generated",
        "evidence": [],
        "tags": ["river"]
    }]
})

selected = story_state.select(project, created["reference"],
                              entry_ids=["chapter-purpose"])
```

`create` accepts the complete initial entry set. `revise(project, state_id,
request, expected_ref=...)` accepts `schema_version` equal to
`writing-assistant-story-state-revision/1`, an `operation_id`, `upsert`, `remove`,
`reason` and `evidence`. An upsert replaces the named entry in a new snapshot;
removals are recorded in the update and do not erase older snapshots. The exact
`expected_ref` must be the current state, except when recovering the same already
published operation.

Creating constraints/adopted facts or changing/removing an established entry
requires the trusted local API argument `user_authorized=True`. Such a revision
also requires update-level evidence. This argument acknowledges authorization
the caller already has; it is not authentication for a remote service, a grant
read from manuscript text, or a request for a new approval on ordinary proposal
updates. JSON cannot supply this argument.

`inspect(project, state_id)` returns the current snapshot and exact reference.
An explicit `reference` selects an older snapshot. `select` returns the exact
snapshot reference, selected complete entries, excluded entry IDs and currentness.
Entry IDs and tags filter only that snapshot. The default `require_current=True`
rejects a stale state. With a restricted record subset, absence of an unseen
successor cannot be established: current selection returns
`story_state_current_unavailable`; an explicit historical selection with
`require_current=False` can return `current=null` under the restricted scope.

### Integrity and recovery

Each state has an authenticated, nonblocking scoped lock. RecordStore supplies
atomic publication, immutable originals and parent CAS. A repeated identical
operation returns its exact existing version, including after interruption and
after later revisions. Reusing an operation ID with different content fails with
`story_state_operation_conflict`; a stale new update fails with
`stale_story_state`. Conflicting established values in the same typed slot fail
with `conflicting_story_fact`. Proposal disagreements can coexist with established
entries and remain visible as proposals.

Each snapshot contains at most 128 entries, at most 131072 canonical entry bytes
and at most 48 distinct evidence versions. A state admits at most 256 snapshots.
Inspecting its lineage uses deterministic operation references for that state;
it does not discover other stories or read unrelated library bodies. These bounds
are operating limits, not prose quality judgments. For file backup, quiesce local
writes and retain the complete configured data directory. After copy-back, obtain
a fresh owner scope; an old scope remains bound to the prior directory identity.

See `schemas/story-state-v1.schema.json`, [story context](story-context.md) and
[Creative Records](records.md) for the structural and storage contracts.
