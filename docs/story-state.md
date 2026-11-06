# 人物与设定状态 / Story state

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

Story state 帮助 Agent 记录“谁知道什么、谁在哪里、资源还剩多少、哪些问题尚未解决”，并把这些信息带入后续写作。它以有版本的 snapshot 保存在 Creative Records 中，方便查看旧决定和修正前后矛盾。

适合追踪人物知识、地点、时间、资源、关系、开放问题和章节目的。条目由调用方明确提供；应用不从稿件中自动提取事实，也不推断人物别名。整理生成内容时先保存为 `proposal`，由 user 决定是否采用。

以下命令使用已初始化的 `../demo-project`，project ID 为 `demo`。初始化见[安装指南](install.md#中文)。这些操作不调用模型。

### 创建第一个状态

将以下虚构示例保存为 `state.json`：

```json
{
  "schema_version": "writing-assistant-story-state-request/1",
  "state_id": "journey",
  "project_id": "demo",
  "operation_id": "initial-purpose",
  "entries": [{
    "id": "chapter-purpose",
    "kind": "purpose",
    "subject": "journey",
    "value": {
      "chapter": 1,
      "aim": "Expose the cost of waiting",
      "open_choices": ["wait", "seek another crossing"]
    },
    "status": "proposal",
    "origin": "generated",
    "evidence": [],
    "tags": ["river"]
  }]
}
```

```sh
writing-assistant story-state --project ../demo-project create state.json > state-result.json
writing-assistant story-state --project ../demo-project inspect journey
```

结果的 `reference` 固定这个 snapshot；`snapshot.entries` 保留完整条目。`state_id` 标识这一组持续修改的 Story state，`operation_id` 标识这次保存。`subject` 对同一对象应使用一致拼写。

### 修改状态，并保留旧版

下面从刚保存的结果取出准确引用，修改章节目的，并生成 revision 请求：

```sh
python3.12 - <<'STATE'
import json
from pathlib import Path
result = json.loads(Path("state-result.json").read_bytes())
Path("state-ref.json").write_text(json.dumps(result["reference"]), encoding="utf-8")
entry = json.loads(Path("state.json").read_bytes())["entries"][0]
entry["value"]["aim"] = "Make the cost of the detour visible"
revision = {
    "schema_version": "writing-assistant-story-state-revision/1",
    "operation_id": "revise-purpose",
    "upsert": [entry], "remove": [],
    "reason": "The chapter now follows the detour.", "evidence": []
}
Path("state-revision.json").write_text(json.dumps(revision), encoding="utf-8")
STATE
writing-assistant story-state --project ../demo-project revise journey state-revision.json --expected-ref state-ref.json
writing-assistant story-state --project ../demo-project inspect journey --reference state-ref.json
```

`upsert` 在新 snapshot 中添加或替换同 ID 条目，`remove` 接受要移除的 entry IDs。旧 snapshot 仍可按准确引用读取。`--expected-ref` 和 `--reference` 文件只放 reference 对象，不放完整结果。

### 选择条目供写作使用

Python 调用方可以按 ID 或 tags 选择一个准确 snapshot 的条目，再交给[Story context](story-context.md#中文)：

```python
from writing_assistant import story_state

project = "../demo-project"
current = story_state.inspect(project, "journey")
selected = story_state.select(
    project, current["reference"], entry_ids=["chapter-purpose"],
)
```

`select` 返回准确 snapshot reference、完整选中条目、排除的 IDs 和 `current`。默认 `require_current=True`，拒绝过时状态。受限 record subset 无法证明没有隐藏后继版本时，返回 `story_state_current_unavailable`；已知历史版本可显式用 `require_current=False` 读取，此时 `current` 可为 `null`。已有 `RecordStore` 与 `Scope` 的调用方可使用相应 `_in_store` API。

### 条目类型与证据

每条 entry 都有 `id`、`kind`、`subject`、`value`、`status`、`origin`、`evidence`、`tags`。

| `kind` | `value` 字段 |
| --- | --- |
| `knowledge` | `holder`, `topic`, `claim` |
| `location` | `entity`, `place` |
| `time` | `event`, `position` |
| `resource` | `holder`, `resource`, integer `amount`, `unit` |
| `relationship` | `source`, `target`, `relation` |
| `open-question` | `question`, `options`, nullable `resolution` |
| `purpose` | `chapter`, `aim`, `open_choices` |

`status` 可为 `proposal`、`user_constraint`、`adopted_fact`。`origin=generated` 只能与 `proposal` 配合。记录 user 已有的采用决定时，另做一次 `origin=user` 操作，保留早先 proposal。这里的 adopted fact 不会修改 `world` run 的事实。

Constraint 和 adopted fact 必须带证据：`{ref, start, end, sha256}` 指向准确 Creative Records 版本和原文半开 byte 范围，digest 对应该片段。应用重新核对读取权限、原件与 digest；每条最多四个 span，每个最多 1 MiB。

创建、修改或移除已建立的 constraint/adopted fact，要求已有明确 user 授权，并通过 CLI 的 `--user-authorized` 或 Python 的 `user_authorized=True` 确认；revision 还需要 update-level evidence。这个参数不从 JSON 或稿件中取得，也不能用作远端认证。普通 proposal 修改不需要这个参数。

### 错误与操作上限

| 结果或错误 | 下一步 |
| --- | --- |
| 重试相同 operation 与内容 | 返回原来准确版本，即使之后已有其他 revision。 |
| `story_state_conflict`, `story_state_operation_conflict` | 同 state 的初始请求或 revision ID 被用于不同内容；核对已有状态，新修改使用新的 operation ID。 |
| `stale_story_state` | 读取当前状态，重新考虑修改，再提供新的准确 `expected_ref`。 |
| `conflicting_story_fact` | 同一 typed slot 的已建立事实冲突；核对并明确修正事实。不同 proposal 可并存。 |
| `output_limit` | 增加 CLI `--max-bytes`；默认 131072，允许 1024–4194304。写入命令应先 inspect 再决定是否重试。 |

Resource amount 为 -1000000000–1000000000，负数可表示明确代价。Time 保留明确文字。Purpose 的 chapter 为 0–20000，0 表示整体目的；`options` 和 `open_choices` 各最多八项。目的可以改变，不固定结局。

每 snapshot 最多 128 条、131072 canonical entry bytes、48 个不同证据版本；每 state 最多 256 个 snapshot。备份方式见[创作记录](records.md#中文)。完整字段见 [story-state schema](../schemas/story-state-v1.schema.json)；输出与失败处理见 [Agent 接入](agent-usage.md#中文)。

## English

Story state helps an Agent track who knows what, where people are, available resources, and unresolved questions for later writing. Versioned snapshots in Creative Records let callers revisit decisions and correct continuity problems.

Use it for knowledge, locations, time, resources, relationships, open questions, and chapter purposes. The caller supplies entries explicitly; the application does not extract facts from prose or infer aliases. Keep extracted generated content as a `proposal` until the user decides to adopt it.

These examples use an initialized `../demo-project` with project ID `demo`; see [installation](install.md#english). State operations make no model call.

### Create the first state

Save this fictional example as `state.json`:

```json
{
  "schema_version": "writing-assistant-story-state-request/1",
  "state_id": "journey",
  "project_id": "demo",
  "operation_id": "initial-purpose",
  "entries": [{
    "id": "chapter-purpose",
    "kind": "purpose",
    "subject": "journey",
    "value": {
      "chapter": 1,
      "aim": "Expose the cost of waiting",
      "open_choices": ["wait", "seek another crossing"]
    },
    "status": "proposal",
    "origin": "generated",
    "evidence": [],
    "tags": ["river"]
  }]
}
```

```sh
writing-assistant story-state --project ../demo-project create state.json > state-result.json
writing-assistant story-state --project ../demo-project inspect journey
```

The result's `reference` fixes this snapshot, and `snapshot.entries` contains complete entries. `state_id` identifies the evolving set of state entries; `operation_id` identifies this save. Use consistent `subject` spelling for the same subject.

### Revise state and retain the previous version

Extract the exact reference, change the chapter purpose, and create a revision request:

```sh
python3.12 - <<'STATE'
import json
from pathlib import Path
result = json.loads(Path("state-result.json").read_bytes())
Path("state-ref.json").write_text(json.dumps(result["reference"]), encoding="utf-8")
entry = json.loads(Path("state.json").read_bytes())["entries"][0]
entry["value"]["aim"] = "Make the cost of the detour visible"
revision = {
    "schema_version": "writing-assistant-story-state-revision/1",
    "operation_id": "revise-purpose",
    "upsert": [entry], "remove": [],
    "reason": "The chapter now follows the detour.", "evidence": []
}
Path("state-revision.json").write_text(json.dumps(revision), encoding="utf-8")
STATE
writing-assistant story-state --project ../demo-project revise journey state-revision.json --expected-ref state-ref.json
writing-assistant story-state --project ../demo-project inspect journey --reference state-ref.json
```

`upsert` adds or replaces named entries in a new snapshot; `remove` accepts entry IDs. Older snapshots remain readable by exact reference. Files supplied to `--expected-ref` and `--reference` contain the reference object alone, not the complete result.

### Select entries for writing

Python callers can select entries by ID or tags within an exact snapshot, then pass it to [story context](story-context.md#english):

```python
from writing_assistant import story_state

project = "../demo-project"
current = story_state.inspect(project, "journey")
selected = story_state.select(
    project, current["reference"], entry_ids=["chapter-purpose"],
)
```

`select` returns the exact snapshot reference, complete selected entries, excluded IDs, and `current`. Default `require_current=True` refuses stale state. A restricted record subset cannot prove the absence of hidden successors and returns `story_state_current_unavailable`. For an explicit historical read, set `require_current=False`; `current` can then be `null`. Callers with an existing `RecordStore` and `Scope` can use the corresponding `_in_store` APIs.

### Entry types and evidence

Each entry has `id`, `kind`, `subject`, `value`, `status`, `origin`, `evidence`, and `tags`.

| `kind` | `value` fields |
| --- | --- |
| `knowledge` | `holder`, `topic`, `claim` |
| `location` | `entity`, `place` |
| `time` | `event`, `position` |
| `resource` | `holder`, `resource`, integer `amount`, `unit` |
| `relationship` | `source`, `target`, `relation` |
| `open-question` | `question`, `options`, nullable `resolution` |
| `purpose` | `chapter`, `aim`, `open_choices` |

`status` is `proposal`, `user_constraint`, or `adopted_fact`. `origin=generated` is valid only for a `proposal`. To record an existing user adoption decision, make a separate `origin=user` operation and retain the earlier proposal. An adopted fact here does not update facts in a `world` run.

Constraints and adopted facts require evidence: `{ref, start, end, sha256}` selects an exact Creative Records version and a half-open original byte range with its digest. The application rechecks access, originals, and hashes. Each entry allows up to four spans, at most 1 MiB each.

Creating, changing, or removing an established constraint/adopted fact requires existing explicit user authorization, acknowledged with CLI `--user-authorized` or Python `user_authorized=True`. A revision also needs update-level evidence. JSON or manuscript text cannot supply that argument, and it is not remote-service authentication. Ordinary proposal updates do not require it.

### Errors and operating bounds

| Result or error | Next step |
| --- | --- |
| Identical operation and inputs | Returns the original exact version, even after later revisions. |
| `story_state_conflict`, `story_state_operation_conflict` | Initial state inputs or a revision ID conflict with saved content. Inspect state and use a new operation ID for a new change. |
| `stale_story_state` | Inspect current state, reconsider the change, then supply the new exact `expected_ref`. |
| `conflicting_story_fact` | Established values conflict in one typed slot. Review and explicitly correct them. Different proposals can coexist. |
| `output_limit` | Increase CLI `--max-bytes`: default 131072, allowed 1024–4194304. Inspect a write's state before deciding whether to retry. |

Resource amounts range from -1000000000 to 1000000000; negative values can represent declared costs. Time remains explicit text. Purpose `chapter` ranges from 0 (overall purpose) to 20000; `options` and `open_choices` allow up to eight strings each. Purposes can change without fixing the ending.

A snapshot allows up to 128 entries, 131072 canonical entry bytes, and 48 distinct evidence versions. A state allows up to 256 snapshots. See [Creative Records](records.md#english) for backup, the [story-state schema](../schemas/story-state-v1.schema.json) for complete fields, and the [Agent interface](agent-usage.md#english) for output and failure handling.
