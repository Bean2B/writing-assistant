# 本地诊断记录

[中文](#中文) · [English](#english)

## 中文

诊断只保存明确选定的本地观察与适用条件，不是执行许可。先区分调用输入、应用契约、模型正文、provider/网络和未知原因；timeout、空输出或延迟本身不能证明应用有 bug。

### 保存与绑定证据

```sh
writing-assistant diagnostics --project ../demo-project capture case.json --evidence evidence.json
writing-assistant task --project ../demo-project diagnostics task-one --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

通过 `capabilities --schema diagnostic-capture`、`diagnostic-revision` 发现格式。只提供已获授权的证据。任务绑定 context 应从 `task diagnostics` 原样复制，设置实际 failure category，不自行推导源码或环境 hash；返回内容不含稿件、URI、私有路径或原始环境。

Context 绑定 `project_id`、`component`、`operation`、`category`、`revision`、`environment`、`code_state`、`inputs`、`configuration`、`trigger`、`branch`、`worktree`。缺少相关条件不能证明可复用；branch/worktree 为 null 表示允许跨这些边界，否则限制适用。不同 clone 仅通过明确配置相同 data root/project ID 共享 case。

Confidence 为 `unknown`、`hypothesis`、`confirmed`，disposition 为 `advisory`、`blocker`。可复用诊断要求原因已确认、条件完整匹配、证据完好和明确未过期的 `expires_at`；错误文字相同不足以证明同因。Credential-free routing/CA metadata 变化会使旧匹配失效，`child_routing_proof=unknown` 不能自动复用历史 blocker。

### 查看与修订

```sh
writing-assistant diagnostics --project ../demo-project show case-ref.json
writing-assistant diagnostics --project ../demo-project show case-ref.json --include-evidence --byte-limit 32768
writing-assistant diagnostics --project ../demo-project revise case-ref.json changes.json
writing-assistant diagnostics --project ../demo-project preflight context.json
writing-assistant diagnostics --project ../demo-project query --component writing-execution --operation writing --limit 20
```

保留返回的完整 result 或 `ref`。默认只看 metadata/证据描述；`--include-evidence` 才读取保存的证据与已授权诊断文字。Reference 绑定不可变revision；更新使用最新 reference 的 CAS，过时返回 `diagnostics_conflict`。适用条件变化要求新证据，首次证据不删除。

确认修复后，明确 revise 对应 case，使用 `status: resolved`、`confidence: confirmed`、有依据的 diagnosis/resolution 和适用的成功 verification。记录 case 本身不执行验证；已有证据可复用时不为结项重跑模型。未知原因或其他项目的 case 不被顺带解决。

Preflight 返回 `blocking`、`matches`、`coverage`、`history`、`warnings`、`next_cursor`、`skipped_checks`、`retry_authorized`。只有已确认、open、未过期且适用的 blocker 阻塞对应操作。没有可选 history namespace 时可报告 `history: absent`、`coverage: complete`、零扫描；损坏或不可访问时为 unavailable/degraded，不能报告无历史问题。已有 case 为 present，但 pending/损坏证据仍可降低 coverage。

Query/preflight 的 `--byte-limit` 限制 JSON，不含 transport 换行；使用返回的 cursor，不将其当作路径。诊断结果结构检查不替代来源完整性和授权；`retry_authorized` 仍为 false。Mutation 的 `output_contract_violation` 可能已有本地效果，先查看返回的 case/pending 引用。

### 中断与保留

```sh
writing-assistant diagnostics --project ../demo-project pending
writing-assistant diagnostics --project ../demo-project recover PENDING_ID
writing-assistant diagnostics --project ../demo-project recover PENDING_ID --action discard
writing-assistant diagnostics --project ../demo-project prune withdrawn-case-ref.json
```

只使用返回的 pending ID。Recover 在保存发布前核对完整 artifacts 与 expected parent；不完整内容保留。Discard 只删除明确选中的 pending transaction；prune 要求 withdrawn case 的最新 ref，不自动删除未解决证据或当前结论。

证据输入、存储 bytes、case/revision 数、扫描、pending、总容量和时长均有上限，见 discovery。容量问题需要明确保留或预算决定，不为凑成功删除证据。二次 capture 失败要保留原始操作错误。原始诊断不进入源码、安装包或公开反馈。

## English

Diagnostic cases retain explicitly selected observations and scoped diagnoses in
the initialized project's separate user data root. They are local user data,
independent of chat history. The application does not scan Git, environment
variables, unrelated files or other clones to discover diagnostics. It sends no
telemetry. See [privacy](privacy.md) for the service boundary of explicit AI calls.

### Capture selected evidence

```sh
writing-assistant diagnostics --project ../demo-project capture case.json --evidence selected-evidence.txt
```

Use `capabilities --schema diagnostic-capture` or
`capabilities --schema diagnostic-revision` to request each schema. `case.json` contains
`case_id`, a complete applicability `context`, and optional `summary`,
`confidence`, `disposition`, `diagnosis`, `expires_at`, `origin` and `secrets`.
Evidence is a separately selected UTF-8 file, never an automatic process or
environment dump. Known credential patterns and explicitly supplied secrets are
redacted before persistence. Retention metadata says whether bytes were redacted,
truncated or retained exactly; altered bytes are not described as an exact original.
Pattern matching cannot recognize every private meaning in arbitrary text, so
select only evidence authorized for this diagnostic purpose.

### Identify the failing boundary first

Keep the observed outcome separate from its cause. A timeout, empty output or
provider error does not by itself establish an application defect. Use the first
retained receipt and the last completed operation before deciding what to inspect:

| Boundary | Evidence to retain | Appropriate next action |
| --- | --- | --- |
| Calling Agent or local input | Command exit code, safe stderr, and whether a valid request reached the application. | Correct the selected input or invocation. Stop dependent commands when their prerequisite fails; do not parse absent stdout as a result. |
| Application | A reproducible contract violation in preparation, status reporting, persistence or recovery, with exact input and source bindings. | Repair that behavior and verify the affected contract. |
| Model output | Completed execution plus the exact returned text and the unmet creative requirement. | Review the content against the user's intent. Literary quality is not proof of an execution or storage defect. |
| Provider, transport or network | An explicit service/transport failure and its safe structured category, if available. | Preserve the failure and inspect relevant routing or service evidence. Do not resend uncertain work. |
| Unattributed | The symptom is known but the evidence does not distinguish the boundaries above. | Keep confidence `unknown` or `hypothesis`; name the missing evidence instead of assigning a root cause. |

Elapsed child-process time can include CLI startup, service waiting, network and
model execution. It does not identify their individual contributions. Local lock
activity only indicates a local operation, not backend health or progress. A
nonterminal diagnostic followed by successful completion remains an observation;
it is not a failed task. Preserve explicit model and effort selections while
investigating. Changing a deadline or model is a workflow choice, not evidence
that the previous failure was fixed.

Context keys are `project_id`, `component`, `operation`, `category`, `revision`,
`environment`, `code_state`, `inputs`, `configuration`, `trigger`, `branch` and
`worktree`. Fact dictionaries contain bounded string, boolean or integer values.
Record all relevant code/dependencies, inputs, configuration, environment and
trigger facts. Missing relevant facts cannot prove reuse. A null branch/worktree
explicitly permits sharing across those boundaries; non-null values restrict
applicability. Clones share cases only through explicit configuration of the same
data root and project ID. There is no implicit clone linkage.

Confidence is `unknown`, `hypothesis` or `confirmed`; disposition is `advisory`
or `blocker`. A reusable diagnosis requires confirmed cause, complete matching
conditions, intact retained evidence and an explicit unexpired `expires_at`.
Identical error wording alone never proves the same cause. Different text does
not invalidate matching structured facts. `origin` is retained as a digest;
ordinary results do not disclose its arbitrary values.

### Bind a case to a prepared writing task

Use `task diagnostics` to obtain the actual execution hook's context instead of
reconstructing code/policy hashes or environment facts:

```sh
writing-assistant task --project ../demo-project diagnostics task-one --expected-plan-sha256 PLAN_SHA256 --include-preflight
```

Copy the returned `context` unchanged into capture metadata, setting only
`category` to the observed structured failure category. For an applicability
revision, preserve the case's category and include explicit new evidence.
The context contains opaque runtime facts, proof-status values and exact semantic input bindings,
without manuscript text, selected URIs, private paths or raw environment values.
Copy its values directly; the diagnostic store applies its own binding format.

The returned `validation` distinguishes verified plan/configuration/policy/record
metadata from selected content/external-original/prompt bytes not read and parent
CAS not checked. Execution retains those independent checks. The query is bounded,
makes no provider/process call or local write, and grants no retry authority.
See [task diagnostics](tasks.md#obtain-task-bound-diagnostic-facts).
Changed credential-free routing or CA file metadata invalidates old matches.
`child_routing_proof=unknown` marks credential-bearing/ambiguous routing or missing
CA metadata as unproven; that prevents automatic diagnostic reuse. This is local
metadata, not authentication, CA-content validation or provider/launch attestation.

### Inspect, revise and check applicability

```sh
writing-assistant diagnostics --project ../demo-project show case-ref.json
writing-assistant diagnostics --project ../demo-project show case-ref.json --include-evidence --byte-limit 32768
writing-assistant diagnostics --project ../demo-project revise case-ref.json changes.json
writing-assistant diagnostics --project ../demo-project preflight context.json
writing-assistant diagnostics --project ../demo-project query --component writing-execution --operation writing --limit 20
```

Save the complete returned capture/revision result or its `ref` as `case-ref.json`.
All diagnostic-store CLI results have definitions in
`capabilities --schema core-results`; operation discovery links the exact output
definition. The CLI checks references, revision numbers, retention metadata,
hashed bindings, applicability decisions and recovery variants before emitting
JSON. Default `show` remains metadata-only; `contents` appears only with explicit
`--include-evidence`. Discovery declares both JSON variants and the CLI binds
validation to that flag. Schema coverage does not authorize evidence access or retry,
and `retry_authorized` remains `false`.

An `output_contract_violation` returns only bounded safe operation identity and
validated references, case IDs or pending IDs where available. Diagnostic
mutations can already have persisted effects, so inspect those references or
`pending` before further action. No diagnostic text, evidence or hashed binding
dictionary is copied into this error.
References bind the exact immutable revision. Revision uses latest-reference CAS;
a stale update returns `diagnostics_conflict`. `changes.json` uses the catalog's
revision schema; `--evidence FILE` explicitly selects additional evidence.
Changing relevant applicability requires new evidence. First evidence remains
retained. Resolving a case requires confirmed cause, a resolution and a recorded
successful verification; recording a case does not itself perform verification.

After a confirmed repair, revise the affected case using its latest exact ref.
Set `status: resolved`, `confidence: confirmed`, the supported `diagnosis` and
`resolution`, and a verification event only when a successful applicable check
exists. Retain that check's candidate and evidence reference. Reuse an existing
check when its scope still applies; do not run a model merely to close a case.
Keep unrelated failures and unknown causes separate. An engineering repair does
not automatically update every project's cases or authorize reopening a paused
writing task.

Default lookup returns safe metadata and evidence descriptors without evidence
text or arbitrary diagnosis prose. `--include-evidence` explicitly reads retained,
redacted evidence and authorized diagnostic prose. Query/preflight accept `--limit`,
`--cursor` and `--byte-limit`; the byte limit bounds JSON excluding its transport
newline. Pagination cursors are returned values, never storage paths.

Preflight returns `blocking`, `matches`, invalidation reasons, `coverage`, `history`,
`warnings`, `next_cursor`, `skipped_checks` and `retry_authorized`. Only a confirmed,
open, unexpired and applicable blocker affects its selected operation. Advisory,
unconfirmed, invalidated or unrelated cases do not pause unrelated work. An absent
optional namespace, after live authority and existing-ancestor checks, reports
`history=absent`, `coverage=complete`, zero scanned cases and no warning. This
means no retained history at that authorized location. Damaged or inaccessible
history reports `history=unavailable` and degraded coverage. Existing cases report
`history=present`; pending recovery and damaged evidence can still degrade coverage.
Authority/security/integrity checks remain mandatory and fail closed.
Diagnostic reuse never authorizes a model retry or skipping a mandatory gate.

### Interrupted publication and retention

```sh
writing-assistant diagnostics --project ../demo-project pending
writing-assistant diagnostics --project ../demo-project recover PENDING_ID
writing-assistant diagnostics --project ../demo-project recover PENDING_ID --action discard
writing-assistant diagnostics --project ../demo-project prune withdrawn-case-ref.json
```

Use only returned pending IDs. Recovery validates complete saved artifacts and
expected parent before publication. Incomplete work is preserved for inspection;
`discard` explicitly removes only that selected pending transaction. Pruning is
explicit, requires a withdrawn case's latest reference, and never automatically
removes unresolved evidence or current conclusions.

The catalog reports the store's default limits. Evidence input, retained bytes,
case/revision counts, scans, pending transactions, total storage and call duration
are bounded. Capacity errors require an explicit retention or budget decision;
do not delete evidence simply to make an affected action succeed. Failure of
secondary capture must preserve the primary action error. Raw diagnostics belong
outside source, packages and public feedback.
