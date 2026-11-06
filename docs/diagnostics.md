# 本地诊断 / Local diagnostics

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

诊断 case 用于保存一次问题的选定证据、原因判断和适用条件。记录保存在项目的独立数据目录，不自动扫描其他文件、环境或 clone，也不发送 telemetry。适合排查执行、保存和恢复问题；AI 正文的文学评价应回到创作要求与审读。

### 先确认问题发生在哪一步

| 观察 | 下一步 |
| --- | --- |
| 参数、文件或请求无效 | 保留 exit code 和安全 stderr，修正输入，停止依赖操作。 |
| 输入准确但准备、状态、保存或恢复违反契约 | 保留准确输入、版本引用及可复现结果，检查应用行为。 |
| 执行完成，正文不符合要求 | 对照创作目标审读准确输出。 |
| 明确的 provider / transport 错误 | 保留 receipt 与安全分类，核对有关服务或 routing 信息。 |
| 只有 timeout、空输出或延迟 | 保持原因 `unknown` 或 `hypothesis`，指出尚缺证据。 |

本地耗时可能包含 CLI 启动、等待、网络与模型执行，不能拆分证明某个环节故障。Lock 只反映本地操作。后续成功前的非 terminal 诊断仍是观察，不等于 task 失败。更换模型或 deadline 也不证明原问题已修复。

### 保存明确选择的证据

```sh
writing-assistant capabilities --schema diagnostic-capture
writing-assistant diagnostics --project ../demo-project capture case.json --evidence selected-evidence.txt
```

`case.json` 包含 `case_id`、完整 `context`，可选 `summary`、`confidence`、`disposition`、`diagnosis`、`expires_at`、`origin`、`secrets`。只选择适合本次诊断的获准 UTF-8 证据；应用在保存前过滤已知 credential pattern 与明确提供的 secrets，并记录 redacted/truncated/exact 状态。过滤不能识别所有私人含义，原始诊断不应进入源码、安装包或公开反馈。

诊断绑定已准备 task 时，先获取应用生成的 context：

```sh
writing-assistant task --project ../demo-project diagnostics TASK_ID --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

原样复制返回的 `context`，仅把 `category` 设为观察到的错误分类。它不包含稿件、URI、私有路径或原始环境；不要重新计算 hash。`validation` 会列出已核对的 metadata 和尚待 execute 检查的正文、外部原件、prompt bytes 与 parent CAS。该命令不调用模型、probe 或进程，不写入本地数据，详见 [task diagnostics](tasks.md#中文)。

### 查看、修订与检查适用性

```sh
writing-assistant diagnostics --project ../demo-project show case-ref.json
writing-assistant diagnostics --project ../demo-project show case-ref.json --include-evidence --byte-limit 32768
writing-assistant diagnostics --project ../demo-project revise case-ref.json changes.json
writing-assistant diagnostics --project ../demo-project preflight context.json
writing-assistant diagnostics --project ../demo-project query --component writing-execution --operation writing --limit 20
```

把 capture/revise 的完整结果或 `ref` 保存为 `case-ref.json`。默认 show、query 和 preflight 返回 metadata 与证据描述；`show --include-evidence` 才返回已保存证据和诊断文字。Reference 指向不可变 revision；revise 使用最新 ref 检查并发，旧 ref 返回 `diagnostics_conflict`。修订格式见 `capabilities --schema diagnostic-revision`，通过 `--evidence FILE` 明确添加新证据。

Context 键为 `project_id`、`component`、`operation`、`category`、`revision`、`environment`、`code_state`、`inputs`、`configuration`、`trigger`、`branch`、`worktree`。填写所有相关条件；branch/worktree 为 null 明确允许跨这些边界复用。不同 clone 只有显式使用相同 data root/project ID 才共享 case。

Confidence 为 `unknown`、`hypothesis`、`confirmed`；disposition 为 `advisory`、`blocker`。诊断复用要求原因 confirmed、条件完整匹配、证据完好且 `expires_at` 未过期。只有 open、confirmed、未过期且适用的 blocker 阻塞相应操作。相同错误文字不能证明同因；routing/CA metadata 变化会使旧匹配失效，`child_routing_proof: unknown` 不能自动复用历史 blocker。

修复后用最新 ref 明确设为 `status: resolved`、`confidence: confirmed`，填写有依据的 diagnosis/resolution 和成功 verification。记录 case 本身不执行验证；已有适用证据可复用，不必为关闭 case 重新调用模型。更改适用条件需要新证据，首次证据继续保留。

Preflight 的 `coverage`、`history`、`warnings`、`skipped_checks` 说明检查范围。没有历史可报告 `history: absent`、`coverage: complete`、零扫描；损坏或不可访问则为 unavailable/degraded。`history: present` 也可能因 pending 或损坏证据而降级。`retry_authorized` 仍为 `false`。

`--byte-limit` 约束 JSON，不含 transport 换行。分页使用返回的 `next_cursor`，不要把它当路径。Mutation 的 `output_contract_violation` 可能已有保存效果，先查看返回的 case/pending 引用。

### 恢复中断保存与管理容量

```sh
writing-assistant diagnostics --project ../demo-project pending
writing-assistant diagnostics --project ../demo-project recover PENDING_ID
writing-assistant diagnostics --project ../demo-project recover PENDING_ID --action discard
writing-assistant diagnostics --project ../demo-project prune withdrawn-case-ref.json
```

只使用返回的 pending ID。Recover 核对完整保存内容与 expected parent 后完成保存；不完整内容继续保留。Discard 只删除选定 pending transaction。Prune 要求 withdrawn case 的最新 ref，不自动删除未解决证据或当前结论。

证据输入、保存 bytes、case/revision 数、扫描、pending、总容量和时长均有限额，见 discovery。容量不足时先决定保留策略；二次诊断保存失败不能覆盖原操作错误。

## English

A diagnostic case stores selected evidence, a diagnosis and the conditions where it applies. Cases live in the project's separate data directory. The application does not automatically scan other files, environments or clones, and sends no telemetry. Use diagnostics for execution, storage and recovery problems; assess literary output against creative requirements and review feedback.

### Identify the failing boundary first

| Observation | Next step |
| --- | --- |
| Invalid arguments, files or request | Retain exit code and safe stderr, correct input and stop dependent operations. |
| Accurate inputs but a preparation, status, storage or recovery contract is violated | Retain exact inputs, version references and a reproducible result; inspect application behavior. |
| Execution completed but prose misses the goal | Review the exact output against the creative requirements. |
| Explicit provider / transport error | Retain the receipt and safe category; inspect relevant service or routing evidence. |
| Only timeout, empty output or delay is known | Keep the cause `unknown` or `hypothesis` and identify missing evidence. |

Local duration can include CLI startup, waiting, network and model execution; it cannot attribute their contributions. Locks describe local operations. A nonterminal diagnostic before later success remains an observation, not a failed task. Changing model or deadline does not establish a repair.

### Capture selected evidence

```sh
writing-assistant capabilities --schema diagnostic-capture
writing-assistant diagnostics --project ../demo-project capture case.json --evidence selected-evidence.txt
```

`case.json` contains `case_id`, a complete `context`, and optional `summary`, `confidence`, `disposition`, `diagnosis`, `expires_at`, `origin`, `secrets`. Select only authorized UTF-8 evidence appropriate to this case. Known credential patterns and explicitly supplied secrets are filtered before storage, with retention metadata distinguishing redacted, truncated and exact bytes. Filtering cannot recognize all private meaning; keep raw diagnostics outside source, packages and public feedback.

For a prepared task, obtain the application's own diagnostic context:

```sh
writing-assistant task --project ../demo-project diagnostics TASK_ID --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

Copy the returned `context` unchanged, setting only `category` to the observed failure category. It contains no manuscript, URI, private path or raw environment; do not hash it again. `validation` names checked metadata and content, external originals, prompt bytes and parent CAS still left to execute. This command makes no model call, probe, process launch or local write; see [task diagnostics](tasks.md#obtain-task-bound-diagnostic-facts).

### Inspect, revise and check applicability

```sh
writing-assistant diagnostics --project ../demo-project show case-ref.json
writing-assistant diagnostics --project ../demo-project show case-ref.json --include-evidence --byte-limit 32768
writing-assistant diagnostics --project ../demo-project revise case-ref.json changes.json
writing-assistant diagnostics --project ../demo-project preflight context.json
writing-assistant diagnostics --project ../demo-project query --component writing-execution --operation writing --limit 20
```

Save the complete capture/revise result or its `ref` as `case-ref.json`. Default show, query and preflight return metadata and evidence descriptors. Only `show --include-evidence` returns retained evidence and diagnostic prose. References identify immutable revisions. Revise checks concurrency using the latest ref; stale refs return `diagnostics_conflict`. Discover the revision format with `capabilities --schema diagnostic-revision`; explicitly add evidence using `--evidence FILE`.

Context keys are `project_id`, `component`, `operation`, `category`, `revision`, `environment`, `code_state`, `inputs`, `configuration`, `trigger`, `branch`, `worktree`. Include every relevant condition. Null branch/worktree explicitly allows reuse across those boundaries. Clones share cases only through explicit configuration of the same data root and project ID.

Confidence is `unknown`, `hypothesis` or `confirmed`; disposition is `advisory` or `blocker`. Reuse requires confirmed cause, complete matching conditions, intact evidence and an unexpired `expires_at`. Only open, confirmed, unexpired and applicable blockers stop the selected operation. Identical error text does not prove identical cause. Changed routing/CA metadata invalidates old matches; `child_routing_proof: unknown` prevents automatic reuse of a historical blocker.

After a repair, use the latest ref to explicitly set `status: resolved`, `confidence: confirmed`, supported diagnosis/resolution and successful verification. Recording a case does not perform verification. Reuse existing applicable evidence without another model call merely to close a case. Changed applicability needs new evidence; first evidence stays retained.

Preflight's `coverage`, `history`, `warnings` and `skipped_checks` explain scope. Absent history can report `history: absent`, `coverage: complete` and zero scans. Damaged or inaccessible history reports unavailable/degraded. `history: present` can also have degraded coverage from pending work or damaged evidence. `retry_authorized` remains `false`.

`--byte-limit` bounds JSON excluding its transport newline. Paginate with returned `next_cursor` values, never treating them as paths. A mutating `output_contract_violation` can follow saved effects; inspect returned case/pending references first.

### Interrupted publication and retention

```sh
writing-assistant diagnostics --project ../demo-project pending
writing-assistant diagnostics --project ../demo-project recover PENDING_ID
writing-assistant diagnostics --project ../demo-project recover PENDING_ID --action discard
writing-assistant diagnostics --project ../demo-project prune withdrawn-case-ref.json
```

Use only returned pending IDs. Recover checks complete saved artifacts and expected parent before completing storage; incomplete work remains retained. Discard removes only the selected pending transaction. Prune requires a withdrawn case's latest ref and does not automatically remove unresolved evidence or current conclusions.

Evidence input, retained bytes, case/revision counts, scans, pending work, total storage and duration are bounded; see discovery. Decide retention before addressing capacity errors. A secondary diagnostic capture failure must not replace the primary operation error.
