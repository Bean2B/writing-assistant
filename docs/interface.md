# 请求格式 / Request format

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

单次写作任务使用 JSON 请求文件。[示例请求](../examples/synthetic/request.json)可直接用于 `demo` 项目；完整字段见[请求 schema](../schemas/request-v1.schema.json)。多章任务使用单独的 [workflow 格式](workflows.md#中文)。

### 最小请求

```json
{
  "schema_version": "writing-assistant-request/1",
  "request_id": "bell-001",
  "project_id": "demo",
  "kind": "writing",
  "request": "写一段关于浮空车站里一口铜钟的短篇开头。",
  "materials": []
}
```

```sh
writing-assistant check-request request.json
writing-assistant task --project ../demo-project prepare request.json --model MODEL
```

`project_id` 必须匹配初始化的项目。新任务使用新 `request_id`；重复 ID 不会重发旧任务。未知字段与不支持的 schema 版本会报错。检查与准备不调用模型，执行步骤见[可恢复任务](tasks.md#中文)。

### 选择任务类型

| `phase` | 用途与材料 |
| --- | --- |
| `concept` | 从初始想法探索人物、设定与情节，无须旧稿；保存为未采用的 `idea`。 |
| `draft` | 撰写正文，省略 `phase` 时使用此值。 |
| `plan-scene` | 使用 `lotus` 准备场景。 |
| `reader-review` | 审读一个 `current-draft`，可带选定的 `prior-prose`。 |
| `continuity-review` | 对照旧稿、场景材料和 `request-material` 检查当前稿。 |
| `revise` | 根据选定 `feedback` 修改一个准确的 `current-draft`。 |

Direct Mode（`none`）支持除 `plan-scene` 之外的全部阶段，不加入 Lotus 方法文本；审读也不加载该方法文本。应用的每次执行使用新 Codex context，Codex 全局指令仍可能参与。切换模式不会删除已有聊天消息。

单次 draft 不自动发起审读，审读也不自动发起返修。Workflow 按已选阶段维护顺序，仍需明确执行每个 task。构思、计划和生成细节保持候选状态；生成文本不自动采用或成为 World Sandbox 事实。

### 引用旧稿与反馈

每份 `materials` 项包含 `uri`、小写 SHA-256 `sha256` 和 `purpose`。旧稿使用 `purpose: current-writing`；可选 `role` 和 `source_kind` 描述用途与来源。通过 `--record-bindings FILE` 将 URI 绑定到应用返回的完整准确 record reference，格式见 [task 材料绑定](tasks.md#中文)。URI 只是选择标识，不会触发文件搜索或替换为最新版本。

返修需要一个 `current-draft` 及选定反馈。每份反馈必须有 `feedback_target: {"uri": "…", "sha256": "…"}`，与该稿的 transport reference 完全一致。应用在读取材料前拒绝缺失或错误 target，并检查保存记录的完整版本关系；相同 bytes 的不同版本不能互换。导入反馈的 target 由调用方声明，不证明其来自应用审读。没有 target 的历史反馈仍可读取。

外部原件还需在相关操作提供 `--artifacts-root DIR --bindings FILE`；它与 record bindings 不同。原件缺失、变化或不可读会报错。Task 的 `--ranges` 使用半开 UTF-8 **byte** offsets；`records bookmark/context` 使用包含 BOM 的 Unicode code-point offsets。

请求最多 32 份材料、1 MiB UTF-8 request text，解析后的材料总计最多 4 MiB；task 的冻结计划可有更低限额。可选 `techniques` 按准确 `pack_id`、`pack_version`、`pack_sha256`、`technique_ids` 选择指导；省略或空数组均不加载，见[技法包](techniques.md#中文)。JSON 格式有效之后，仍会检查项目、材料、阶段和执行条件。

### 读取结果

```sh
writing-assistant capabilities --schema core-results
writing-assistant capabilities --operation 'task inspect'
```

[核心结果 schema](../schemas/core-results-v1.schema.json)覆盖 discovery、task、workflow、records、诊断、配置、doctor、legacy writing 和 world JSON 输出。具体操作的 `output_schema` 与 `output_validation` 说明输出形式。`--help`、`--version` 为文本；`records show --raw`、`world projection --raw`、`world resolve` 为准确 bytes，无额外 wrapper 或换行。

紧凑结果通过 `view: compact` 和 `omitted_fields` 声明省略项，保留状态与准确引用。Records 分页即使当前页为空，也应沿 `next_cursor` 继续；`total: null` 表示未报告完整总数。

输出不符合契约时，CLI 在 stderr 返回 `output_contract_violation` 和 exit `2`。只读操作的 `effect_status` 为 `none`，写入操作可能为 `unknown`：本地效果可能已经保存，应先 inspect。输出格式校验不代替材料完整性、执行状态或内容审读。命令处理见 [Agent guide](agent-usage.md#中文)，耗时与 usage/cost 字段见[使用说明](usage.md#中文)与 [Codex 支持](codex-support.md#中文)。

## English

A single writing task uses a JSON request file. The [example request](../examples/synthetic/request.json) works with a `demo` project; the [request schema](../schemas/request-v1.schema.json) defines every field. Multi-chapter work uses the separate [workflow format](workflows.md#english).

### A minimal request

```json
{
  "schema_version": "writing-assistant-request/1",
  "request_id": "bell-001",
  "project_id": "demo",
  "kind": "writing",
  "request": "Write a short opening about a brass bell in a floating station.",
  "materials": []
}
```

```sh
writing-assistant check-request request.json
writing-assistant task --project ../demo-project prepare request.json --model MODEL
```

`project_id` must match the initialized project. Use a new `request_id` for new work; repeating an ID does not resend earlier work. Unknown fields and unsupported schema versions are errors. Checking and preparation make no model call. See [durable tasks](tasks.md#english) for execution.

### Choose a phase

| `phase` | Purpose and material |
| --- | --- |
| `concept` | Explore characters, setting and plot from an initial idea; no draft required. Saves an unadopted `idea`. |
| `draft` | Write prose; the default when `phase` is omitted. |
| `plan-scene` | Prepare a scene using `lotus`. |
| `reader-review` | Review one `current-draft`, optionally with selected `prior-prose`. |
| `continuity-review` | Check the current draft against selected earlier prose, scene material and `request-material`. |
| `revise` | Revise one exact `current-draft` using selected `feedback`. |

Direct Mode (`none`) supports every phase except `plan-scene` without adding Lotus method text. Reviews also omit that method text. Each application execution starts a fresh Codex context, although Codex global instructions can still apply. Changing mode does not remove messages from an existing chat.

A standalone draft does not start a review, and a review does not start revision. A workflow maintains the selected phase order and still requires explicit execution of each task. Concepts, plans and generated details remain candidates; generated text is not automatically adopted or made into World Sandbox facts.

### Include earlier writing and feedback

Each `materials` entry has a `uri`, lowercase SHA-256 `sha256` and `purpose`. Use `purpose: current-writing` for earlier writing. Optional `role` and `source_kind` describe its use and source. Supply `--record-bindings FILE` to bind each URI to a complete exact record reference returned by the application; see [task material bindings](tasks.md#english). A URI labels a selection; it does not search files or select the latest version.

Revision requires one `current-draft` and selected feedback. Every feedback entry must declare `feedback_target: {"uri": "…", "sha256": "…"}` matching that draft's exact transport reference. Missing or wrong targets are rejected before content is read; saved feedback also has its complete version relationship checked. Versions containing identical bytes are not interchangeable. Imported feedback declares applicability through its caller-supplied target, not authenticated application review provenance. Historical targetless feedback remains readable.

External originals also require `--artifacts-root DIR --bindings FILE` on the relevant operations, separately from record bindings. Missing, changed or unreadable originals are errors. Task `--ranges` use half-open UTF-8 **byte** offsets; `records bookmark/context` uses Unicode code-point offsets including a BOM.

Requests allow at most 32 materials, 1 MiB of UTF-8 request text and 4 MiB of resolved material in total; frozen task limits can be lower. Optional `techniques` selects exact `pack_id`, `pack_version`, `pack_sha256` and `technique_ids`. An absent or empty selection loads none; see [techniques](techniques.md#english). After JSON validation, the application still checks project, material, phase and execution conditions.

### Core result contracts

```sh
writing-assistant capabilities --schema core-results
writing-assistant capabilities --operation 'task inspect'
```

The [core result schema](../schemas/core-results-v1.schema.json) covers discovery, tasks, workflows, records, diagnostics, configuration, doctor, legacy writing and world JSON outputs. Each operation declares its `output_schema` and `output_validation`. `--help` and `--version` return text; `records show --raw`, `world projection --raw` and `world resolve` return exact bytes without an added wrapper or newline.

Compact responses declare `view: compact` and `omitted_fields`, retaining status and exact references. For record pagination, follow `next_cursor` even after an empty page; `total: null` means no complete total was reported.

An invalid output contract returns `output_contract_violation` on stderr with exit `2`. Read-only operations report `effect_status: none`; mutations can report `unknown` because local effects may already be saved. Inspect them first. Output shape checks do not replace material integrity, execution-state checks or content review. See the [Agent guide](agent-usage.md#english) for result handling, and [usage](usage.md#english) and [Codex support](codex-support.md#english) for timing, usage and cost fields.
