# Codex 支持 / Codex support

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

Writing Assistant 通过另行安装的 Codex CLI 及其已有登录执行 AI 请求。保存记录、准备 task 和查看进度可以离线完成。安装应用不包含 Python、Codex 或登录凭据，见[安装指南](install.md#中文)。

### 支持环境

| 项目 | 当前支持 |
| --- | --- |
| OS / architecture | macOS arm64 |
| Python | 3.12 |
| Codex CLI | `0.166.0-alpha.6`、`0.164.0-alpha.11.1` |

其他 Codex build 返回 `capability_unsupported`。此集成的执行入口是本地 Codex CLI；Windows、Linux、desktop、IDE 与 cloud 执行路径不在支持范围内。

```sh
writing-assistant doctor
```

Doctor 检查本机版本、帮助和应用的 launch 配置，不调用模型。它使用临时空配置目录探查 Code Mode 及其 host 已关闭，不修改全局设置。`live_supported: true`、`launch_configuration: feature_flags_verified` 表示通过本地检查；`probe_scope: local-version-help-and-feature-flags`、`runtime_readiness: not_checked` 说明尚未验证实际请求。登录、所选模型、runtime tool mode 或服务仍可能导致执行失败。

### 选择模型与 effort

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL --reasoning-effort high --timeout 120
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

将 `MODEL` 换成账号可用的选定模型，并复制返回的 task ID 与 plan digest。准备不发送请求，详见[可恢复任务](tasks.md#中文)。

`--reasoning-effort` 接受 `low`、`medium`、`high`、`xhigh`、`max`、`ultra`，原样传给 Codex `model_reasoning_effort`，与模型一起冻结在 task。省略任一设置时使用忽略 user CLI 配置后的 CLI 默认值，不继承当前 Agent 的设置。请求值不证明后端实际模型或 effort；不可用组合不会静默替换。Native `ultra` 可能包含自动 delegation，可观察到的 delegation 仍返回 `capability_unsupported`。

每个 task 启动新的 Codex context，并传入选定项目材料。Codex 自身的系统、全局 user 和安全指令仍可能参与，准备结果不能展示全部 Codex context。应用不修改你的全局 Codex 规则或配置。

### 环境与数据访问

应用只向 subprocess 转交以下已存在的变量：

| 用途 | 名称 |
| --- | --- |
| 可执行文件、账号与认证目录 | `PATH`, `HOME`, `CODEX_HOME` |
| Locale | `LANG`, `LANGUAGE`, `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME` |
| 临时目录 | `TMPDIR`, `TMP`, `TEMP` |
| 已有 proxy / bypass routing | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` 及小写形式 |
| 自定义 CA 路径 | `CODEX_CA_CERTIFICATE`, `SSL_CERT_FILE` |

应用不读取登录存储或 keychain 内容，不转交无关 API key/token、`PYTHONPATH`、`PYTHONHOME`、shell/loader controls、调用方 bridge 或任意前缀变量。依赖被排除变量的 wrapper 不在支持范围内。

以上约束应用传入的环境，OS/runtime 仍可能增加字段。Codex 保留账号认证、routing、trust 配置及普通 OS 权限；这不提供 OS 或 network isolation。可见 command/file/MCP/web/delegation 活动会被拒绝为 `capability_unsupported`，本地观察无法证明未暴露的 provider 活动。发送到服务的材料与本地保存内容见[隐私](privacy.md#中文)。

### 耗时、费用与失败恢复

默认本地 timeout 为 120 秒，`--timeout` 要求大于 0、至多 600 秒。它不构成 token 或费用上限；本地进程停止也不证明远端计算停止。未知结果不自动重发，先查看保存状态与引用。

| 错误 | 含义与下一步 |
| --- | --- |
| `codex_missing` | 找不到可执行文件，检查安装与 `PATH`。 |
| `capability_unsupported` | build、必要能力或暴露的工具活动不受支持，运行 doctor。 |
| `codex_model_failure` | CLI 或模型报告 terminal failure，保留 receipt。 |
| `codex_timeout`、`codex_cancelled` | 本地 deadline 或中断，先查看保存结果。 |
| `codex_malformed` | 最终输出缺失、无效或超限。 |
| `codex_unknown` | 无法确认完成状态，保留现有 task，勿换 ID 重发。 |

运行时 `turn.failed` 会停止本地进程并保留诊断；`item.completed` 中的 error 可能先于成功文字 turn，单独出现不判定整个 task 失败。完成要求成功 terminal turn、正常退出及完整有效的最终输出。未知或部分 stream 仍受 timeout、取消与输出限制。

诊断 stream/probe 中识别到的 proxy/CA 片段会被过滤；redacted/completeness 标记描述保留字节。最终文本有独立的 `output_complete`，不能从 `streams_complete` 推断。Usage metadata 也可能被过滤；此机制不能识别所有私密内容。显式原文读取保持获准内容的原始 bytes。

Receipt 的 `observation_summary` 包含：

- `elapsed`：`unit: seconds`、`scope: local_codex_adapter_after_qualification`，从资格检查结束后计入 adapter 的本地执行、停止、stream draining 与最终输出读取；不含资格检查或后续存储，也不是整个 task、模型计算或网络耗时。未观测时 `value: null`。
- `usage_status`：`reported`、`unavailable` 或 `redacted`；provider 报告保存在独立 `usage`。缺失不表示消耗为零。
- `cost`：`status: unknown`、`amount: null`、`currency: null`。应用不提供收费证明，也不根据 token 估价。

成功、失败和不确定的新 receipt 使用同一摘要；reconcile 复用保存事实。历史 receipt 可缺少摘要，不回填历史 bytes。存储故障可能留下不完整结果，恢复步骤见[使用说明](usage.md#中文)。

## English

Writing Assistant executes AI requests through a separately installed Codex CLI and its existing sign-in. Saving records, preparing tasks and inspecting progress work offline. The application does not bundle Python, Codex or credentials; see [installation](install.md#english).

### Supported environment

| Component | Current support |
| --- | --- |
| OS / architecture | macOS arm64 |
| Python | 3.12 |
| Codex CLI | `0.166.0-alpha.6`, `0.164.0-alpha.11.1` |

Other Codex builds return `capability_unsupported`. This integration executes through the local Codex CLI. Windows, Linux, desktop, IDE and cloud execution paths are outside its support scope.

```sh
writing-assistant doctor
```

Doctor checks local version, help and application launch configuration without calling a model. A temporary empty configuration directory verifies that Code Mode and its host are disabled, leaving global settings unchanged. `live_supported: true` and `launch_configuration: feature_flags_verified` report successful local checks. `probe_scope: local-version-help-and-feature-flags` and `runtime_readiness: not_checked` mean no actual request was verified. Sign-in, the selected model, runtime tool mode or service can still cause execution to fail.

### Choose a model and inspect the input

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL --reasoning-effort high --timeout 120
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

Replace `MODEL` with the selected model available to the account. Copy the returned task ID and plan digest. Preparation does not send a request; see [durable tasks](tasks.md#english).

`--reasoning-effort` accepts `low`, `medium`, `high`, `xhigh`, `max`, `ultra`, passed unchanged as Codex `model_reasoning_effort` and frozen with the model in the task. Omitted settings use CLI defaults with user CLI configuration ignored, without inheriting the calling Agent's settings. Requested values do not attest backend model identity or effort; unavailable combinations are not silently replaced. Native `ultra` can involve automatic delegation; exposed delegation still returns `capability_unsupported`.

Each task starts a fresh Codex context with selected project material. Codex can still apply its own system, global user and safety instructions. Prepared input does not reveal all Codex context. The application does not edit your global Codex rules or configuration.

### Subprocess environment and observable activity

The application forwards only these existing environment variables:

| Purpose | Names |
| --- | --- |
| Executable, account and auth directories | `PATH`, `HOME`, `CODEX_HOME` |
| Locale | `LANG`, `LANGUAGE`, `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME` |
| Temporary directories | `TMPDIR`, `TMP`, `TEMP` |
| Existing proxy / bypass routing | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and lowercase forms |
| Custom CA paths | `CODEX_CA_CERTIFICATE`, `SSL_CERT_FILE` |

It does not read auth-store or keychain contents, or forward unrelated API keys/tokens, `PYTHONPATH`, `PYTHONHOME`, shell/loader controls, caller bridges or arbitrary prefixed variables. Wrappers requiring excluded variables are unsupported.

This bounds the environment supplied by the application; the OS/runtime can add fields. Codex retains account authentication, routing, trust settings and ordinary OS permissions. This provides no OS or network isolation. Exposed command/file/MCP/web/delegation activity is rejected as `capability_unsupported`; local observation cannot establish unexposed provider activity. See [privacy](privacy.md#english) for material sent to the service and local storage.

### Timeouts, results, and interrupted work

The default local timeout is 120 seconds. `--timeout` must be greater than 0 and at most 600 seconds. It is not a token or cost ceiling; stopping a local process does not prove remote computation stopped. Uncertain results are not automatically resent. Inspect saved status and references first.

| Error | Meaning and next step |
| --- | --- |
| `codex_missing` | Executable not found; check installation and `PATH`. |
| `capability_unsupported` | Unsupported build, required capability or exposed tool activity; run doctor. |
| `codex_model_failure` | CLI or model reported terminal failure; retain the receipt. |
| `codex_timeout`, `codex_cancelled` | Local deadline or interruption; inspect saved results first. |
| `codex_malformed` | Final output is missing, invalid or oversized. |
| `codex_unknown` | Completion cannot be established; preserve the task and do not resend with a new ID. |

A runtime `turn.failed` stops the local process and retains diagnostics. An `item.completed` error can precede a successful text turn; alone it does not fail the whole task. Completion requires a successful terminal turn, normal exit and complete valid final output. Unknown or partial streams remain subject to timeout, cancellation and output limits.

Recognized proxy/CA fragments in diagnostic streams/probes are filtered, with redacted/completeness flags describing retained bytes. Final text has its own `output_complete`; `streams_complete` cannot establish it. Usage metadata may also be filtered. Filtering cannot identify all private content; explicit original-content reads preserve authorized bytes.

A receipt's `observation_summary` contains:

- `elapsed`: `unit: seconds`, `scope: local_codex_adapter_after_qualification`. It measures the adapter's local lifecycle after qualification, including execution, stopping, stream draining and final-output reading. It excludes qualification and later storage; it is not total task, model compute or network time. Unmeasured `value` is `null`.
- `usage_status`: `reported`, `unavailable` or `redacted`; the separate `usage` retains provider-reported metadata. Missing usage does not mean zero consumption.
- `cost`: `status: unknown`, `amount: null`, `currency: null`. The application provides no charge attestation or token-based price estimate.

New successful, failed and uncertain receipts use the same summary; reconciliation reuses saved facts. Historical receipts can omit it and are not rewritten. Storage failures can leave incomplete results; see [recovery](usage.md#english).
