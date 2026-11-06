# 可恢复的写作任务

[中文](#中文) · [English](#english)

## 中文

Agent 准备一个明确任务、查看被冻结的准确输入，在 user 授权内执行，再 inspect 或 reconcile 已保存的结果。生成文本仍未采用。Task ID 是应用请求 ID，与聊天、进程 ID 无关。[章节 workflow](workflows.md) 按保存的顺序准备这些相同的 task。

### 准备与准确绑定

```sh
writing-assistant capabilities --project ../demo-project
writing-assistant task --project ../demo-project prepare request.json --model MODEL
```

请求格式见 [接口说明](interface.md)。省略 `--model` 时记录忽略 user CLI 配置后的 Codex 默认值，不继承调用方 Agent 的模型，也不固定 provider 的未来默认值。`--reasoning-effort` 支持明确选择 `low`、`medium`、`high`、`xhigh`、`max`、`ultra`，原值冻结进计划并传给 `model_reasoning_effort`；实际模型或账户仍可能拒绝。Native `ultra` 可能涉及 delegation，可见的不受支持工具活动仍按应用边界处理。

`task prepare` 不调用 provider，也不执行资格 probe。它在 Creative Records 保存不可变计划与准确 prompt，返回 `task_id`、`attempt_id`、`plan_sha256`、准确 `plan` reference、状态和可用 `actions`。

每项材料通过 `--record-bindings FILE` 明确绑定，复制应用返回的完整 `ref`，不要自行推导存储 ID：

```json
[{"uri":"selected:draft-one","ref":{"contract":"creative-records/1","project_id":"demo","record_id":"COPY_RETURNED_RECORD_ID","version_id":"COPY_RETURNED_VERSION_ID","sha256":"COPY_RETURNED_SHA256"}}]
```

占位值不可直接使用。URI 只标识选择，不授权搜索文件。`--ranges FILE` 可选择 `[{"uri":"selected:draft-one","start":0,"end":128}]`：范围为原文的半开 **byte** 区间，必须保持 UTF-8 边界，BOM 占用自身字节。材料 digest 绑定所选片段，binding 保留完整原文 reference。`records bookmark/context` 使用 Unicode code points，不能混用偏移。

外部原件还要求在 prepare、execute、reconcile 提供 `--artifacts-root DIR --bindings FILE`，它与 `--record-bindings` 各自独立。缺少 resolver 返回 `reference_unavailable`；查看已冻结上下文不要求重读外部原件。技法选择同样冻结准确 pack/version/digest/IDs。

可用上限见 `capabilities` 的 `task_options.limits`；`--limits FILE` 提供全部键，只能降低上限。每个 task 最多一次本地 attempt，`max_attempts` 不超过一。Local timeout 大于零、至多 600 秒。进程与字节上限不等于远端 token、费用或计算停止保证。

### 查看、诊断与状态

```sh
writing-assistant task --project ../demo-project inspect task-one
writing-assistant task --project ../demo-project inspect task-one --include-context --max-bytes 32768
writing-assistant task --project ../demo-project diagnostics task-one --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

默认 inspect 返回状态、准确绑定、关系、证据引用和 actions，不返回稿件正文。显式上下文读取遵守完整 UTF-8 JSON 加末尾换行的上限；必要 metadata 放不下时返回 `output_limit`。Prepare/execute/reconcile 的 mutation receipt 上限为 32768 bytes；较大结果使用 `view: compact`、`omitted_fields`，同时保留 task 身份、计划引用、状态、effects 与证据。

`details.result`、`details.receipt`、`plan` 是可用 `records read/show` 完整读取的准确引用。`details.inspect_required_bytes` 描述完整 view 大小，但不绕过 inspect 自身上限。紧凑化不改变是否 dispatch、是否保存内容或是否允许另一次 attempt。

未保存 model result 的 reserved/uncertain task 可返回 `local_runtime`。`task_lock: held` 只说明有本地操作持锁；`available` 只说明当前未观察到持锁。`backend_status` 始终为 `unknown`。Reservation 年龄不是模型耗时、剩余时间、进度或重试许可。锁不可读或被替换时不能报告 available。

`task diagnostics` 返回 `writing-assistant-task-diagnostics/1`，只报告已绑定的 plan/configuration/policy/record metadata，不返回稿件、URI、私有路径或原始环境。它不检查所选原件/prompt bytes 或 parent CAS，不调用 provider、probe、进程或本地写入。将返回 `context` 原样复制给 [diagnostic case](diagnostics.md)，不要再次 hash。Routing/CA metadata 的缺失或歧义不能证明历史诊断可复用。

### 执行与恢复

```sh
writing-assistant task --project ../demo-project execute task-one --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect task-one
writing-assistant task --project ../demo-project reconcile task-one
```

Execute 重核配置、版本、范围、模型、effort、limits、应用策略和数据目录身份。相同 ID 的不同输入返回 `task_conflict`；不匹配或过时计划返回 `stale_plan`。保留原 task，不通过换 ID 替代不确定工作。

已完成的重复请求返回已存结果；reserved 或 uncertain attempt 不会再次 dispatch。`model_status` 与 `materialization_status` 分别记录模型和本地保存结果：已有生成 bytes 不意味着 draft 保存完成。Reconcile 只使用保存的证据，不调用模型，也不创建新 attempt；缺失或损坏证据不能推定为 completed。

Execute/reconcile 失败为 exit `2`，保留 stdout 的状态引用和 stderr 的安全错误。Inspect 本身可成功返回 uncertain 状态；它的 `model_calls: 0` 只表示这次查看，不表示 task 历史未调用模型。本地停止不证明远端停止。

资格检查不调用模型。运行中 `turn.failed` 触发本地停止并保留首次暴露 bytes；`item.completed` 的 error 可能先于成功文字结果，只记录而不单独判定整个 task 失败。未知流继续受 timeout、取消与输出上限约束。

Legacy 顶层 `prepare` 返回临时 `prepared-unexecuted` packet；顶层 `execute` 不执行先前 prepare 的 frozen task。需要准确已查看绑定时使用 `task prepare/inspect/execute`。结果字段见 [core schema](../schemas/core-results-v1.schema.json)，操作耗时边界见 [CLI 使用](usage.md)。

## English

An Agent prepares one explicit writing task, inspects its exact frozen inputs,
executes it under the user's authorization, and inspects or reconciles its saved
outcome. Generated text remains unadopted. Task IDs are application request IDs;
they are independent of chats and local process IDs.

For a bounded chapter sequence, [durable workflows](workflows.md) prepare these
same tasks in an application-owned order and preserve their exact dependencies.
The Agent supplies the goal once and explicitly executes each returned task.
Individual tasks can also select optional [technique packs](techniques.md) by
exact version, digest and technique IDs; the plan freezes the selected guidance.

### Discover and prepare

```sh
writing-assistant capabilities --project ../demo-project
writing-assistant task --project ../demo-project prepare request.json --model MODEL
```

The catalog includes actual command arguments, application schemas, effects,
configuration support, limits and recovery. The request uses
`writing-assistant-request/1`; see [request format](interface.md). Replace `MODEL`
with the user's selected Codex model. Omission records the Codex CLI default,
with user CLI configuration ignored; it does not inherit the calling Agent's model
or guarantee a pinned provider default.

Use `--reasoning-effort` to request `low`, `medium`, `high`, `xhigh`, `max` or
`ultra` explicitly. The plan freezes the exact value independently of `--model`
and includes it in its identity and diagnostic applicability. Execution passes
the unchanged value as Codex `model_reasoning_effort`; it does not copy the
calling Agent's setting or substitute another effort. Omission preserves the CLI
default with user CLI configuration ignored. Requested effort is not backend
attestation; a model or account may still reject it. In native Codex, `ultra` can
involve automatic delegation, which remains subject to this application's
unsupported-tool-activity boundary. Existing plans without effort fields remain
readable. A prepared plan bound to an older execution policy can still be stale.

`task prepare` makes no provider call or capability probe. It saves an immutable
plan and exact prompt in Creative Records, returning `task_id`, `attempt_id`,
`plan_sha256`, the exact `plan` record reference, statuses and available `actions`.
Every selected material must have an explicit `--record-bindings FILE` entry:

```json
[{"uri":"selected:draft-one","ref":{"contract":"creative-records/1","project_id":"demo","record_id":"COPY_RETURNED_RECORD_ID","version_id":"COPY_RETURNED_VERSION_ID","sha256":"COPY_RETURNED_SHA256"}}]
```

Copy the complete `ref` returned by `records save` or another application
operation; the example's placeholder values are not usable references. A URI
labels the explicit selection and does not authorize a filesystem search.

For a selected part of a record, pass `--ranges FILE` with
`[{"uri":"selected:draft-one","start":0,"end":128}]`. These are half-open **byte**
offsets in the original record; the selected bytes must decode as UTF-8. The
request material's `sha256` binds the selected bytes, while the binding retains
the full original record reference and its original digest. A BOM occupies its
UTF-8 bytes. Do not reuse continuation offsets here: `records bookmark/context`
uses `unicode_code_points_utf8_including_bom` instead.

Reference-backed originals additionally require `--artifacts-root DIR --bindings
FILE` at preparation, execution and reconciliation. These are explicit producer
descriptor/path/audience bindings, separate from `--record-bindings`; no callable
or external path is discovered or persisted automatically. Missing required
original resolution returns `reference_unavailable`. Inspection of saved frozen
context does not require re-reading external originals.

Task limits are discoverable under catalog `task_options.limits`. Supply all
keys in `--limits FILE` to lower them. One local attempt is supported;
`max_attempts` cannot exceed one. Request/material/prompt/output bounds are
independent. Local timeout must be greater than zero and at most 600 seconds.
Local process and byte limits do not establish backend termination or hard remote
cost/token limits.

### Inspect from another Agent

Only the initialized project location and task ID are needed:

```sh
writing-assistant task --project ../demo-project inspect task-one
writing-assistant task --project ../demo-project inspect task-one --include-context --max-bytes 32768
```

The default response contains status, exact selected bindings, relations, evidence
references and available actions. It does not return manuscript bodies. Explicit
context reads use frozen selected text, enforce the complete UTF-8 JSON result
bound including the final newline, and declare omitted text. Oversized mandatory
metadata returns `output_limit`; it is never silently truncated.

`task prepare`, `task execute` and `task reconcile` return mutation receipts
bounded to 32768 UTF-8 JSON bytes including the final newline. Ordinary receipts
keep the full view. A larger view returns the same task contract with
`view: compact` and explicit `omitted_fields`, while retaining task identity,
exact plan reference/digest, status, effect status, available actions and evidence
references. `details.inspect_required_bytes` describes the full saved view;
inspection with an explicit sufficient `--max-bytes` still enforces its normal
bound and can refuse it. Compaction does not change whether execution occurred,
content was saved, or another attempt is permitted.

When present, `details.result` and `details.receipt` are exact saved record
references; use `records read/show` to retrieve those complete artifacts. This
also supports a saved artifact larger than inspection's maximum. A qualification
failure retains its small `qualification` receipt and first observation/reference
set directly: later task inspection need not reconstruct that invocation's
qualification result. A compact diagnostic blocker retains `code` and
`diagnostics_summary`; `details.diagnostics_operation` points to
`task diagnostics --include-preflight` with the returned plan digest. That is a
fresh applicability query, not a reconstruction of the original omitted matches.

The [core result schema](../schemas/core-results-v1.schema.json) describes full
and compact task results. `capabilities --schema core-results` retrieves it, and
operation discovery identifies the corresponding `output_schema`. The CLI checks
these core fields before emitting task responses. `output_contract_violation`
returns a safe operation/task identity and validated exact references when
available. Its `effect_status: unknown` on a mutation requires inspection of
existing effects; it never grants retry authority. No manuscript, private path or
untrusted nested result is included in this error.

For a reserved task with no saved model result (`status: uncertain`), inspection
also returns a point-in-time `local_runtime` observation. `task_lock: held` and
`state: local_operation_active` mean a local task operation holds the authenticated
exclusive task lock. `task_lock: available` and
`state: no_local_operation_observed` mean no such operation was observed holding
that lock. This uses a nonblocking shared-lock probe, without a PID check, lock
deletion, provider call, process launch, or status write. A missing lock reports
`state: unknown`; an unreadable, replaced or invalid lock fails inspection rather
than reporting availability. Prepared tasks and tasks with a saved model result
do not receive this field. Existing task statuses, actions and attempt limits are
unchanged.

`reservation_received_at` comes from the saved dispatch intent.
`seconds_since_reservation` measures wall-clock time since that reservation at
`observed_at`; it is `null` if the clock moved before the recorded time. It is
neither model execution duration nor an estimate of remaining time. Lock ownership
does not establish native-process health, network progress, model activity,
backend completion or backend stop. `backend_status` remains `unknown`, including
when no local operation is observed. Preserve uncertain work and its no-resend
fence; this observation does not authorize another attempt.

To read the complete plan explicitly, save the returned `plan` reference as JSON
and use `records read plan-ref.json --output plan.json` or `records show --ref
plan-ref.json`. These are application operations over that exact reference; no
private storage-path or ID derivation is needed. Exact record reads can return
the complete selected body up to the RecordStore body limit. They do not inherit
`task inspect`'s smaller output bound. See [records](records.md) for bounded
continuation context and paginated record search.

### Obtain task-bound diagnostic facts

```sh
writing-assistant task --project ../demo-project diagnostics task-one --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project diagnostics task-one --expected-plan-sha256 PLAN_SHA256 --include-preflight --max-bytes 32768
```

This returns `writing-assistant-task-diagnostics/1` with `context`, optional
`preflight`, and an explicit `validation` summary. The context is the same fact
set used by task execution's diagnostic hook. It contains no request prose,
material text, selected URI, private path or raw environment value. Runtime
environment facts use opaque hashes and proof-status values. Copy returned context values as supplied;
do not hash them again.

The operation authenticates the inspected plan digest, live data-root authority,
current configuration/policy and selected exact record metadata. Internally it
reads the bounded saved plan, then returns metadata only. It does not read selected
content, external originals or prompt bytes, and does not check parent CAS.
Those checks still run at execution. `validation` names this distinction;
successful metadata inspection does not establish that external original bytes
are available or authorize dispatch. The operation makes no provider call,
capability probe, process launch or local write. Optional preflight reads retained
diagnostic evidence internally and returns bounded metadata only.

To record an observed failure, copy the returned `context` into a diagnostic
capture JSON file and set its `category` to the structured failure category.
Supply `case_id` and explicit selected evidence with `diagnostics capture`; see
[diagnostic cases](diagnostics.md). To revise applicability of an existing case,
copy the context into `changes.json`, retain that case's category, and use its
exact latest reference with `diagnostics revise --evidence FILE`. Cause confidence,
blocker disposition and expiry are explicit evidence-backed choices. This query
does not infer them or grant retry authority. Repeat with `--include-preflight`
to inspect applicable cases before executing the unchanged plan.

Credential-free proxy endpoint and CA file metadata changes invalidate matching
context. Credential-bearing or ambiguous routing, or unavailable CA metadata,
sets `child_routing_proof=unknown`; such conditions cannot automatically reuse a
historical blocker. These facts do not inspect auth stores, verify credentials or
CA contents, establish provider availability, or attest a later launch environment.

### Execute and recover

```sh
writing-assistant task --project ../demo-project execute task-one --expected-plan-sha256 PLAN_SHA256
writing-assistant task --project ../demo-project inspect task-one
writing-assistant task --project ../demo-project reconcile task-one
```

Copy `PLAN_SHA256` from inspection. Execution rechecks the frozen configuration,
selected versions/ranges, model/options/limits, application execution policy and
data-root identity before dispatch. Changed input under the same task ID is
`task_conflict`; a mismatched or stale execution plan is `stale_plan`. Preserve
and inspect the original task. Do not replace unknown work by changing its ID.

Completed duplicates return the saved outcome. A reserved or uncertain attempt
is never dispatched again. The status distinguishes `model_status` from
`materialization_status`: saved model output can exist even when local draft
materialization conflicts or is incomplete. Reconciliation makes no provider
call and uses verified saved evidence only. Repeating it cannot create another
model attempt. Missing or corrupt evidence is never inferred to be completion.
A parent-version conflict preserves saved generated bytes for inspection.

Inspect both the exit code and JSON. Failed execute/reconcile operations use exit
code `2` and a payload-free JSON error on stderr; preserve any status/reference
result emitted on stdout. Inspection is a status query and can succeed while
reporting uncertainty. Its `model_calls: 0` describes that inspection invocation,
not the entire task's history. A local process stop does not attest backend stop.

Qualification checks version, required flags and the application's explicit
no-tool launch configuration without calling a model. Unknown or incompatible
configuration refuses dispatch. During execution, `turn.failed` stops the local
process promptly and retains its first exposed bytes without waiting for the task
deadline. An `item.completed` error, including the Code Mode host-disabled
diagnostic, is retained while the application waits for completion or the ordinary
timeout, cancellation and output bounds. It does not establish the whole request's
result. Interrupted and failed tasks retain the same no-resend safeguards.

### Legacy commands

Top-level `prepare --project PROJECT REQUEST_FILE` produces an ephemeral
`writing-assistant-packet/1` with `prepared-unexecuted`; it does not register a
frozen task. Top-level `execute --project PROJECT REQUEST_FILE` performs immediate
preparation and execution with its legacy reservation safeguards. It does not
execute an earlier top-level `prepare` result. Use `task prepare/inspect/execute`
when the execution must bind a durable inspected plan.
Reference-backed legacy execution also requires the explicit
`--artifacts-root DIR --bindings FILE` pair alongside `--record-bindings FILE`;
the selected resolver is passed to both material and stored-relation reads.
