# Agent 使用说明 / Agent guide

[中文](#中文) · [English](#english)

## 中文

Writing Assistant 通过本地 CLI 为 Agent 提供创作记录、写作 task 和章节 workflow。你给出创作目标并决定采用哪些结果；应用保存输入、阶段顺序、状态和版本关系，Agent 调用所需操作并向你解释结果。

### 开始使用

按[安装指南](install.md#中文)安装后，先查看项目与可用操作：

```sh
writing-assistant config --project ../demo-project
writing-assistant capabilities --project ../demo-project
writing-assistant capabilities --operation 'task prepare'
```

新项目只初始化一次，创作数据放在源码与安装目录之外：

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
```

默认启用 `lotus` 写作模式与 World Sandbox。Direct Mode 使用 `--writing-mode none --world-sandbox off`。已有项目通过 `config` 明确修改设置，在下一个任务边界生效。两种模式均支持构思、写作、审读和返修；`plan-scene` 需要 `lotus`。

### 准备、查看并执行一个任务

将[示例请求](../examples/synthetic/request.json)的 JSON 保存为本地 `request.json`，或复制[请求格式](interface.md#中文)中的最小示例。填写本次 `request`、匹配的 `project_id` 和新的 `request_id`：

```sh
writing-assistant check-request request.json
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

将 `MODEL` 换成选定且账号可用的 Codex 模型，从返回值复制 `TASK_ID` 与 `PLAN_SHA256`。前三条命令不调用模型；`task execute` 才发送已准备的任务。模型和 `--reasoning-effort` 不继承当前 Agent 的设置，详见 [Codex 支持](codex-support.md#中文)。

应用负责冻结输入、校验准确版本、保存执行结果和维护依赖；Agent 负责选择获准材料、明确执行并处理返回状态。生成内容保留为未采用版本，由你决定是否使用。

| 需求 | 入口 |
| --- | --- |
| 保存、查找、读取原文 | [创作记录](records.md#中文) |
| 构思、单次写作、审读、返修 | [请求格式](interface.md#中文)与[可恢复任务](tasks.md#中文) |
| 按阶段生成多个章节 | [章节 workflow](workflows.md#中文) |
| 选择技法、Story state 与写作上下文 | [技法包](techniques.md#中文)、[Story state](story-state.md#中文)、[Story context](story-context.md#中文) |
| 推进 World Sandbox | [角色行动推演](world.md#中文) |

### 处理命令结果

通常读取 exit code、stdout JSON 和 stderr。正常 JSON 以一个换行结束；`--help`、`--version` 返回文本。`records show --raw`、`world projection --raw` 与 `world resolve` 返回原始 bytes，不加 JSON wrapper 或换行。

错误通常使用 exit code `2` 和 stderr JSON 的 `status: error`、`code`。执行失败也可能在 stdout 留下状态和保存引用，应一并保留。前置操作失败后停止依赖操作，不解析空 stdout，也不只凭 exit code `0` 宣称已生成内容。

结果不明时先 `task inspect`。如需根据已保存结果完成本地保存，使用 `task reconcile`；它不再次调用模型。`output_contract_violation` 也可能发生在本地效果已保存之后，应先查看原 task。不要通过换 ID 重发结果未知的任务。详见[恢复](usage.md#中文)与[诊断](diagnostics.md#中文)。

### 发现接口与读取细节

```sh
writing-assistant capabilities --schema request
writing-assistant capabilities --detail
```

`--operation`、`--schema`、`--detail` 互斥。Discovery 不扫描稿件或调用模型。输出上限 `--max-bytes` 默认为 131072、最大 1048576，包含 UTF-8 JSON 的末尾换行。超限返回 `capabilities_output_limit`；未知名称返回 `unknown_capability_operation` 或 `unknown_capability_schema`。优先请求需要的单项操作或 schema。

保存准确 reference，再用 `records read/show` 读取全文。紧凑结果的 `omitted_fields` 表示响应省略了字段，不表示存储内容丢失。任务、workflow、记录和诊断的详细限额见对应页面及 discovery。

## English

Writing Assistant gives Agents a local CLI for creative records, writing tasks and chapter workflows. You set the creative goal and choose which results to use. The application stores inputs, phase order, status and version relationships; the Agent invokes the needed operations and explains their results.

### Get started

Follow the [installation guide](install.md#english), then inspect the project and available operations:

```sh
writing-assistant config --project ../demo-project
writing-assistant capabilities --project ../demo-project
writing-assistant capabilities --operation 'task prepare'
```

Initialize a new project once, keeping creative data outside source and installation directories:

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
```

The defaults are `lotus` writing mode and World Sandbox enabled. For Direct Mode, add `--writing-mode none --world-sandbox off`. Change an existing project's settings explicitly with `config`; changes apply at the next task boundary. Both modes support concept work, drafting, review and revision; `plan-scene` requires `lotus`.

### Prepare, inspect and execute one task

Save the JSON from the [example request](../examples/synthetic/request.json) locally as `request.json`, or copy the minimal example in [request format](interface.md#english). Set the current `request`, matching `project_id` and a new `request_id`:

```sh
writing-assistant check-request request.json
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

Replace `MODEL` with the selected Codex model available to the account. Copy `TASK_ID` and `PLAN_SHA256` from the response. The first three commands make no model call; `task execute` sends the prepared task. Model and `--reasoning-effort` settings are not inherited from the calling Agent; see [Codex support](codex-support.md#english).

The application freezes inputs, checks exact versions, stores results and maintains dependencies. The Agent selects permitted material, explicitly executes operations and handles their returned status. Generated content remains unadopted until you decide to use it.

| Need | Guide |
| --- | --- |
| Save, find and read original text | [Creative records](records.md#english) |
| Concept work, one writing task, review or revision | [Request format](interface.md#english) and [durable tasks](tasks.md#english) |
| Generate chapters in a saved phase order | [Chapter workflows](workflows.md#english) |
| Select techniques, story state and context | [Techniques](techniques.md#english), [story state](story-state.md#english), [story context](story-context.md#english) |
| Advance World Sandbox | [Character action simulation](world.md#english) |

### Consume command results

Read the exit code, stdout JSON and stderr together. Normal JSON ends with a newline; `--help` and `--version` return text. `records show --raw`, `world projection --raw` and `world resolve` return original bytes without a JSON wrapper or added newline.

Errors normally use exit code `2` with `status: error` and `code` in stderr JSON. A failed execution can also emit status and saved references on stdout; retain both. Stop dependent operations after a prerequisite fails. Do not parse empty stdout or infer generation from exit code `0` alone.

Inspect an uncertain task with `task inspect`. Where saved evidence allows local completion, `task reconcile` saves the result without another model call. An `output_contract_violation` can occur after local effects were saved, so inspect the original task first. Do not resend uncertain work under a different ID. See [recovery](usage.md#english) and [diagnostics](diagnostics.md#english).

### Discover details when needed

```sh
writing-assistant capabilities --schema request
writing-assistant capabilities --detail
```

`--operation`, `--schema` and `--detail` are mutually exclusive. Discovery scans no manuscript and calls no model. `--max-bytes` bounds complete UTF-8 JSON including its newline: default 131072, maximum 1048576. Oversized output returns `capabilities_output_limit`; unknown names return `unknown_capability_operation` or `unknown_capability_schema`. Prefer the specific operation or schema needed next.

Keep exact returned references and read full content with `records read/show`. A compact response's `omitted_fields` describes response omissions, not lost stored content. Each guide and the capability catalog document the relevant limits.
