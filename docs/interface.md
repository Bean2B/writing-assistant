# 请求格式 / Request format

[中文](#中文) · [English](#english)

## 中文

Agent 使用 JSON 文件向本地 CLI 提交写作任务。[示例请求](../examples/synthetic/request.json)可以作为起点，
完整字段定义见[请求 schema](../schemas/request-v1.schema.json)。本页说明写作和审读请求。

`capabilities --schema core-results` 可读取核心输出 schema，覆盖 discovery、durable task、
task diagnostics、全部 records/continuation、diagnostic-store、配置、doctor、请求检查、
legacy `prepare/execute` 和 world JSON 输出，以及 CLI error。
`records show --raw`、`world projection --raw` 与 byte-only `world resolve` 按独立 transport
声明保留 bytes，不添加 JSON wrapper 或换行；不能将这些 byte 分支计作 JSON 输出。
records 的分页、scan 与 namespace 限制见 records 文档；`total: null` 表示未报告完整总数，
即使当前页为空也应沿 `next_cursor` 继续。operation 的 `output_schema` 与
`output_validation` 明确各分支。mutation 返回 `view: compact` 时保留状态与准确引用，
省略字段通过明确的详情入口读取；`output_contract_violation` 中 mutation 的
`effect_status: unknown` 要求先检查已有结果，不授权重发。

每次新任务使用新的 `request_id`；`project_id` 必须与初始化的项目一致。
`request` 是本次要求，`materials` 是选定材料。`check-request` 离线检查格式，
`prepare` 核对项目和材料后生成待执行输入，两者都不调用模型。

引用旧稿时，用 `--record-bindings FILE` 把材料 URI 对应到准确的保存版本。
URI 本身不授予权限，工具也不会据此扫描其他文件或自动换成最新稿。引用的原文缺失、
变化或不可读时会报错。每次最多 32 份材料，请求文字最多 1 MiB，选定原文合计最多
4 MiB；JSON 格式正确不等于材料可以读取或任务可以执行。

`phase` 决定这次是初始构思、写作、场景准备、读者审读、连续性检查还是修改，准确枚举值见下方英文参考表。
`concept` 在两种模式中都可从初始想法开始，无须已有场景或稿件；新增设定、人物和情节
保留为候选，输出保存为未采用的 `idea`，不会自动成为 World Sandbox 事实。
审读须明确选定当前稿；修改须同时提供当前稿与反馈，并通过 `feedback_target` 绑定
同一个准确版本。直接模式支持初始构思、写作、两种审读和修改，场景准备使用 `lotus`。
从莲花切到直接模式时须使用新的上下文，已有 chat 的
历史消息不会因切换而消失。

`task execute` 或 legacy `execute` 才会调用 Codex，保存输入、输出及诊断信息。
单项任务由 Agent 明确发起；[workflow](workflows.md) 根据一次给定的目标保存阶段顺序和准确依赖，
Agent 用 `next` 准备下一任务，再明确执行。前置阶段失败时不能推进依赖。
可选 [technique packs](techniques.md) 按准确版本、digest 和 technique ID 选择；未选择时不载入。
结果由 user 决定是否采用。命令结果处理见 [Agent 接入说明](agent-usage.md)，接入范围和失败处理
见 [Codex 支持](codex-support.md)。
需要冻结并检查执行输入时，使用[durable task 操作](tasks.md)；`capabilities` 默认提供紧凑索引，
用 `--operation 'task prepare'` 读取具体操作，用 `--schema request` 读取 schema。
新 task range 使用 byte offsets，既有 continuation range
仍使用包含 BOM 的 Unicode code-point offsets。

## English

Agents submit writing tasks to the local CLI using JSON files. The complete field definitions are in the
[request schema](../schemas/request-v1.schema.json); the
[example request](../examples/synthetic/request.json) is a minimal starting point.
This page covers writing and review requests.

#### A writing request

A request uses `schema_version: writing-assistant-request/1` and includes
`request_id`, `project_id`, `kind`, `request`, and `materials`. For writing,
`kind` is `writing`. The project ID must match the initialized project. Give
each new AI task a new request ID; reusing one does not resend earlier work.

```sh
writing-assistant check-request examples/synthetic/request.json
writing-assistant prepare --project ../demo-project examples/synthetic/request.json
```

`check-request` checks the request without calling a model. `prepare` checks the
project and selected material, then returns a `writing-assistant-packet/1`
with status `prepared-unexecuted`. Neither command generates text.
Unknown fields and unsupported schema versions are errors.

Optional `techniques` selects data-only writing guidance by exact `pack_id`,
`pack_version`, `pack_sha256` and explicit `technique_ids`. Discover these with
`technique list/show`; an absent or empty selection loads none. Pack changes or
phase mismatches are rejected before preparation. See [techniques](techniques.md)
for fields, limits and versioned extensions. A [workflow request](workflows.md)
uses its separate `writing-assistant-workflow-request/1` schema to define one
bounded chapter sequence; the application prepares the individual writing
requests and exact dependencies when explicitly advanced.

#### Include earlier writing

Each material reference has a `uri`, a lowercase `sha256`, and a `purpose`.
For earlier writing, use `current-writing`. The URI identifies material; it
does not grant permission or cause the tool to search your files.

Use `--record-bindings FILE` to supply a JSON array of `{"uri": ..., "ref": ...}`
objects. Each `ref` identifies an exact saved record version. The supplied
content and request digest must match, and the record must belong to the
permitted project scope. Material that references an external original also
requires `--artifacts-root` and `--bindings` on the relevant read. Missing or
changed originals are reported rather than replaced with another version.

Requests allow at most 32 materials, up to 1 MiB of UTF-8 request text and 4 MiB
of resolved material in total. JSON Schema character counts do not replace
these byte limits. A valid JSON shape alone does not authorize a task.

#### Writing, review, and revision

The optional `phase` selects the task:

| Phase | Task and required material |
| --- | --- |
| `concept` | Build initial story concept candidates; no existing scene or draft is required. |
| `draft` | Write the requested prose; this is the default. |
| `plan-scene` | Prepare the current scene using the selected writing method. |
| `reader-review` | Review one `current-draft`, with optional selected `prior-prose`. |
| `continuity-review` | Check one `current-draft` against selected earlier writing, permitted scene material and explicit `request-material`. |
| `revise` | Revise an explicitly selected draft using supplied feedback. |

Material `role` and `source_kind` describe how each selected source is used.
Revision needs one `current-draft` and selected `feedback`. Each feedback material
must declare `feedback_target: {"uri": ..., "sha256": ...}` equal to that exact
current draft's transport reference. Same bytes under a different version do not
make the references interchangeable. Missing or wrong targets are rejected before
content resolution; stored targetless feedback stays readable. Recorded task
feedback targets are checked against full exact bindings. Imported feedback's
target is caller-declared applicability, not authenticated review provenance.
The app preserves these writing relations separately from the pinned companion
formats in the
[writing request](../src/writing_frameworks/schemas/request-v1.schema.json),
[prepared input](../src/writing_frameworks/schemas/prepared-v1.schema.json), and
[output reference](../src/writing_frameworks/schemas/output-reference-v1.schema.json)
schemas.

The `none` writing mode supports `concept`, `draft`, both review phases and `revise`;
`plan-scene` requires `lotus`. Direct draft/revision has no Lotus instruction
injection. A review does not load the Lotus method text.
Reader review receives the exact draft and selected earlier prose. Continuity
review may also receive explicitly bound concept, plan or seed material as
`request-material`. Those inputs remain proposals or user-supplied content;
binding them does not establish world facts. In a workflow, the two reviews use
fresh tasks and do not receive each other's feedback.
Concept construction explores premises, characters, pressures, world and plot
possibilities. Both modes keep generated details as candidates, saved as an
unadopted `idea`; the operation does not establish World Sandbox facts or adopt
settings. Direct concept preparation also loads no Lotus instructions.
Changing modes cannot remove earlier messages from an existing Codex chat;
use a new context when switching from Lotus to Direct Mode.

Legacy `execute` prepares the selected task and makes one bounded Codex call. It saves
input, exposed output, and diagnostics locally. Writing does not schedule review,
and review does not schedule revision for standalone tasks. Workflows prepare
their explicitly selected next stage after complete prerequisite evidence.
The user decides whether to adopt any result.
The [Agent interface guide](agent-usage.md) describes command result handling.
See [Codex support](codex-support.md) for compatibility and failure handling.
For an inspected frozen execution binding, use [durable task operations](tasks.md).
`capabilities` returns a compact index without a provider call. Use
`capabilities --operation 'task prepare'` for actual arguments and operating limits,
or `capabilities --schema request` for the current schema body. Task ranges use byte offsets; existing
continuation selections use `unicode_code_points_utf8_including_bom`.

#### Core result contracts

`capabilities --schema core-results` returns the
[core output schema](../schemas/core-results-v1.schema.json). Its definitions cover
capability discovery, durable task full/compact results, task-bound diagnostics,
all Creative Records and diagnostic-store JSON operations, configuration,
local Codex qualification, request checking, legacy preparation/execution,
world JSON operations, technique discovery, workflow views, and the CLI error
envelope. Every discoverable JSON operation links its definition; `world resolve`
declares a byte-only transport.
Operation discovery supplies `output_schema` and `output_validation: core-fields`
for JSON outputs. Schema bytes and the CLI's
fixed field checks come from the same definitions. They preserve existing JSON
envelopes and allow additive receipt metadata; provider usage remains opaque JSON,
and an absent optional observation summary on an older receipt is not backfilled.
When an observation summary is present, its elapsed unit/scope and unknown cost
fields are checked explicitly.
Optional `operation_timings` entries describe the first observed local task
operation, with an exact record reference, monotonic elapsed seconds and an
explicit measurement scope. Older tasks can omit them. A sampled outcome can
differ from the current task state; consult [task timing](usage.md) for its limits.
An optional `timing_recording` warning reports unavailable timing persistence
without changing an already completed task effect.

The checks establish the declared core field types, identifiers, versions and
missing/null behavior. They do not replace source integrity, ownership, exact
input, execution-state or content validation in the owning application modules.
An outbound mismatch returns `output_contract_violation` on stderr with exit 2.
It retains only allowlisted safe operation/project/request/task/run/case/pending
identity, digest and exact record, bookmark, diagnostic or projection references
where available. Read-only
operations report `effect_status: none`; covered mutations, including an original
file readback, report `unknown` because local effects can already exist. Inspect
those effects before any further action.

Configuration read and change results retain their existing envelopes. A
configuration read reports `effect_status: none` on a contract failure; a change
can already have persisted effects and reports `unknown`. Explicit configuration
inspection still returns its configured data path; safe errors never copy that
path. Doctor results describe local probe scope and keep runtime readiness
`not_checked`; schema validation does not establish provider compatibility.

Records traversal pages can report `total: null` with `scan.scanned` and
`scan.complete`; continue with `next_cursor` even after an empty match page.
History pages validate bounded complete metadata topology, with original-byte
verification limited to returned versions. See [records](records.md) for cursor,
scan, namespace and output-byte limits. Python legacy list/history shapes remain
accepted by the result definitions.

`records show` and `world projection` explicitly declare
`output_validation: json-fields-or-original-bytes` and `output_variants`. The
default JSON branch uses its linked definition; `--raw` returns
the exact selected original bytes after RecordStore integrity checks and a byte
type/size check, or the native world's selected projection checks. `world resolve`
itself selects exact projection bytes and declares `output_validation: original-bytes`
with `output_schema: null`. These byte branches receive no wrapper or added newline;
records originals can be empty or non-UTF-8. Unexpected JSON in a requested byte
branch, or unexpected bytes in a JSON branch, fail before publication.

The schema describes output transport shapes. World observation/profile/action
objects retain native semantic validation and visibility rules; provider usage
remains opaque. Neither shape validation nor an exact projection reference grants
writer disclosure approval, adoption, remote stop assurance or cost attestation.
Text help/version output remains text, outside JSON result definitions.
