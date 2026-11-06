# Codex 支持 / Codex support

[中文](#中文) · [English](#english)

## 中文

Agent 调用写作助手的本地 CLI，明确发起 AI 任务时，应用通过另行安装的 Codex CLI
沿用其已有登录执行请求。保存记录和准备材料可以离线完成，调用契约见
[Agent 接入说明](agent-usage.md)。

支持的本地环境为 **macOS arm64 与 Python 3.12**。允许使用的 Codex CLI 版本为
`0.166.0-alpha.6` 和 `0.164.0-alpha.11.1`，其他版本返回 `capability_unsupported`。
Windows、Linux、desktop、IDE 和 cloud 执行路径不在本接入方式的支持范围内。

`doctor` 检查本机版本、帮助信息以及应用共用 launch 配置，不调用模型。配置探查使用临时空
配置目录，明确关闭 Code Mode 及其 host，不修改全局设置。
`launch_configuration=feature_flags_verified` 且 `live_supported: true` 表示 CLI 满足这些
本地要求。兼容字段 `live_supported` 只报告本地资格；`probe_scope` 为
`local-version-help-and-feature-flags`，`runtime_readiness` 为 `not_checked`。
probe 不检查所选模型的 runtime tool mode、不认证请求，也不确认生成一定完成。
配置状态不明或冲突时拒绝 dispatch；实际请求仍可能因登录、模型可用性、服务错误或返回结果而失败。

`task prepare` 冻结输入，`task inspect` 查询状态，`task execute` 按返回的 plan digest
发起请求，`task reconcile` 从已保存证据完成本地恢复。旧版顶层 `prepare/execute` 的
独立行为见 [durable task 说明](tasks.md)。用 `--model` 选择 Codex 账号可以使用的
模型；省略时使用忽略 user CLI 配置后的默认值，不继承调用方 Agent 的模型。请求模型名
也不等于已确认的后端模型身份。

用 `--reasoning-effort` 明确选择 `low`、`medium`、`high`、`xhigh`、`max` 或 `ultra`；
应用把该值冻结到 task，并原样传给 native `model_reasoning_effort`。省略时沿用忽略 user CLI
配置后的默认值，不从调用方 Agent 继承，也不证明后端实际使用的 effort。native `ultra`
可能包含自动 delegation；可见 delegation 仍按 `capability_unsupported` 处理，不静默替换 effort。

每次任务使用新的 Codex 上下文，交给它的项目材料由你选择。Codex 自身的系统、全局
user 和安全指令仍可能参与，准备结果不能展示全部 Codex 上下文。工具不修改你的全局
Codex 规则或配置。

应用只转交下方英文参考表中列出的环境变量，保留已有登录、proxy/bypass routing 和 CA 设置，不读取
登录存储或 keychain 内容，也不转交无关 API key、token、调用方 bridge 或任意环境变量。
这只约束应用传给 subprocess 的环境；OS/runtime 可能自行增加字段，普通 OS 文件访问权限
仍然存在，不能据此声称具有 OS 或 network isolation。可观察到的工具调用和 delegation
返回 `capability_unsupported`；未暴露的 provider 活动及未来协议形式不在此观察结论内。

默认本地超时为 120 秒，`--timeout` 最大 600 秒；这不等于 token 或费用上限。
输入、可见输出和诊断记录保存在本地，生成内容需要审读。超时、取消、无效输出和结果
不明会报错，不自动重发。本地进程结束不证明远端服务已经停止。文件系统故障也可能
导致结果或诊断保存不完整，应保留已有输入和记录，按[使用与恢复](usage.md)核对结果。
执行期间识别到 `turn.failed` 会及时停止本地进程并保留诊断。`item.completed` 中的 error，
包括 Code Mode host-disabled 诊断，可能出现在成功文字 turn 之前；应用保留它，但不据此停止
进程或判定整个请求的结果。完成仍要求成功的 terminal turn、正常进程退出及完整有效的最终输出。
未知或部分 stream 仍受原有 timeout、取消和输出边界约束。
诊断 stream/probe 中识别到的 proxy/CA 片段会被过滤，并标记 redacted/incomplete；长度和
digest 描述保留字节。final-message artifact 的字节不受该过滤影响，完整性由独立的
`output_complete` 说明。`streams_complete=false` 不能替代该判断。形似已知私人片段的
usage metadata 可能被省略；过滤无法识别所有 secret，显式 raw content read 仍保持授权
内容的原始字节。

receipt 的 `observation_summary.elapsed` 返回 `value`、`unit: seconds` 和
`scope: local_codex_adapter_after_qualification`，表示 qualification 之后 adapter
本地生命周期的观测耗时，包含本地停止、stream draining 和最终输出读取；不包含
qualification 或后续记录保存，也不表示整个 task、模型计算或网络耗时。没有观测值时，
包括 qualification 失败，`value` 为 `null`，不会补成零。`usage_status` 区分
`reported`、`unavailable`、`redacted`，既有 `usage` 保留 provider 报告的 metadata；
缺失或经过过滤不表示没有消耗 token。`cost` 保持 `status: unknown`、`amount: null`、
`currency: null`；应用没有受支持的收费证明，也不按 token 估价。成功、失败、timeout
和 unknown 的新 receipt 使用同一摘要；reconciliation 只复用保存事实。旧 receipt
可能没有该字段，表示当时未记录，不会为回填摘要改写历史字节。

## English

An Agent invokes Writing Assistant's local CLI. When it explicitly requests an
AI task, the application uses a separately installed Codex CLI with its existing
authentication. Saving records and preparing material work offline. The calling
contract is described in the [Agent interface guide](agent-usage.md).

#### Supported environment

The supported local environment is **macOS arm64 with Python 3.12**. Accepted
Codex CLI builds are `0.166.0-alpha.6` and `0.164.0-alpha.11.1`. Other builds are
rejected as `capability_unsupported`. Windows, Linux, desktop, IDE, and cloud
execution paths are outside this integration's support scope.

Run `writing-assistant doctor` before an AI task. It checks local version and
help output and the application's launch configuration without calling a model.
It uses the same launch overrides for a local feature-state probe in a temporary
empty configuration root. Both `features.code_mode.enabled` and `code_mode_host`
are disabled for these no-tool tasks. This leaves the user's global settings
unchanged. `launch_configuration=feature_flags_verified` and `live_supported: true`
mean the installed CLI meets these local requirements. The compatibility field
`live_supported` reports only this local qualification: `probe_scope` is
`local-version-help-and-feature-flags` and `runtime_readiness` is `not_checked`.
The probe does not check the selected model's runtime tool mode, authenticate a
request, or establish that generation will complete. Unknown or incompatible
feature state refuses dispatch; a request can still fail because of sign-in,
model availability, service errors, or its result.

#### Choose a model and inspect the input

```sh
writing-assistant capabilities --project ../demo-project
writing-assistant task --project ../demo-project prepare examples/synthetic/request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

`task prepare` does not send the task. Copy the returned task ID and plan digest
into the inspect/execute calls. See [durable tasks](tasks.md) for saved-byte
recovery and the separate legacy top-level `prepare/execute` behavior.
Use `--model` to select a model available to
your Codex account. If omitted, the CLI default is used with user CLI
configuration ignored; it does not inherit the model selected in your current
Agent's context. The requested model name is not confirmation of the backend model identity.

`--reasoning-effort` explicitly selects `low`, `medium`, `high`, `xhigh`, `max` or
`ultra` and passes it unchanged as `model_reasoning_effort`. The task freezes this
choice independently of the model. Omission uses the CLI default with user
configuration ignored. The calling Agent's effort is not inherited, and requested
effort does not attest the backend's setting. Codex's native `ultra` can involve
automatic delegation; exposed delegation still returns `capability_unsupported`.
An unavailable model/effort combination is not silently replaced.

Each task starts a fresh Codex context. The tool passes the selected project
material, while Codex can still apply its own system, global user, and safety
instructions. Inspecting the prepared input does not reveal all of Codex's
context. The tool does not edit your global Codex rules or configuration.

#### Subprocess environment and observable activity

The application forwards only these environment names when present:

| Purpose | Names |
| --- | --- |
| Executable/account/auth directories | `PATH`, `HOME`, `CODEX_HOME` |
| Locale | `LANG`, `LANGUAGE`, `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME` |
| Temporary directories | `TMPDIR`, `TMP`, `TEMP` |
| Existing routing/bypass | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and their lowercase forms |
| Custom CA paths | `CODEX_CA_CERTIFICATE`, `SSL_CERT_FILE` |

It does not add or change proxy routing, inspect auth-store/keychain contents,
or forward unrelated API keys/tokens, `PYTHONPATH`/`PYTHONHOME`, shell/loader
controls, bridge identifiers or arbitrary `CODEX_*`/`LC_*` variables. Existing
CLI account authentication remains the supported route. Undocumented wrappers
that require excluded variables are outside this boundary.

This controls the environment supplied by the application; the OS/runtime may
synthesize its own fields. The retained account/auth, routing and trust inputs,
and ordinary OS access permissions remain available to Codex. No OS or network
isolation is established. Exposed command/file/MCP/web/delegation tool activity
is classified as `capability_unsupported`. Unexposed provider activity and future
protocol forms cannot be established from local observations.

#### Timeouts, results, and interrupted work

Requests have a 120-second local deadline by default. `--timeout` accepts more
than 0 and at most 600 seconds. These local limits are not a token or cost ceiling.

Inputs, exposed output, and diagnostics are saved locally. Review generated
text before using it. A timeout, cancellation, invalid output, or uncertain
completion is reported as an error. A locally stopped process does not prove
that the remote service stopped computing.
Supported terminal JSONL errors are detected while the process runs. A
`turn.failed` triggers local stopping and retains the exposed diagnostics promptly,
before the local deadline. An `item.completed` error, including the Code Mode
host-disabled diagnostic, can precede a successful text turn. It is retained
without stopping the process or deciding the whole request's result. Completion
still requires a successful terminal turn, process exit, and complete valid final
output. Unknown or partial streams remain subject to the ordinary timeout,
cancellation and output bounds.
Diagnostic stdout/stderr and probe messages can be filtered for recognized
configured proxy/CA fragments. `stdout_redacted`/`stderr_redacted`, probe
`redacted`, and completeness flags identify altered or incomplete diagnostics.
`streams_complete=false` does not itself describe final-message completeness;
the separate unchanged output artifact has `output_complete`. Recognized private
fragments in provider usage metadata can cause that metadata to be omitted.
This filtering is bounded and does not scan authentication stores or detect every
possible secret. Ordinary writing results expose references rather than bodies;
explicit raw content reads preserve authorized content bytes.

Receipts include an `observation_summary`. Its `elapsed` contains `value`,
`unit: seconds`, and `scope: local_codex_adapter_after_qualification`. This is the
recorded local adapter lifecycle after qualification, including process stopping,
stream draining and final-output reading. It excludes qualification and later
record storage; it is not total task latency, model compute time or network time.
An unmeasured value, including qualification failure, is `null` rather than zero.
`usage_status` is `reported`, `unavailable` or `redacted`; the separate `usage`
retains reported provider metadata. Unavailable or redacted usage does not imply
that no tokens were consumed. `cost` has `status: unknown`, `amount: null` and
`currency: null`: the application has no supported charge attestation and does
not estimate a price from tokens. These facts apply to saved failed/timeout/
unknown attempts as well as successful ones. Reconciliation uses saved facts
without dispatching again. Older saved receipts can omit the summary; omission
means not recorded, and their original bytes are not rewritten to backfill it.

| Code | Meaning |
| --- | --- |
| `codex_missing` | The local executable was not found. |
| `capability_unsupported` | The build, required capability, or exposed tool activity is unsupported. |
| `codex_model_failure` | The CLI or model reported a terminal failure. |
| `codex_timeout` | The local deadline was reached. |
| `codex_cancelled` | An interruption or cancellation was observed. |
| `codex_malformed` | The output was missing, invalid, or too large. |
| `codex_unknown` | Completion could not be established. |

The tool does not automatically resend a request with an uncertain outcome.
Keep its input and saved records, then inspect the result before starting more
work. A filesystem failure can prevent a complete result or diagnostic record
from being saved. See [recovery](usage.md) and [privacy](privacy.md).
