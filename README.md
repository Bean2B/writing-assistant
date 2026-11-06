# Writing Assistant

**面向 Agent 的 AI 写作助手，由 Codex 开发。**

[中文](#中文) · [English](#english) · [下载 v0.1.1](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1) · [安装指南](docs/install.md) · [Agent 接入](docs/agent-usage.md)

## 中文

让 Agent 围绕同一写作项目持续工作：保存灵感与草稿、管理设定与写作材料、构思情节、撰写章节、审读和修订。
Writing Assistant 在本地管理这些内容及任务进度，Agent 通过 CLI 使用应用，你决定创作方向和最终采用的内容。

### 主要功能

| 功能 | 可以做什么 |
| --- | --- |
| **构思与写作** | 根据你的要求生成构思候选、场景规划与正文，对指定稿件提出反馈或进行修订。 |
| **章节流程** | 按章节组织规划、写作和审读；保存每一步的输入、结果与进度，便于中断后接续。 |
| **创作资料库** | 保存灵感、设定与草稿；搜索内容、查看历史版本，用书签定位需要接续的稿件。 |
| **Story state 与写作上下文** | 记录人物知道什么、身处何地、关系如何变化，为当前任务选择相关材料。 |
| **写作技法包** | 为任务选择内置技法，辅助处理人物选择、情节因果、后果与细节呼应。 |
| **角色行动推演** | 请求角色决策，推进场景内日程与状态，将选定的角色可见信息保存为写作材料。 |

应用负责保存记录、关联版本和安排章节阶段；Agent 负责选择材料并执行当前任务。生成文本保留为候选稿件，由你决定是否采用。

### 开始使用

**运行要求：Apple Silicon Mac、Python 3.12。** AI 写作另需已登录的受支持 Codex CLI；具体版本见 [Codex 支持](docs/codex-support.md)。保存、检索和整理记录可以离线使用。

你可以把下面这段话交给 Codex：

> 请按照 https://github.com/Bean2B/writing-assistant/blob/main/docs/install.md 安装 Writing Assistant，检查运行环境，并为我建立独立的创作项目和数据目录。已有项目请先检查并保留。

也可以按[安装指南](docs/install.md)自行安装。安装完成后，Agent 可以先保存一个虚构灵感：

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
printf '%s\n' '故事点子：一封没有署名的信。' > ../demo-project/idea.txt
writing-assistant records --project ../demo-project save ../demo-project/idea.txt --operation-id idea-001 --kind idea --title "信的点子"
writing-assistant records --project ../demo-project search 信
```

这组命令适用于新项目，不调用模型；已有项目直接使用原路径。示例假定已激活安装环境，或将 `writing-assistant` 替换为安装时得到的完整路径。随后可让 Agent 根据你的目标使用[写作任务](docs/tasks.md)或[章节流程](docs/workflows.md)。

### 文档

| 我想了解… | 阅读 |
| --- | --- |
| 安装、下载或升级 | [安装指南](docs/install.md) · [下载说明](docs/release.md) |
| 让 Agent 接入应用 | [Agent 接入](docs/agent-usage.md) · [CLI 使用](docs/usage.md) · [请求格式](docs/interface.md) |
| 写作、审读与修订 | [写作任务](docs/tasks.md) · [章节流程](docs/workflows.md) · [审读意见](docs/review-decisions.md) |
| 管理设定与资料 | [创作记录](docs/records.md) · [Story state](docs/story-state.md) · [上下文](docs/story-context.md) · [角色行动推演](docs/world.md) |
| 选择和使用技法 | [技法包](docs/techniques.md) |
| 兼容性、消耗与故障恢复 | [Codex 支持](docs/codex-support.md) · [诊断](docs/diagnostics.md) · [版本记录](CHANGELOG.md) |

### 数据与许可

创作数据保存在你选择的本地目录。项目和开发者不收集使用数据，应用没有遥测、自动上传或网络同步。明确执行 AI 任务时，相关材料会通过 Codex 发送给其服务；Codex 也可能加载本机全局指令。详见[隐私说明](docs/privacy.md)。

你的输入和创作结果归你所有。软件采用 [Apache-2.0](LICENSE)，Copyright 2026 Bean2B；软件许可证不适用于你的创作内容。

问题与建议请使用 [Issues](https://github.com/Bean2B/writing-assistant/issues)，并提供不含私人内容的简短例子。PR 目前仅用于开发者维护。

## English

**An AI writing assistant for Agents, developed by Codex.**

Give an Agent a place to manage a writing project over time: collect ideas and drafts, organize settings and source material, plan scenes, write chapters, review and revise. Writing Assistant manages the material and task progress locally. Agents use its CLI; you choose the creative direction and the results to keep.

### Features

| Feature | What it does |
| --- | --- |
| **Concepts and writing** | Develop an initial idea, generate scenes and prose, request feedback, and revise a selected draft. |
| **Chapter workflows** | Organize planning, drafting and review by chapter, with saved inputs, results and progress for resuming interrupted work. |
| **Creative records** | Save ideas, settings and drafts; search text, inspect earlier versions and bookmark a draft to continue. |
| **Story state and context** | Track character knowledge, locations and relationships, and select relevant material for the current task. |
| **Technique packs** | Select built-in guidance for character choices, causal structure, consequences and recurring details. |
| **Character action simulation** | Request character decisions, advance schedules and state, and save selected character-visible information as writing material. |

The application stores records, binds versions and orders chapter phases. The Agent selects material and executes the current task. Generated prose remains a candidate for you to review and adopt.

### Getting started

**Requires Apple Silicon macOS and Python 3.12.** AI writing also requires a signed-in, supported Codex CLI; see [Codex support](docs/codex-support.md#english) for accepted versions. Saving, searching and organizing records work offline.

You can give Codex this request:

> Install Writing Assistant using https://github.com/Bean2B/writing-assistant/blob/main/docs/install.md#english. Check the environment and create a separate writing project and data directory. Inspect and preserve any existing project first.

Or follow the [installation guide](docs/install.md#english) yourself. Once installed, the Agent can save a fictional idea:

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
printf '%s\n' 'Story idea: a letter with no signature.' > ../demo-project/idea.txt
writing-assistant records --project ../demo-project save ../demo-project/idea.txt --operation-id idea-001 --kind idea --title "Letter idea"
writing-assistant records --project ../demo-project search letter --ignore-case
```

These commands create a new project without calling a model. Use the existing path for an existing project. Activate the installation environment first, or replace `writing-assistant` with its full installed path. Continue with [writing tasks](docs/tasks.md#english) or [chapter workflows](docs/workflows.md#english) for your creative goal.

### Documentation

| Topic | Guides |
| --- | --- |
| Installation, downloads and upgrades | [Install](docs/install.md#english) · [Downloads](docs/release.md#english) |
| Agent integration | [Agent usage](docs/agent-usage.md#english) · [CLI usage](docs/usage.md#english) · [Request format](docs/interface.md#english) |
| Writing, review and revision | [Tasks](docs/tasks.md#english) · [Workflows](docs/workflows.md#english) · [Review decisions](docs/review-decisions.md#english) |
| Settings and writing material | [Records](docs/records.md#english) · [Story state](docs/story-state.md#english) · [Context](docs/story-context.md#english) · [Character actions](docs/world.md#english) |
| Technique packs | [Select and use packs](docs/techniques.md#english) |
| Compatibility, usage and recovery | [Codex support](docs/codex-support.md#english) · [Diagnostics](docs/diagnostics.md#english) · [Changelog](CHANGELOG.md#english) |

### Data and license

Your writing is stored in a local directory you choose. The project and its developers do not collect usage data. The application has no telemetry, automatic uploads or network synchronization. Explicit AI tasks send relevant material through Codex to its service; Codex may also load local global instructions. See [Privacy](docs/privacy.md#english).

Your inputs and creative results remain yours. The software is licensed under [Apache-2.0](LICENSE), Copyright 2026 Bean2B. The software license does not license your writing.

Report problems or suggestions in [Issues](https://github.com/Bean2B/writing-assistant/issues) with a short example containing no private material. Pull requests are currently reserved for developer maintenance.
