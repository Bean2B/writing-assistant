# Writing Assistant

[中文](#中文) · [English](#english)

## 中文

写作助手是一款由 AI 驱动、由 **Codex 开发**的写作应用，主要操作者是 **Agent**，
最终服务于人类 user 的创作目标。应用是 Agent 完成这些工作的工具：user 提供目标和授权，
拥有自己的数据，并决定采用哪些结果。

Agent 操作创作记录、写作任务、章节 workflow 和故事处境：选择获准使用的材料与准确版本，
提供 user 的目标，并处理返回结果。应用保存 workflow 的阶段顺序、task 依赖和中断后的进度。

应用在本地运行，支持 Apple Silicon Mac 和 Python 3.12。当前调用接口是本地 CLI，
通过请求文件和结构化结果交互。调用它的 Agent 需要能够执行本地进程，并访问获准使用的
项目文件。AI 功能需要另行安装受支持的 Codex CLI；保存和检索记录不调用模型。

### 提供给 Agent 的能力

- **创作记录。** 保存灵感、场景、设定和草稿，保留原文字节及版本历史。
- **选定上下文。** 检索记录，为准确的草稿版本设置书签，准备任务所需的片段、
  创作决定和问题。
- **Codex 写作。** 通过结构化请求文件生成正文、明确发起修改，或审读选定稿件。
- **章节 workflow。** 一次给定目标和范围，依次准备规划、写作和独立审读任务，保存章节目的、准确材料、审读证据和反馈选择，并按明确策略控制暂停或有限修改。
- **故事状态。** 用有版本的记录保存人物知识、时间、地点、代价、关系和待决选择，保留准确证据与 proposal 状态。
- **写作 techniques。** 发现并明确选择有版本的指导，并根据明确的任务和故事标签检查有上限的适用建议。
- **故事推演。** 从给定处境出发，探索人物可能采取的行动及其后果，保留选定的创作材料。

调用方 Agent 在 user 的授权范围内检查并明确执行 workflow 准备的任务。准备材料、
执行 AI 请求和采用结果是不同的动作。单项写作任务仍可单独使用；workflow 只准备选定的阶段。

### 配置 Agent 的执行环境

把 [v0.1.1 release 页面](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1)交给 Codex 并要求安装，Codex 可按[完整安装指南](docs/install.md)检查环境、下载与校验 wheel、安装、初始化项目并读回配置。该指南也提供用户自主安装的完整命令。以下说明保留源码构建与基本使用入口。

需要预先安装带有 `venv` 和 `pip` 的 Python 3.12。应用本身没有第三方 Python 依赖。
从源码目录执行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip wheel --no-index --no-deps --no-build-isolation . -w dist
.venv/bin/python -m pip install --no-index --no-deps dist/writing_assistant-0.1.1-py3-none-any.whl
```

也可以直接从源码目录调用，无须先安装 package：

```sh
PYTHONPATH=src python3.12 -B -m writing_assistant capabilities
```

从源码运行下方示例时，用这条 module 调用替换 `.venv/bin/writing-assistant`。

Agent 初始化项目，并为创作内容指定独立的数据目录：

```sh
.venv/bin/writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
```

以下调用保存并检索一条虚构灵感：

```sh
printf '%s\n' '故事点子：一封没有署名的信。' > ../demo-project/idea.txt
.venv/bin/writing-assistant records --project ../demo-project save ../demo-project/idea.txt --operation-id idea-001 --kind idea --title "信的点子"
.venv/bin/writing-assistant records --project ../demo-project search 信
```

保存的内容位于 `../demo-data`，与源码和安装环境分开。
如何修订、查看历史和设置书签，见[创作记录](docs/records.md)。
下载信息见[版本说明](docs/release.md)，应用、技法包和 schema 的版本分别管理，见[版本号规则](docs/versioning.md)。

#### 调用 AI 写作

AI 功能使用本机已登录的 Codex CLI。先检查版本是否受支持：

```sh
.venv/bin/writing-assistant doctor
```

项目附带一个只要求写一句话的示例。Agent 可以先查看准备交给模型的材料：

```sh
.venv/bin/writing-assistant prepare --project ../demo-project examples/synthetic/request.json
```

`prepare` 离线运行。在已获授权的 AI 任务中，Agent 用下面的命令发起请求并保存结果：

```sh
.venv/bin/writing-assistant execute --project ../demo-project --model gpt-6.1-sol examples/synthetic/request.json
```

最后这条命令会通过 Codex 调用 AI。Agent 为新任务设置 `request`，并使用新的 `request_id`。
命令结果、主动执行和请求中断后的处理方法见 [Agent 接入说明](docs/agent-usage.md)。

### 你的创作和数据

你输入的内容，以及使用工具产生的草稿、生成文本、记录和本地诊断信息，都归你所有。
使用本工具不代表允许项目或开发者收集、使用、再分发这些内容。软件许可证也不适用于
你的创作内容。

项目及开发者不收集你的使用数据；应用不自动上传数据或诊断信息，也不提供网络共享或同步。
只有 Agent 代表你明确发起 AI 任务时，才会把该任务和必要的获准材料交给 Codex，
由它使用既有服务完成请求。
这部分需要联网，并受该服务自身条款约束。详见[隐私说明](docs/privacy.md)。

### 兼容范围与文档

支持的 AI 接入方式是 Codex。支持的环境和允许使用的 CLI 版本见
[Codex 支持](docs/codex-support.md)；其他操作系统、CLI 版本和接入方式不在支持范围内。
写作效果会受任务、材料和模型影响，生成结果需要你审读和取舍。

- [Agent 接入说明](docs/agent-usage.md)
- [章节 workflow](docs/workflows.md)
- [写作 techniques 与 pack 扩展](docs/techniques.md)
- [CLI 操作与恢复](docs/usage.md)
- [保存、检索与接续草稿](docs/records.md)
- [推进故事](docs/world.md)
- [请求格式](docs/interface.md)
- [版本记录](CHANGELOG.md)

### 反馈与许可

遇到问题或有改进建议，可以到 [Issues](https://github.com/Bean2B/writing-assistant/issues)
说明。请用简短的虚构例子复现，避免附上真实稿件、凭据或私人日志。公开 repo 不接收 PR。
另见[安全说明](SECURITY.md)和[行为准则](CODE_OF_CONDUCT.md)。

采用 [Apache-2.0](LICENSE)，Copyright 2026 Bean2B。
适用范围和外部工具信息见[许可状态](LICENSE-STATUS.md)与[第三方声明](THIRD_PARTY_NOTICES.md)。

## English

Give Codex the [v0.1.1 release page](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1) and request installation. The [complete installation guide](docs/install.md#english) covers environment checks, versioned downloads, SHA-256 verification, installation, project initialization and configuration readback. It also provides the full manual installation commands.

Writing Assistant is an AI-powered writing application developed by **Codex**.
Its primary operator is an **Agent**, working toward a human user's creative
goals. The application is a tool in that work: the user provides goals and
authorization, owns their data, and decides which results to adopt.

The Agent operates on creative records, writing tasks, chapter workflows and
story situations. It selects permitted material and exact versions, supplies
the user's goal and handles the returned outcome. The application keeps the
workflow's phase order, task dependencies and interruption recovery.

The application runs locally on macOS with Apple Silicon and Python 3.12.
Its current invocation interface is a local CLI with request files and structured
results. The calling Agent needs access to a local process runner and the
permitted project files. AI tasks use a separately installed, supported Codex CLI;
saving and searching records work without a model call.

### Capabilities available to Agents

- **Creative records.** Save ideas, scenes, settings, and drafts while preserving
  original bytes and version history.
- **Selected context.** Search records, bookmark an exact draft version, and
  prepare the passages, decisions, and questions selected for a task.
- **Codex writing.** Request prose, an explicit revision, or feedback on a
  selected draft through structured request files.
- **Chapter workflows.** Create a bounded goal once, then advance through
  planning, drafting and independent evidence-linked review tasks with saved
  purpose, exact context, explicit feedback choices and bounded material policy.
- **Story state.** Keep versioned character knowledge, time, location, costs,
  relationships and unresolved choices with exact evidence and proposal status.
- **Writing techniques.** Discover and explicitly select versioned guidance
  for task dependencies, character choices, state, outcomes and recurring details;
  inspect bounded applicability suggestions from explicit task and story tags.
- **Story development.** Explore character actions and their consequences from
  a defined situation, and retain selected material for writing.

The calling Agent inspects and explicitly executes the tasks prepared by a
workflow within the user's authorization. Preparing context, executing an AI
request, and adopting the result are separate actions. Individual writing tasks
remain available; a workflow prepares only its explicitly selected stages.

### Set up the Agent's execution environment

Install Python 3.12 with `venv` and `pip`. The package itself has no third-party
Python dependencies. From the source directory:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip wheel --no-index --no-deps --no-build-isolation . -w dist
.venv/bin/python -m pip install --no-index --no-deps dist/writing_assistant-0.1.1-py3-none-any.whl
```

For direct source invocation from the checkout root, no package installation is needed:

```sh
PYTHONPATH=src python3.12 -B -m writing_assistant capabilities
```

Use this module invocation in place of `.venv/bin/writing-assistant` in the
examples when running from source.

The Agent initializes a project with a separate directory for creative data:

```sh
.venv/bin/writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
```

The following calls save and search a fictional idea:

```sh
printf '%s\n' 'Story idea: a letter with no signature.' > ../demo-project/idea.txt
.venv/bin/writing-assistant records --project ../demo-project save ../demo-project/idea.txt --operation-id idea-001 --kind idea --title "Letter idea"
.venv/bin/writing-assistant records --project ../demo-project search letter --ignore-case
```

Saved writing lives in `../demo-data`, outside the source and installation.
See [saving and finding your writing](docs/records.md) for revisions, history,
and bookmarks. Download information is in [version information](docs/release.md).

#### Invoke an AI writing task

AI features require a supported Codex CLI with its existing sign-in. Check
compatibility first:

```sh
.venv/bin/writing-assistant doctor
```

The included example asks for one sentence about a brass bell. The Agent can
inspect its prepared input before sending it:

```sh
.venv/bin/writing-assistant prepare --project ../demo-project examples/synthetic/request.json
```

`prepare` works offline. To send the example to Codex and save the result:

```sh
.venv/bin/writing-assistant execute --project ../demo-project --model gpt-6.1-sol examples/synthetic/request.json
```

This last command makes an AI request through Codex. For another task, the Agent
sets `request` and uses a new `request_id`. The [Agent interface guide](docs/agent-usage.md)
describes command results, explicit execution, and handling interrupted requests.

### Your writing and data

Your inputs, drafts, generated text, records, and local diagnostics remain yours.
Using the tool gives the project and its developers no permission to collect,
use, or redistribute them. The software license does not license your writing.

The project and its developers do not collect your usage data. The tool does not
automatically upload data or diagnostics, or provide network sharing or
synchronization. When an Agent explicitly starts an AI task on your behalf, it
sends the task and the necessary permitted material to Codex, which uses its existing service.
That part requires a network connection and is subject to the service's own
terms. See [privacy](docs/privacy.md).

### Compatibility and documentation

Codex is the supported AI integration. The supported environment and accepted CLI
versions are listed in [Codex support](docs/codex-support.md). Other operating
systems, CLI builds, and integrations are outside this support scope. Writing quality
still depends on the task, material, and model; review a result before using it.

- [Agent interface guide](docs/agent-usage.md)
- [Durable chapter workflows](docs/workflows.md)
- [Writing techniques and pack extensions](docs/techniques.md)
- [CLI operations and recovery](docs/usage.md)
- [Saving, searching, and continuing drafts](docs/records.md)
- [Developing a story](docs/world.md)
- [Request format](docs/interface.md)
- [Version history](CHANGELOG.md)

### Feedback and license

Report problems or suggest improvements in
[Issues](https://github.com/Bean2B/writing-assistant/issues). A small made-up
example is most useful; please leave out manuscripts, credentials, and private
logs. This public repository does not accept PRs. See the [security guidance](SECURITY.md) and
[code of conduct](CODE_OF_CONDUCT.md).

[Apache-2.0](LICENSE). Copyright 2026 Bean2B. See
[license status](LICENSE-STATUS.md) and [third-party notices](THIRD_PARTY_NOTICES.md)
for scope and external tool information.
