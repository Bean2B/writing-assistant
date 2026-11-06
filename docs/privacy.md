# 隐私与数据 / Privacy and data

[中文](#中文) · [English](#english)

## 中文

Writing Assistant 在你的本地环境运行。项目和开发者不收集使用数据，应用没有遥测、自动上传、网络共享或同步。

### 你的内容归你所有

在你与本项目及开发者之间，你的输入、稿件、生成结果、保存记录和本地诊断信息都归你所有。使用软件不授予项目或开发者收集、使用或再分发这些数据的权限。[软件许可证](../LICENSE)不适用于你的创作内容。

### 本地保存什么

| 内容 | 保存位置 |
| --- | --- |
| 项目配置 | 项目目录中的 `.writing-assistant/config.json` |
| 灵感、稿件与历史版本 | 初始化时选择的数据目录 |
| 任务输入、输出、进度与诊断 | 同一数据目录内的相应记录 |

保存、检索、整理材料和本地恢复不调用模型。`doctor` 只调用本机 Codex CLI 的版本、帮助和配置探查命令。

这些文件受本机文件访问权限控制。拥有相应权限的软件也可以读取它们，应用不提供独立的文件加密。备份应在停止写入后进行，并保留完整项目配置和数据目录；操作步骤见 [备份与恢复](usage.md)。

### 何时会联网

当 Agent 在你的授权内明确执行 AI 写作或角色行动推演任务时，应用将请求和选定材料交给本机 Codex CLI，由它使用既有登录访问 AI 服务。应用没有向开发者发送内容的接口。

Codex 可能加载自身的系统指令和本机全局指令，例如 `AGENTS.md`。应用准备的输入不代表完整模型上下文。AI 服务的数据处理、保留和费用受该服务的条款及设置约束；发送敏感内容前请检查相应设置。模型选择、兼容版本和超时行为见 [Codex 支持](codex-support.md)。

### 日志与问题反馈

诊断内容保存在本地，可能包含路径、标题、请求或输出。应用会过滤诊断流中已识别的代理和证书配置片段，但不能保证识别所有私人信息；原始创作输出保持原样。

公开反馈请提供虚构材料和最小复现步骤，避免上传稿件、凭据、个人配置或完整日志。详见 [安全说明](../SECURITY.md)和[诊断指南](diagnostics.md)。

## English

Writing Assistant runs in your local environment. The project and its developers do not collect usage data. The application has no telemetry, automatic uploads, network sharing or synchronization.

### Your content belongs to you

As between you and this project or its developers, your inputs, manuscripts, generated results, saved records and local diagnostics remain yours. Using the software grants no permission to collect, use or redistribute them. The [software license](../LICENSE) does not license your writing.

### What is stored locally

| Content | Location |
| --- | --- |
| Project configuration | `.writing-assistant/config.json` in the project directory |
| Ideas, manuscripts and saved versions | The data directory chosen during initialization |
| Task inputs, outputs, progress and diagnostics | Their corresponding records in the same data directory |

Saving, searching, organizing material and local recovery do not call a model. `doctor` only runs the local Codex CLI's version, help and configuration probes.

Local file permissions control access. Other software with sufficient permission can read these files; the application does not provide separate file encryption. Stop writes before backing up, and preserve the complete project configuration and data directory. See [backup and recovery](usage.md#english).

### When a network connection is used

When an Agent explicitly executes an authorized AI writing or character-decision task, the application passes the request and selected material to the local Codex CLI. Codex uses its existing sign-in to access its AI service. The application has no endpoint for sending content to the developer.

Codex may load its system instructions and local global instructions such as `AGENTS.md`. The application's prepared input is not the complete model context. Data handling, retention and charges are governed by the AI service's terms and settings; check them before sending sensitive material. See [Codex support](codex-support.md#english) for model selection, accepted versions and timeout behavior.

### Logs and issue reports

Diagnostics stay local and may contain paths, titles, requests or outputs. The application filters recognized proxy and certificate configuration fragments from diagnostic streams, but cannot identify every private detail. Original creative output is preserved unchanged.

Use fictional material and minimal reproduction steps in public reports. Leave out manuscripts, credentials, personal configuration and complete logs. See [Security](../SECURITY.md#english) and [Diagnostics](diagnostics.md#english).
