# 章节 workflow

[中文](#中文) · [English](#english)

## 中文

Workflow 把一次获授权的目标转成有上限的章节 task 序列，保存阶段、准确输入、task 身份、checkpoint 和输出引用。Agent 调用 `workflow next` 准备下一项，再明确执行返回的 task；只有 `task execute` 调用模型。完成 workflow 不自动采用正文或建立 World 事实。

### 创建与推进

在已初始化的项目中保存请求文件：

```json
{
  "schema_version": "writing-assistant-workflow-request/1",
  "workflow_id": "letter-story",
  "project_id": "demo",
  "goal": "Write two short chapters about a courier returning an unsigned letter.",
  "chapters": 2
}
```

```sh
writing-assistant workflow --project ../demo-project create workflow.json --model MODEL
writing-assistant workflow --project ../demo-project inspect letter-story
writing-assistant workflow --project ../demo-project next letter-story --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 TASK_PLAN_SHA256
```

复制返回的 workflow/task ID 和 digest。完成 task 后再次调用 `next`，直到 `status: completed`。Create、inspect、next 不调用 provider，也不运行资格 probe。模型、effort、timeout、配置、策略和选择在 create 时冻结。

`lotus` 默认每章依次 `plan-scene`、`draft`、`reader-review`、`continuity-review`；`none` 从 draft 开始。可选 `policy` 明确选择 `concept`、`plan_scene`、`reader_review`、`continuity_review`、`revise`。Concept 只运行一次；显式 revise 每章最多一次，使用准确 draft 与选定反馈，没有循环打分放行。

Reader/continuity review 分别使用新 task，不读取对方反馈。新 workflow 要求带准确 draft 与可见引用证据的 structured companion。应用验证字段和引文字节，不判断文学意见正确与否。缺少或格式错误的反馈不能满足依赖。

### 材料、目的与范围

请求 schema 为 [writing-workflow](../schemas/writing-workflow-v1.schema.json)。`chapters` 为 1–20，goal 最多 16384 UTF-8 bytes。`start_chapter` 默认 1，实际章节号及最后一章不超过 20000；章节 purpose 使用实际章节号。可通过 `bindings` 明确选择最多八个准确 Creative Records 版本。

`policy.recent_chapters` 为 0–4，默认 2。`limits` 只能降低 `max_material_bytes`、`max_prompt_bytes`、`max_output_bytes` 的默认 262144、524288、262144。超限停止准备，不删除必需材料来凑预算。

可选 `context` 指定准确 state、`earlier_prose`、tags、`max_bytes`、`max_items`。应用加入自己的已完成章节，再调用 [故事上下文](story-context.md) 选择器。Receipt 保留准确原件、选择原因和排除项；原文不被摘要替代，不扫描其他资料。片段引用只能使用模型实际看见的范围。

`purpose: {aim, open_choices}` 默认来自目标；当前章节选定的 state purpose 优先。通过 `workflow update WORKFLOW_ID UPDATE_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA` 保存带 `reason` 的 purpose/context 修改。修改只影响后继准备；已准备的 task 保持原输入，并记录其准确 plan reference。

技法建议来自明确 phase/task/tags，不自动选择指导。准确 `techniques`（包括空数组）冻结到 workflow 和 task。原件 resolver 的 `--artifacts-root DIR --bindings FILE` 与请求中的 record bindings 独立，不授权目录扫描。

### 审读意见与恢复

`review_policy.material_action` 为 `advisory`（默认）、`hold` 或 `revise`。只有未解决的 `confirmed-contradiction` 且 `impact: material` 才触发；uncertainty/preference 保持 advisory。`max_revisions` 为 0 或 1，自动 revise 要求 1；没有适用意见时显式跳过该 revision slot。

Hold 返回 `status: blocked`、`code: workflow_review_hold` 与准确 review reference。用 `workflow decide` 提供章节、准确 `review_decision`、意见 ID、`accepted/rejected/deferred`、reason，以及 `progression: apply-policy` 或已获授权的 `continue`。Continue 只针对被引用的 review，不取消其他 review 的 hold。接受反馈不等于采用正文；旧意见和已拒绝意见继续保留。

格式错误的完成 review 可用 `workflow repair-review`，提供 `reason` 与 structured `review_output`，并核对 plan/checkpoint digest。原始输出不删除；修复不调用模型，也不授权 redispatch。

结果为 `writing-assistant-workflow/1`，保留准确 plan/checkpoint、进度、`current_task`、输出与 actions，不含稿件正文。`model_calls: 0` 指当前 workflow 操作；task 自己保留执行历史，正文仍为 `adopted: false`。

Next 必须带 `--expected-plan-sha256`，可加 `--expected-checkpoint-sha256`。依赖要求 task、model、materialization 全部完成且准确输出完整；失败、损坏、stale、冲突或不确定结果不能推进。Inspect 后使用原 task 的保存证据 reconcile，不重发模型、不换 ID。

`--max-bytes` 为 1024–4194304，默认 32768，包含 JSON 末尾换行。输出列表过大可返回 compact view 与 `details.outputs_checkpoint`，不截断已存输出。Blocked next 同时返回 stdout 状态、stderr 安全错误和 exit `2`。Mutation 的 `output_contract_violation` 表示 effects 可能已保存，先查看原 workflow。历史计划仍可读；应用源码或配置变化可拒绝继续推进。

## English

A workflow turns one authorized goal into a bounded sequence of chapter tasks.
The application stores the phase order, exact selected inputs, task identities,
checkpoint and output references. `workflow next` observes the current result
and prepares the next durable task. The Agent inspects and explicitly executes
that task, then calls `next` again. No per-chapter prompt files or custom
orchestration script are required.

### Create once, then advance explicitly

For a project initialized with the `lotus` writing mode, save a synthetic
`workflow.json`:

```json
{
  "schema_version": "writing-assistant-workflow-request/1",
  "workflow_id": "letter-story",
  "project_id": "demo",
  "goal": "Write two short chapters about a courier returning an unsigned letter.",
  "chapters": 2
}
```

```sh
writing-assistant workflow --project ../demo-project create workflow.json --model MODEL
writing-assistant workflow --project ../demo-project inspect letter-story
writing-assistant workflow --project ../demo-project next letter-story --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 TASK_PLAN_SHA256
writing-assistant workflow --project ../demo-project next letter-story --expected-plan-sha256 PLAN_SHA256
```

Copy `PLAN_SHA256` from the workflow and `TASK_ID` and `TASK_PLAN_SHA256` from
its `current_task`. Replace `MODEL` with the user's selected Codex model. Repeat
the task inspection/execution and `next` calls until `status` is `completed`.
Only `task execute` calls the model. `create`, `inspect` and `next` make no
provider call or capability probe. Model, reasoning effort, local timeout,
configuration, policy and selections are frozen when creating the workflow.

The default sequence is `plan-scene`, `draft`, `reader-review`,
`continuity-review` for each chapter in `lotus` mode. In `none` mode the default
starts at `draft`, with both review stages. Optional `policy` keys choose
`concept`, `plan_scene`, `reader_review`, `continuity_review` and `revise`.
`concept` runs once before chapter tasks; `revise` adds at most one revision per
chapter using the exact draft and selected review feedback. A review is a fresh
task context. There is no automatic revision loop or numerical literary pass
gate. Guidance and feedback do not establish prose quality or user acceptance.
Reader review receives the exact draft and selected recent prose. Continuity
review also receives explicitly selected seed material and the workflow's concept
or chapter plan when present. Plans and generated details stay candidates; these
inputs do not establish World Sandbox facts. Neither review sees the other's
feedback. New workflows require a structured evidence companion for each review.
The application validates exact targets and visible evidence spans while retaining
the original output. These checks do not decide whether the review is correct.
Missing or malformed feedback cannot satisfy a dependency.

`review_policy.material_action` selects `advisory` (default), `hold`, or `revise`.
Only unresolved `confirmed-contradiction` observations with `impact: material`
trigger this policy. Uncertainty and wording preferences remain advisory.
`review_policy.max_revisions` is zero or one; `revise` requires one and reserves
at most one revision per chapter. When no applicable concern exists, that slot
is explicitly skipped. The legacy explicit `policy.revise` selects one requested
revision independently of automatic feedback branching.

A material hold returns `status: blocked`, `code: workflow_review_hold` and exact
review decision references. `workflow next` preserves the hold. Save explicit
choices with `workflow decide WORKFLOW_ID CHOICES_FILE --expected-plan-sha256 SHA
--expected-checkpoint-sha256 SHA`. A choice file contains `chapter`, an exact
`review_decision` reference, `observations` with `observation_id`, `disposition`
(`accepted`, `rejected`, `deferred`) and `reason`, plus a top-level `reason` and
`progression` (`apply-policy` or an explicitly authorized `continue`). Originals,
rejected feedback and user-directed continuation remain in immutable records.
`continue` applies only to the referenced review decision; another review's
material concerns retain their configured policy. Choices saved after a task is
prepared affect successor preparation and record that frozen task reference;
they do not cancel or alter the prepared task. Execute a prepared task only
within the user's current authorization.
See [review decisions](review-decisions.md) for the structured output contract.

### Inputs and dependencies

The [workflow request schema](../schemas/writing-workflow-v1.schema.json) is
discoverable through `capabilities --schema writing-workflow`. A workflow has
one to twenty chapters and a nonempty goal of at most 16384 UTF-8 bytes.
`start_chapter` defaults to one and identifies the first actual chapter number,
up to 20000; the last selected chapter must also remain within that bound. For a
one-chapter continuation at chapter eleven, use `start_chapter: 11`, `chapters: 1`
and a selected purpose entry with `value.chapter: 11`. Saved steps, outputs and
purpose matching use actual chapter numbers; the prompt also identifies the
position within this workflow. Existing earlier chapters enter through explicit
`context.earlier_prose`, while recent context comes from this workflow's outputs.
Optional `bindings` select up to eight exact Creative Records versions using
`[{"uri":"selected:idea","ref":RETURNED_RECORD_REFERENCE}]`. Copy a complete
returned reference; this shorthand is not executable JSON. The application uses
only those authorized inputs and the workflow's own completed outputs.

The workflow builds the next task's bounded context from the selected initial
material, current chapter results and recent completed chapter text.
`policy.recent_chapters` controls this recent context window from zero to four
chapters, default two. Optional `limits` lower `max_material_bytes`,
`max_prompt_bytes` and `max_output_bytes` from defaults 262144, 524288 and 262144.
Oversized context stops preparation instead of silently removing required
material. Technique selection uses the same exact version, digest and explicit
IDs as an individual [writing task](techniques.md).

Optional `context` combines an exact `state` selection, an explicit
`earlier_prose` index, `tags`, `max_bytes` and `max_items`. The application adds
its own recent completed chapters and calls the bounded context selector. Each
prepared task exposes the exact context receipt; that receipt lists selected
originals, reasons and budget/relevance exclusions. Earlier prose can use exact
UTF-8 byte ranges. Review quotes resolve only inside the displayed slice and
retain offsets into the complete original. No prose summary replaces originals,
and no library scan is performed. See [story context](story-context.md).

`story-state create`, `revise` and `inspect` persist typed knowledge, location,
time, resource, relationship, open-question and purpose entries. Generated
entries stay proposals; user-established constraints and adopted facts require
explicit authorization. Changes use an exact prior reference. This local state
does not mutate World Sandbox facts. See [story state](story-state.md).

The workflow saves `purpose: {aim, open_choices}`; omission starts from the
authorized goal. A selected state purpose entry for the current chapter takes
precedence. `workflow update WORKFLOW_ID UPDATE_FILE --expected-plan-sha256 SHA
--expected-checkpoint-sha256 SHA` saves `{reason, changes}` where `changes`
contains `purpose`, `context`, or both. Updates affect successor tasks. Any
already prepared task keeps its frozen inputs, and the update records its exact
plan reference. Purpose changes never prescribe an ending.

Workflow creation exposes bounded technique suggestions derived from declared
phase/task and explicitly selected state/context tags. Suggestions apply no
technique. The accepted exact `techniques` selection, including an empty array,
is frozen in the workflow and every prepared task.

Reference-backed originals require `--artifacts-root DIR --bindings FILE` at
workflow creation and when `next` needs those originals. These flags describe
explicit producer bindings; they are separate from the workflow request's
record-version `bindings`. They never authorize a directory scan. Execute or
reconcile a returned task with any required artifact resolver flags as described
in [durable tasks](tasks.md).

### Inspect and recover

Results use `writing-assistant-workflow/1`. They include the frozen `plan`
reference/digest, exact `checkpoint` reference/digest, progress, `current_task`,
exact output references and available `actions`. They contain no manuscript
bodies. `model_calls: 0` and `dispatch_attempts: 0` describe the workflow command
invocation; tasks retain their own execution history. Generated text stays
`adopted: false`.

`inspect` is read-only. `next` may save a checkpoint and prepare a task, and is
safe to resume using the same workflow ID. It requires `--expected-plan-sha256`;
add `--expected-checkpoint-sha256 CHECKPOINT_SHA256` to require the checkpoint
just inspected. Inspect after a concurrency or stale-input error and preserve
the existing workflow and task identities.

A dependency is satisfied only by a completed task with completed model and
local materialization states and verified exact output. Failed, uncertain,
blocked, corrupt, stale or conflicting work cannot advance the workflow. Read
the returned current task with `task inspect`; when applicable, use its saved
evidence with `task reconcile`. `next` never retries the model, creates a
replacement attempt, adopts text or converts generated proposals into World
Sandbox facts. An unresolved failure remains blocked for the Agent to report.

Both inspection and advancement bound complete UTF-8 JSON including newline
with `--max-bytes`, from 1024 to 4194304 bytes, default 32768. A large output list
returns `view: compact`, `omitted_fields: ["outputs"]` and an exact checkpoint
reference in `details.outputs_checkpoint`; it does not truncate saved outputs.
Read that checkpoint through the exact record operation when needed.
A blocked `next` returns its status view on stdout plus exit code `2` and a
payload-free JSON error on stderr. `inspect` can succeed while reporting a blocked
state. Preserve a failing result and stderr before correcting
inputs. On `output_contract_violation`, a mutating command reports
`effect_status: unknown`; inspect the existing workflow because a plan,
checkpoint or task may already have been saved. Creating a workflow does not
authorize model execution or publication. The user retains adoption decisions.

For a completed review whose structured output is missing or malformed, preserve
its original content reference. `workflow repair-review WORKFLOW_ID REPAIR_FILE
--expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA` accepts
`{reason, review_output}` and validates the supplied structured correction
against the same exact target and selected evidence. It records the original
reference and correction before `next` consumes it. This operation makes no
model call. Unsupported review claims require an explicit decision; formatting
failure alone never authorizes redispatch. Historical plans remain inspectable;
changed application source or configuration refuses further progression.
