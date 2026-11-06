# 可恢复的写作任务 / Durable writing tasks

[中文](#中文) · [English](#english)

## 中文

Task 保存一次写作操作的输入、执行状态和结果，便于中断后继续查看。应用冻结计划并维护版本关系；Agent 查看计划后明确执行。Task ID 来自请求的 `request_id`，与聊天或进程 ID 无关。多个章节可交给 [workflow](workflows.md#中文)维护顺序。

### 准备并查看

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project inspect TASK_ID --include-context --max-bytes 32768
```

`request.json` 使用[请求格式](interface.md#中文)。将 `MODEL` 换成选定模型，复制 prepare 返回的 `task_id`、`plan_sha256` 和完整 `plan` reference。准备会保存不可变计划和准确 prompt，不调用模型或进行 Codex probe。默认 inspect 只返回状态、材料绑定、关系、引用与 `actions`；`--include-context` 才读取冻结的正文。

准备时可设置 `--reasoning-effort` 和 `--timeout`，后续 execute 沿用被冻结的值。省略模型或 effort 时使用忽略 user CLI 配置后的 Codex 默认值，不继承当前 Agent 设置。可用 effort 和支持限制见 [Codex 支持](codex-support.md#中文)。

### 绑定准确材料

对请求中的每个 URI，通过 `--record-bindings FILE` 提供应用返回的准确 record reference：

```json
[
  {
    "uri": "selected:draft-one",
    "ref": {
      "contract": "creative-records/1",
      "project_id": "demo",
      "record_id": "COPY_RETURNED_RECORD_ID",
      "version_id": "COPY_RETURNED_VERSION_ID",
      "sha256": "COPY_RETURNED_SHA256"
    }
  }
]
```

用实际返回值替换全部占位符。URI 只标记选定材料，不搜索目录，也不自动切换到新版本。返修的准确 draft/feedback target 要求见[请求格式](interface.md#中文)。

`--ranges FILE` 可选片段，例如 `[{"uri":"selected:draft-one","start":0,"end":128}]`。这是原文半开的 **byte** 区间，必须对齐 UTF-8 边界；BOM 占用自身字节。请求材料的 digest 绑定选定片段，record binding 保留完整原文 reference。`records bookmark/context` 使用 Unicode code points，不能混用偏移。

引用外部原件时，在 prepare、execute、reconcile 提供 `--artifacts-root DIR --bindings FILE`，与 `--record-bindings` 独立。缺少所需 resolver 返回 `reference_unavailable`；inspect 冻结上下文不必重读外部原件。可选技法也按准确版本、digest 与 ID 冻结。

`capabilities --operation 'task prepare'` 提供 `task_options.limits`。`--limits FILE` 必须包含全部键，且只能降低上限；`max_attempts` 固定为 `1`。Local timeout 为大于 0、至多 600 秒。限额约束本地输入、输出和进程，不保证远端 token 或费用上限。

### 执行与恢复

```sh
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project reconcile TASK_ID
```

从 inspect 复制 `PLAN_SHA256`。Execute 重核配置、准确材料与范围、模型/effort、限额、执行策略和数据目录身份，再调用 Codex。同一 ID 的不同输入返回 `task_conflict`；摘要不匹配或计划过时返回 `stale_plan`。保留原 task 并查看原因。

每个 task 最多一次本地 attempt。已完成的重复调用返回保存结果；reserved 或 uncertain attempt 不再次 dispatch。`reconcile` 只使用已保存证据完成本地保存，不调用模型或创建 attempt。父版本冲突会保留生成 bytes，缺失或损坏的证据不会被当作完成。

| 字段 | 读取方式 |
| --- | --- |
| `status` | task 的整体状态。 |
| `model_status` | 模型结果是否完成。 |
| `materialization_status` | 应用是否完成本地结果保存。 |
| `actions` | 当前状态支持的后续操作。 |
| `adopted` | 生成结果保持 `false`，采用由你决定。 |

同时检查 exit code、stdout 与 stderr。失败的 execute/reconcile 使用 exit `2`，stdout 可能仍有状态与准确引用。Inspect 可成功返回 uncertain 状态；该次 `model_calls: 0` 不代表历史未调用模型。不要通过换 ID、模型或 deadline 重发结果未知的任务；本地停止也不证明远端停止。

### 读取完整结果与本地状态

Prepare/execute/reconcile 的 receipt 上限为 32768 UTF-8 JSON bytes（含末尾换行）。较大结果使用 `view: compact` 与 `omitted_fields`，保留身份、状态、效果、引用和 actions。`details.inspect_required_bytes` 给出完整 view 大小；inspect 仍受自身 `--max-bytes` 限额约束，必要 metadata 超限时返回 `output_limit`。

`plan`、`details.result`、`details.receipt` 是准确 record reference。将其保存为 JSON，用 `records read REF_FILE --output NEW_FILE` 或 `records show --ref REF_FILE` 读取完整记录，详见[创作记录](records.md#中文)。结果紧凑化不改变保存内容或 attempt 限制。Mutation 的 `output_contract_violation` 可能已有本地效果，先 inspect。

未保存模型结果的 reserved/uncertain task 可返回 `local_runtime`：`task_lock: held` 表示有本地操作持锁，`available` 表示本次未观察到持锁；`backend_status` 始终为 `unknown`。缺失 lock 的状态为 unknown，不可读或被替换则报错。Reservation 年龄不表示模型耗时、进度或重试许可。Task 耗时记录见[使用说明](usage.md#中文)。

### 获取 task 诊断上下文

```sh
writing-assistant task --project ../demo-project diagnostics TASK_ID --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

结果 `writing-assistant-task-diagnostics/1` 提供 `context`、可选 `preflight` 和 `validation`。它核对 plan/configuration/policy/record metadata，不读取所选正文、外部原件或 prompt bytes，也不检查 parent CAS。Execute 仍需这些检查。此操作不调用 provider、不启动 probe 或进程、不写入本地数据。

把 `context` 原样复制给[诊断 case](diagnostics.md#中文)，只把 `category` 改为实际观察到的错误分类。它不含稿件、URI、私有路径或原始环境值；不要再次 hash。Routing/CA metadata 缺失或不明确时，历史诊断不能自动复用。

### Legacy 命令

顶层 `prepare` 返回临时 `prepared-unexecuted` packet；顶层 `execute` 会重新准备并立即执行，不执行之前的 packet。需要查看并执行同一份冻结输入时，使用本页的 `task prepare/inspect/execute`。

## English

A task saves one writing operation's inputs, execution state and result so it can be inspected after an interruption. The application freezes the plan and maintains version relationships; the Agent inspects and explicitly executes it. A task ID comes from the request's `request_id`, independently of chat or process IDs. [Workflows](workflows.md#english) maintain the order of multi-chapter work.

### Discover and prepare

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project inspect TASK_ID --include-context --max-bytes 32768
```

Use the [request format](interface.md#english) for `request.json`. Replace `MODEL` with the selected model. Keep the returned `task_id`, `plan_sha256` and complete `plan` reference. Preparation saves an immutable plan and exact prompt without a model call or Codex probe. Default inspection returns status, material bindings, relationships, references and `actions`; only `--include-context` reads frozen text.

Set `--reasoning-effort` and `--timeout` at preparation if needed; execute uses the frozen values. Omitted model/effort uses the Codex CLI default with user CLI configuration ignored, without inheriting the calling Agent's settings. See [Codex support](codex-support.md#english) for accepted efforts and limits.

### Bind exact material

For each request URI, supply an application-returned exact record reference through `--record-bindings FILE`:

```json
[
  {
    "uri": "selected:draft-one",
    "ref": {
      "contract": "creative-records/1",
      "project_id": "demo",
      "record_id": "COPY_RETURNED_RECORD_ID",
      "version_id": "COPY_RETURNED_VERSION_ID",
      "sha256": "COPY_RETURNED_SHA256"
    }
  }
]
```

Replace every placeholder with its actual returned value. The URI labels a selection; it does not search directories or switch to a newer version. See [request format](interface.md#english) for exact draft/feedback targets used in revision.

For a slice, `--ranges FILE` accepts entries such as `[{"uri":"selected:draft-one","start":0,"end":128}]`. These are half-open **byte** offsets into the original, aligned to UTF-8 boundaries; a BOM occupies its own bytes. The material digest binds the selected slice, while the record binding retains the complete original reference. Do not reuse `records bookmark/context` offsets, which count Unicode code points.

External originals additionally require `--artifacts-root DIR --bindings FILE` at prepare, execute and reconcile, separately from `--record-bindings`. A missing required resolver returns `reference_unavailable`. Inspecting frozen context does not require reading external originals again. Optional techniques also freeze exact versions, digests and IDs.

`capabilities --operation 'task prepare'` exposes `task_options.limits`. A `--limits FILE` must provide every key and can only lower defaults; `max_attempts` must remain `1`. Local timeout must be greater than 0 and at most 600 seconds. Limits bound local input, output and process activity, without guaranteeing a remote token or cost ceiling.

### Execute and recover

```sh
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project reconcile TASK_ID
```

Copy `PLAN_SHA256` from inspection. Execute rechecks configuration, exact material and ranges, model/effort, limits, execution policy and data-root identity before calling Codex. Changed inputs under one ID return `task_conflict`; a mismatched digest or stale plan returns `stale_plan`. Preserve and inspect the original task.

Each task supports at most one local attempt. Completed duplicate calls return the saved result; reserved or uncertain attempts are never dispatched again. `reconcile` completes local storage from saved evidence without a model call or another attempt. A parent-version conflict preserves generated bytes. Missing or corrupt evidence is not inferred to be completion.

| Field | Meaning |
| --- | --- |
| `status` | Overall task state. |
| `model_status` | Whether the model result completed. |
| `materialization_status` | Whether the application completed local result storage. |
| `actions` | Follow-up operations available in the current state. |
| `adopted` | Generated results stay `false`; you decide adoption. |

Read exit code, stdout and stderr together. Failed execute/reconcile operations use exit `2`; stdout may still contain status and exact references. Inspection can succeed while reporting uncertainty. Its `model_calls: 0` describes that inspection, not the task's history. Do not resend uncertain work by changing its ID, model or deadline. Local stopping does not prove remote stopping.

### Inspect from another Agent

Prepare/execute/reconcile receipts are bounded to 32768 UTF-8 JSON bytes including the newline. Larger views use `view: compact` and `omitted_fields`, retaining identity, status, effects, references and actions. `details.inspect_required_bytes` describes the full view size; inspection still enforces its own `--max-bytes` and returns `output_limit` if required metadata cannot fit.

`plan`, `details.result` and `details.receipt` are exact record references. Save a reference as JSON and read the full record using `records read REF_FILE --output NEW_FILE` or `records show --ref REF_FILE`; see [creative records](records.md#english). Compaction changes neither stored content nor attempt limits. A mutating `output_contract_violation` can follow saved local effects; inspect first.

Reserved/uncertain tasks without a saved model result can include `local_runtime`. `task_lock: held` means a local operation holds the lock; `available` means none was observed holding it at inspection. `backend_status` is always `unknown`. A missing lock reports unknown; unreadable or replaced locks fail inspection. Reservation age measures neither model duration nor progress and grants no retry. See [usage](usage.md#english) for task duration records.

### Obtain task-bound diagnostic facts

```sh
writing-assistant task --project ../demo-project diagnostics TASK_ID --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

The `writing-assistant-task-diagnostics/1` response provides `context`, optional `preflight` and `validation`. It checks plan/configuration/policy/record metadata, without reading selected content, external originals or prompt bytes, or checking parent CAS. Execute still performs those checks. This operation makes no provider call, probe, process launch or local write.

Copy `context` unchanged into a [diagnostic case](diagnostics.md#english), changing only `category` to the observed failure category. It contains no manuscript, URI, private path or raw environment value; do not hash its values again. Missing or ambiguous routing/CA metadata prevents automatic reuse of historical diagnostics.

### Legacy commands

Top-level `prepare` returns an ephemeral `prepared-unexecuted` packet. Top-level `execute` prepares again and runs immediately; it does not execute an earlier packet. Use `task prepare/inspect/execute` to inspect and execute the same frozen input.
