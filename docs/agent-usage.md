# Agent 使用说明

[中文](#中文) · [English](#english)

## 中文

Writing Assistant 是由 AI 驱动、由 Codex 开发的写作应用。Agent 是主要操作者；user 提供创作目标和授权，拥有数据，并决定是否采用生成结果。应用仍是完成这些工作的工具。

### 操作职责

Agent 依据当前配置选择记录、写作和故事操作，只读取获准材料，保留准确版本与引用。准备、执行、审读、返修和采用分别处理。每次操作都检查返回状态和保存的引用；不确定的结果先保留，再决定下一步。

默认入口为已安装的 `writing-assistant` CLI。Agent 需要本地进程执行权限，以及项目和选定材料的访问权限。安装见 [README](../README.md)。从源码根目录直接调用时，可用 `PYTHONPATH=src python3.12 -B -m writing_assistant` 替换命令名。

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant capabilities --project ../demo-project
writing-assistant config --project ../demo-project
```

创作数据使用独立目录。`init` 默认选择 `lotus` 写作模式并启用 World Sandbox，不执行 AI 任务。需要 Direct Mode 时，初始化可指定 `--writing-mode none --world-sandbox off`；之后通过 `config` 明确修改，修改在下一次任务边界生效。`none` 支持构思、写作、审读和返修；`plan-scene` 需要 `lotus`。

### 先发现接口，再准备任务

```sh
writing-assistant capabilities --operation 'task prepare'
writing-assistant capabilities --schema request
writing-assistant capabilities --detail
```

这三种选择互斥。默认返回紧凑操作索引和 schema 引用。`--max-bytes` 限制包含末尾换行的完整 UTF-8 JSON，默认 131072，最大 1048576；超限返回 `capabilities_output_limit`，不输出半截结果。未知名称返回 `unknown_capability_operation` 或 `unknown_capability_schema`。发现接口不会扫描稿件正文、调用模型或启动 provider 进程。

请求使用 `writing-assistant-request/1`，`project_id` 必须匹配项目。`phase: concept` 不要求已有稿件，生成的构思保存为未采用的 `idea`；设定与事件仍为候选。

```sh
writing-assistant check-request examples/synthetic/request.json
writing-assistant task --project ../demo-project prepare examples/synthetic/request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

从结果复制 `TASK_ID` 与 `PLAN_SHA256`，将 `MODEL` 替换为 user 选择且 Codex 可用的模型。`check-request`、`task prepare`、`task inspect` 不调用模型。`task execute` 才执行已准备的准确计划；生成结果不自动采用。`--reasoning-effort` 明确传递 effort，不继承调用方 Agent 的设置。

材料、准确 record reference、引用范围和外部原件 resolver 的要求见 [durable task](tasks.md) 与 [请求格式](interface.md)。可选技法按准确版本、digest 和 ID 明确选择，见 [技法包](techniques.md)。章节序列可由 [workflow](workflows.md) 保存顺序与依赖，Agent 明确执行返回的 task。

### 处理结果与恢复

同时检查 exit code、stdout JSON 和 stderr。错误通常为 exit code `2` 与 stderr 上的 `status: error`、`code`；AI 执行失败仍可能在 stdout 留下状态与引用。先保存失败结果，再修正输入；前置操作失败时停止依赖操作，不把空 stdout 当作 JSON。

`context_budget_exceeded` 的 `required_bytes`、`allowed_bytes` 包含完整结果与换行的字节数。成功退出不表示执行过 AI：准备结果可以是 `prepared-unexecuted`，`doctor` 只报告本地资格且 `runtime_readiness: not_checked`。

查看准确原文时，使用返回的 reference 与 `records read/show`。JSON、原始 bytes 和紧凑 receipt 各有契约；不得把省略字段当成存储内容丢失。`output_contract_violation` 的 mutation 可能已有本地效果，先 inspect，不能因此重试模型。

模型正文、记录、审读反馈、采用正文和 World 事实保持不同含义。Standalone draft 不自动开始审读或返修；workflow 仅在明确推进且依赖完整时准备选定阶段。原件、候选版本和未解决结果继续保留。

调用与恢复边界见 [CLI 使用](usage.md)、[诊断](diagnostics.md) 和 [Codex 支持](codex-support.md)。只在已授权任务内执行 AI；不确定结果不通过更换 task ID、模型或 deadline 自动重发。

## English

Writing Assistant is an AI-powered writing application developed by Codex.
The Agent is its primary operator, acting toward a human user's creative goals.
The application remains a tool: the user provides goals and authorization, owns
their data, and decides content adoption.

### Operating responsibilities

The calling Agent coordinates the work through explicit application operations:

| Area | Agent responsibility |
| --- | --- |
| Functions | Choose record, writing, or world operations appropriate to the authorized task and current project configuration. |
| Data | Select permitted material, retain exact version references, and keep original records, model output, and world facts distinct. |
| Workflow | Choose each next operation explicitly. Preparation, execution, review, revision, and content adoption are separate actions; the user decides adoption. |
| Execution | Supply the required inputs, carry any explicit model selection, inspect the returned status and saved references, and preserve uncertain outcomes before considering another action. |

The current invocation interface is the installed `writing-assistant` CLI.
The Agent calls it through a local process runner and exchanges request files
and structured command results. The application runs in the user's local
environment; the Agent needs permission to access the project and selected
material. The sections below describe the available calls and their limits.

### Initialize and inspect a project

Install the application in the Agent's execution environment using the
[README](../README.md). The examples below assume `writing-assistant` is on
`PATH`; otherwise use its installed path, such as `.venv/bin/writing-assistant`.
From the source checkout root, invoke the module directly without installation:

```sh
PYTHONPATH=src python3.12 -B -m writing_assistant capabilities
```

Replace `writing-assistant` with `PYTHONPATH=src python3.12 -B -m writing_assistant`
in the commands below when using source. If a source invocation reports
`ModuleNotFoundError: No module named 'writing_assistant'`, check the checkout
root, `PYTHONPATH=src`, and Python 3.12 before retrying the command.

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant capabilities --project ../demo-project
writing-assistant config --project ../demo-project
```

Keep creative data outside source and installation directories. Read the saved
configuration before preparing a task. `init` defaults to Lotus and World Sandbox;
it does not start an AI request. Select both initial settings in the same command:

```sh
writing-assistant init --project ../direct-project --data-dir ../direct-data --project-id direct --writing-mode none --world-sandbox off
```

Later changes use `config --writing-mode lotus` or `config --world-sandbox on`
with `--project`. Changes apply at the next task boundary. Both writing modes
support initial concept construction, drafting, review and revision; `lotus`
also supports scene planning. The catalog reads
application metadata and selected configuration without scanning manuscript
bodies or starting a provider process. Its command arguments come from the live
parser and its schemas are the shipped application schemas.

Default discovery returns a compact operation index and schema references.
Request the specific details needed for the next operation:

```sh
writing-assistant capabilities --operation 'task prepare'
writing-assistant capabilities --schema request
writing-assistant capabilities --detail
```

`--operation` selects one exact operation, `--schema` selects one schema body,
and `--detail` returns all operation details while retaining schema references.
These selections are mutually exclusive. `--max-bytes` bounds the complete UTF-8
JSON result including its newline (default 131072, maximum 1048576). An oversized
result returns `capabilities_output_limit` with no partial output; select a narrower
view or increase the explicit bound. Unknown operation/schema names refuse with
`unknown_capability_operation` or `unknown_capability_schema`.

### Prepare and execute an explicit task

Use a JSON file matching `writing-assistant-request/1`. The
[example request](../examples/synthetic/request.json) uses project ID `demo` and
no additional material. For another task, set `request`, the matching
`project_id`, and a new `request_id`.
Use `phase: concept` to build initial premise, character, world and plot candidates
without an existing scene or draft. Its output is saved as an unadopted `idea`;
proposed settings and events do not become World Sandbox facts.

```sh
writing-assistant check-request examples/synthetic/request.json
writing-assistant task --project ../demo-project prepare examples/synthetic/request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

Replace `MODEL` with the user's selected model available through Codex.
`check-request`, `task prepare` and `task inspect` do not invoke a model or qualify
a provider. Copy `TASK_ID` and `PLAN_SHA256` from the returned status. `task execute`
binds the inspected immutable plan and supports one stable local attempt. A new
Agent needs only project location and task ID; explicit `--include-context` reads
bounded frozen text. `task reconcile` completes local effects from saved evidence
without a model call. See [durable tasks](tasks.md) for identity, exact reads,
limits and interruption recovery.
`task diagnostics TASK_ID --expected-plan-sha256 SHA` returns metadata-only
applicability facts from the same execution hook. Add `--include-preflight` to
inspect scoped cases, then use the returned context for explicit diagnostic
capture/revision without reconstructing private hashes. Its `validation` states
which checks remain for execution.

For a chapter sequence, use [durable workflows](workflows.md): create one goal,
call `workflow next`, inspect and explicitly execute the returned durable task,
then call `next` again. The application keeps phase order, exact feedback targets,
bounded recent context and saved progress. Failed prerequisites stop progression.
No custom orchestration script or per-chapter request files are needed.
[Technique packs](techniques.md) provide optional explicitly selected versioned
guidance; `technique list/show` discovers their exact versions and digests offline.

Legacy top-level `prepare` returns an ephemeral packet; legacy top-level `execute`
prepares and runs immediately. They are separate from the durable task commands.
`world advance` explicitly requests Codex decisions; see [story development](world.md).
Model-dispatch operations require the user's authorization for an AI task.

Pass permitted material using exact saved references and explicit bindings.
Do not substitute a newer draft or include unrelated files. See the
[request format](interface.md) for schema fields, source roles, and byte limits,
and [creative records](records.md) for save, read, search, and bookmark commands.

### Consume command results

Normal operation results are UTF-8 JSON on standard output, followed by a newline.
`--help` and `--version` return text. `records show --raw` returns original
record bytes; `world projection --raw` and `world resolve` return projection
bytes. These outputs have no extra JSON result wrapper. Capture them without
decoding or adding a newline when preserving an exact byte sequence.

Inspect both the exit code and the result. Command errors use exit code `2`
and a JSON object on standard error with `status: error` and a `code`.
`context_budget_exceeded` also returns `required_bytes` and `allowed_bytes`;
these counts include complete serialized output and its newline, without content
or private paths.
An AI execution failure can also leave a result on standard output; preserve it.
Stop a dependent command when its prerequisite exits unsuccessfully. Save its
stderr before correcting the input, and parse stdout as JSON only when it contains
a result. Use regular request files rather than an inline shell encoding pipeline
when preserving non-ASCII text. These caller checks do not dispatch a model.
Exit code `0` alone is not proof that AI execution occurred: for example,
`prepare` returns `prepared-unexecuted`, and `doctor` reports local capability
qualification through `live_supported`, with `runtime_readiness: not_checked`,
without executing the task.

Return the actual status and saved references to the calling workflow. Preserve
an uncertain outcome; do not change a request ID to resend unknown work. Inspect
existing records before taking another action. See [recovery](usage.md) for
error codes and local data recovery.
Classify a failure using the [observed boundary](diagnostics.md#identify-the-failing-boundary-first)
before assigning its cause. Model quality, provider/network failure and an
application contract violation need different remedies; latency alone does not
distinguish them.

World runs from a supported earlier version are read-only: reads, projections,
resolution, replay, and queries of completed receipts remain available. Updates
return `legacy_source_read_only`; do not retry advancement, branch creation,
time advancement, new materialization, or unfinished settlement on that run.
Preserve it and create a new run from an explicit current configuration for new
world work. There is no automatic migration. This does not make creative records
read-only; see [world run compatibility](world.md#runs-from-an-earlier-version).

### Preserve user control and data

Recording material, preparing context, generating text, and adopting text are
separate actions. A standalone draft does not schedule review or revision.
A workflow prepares its selected successor only when explicitly advanced and
its prerequisite has complete saved evidence. The user decides content adoption.
Keep original text, exact version references, and unresolved outcomes intact.

Each AI task uses a fresh Codex context. Carry an explicit model selection with
`--model`; omission uses the CLI default with user CLI configuration ignored.
It does not inherit the calling Agent's model. Codex's own system and global
instructions can still apply. Supported builds, local time limits, and request
interruption limits are described in [Codex support](codex-support.md).
Use `--reasoning-effort` on `task prepare`, legacy `execute`, or `world advance`
to carry an explicit supported native effort. Durable preparation freezes it in
the plan; omission preserves the CLI default and does not inherit Agent settings.

Creative data and local diagnostics belong to the user. Keep them outside source
and packages, and use fictional data for public reports. Explicit AI requests
send selected permitted material through Codex's existing service. See
[privacy](privacy.md) for local storage and external service boundaries.
Explicit [diagnostic cases](diagnostics.md) provide scoped applicability checks,
immutable revisions and bounded retained-evidence reads. An advisory case does
not pause unrelated work; reduced optional diagnostic coverage does not replace
the primary action error or bypass authority checks.
