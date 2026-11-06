# 章节 workflow / Chapter workflows

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

Workflow 把一个创作目标变成有上限的章节 task 序列。应用保存阶段顺序、准确材料、task ID、checkpoint 和输出；Agent 调用 `next` 准备下一项，再明确执行返回的 task。你可以随时查看进度，生成内容保持未采用状态。

### 创建与推进

在已初始化的 `demo` 项目旁保存 `workflow.json`：

```json
{
  "schema_version": "writing-assistant-workflow-request/1",
  "workflow_id": "letter-story",
  "project_id": "demo",
  "goal": "写两个短章节，讲述信使归还一封没有署名的信。",
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

将 `MODEL` 换成选定模型。从 workflow 返回值复制 `PLAN_SHA256`，从 `current_task` 复制 `TASK_ID` 和 `TASK_PLAN_SHA256`。完成 task 后再次调用 `workflow next`，重复查看、执行和推进，直到 `status: completed`。

Create、inspect、next 不调用模型或 probe；只有 `task execute` 发送任务。模型、effort、timeout、配置、策略与材料选择在 create 时冻结。应用维护阶段和依赖，无须编写逐章请求文件或额外调度脚本。

### 选择阶段与上下文

`lotus` 默认每章依次执行 `plan-scene`、`draft`、`reader-review`、`continuity-review`；`none` 从 `draft` 开始。可选 `policy` 键为 `concept`、`plan_scene`、`reader_review`、`continuity_review`、`revise`。Concept 在章节前运行一次；显式 revise 每章最多一次，没有反复改写打分的循环。

两种审读各用新 task，彼此不接收反馈。Reader review 接收准确 draft 与选定近期正文；continuity review 还可接收选定 seed material、构思或章节计划。新 workflow 的审读要求[带证据的结构化输出](review-decisions.md#中文)，应用核对准确 target 与可见引文。字段有效不代表文学意见正确；格式错误或缺失的反馈不能满足依赖。构思、计划和正文不会自动成为 World Sandbox 事实。

| 选项 | 用途与范围 |
| --- | --- |
| `chapters` | 1–20 章；`goal` 最多 16384 UTF-8 bytes。 |
| `start_chapter` | 默认 1；实际章节号及最后一章均不超过 20000。 |
| `bindings` | 显式选择最多八个准确 Creative Records 版本。 |
| `policy.recent_chapters` | 带入本 workflow 的近期已完成正文，0–4 章，默认 2。 |
| `limits` | 只能降低 `max_material_bytes`、`max_prompt_bytes`、`max_output_bytes`，默认分别为 262144、524288、262144。 |
| `techniques` | 准确版本、digest 与 technique ID；建议不会自动变成选择，空数组不加载技法。 |

例如接写第 11 章，设置 `start_chapter: 11`、`chapters: 1`，相关 purpose 条目的 `value.chapter` 也使用 `11`。已有章节通过显式 `context.earlier_prose` 进入，近期窗口来自本 workflow 已完成输出。

可选 `context` 包含准确 `state`、`earlier_prose`、`tags`、`max_bytes`、`max_items`。应用的[Story context](story-context.md#中文)选择器保存原文引用、选择原因与排除项，不扫描资料库。片段引文只能落在模型实际看见的范围，offset 仍指向完整原文。超限停止准备，不静默删除必需材料。

`purpose: {aim, open_choices}` 默认来自目标，当前章节选定的 state purpose 优先。使用 `workflow update WORKFLOW_ID UPDATE_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA` 保存 `{reason, changes}`，`changes` 可包含 `purpose`、`context` 或两者。更新影响后续准备；已准备的 task 保持冻结输入，更新记录保留其 plan reference。

外部原件需要在 create 与读取原件的 next 操作提供 `--artifacts-root DIR --bindings FILE`，与请求里的 record `bindings` 独立。执行 task 时也需相应 resolver，见[可恢复任务](tasks.md#中文)。

### 处理审读意见

`review_policy.material_action` 可为 `advisory`（默认）、`hold`、`revise`。只有未解决的 `confirmed-contradiction` 且 `impact: material` 才触发策略；不确定意见和措辞偏好仍为 advisory。`max_revisions` 为 0 或 1，`revise` 要求 1；没有适用意见时跳过该 revision slot。显式 `policy.revise` 独立选择一次返修。

Hold 返回 `status: blocked`、`code: workflow_review_hold` 与准确 review reference。先查看意见，再用以下命令保存明确选择：

```sh
writing-assistant workflow --project ../demo-project decide letter-story choices.json --expected-plan-sha256 PLAN_SHA256 --expected-checkpoint-sha256 CHECKPOINT_SHA256
```

`choices.json` 包含 `chapter`、准确 `review_decision` reference、`observations`（每项有 `observation_id`、`disposition: accepted/rejected/deferred`、`reason`），以及顶层 `reason` 和 `progression: apply-policy/continue`。`continue` 需要你明确选择，只作用于该 review；其他 review 的 hold 继续有效。保存选择不会取消或改写已准备 task，也不等于采用正文。

格式错误的完成 review 可用 `workflow repair-review WORKFLOW_ID REPAIR_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA`。文件包含 `{reason, review_output}`，校正仍按原 target 与可见证据验证。原输出与校正均保留，不调用模型。缺乏依据的意见需明确决定，不能仅因格式错误重新派发。

### 状态与恢复

结果 `writing-assistant-workflow/1` 包含准确 plan/checkpoint reference 与 digest、进度、`current_task`、输出引用和 `actions`，不含稿件正文。`model_calls: 0` 描述本次 workflow 命令；task 自己保留调用历史。

Next 要求 `--expected-plan-sha256`；加上 `--expected-checkpoint-sha256` 可要求状态仍与刚查看的一致。发生并发冲突或 stale 错误后重新 inspect，沿用原 workflow/task ID。

依赖要求 task、model 和 materialization 全部完成，且输出完整。失败、不确定、冲突、损坏或过时 task 都会停止推进。先 `task inspect`，需要时用保存证据 `task reconcile`；next 不重试模型或创建替代 attempt。

`--max-bytes` 默认为 32768，范围 1024–4194304，包含 JSON 末尾换行。输出列表较大时返回 compact view 与 `details.outputs_checkpoint`，完整输出仍可按该 reference 读取。Blocked next 使用 exit `2`，stdout 留状态、stderr 留安全错误；inspect 可以成功返回 blocked。Mutation 的 `output_contract_violation` 可能已有本地保存效果，先查看原 workflow。旧计划仍可查看，应用源码或配置变化可能拒绝继续推进。

## English

A workflow turns one creative goal into a bounded sequence of chapter tasks. The application stores phase order, exact material, task IDs, checkpoints and outputs. The Agent calls `next` to prepare the next task, then explicitly executes it. Progress remains inspectable and generated content stays unadopted.

### Create once, then advance explicitly

Save `workflow.json` beside an initialized `demo` project:

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

Replace `MODEL` with the selected model. Copy `PLAN_SHA256` from the workflow response and `TASK_ID`/`TASK_PLAN_SHA256` from `current_task`. After completing the task, call `workflow next` again. Repeat inspection, execution and advancement until `status: completed`.

Create, inspect and next make no model call or probe; only `task execute` sends a task. Creation freezes model, effort, timeout, configuration, policy and material selections. The application maintains phases and dependencies without per-chapter request files or an extra orchestration script.

### Inputs and dependencies

The default `lotus` sequence per chapter is `plan-scene`, `draft`, `reader-review`, `continuity-review`; `none` starts at `draft`. Optional `policy` keys are `concept`, `plan_scene`, `reader_review`, `continuity_review`, `revise`. Concept runs once before chapters; an explicit revision adds at most one revision per chapter, without a repeated scoring loop.

Reviews use separate fresh tasks and do not receive each other's feedback. Reader review receives the exact draft and selected recent prose. Continuity review may also receive selected seed material, concept or chapter plan. New workflows require [structured review evidence](review-decisions.md#english); the application checks exact targets and visible quotes. Valid fields do not establish literary correctness. Missing or malformed feedback cannot satisfy dependencies. Concepts, plans and prose do not automatically become World Sandbox facts.

| Option | Purpose and range |
| --- | --- |
| `chapters` | 1–20 chapters; `goal` is at most 16384 UTF-8 bytes. |
| `start_chapter` | Defaults to 1; actual chapter numbers, including the last, must stay within 20000. |
| `bindings` | Explicitly selects up to eight exact Creative Records versions. |
| `policy.recent_chapters` | Includes this workflow's recent completed prose: 0–4 chapters, default 2. |
| `limits` | Can only lower `max_material_bytes`, `max_prompt_bytes`, `max_output_bytes`, whose defaults are 262144, 524288, 262144. |
| `techniques` | Exact versions, digests and technique IDs; suggestions select nothing automatically and an empty array loads none. |

For a continuation at chapter 11, use `start_chapter: 11`, `chapters: 1` and `value.chapter: 11` in a relevant purpose entry. Earlier chapters enter through explicit `context.earlier_prose`; the recent window uses this workflow's completed outputs.

Optional `context` contains exact `state`, `earlier_prose`, `tags`, `max_bytes` and `max_items`. The [story context](story-context.md#english) selector retains original references, selection reasons and exclusions without scanning a library. Quotes must fall within text shown to the model, retaining offsets into the complete original. Oversized context stops preparation instead of silently removing required material.

`purpose: {aim, open_choices}` defaults from the goal; a selected state purpose for the current chapter takes precedence. Save `{reason, changes}` with `workflow update WORKFLOW_ID UPDATE_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA`; `changes` may contain `purpose`, `context` or both. Updates affect future preparation. Prepared tasks keep frozen input and their plan reference is retained in the update record.

External originals require `--artifacts-root DIR --bindings FILE` at create and when next reads them, separately from record `bindings` inside the request. Task execution also needs the relevant resolver; see [durable tasks](tasks.md#english). Complete fields are in the [workflow request schema](../schemas/writing-workflow-v1.schema.json).

### Handle review feedback

`review_policy.material_action` is `advisory` (default), `hold` or `revise`. Only unresolved `confirmed-contradiction` observations with `impact: material` trigger it; uncertainty and wording preferences remain advisory. `max_revisions` is 0 or 1, and `revise` requires 1. An unused revision slot is skipped when no concern applies. Explicit `policy.revise` independently selects one revision.

A hold returns `status: blocked`, `code: workflow_review_hold` and exact review references. Inspect the feedback, then save explicit choices:

```sh
writing-assistant workflow --project ../demo-project decide letter-story choices.json --expected-plan-sha256 PLAN_SHA256 --expected-checkpoint-sha256 CHECKPOINT_SHA256
```

`choices.json` contains `chapter`, an exact `review_decision` reference, `observations` (each with `observation_id`, `disposition: accepted/rejected/deferred` and `reason`), plus top-level `reason` and `progression: apply-policy/continue`. `continue` requires your explicit choice and applies only to that review; another review's hold remains effective. Choices do not cancel or rewrite a prepared task or adopt prose.

For a completed review with malformed structured output, use `workflow repair-review WORKFLOW_ID REPAIR_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA`. The file contains `{reason, review_output}`; corrections are validated against the same target and visible evidence. Both original and correction are retained, without a model call. Unsupported claims need an explicit decision; a formatting failure does not justify redispatch.

### Inspect and recover

The `writing-assistant-workflow/1` result contains exact plan/checkpoint references and digests, progress, `current_task`, output references and `actions`, without manuscript bodies. `model_calls: 0` describes that workflow command; tasks retain their own call history.

Next requires `--expected-plan-sha256`. Add `--expected-checkpoint-sha256` to require the state just inspected. Inspect again after a concurrency or stale-input error, keeping the original workflow/task IDs.

Dependencies require completed task, model and materialization states plus complete output. Failed, uncertain, conflicting, corrupt or stale tasks stop progression. Use `task inspect`, then `task reconcile` where saved evidence supports recovery. Next never retries a model or creates a replacement attempt.

`--max-bytes` defaults to 32768, accepts 1024–4194304 and includes the JSON newline. A large output list returns a compact view with `details.outputs_checkpoint`; complete outputs remain readable through that reference. Blocked next uses exit `2`, status on stdout and a safe error on stderr. Inspection can succeed while reporting blocked. Mutating `output_contract_violation` can follow saved effects; inspect the original workflow first. Historical plans remain inspectable, although changed source or configuration may prevent further progression.
