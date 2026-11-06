<h1 align="center">Writing Assistant</h1>

<p align="center">
  <strong>面向 Agent 的本地 AI 写作助手</strong><br>
  构思、写作、审读与修订，让 Agent 在同一个项目中持续创作。
</p>

<p align="center">
  <a href="https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1"><strong>下载 v0.1.1</strong></a> ·
  <a href="#快速上手">快速上手</a> ·
  <a href="#功能一览">功能一览</a> ·
  <a href="docs/agent-usage.md">Agent 使用说明</a> ·
  <a href="docs/en/README.md">English</a>
</p>

<p align="center">
  macOS (Apple Silicon) · Python 3.12 · Apache-2.0 · 由 Codex 开发
</p>

<a id="中文"></a>

Writing Assistant 为 Agent 提供写作所需的操作与项目管理能力。你确定创作方向，Agent 通过 CLI 调用应用，整理资料、准备写作任务、生成稿件并处理审读意见。设定、稿件版本和任务进度保存在本地，方便继续创作时找回所需内容。

当前版本通过 **Codex CLI** 执行 AI 写作任务。开始前请查看[兼容要求](docs/codex-support.md#中文)；保存、查找和整理记录可以离线使用。

## 功能一览

<table>
  <tr>
    <td width="50%" valign="top"><strong>✍️ 构思与写作</strong><br>围绕你的要求生成构思候选、场景规划和正文，也可以审读或修订已有稿件。</td>
    <td width="50%" valign="top"><strong>📖 章节流程</strong><br>按章节组织规划、起草和审读，保存各阶段进度，让 Agent 接着已有任务继续。</td>
  </tr>
  <tr>
    <td valign="top"><strong>🗂️ 创作资料管理</strong><br>保存灵感、设定与草稿，检索原文、查看修改历史，为选定版本保存续写书签。</td>
    <td valign="top"><strong>🧭 人物与设定管理</strong><br>记录人物位置、关系和已知信息，为当前章节选择相关设定与前文。</td>
  </tr>
  <tr>
    <td valign="top"><strong>🧩 写作技法包</strong><br>按需选用人物协作、信息变化、选择代价、行动结果和细节呼应等写作指导。</td>
    <td valign="top"><strong>🎭 角色行动推演</strong><br>请求角色决策、推进场景内日程和状态，提取选定角色可见的信息用于写作。</td>
  </tr>
</table>

## 如何用于创作

### 从想法开始，也能接着已有稿件写

把题材、人物、基调和篇幅要求交给 Agent。它可以调用应用生成构思与场景规划，再进入正文；已有稿件也可以作为材料，用于续写、审读或修订。每次任务保存输入和输出，方便回看当时使用的要求与版本。

[写作任务](docs/tasks.md#中文) · [请求格式](docs/interface.md#中文)

### 让多章创作有明确的步骤

章节 workflow 组织规划、正文和审读阶段，关联上一阶段的结果并记录当前进度。Agent 查看下一项任务后执行，应用保存结果并准备后续阶段。审读意见可以接受、拒绝或暂缓；最终采用哪些文字由你决定。

[章节流程](docs/workflows.md#中文) · [处理审读意见](docs/review-decisions.md#中文)

### 写得越久，越需要找得回资料

创作记录保存原文和修改版本；Story state 记录人物、关系、地点与已知信息；Story context 将选定设定和前文组织成当前任务的材料。Agent 可以按需查找与选择，避免每次都靠重新讲述整部作品来交接。

[创作记录](docs/records.md#中文) · [人物与设定](docs/story-state.md#中文) · [写作上下文](docs/story-context.md#中文)

### 按当前任务选择写作技法

内置技法包提供可组合的写作指导。例如，用共同任务连接人物选择，检查人物当时能知道什么，让行动产生具体后果，或让再次出现的细节影响后续发展。Agent 可查看适用条件，选择需要的技法用于写作和审读。

[查看技法与用法](docs/techniques.md#中文) · [角色行动推演](docs/world.md#中文)

## 快速上手

**1. 安装应用。** 下载 [v0.1.1 的 wheel](https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl)，按[安装指南](docs/install.md#中文)完成校验和安装。你也可以把下面的要求直接交给 Codex：

> 请按 https://github.com/Bean2B/writing-assistant/blob/main/docs/install.md 安装 Writing Assistant。先检查兼容环境和已有项目，再与我确定项目和数据目录；已有内容请保留。安装完成后告诉我如何开始使用。

**2. 让 Agent 读取使用说明。** 将 [Agent 使用说明](docs/agent-usage.md#中文)和项目路径交给它。应用通过本地 CLI 提供操作，部分资料管理能力也提供 Python API。

**3. 给出本次创作目标。** 例如，可以用这段指令开始一个新项目：

> 请用 Writing Assistant 辅助我构建一部新作品。先与我确认题材、主角、基调和篇幅，再整理设定与章节规划，等我确认后开始正文。将创作材料保存在指定的本地项目中。

这是一段操作请求示例。沟通与选择由 Agent 和你完成；应用负责执行明确的任务并保存项目内容。

## 常见问题

<details>
<summary><strong>我需要自己操作命令行吗？</strong></summary>

可以让具备本地命令执行能力的 Agent 按文档操作。你主要提供创作要求、查看结果并作出选择；想直接操作时，也可以使用 CLI。应用当前的 AI 执行方式及兼容条件见 [Codex 支持](docs/codex-support.md#中文)。

</details>

<details>
<summary><strong>稿件会上传或共享给开发者吗？</strong></summary>

应用将创作数据保存在你指定的本地目录，不收集使用数据，也没有遥测、自动上传或网络同步。执行 AI 任务时，相关材料会通过 Codex 发送到其使用的模型服务。你的输入和创作结果归你所有。详见[隐私说明](docs/privacy.md#中文)。

</details>

<details>
<summary><strong>中断后能继续吗？如何备份？</strong></summary>

任务和章节流程会保存进度。中断后先让 Agent 查看已有状态与结果，再判断能否继续或完成本地恢复。备份需要在停止写入后保存项目配置和完整数据目录，具体步骤见[使用与恢复](docs/usage.md#中文)。

</details>

<details>
<summary><strong>支持哪些系统和模型？</strong></summary>

当前支持 Apple Silicon macOS、Python 3.12，以及[兼容列表中的 Codex CLI](docs/codex-support.md#中文)。模型需在你的 Codex 账号中可用，并由 Agent 为任务明确选择。应用不会自动沿用当前对话的模型设置。

</details>

## 文档

| 你想做什么 | 从这里开始 |
| --- | --- |
| 安装、下载或升级 | [安装](docs/install.md#中文) · [下载与升级](docs/release.md#中文) |
| 让 Agent 使用应用 | [Agent 使用说明](docs/agent-usage.md#中文) · [请求格式](docs/interface.md#中文) |
| 写作、续写与审读 | [写作任务](docs/tasks.md#中文) · [章节流程](docs/workflows.md#中文) · [审读意见](docs/review-decisions.md#中文) |
| 管理材料、设定与技法 | [创作记录](docs/records.md#中文) · [人物与设定](docs/story-state.md#中文) · [上下文](docs/story-context.md#中文) · [技法](docs/techniques.md#中文) · [角色行动](docs/world.md#中文) |
| 处理问题或恢复数据 | [使用与恢复](docs/usage.md#中文) · [诊断](docs/diagnostics.md#中文) · [Codex 支持](docs/codex-support.md#中文) |

## 反馈与许可

问题和建议请提交到 [GitHub Issues](https://github.com/Bean2B/writing-assistant/issues)，附上版本与简短复现步骤，避免包含稿件、私人资料或凭据。PR 目前仅用于开发者维护。版本说明见 [Changelog](CHANGELOG.md#中文)。

本项目由 **Codex 开发**，采用 [Apache-2.0](LICENSE) 许可证。Copyright 2026 Bean2B。软件许可证不适用于你的创作内容。

<a id="english"></a>

[Read the English README →](docs/en/README.md)
