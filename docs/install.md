# 安装 / Installation

[中文首页](../README.md) · [English home](en/README.md) · [中文](#中文) · [English](#english)

## 中文

安装 **Writing Assistant v0.1.1**，创建本地写作项目，再让 Agent 按[使用说明](agent-usage.md#中文)操作。

[运行要求](#运行要求) · [交给 Codex 安装](#推荐交给-codex-安装) · [自行安装](#自行安装) · [更新与备份](#更新与备份)

### 运行要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Apple Silicon macOS |
| Python | Python 3.12，包含 `venv` 和 `pip` |
| AI 写作 | 另行安装并登录受支持的 Codex CLI；[查看具体版本](codex-support.md) |

应用本身没有第三方 Python runtime 依赖。安装和本地记录操作不调用模型；AI 任务才通过 Codex 使用网络服务。

### 推荐：交给 Codex 安装

把下面的要求交给 Codex，并指定你希望使用的目录：

> 请按本页安装 Writing Assistant。先检查运行环境与已有安装，保留已有项目；确认目录后，下载并校验发行包，完成安装和本地环境检查。最后给我应用路径、项目路径、数据路径，以及开始创作的方法。

Agent 可按下方完整步骤执行。已有项目保留并复用；完成后从 [Agent 使用说明](agent-usage.md#中文)继续。

### 自行安装

**1. 在单独的目录中下载、校验和安装。** 先进入你选定的写作工作目录，例如新建的 `writing-workspace`。下方命令要求该目录中还没有 `.venv`；中途失败会停止安装。

```sh
(
  set -eu
  test ! -e .venv || { printf '%s\n' 'An installation already exists at .venv; inspect it before continuing.' >&2; exit 1; }
  mkdir -p downloads
  curl -fL https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl -o downloads/writing_assistant-0.1.1-py3-none-any.whl
  curl -fL https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/SHA256SUMS -o downloads/SHA256SUMS
  python3.12 - <<'VERIFY'
from pathlib import Path
import hashlib
wheel = Path("downloads/writing_assistant-0.1.1-py3-none-any.whl")
entries = [line.split() for line in Path("downloads/SHA256SUMS").read_text().splitlines()]
expected = [entry[0] for entry in entries if len(entry) == 2 and entry[1] == wheel.name]
if len(expected) != 1 or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected[0]:
    raise SystemExit("SHA-256 verification failed; installation stopped")
print("SHA-256 verified")
VERIFY
  python3.12 -m venv .venv
  .venv/bin/python -m pip install --no-index --no-deps downloads/writing_assistant-0.1.1-py3-none-any.whl
  .venv/bin/writing-assistant --version
)
```

**2. 初始化新项目。** 仍在同一目录执行：

```sh
source .venv/bin/activate
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant config --project ../demo-project
writing-assistant capabilities --project ../demo-project
```

`demo-project` 保存配置，`demo-data` 保存稿件和运行记录；两者都在安装目录之外。示例 ID `demo` 与随源码提供的示例请求一致。可以选择其他路径和 ID，后续请求需使用对应值。已有项目只需查询 `config`，不要重复执行 `init`。

**3. 检查 AI 接入。**

```sh
writing-assistant doctor
```

`doctor` 不调用模型。`live_supported: true` 表示本机 CLI 符合接入要求，`runtime_readiness: not_checked` 表示没有发送真实 AI 请求。检查未通过时，本地记录仍可使用；按 [Codex 支持](codex-support.md)处理缺失条件。

安装完成后，从[保存一条灵感](records.md)或 [Agent 接入](agent-usage.md)开始。新终端中需再次激活 `.venv`，也可以使用安装时得到的 CLI 完整路径。

<details>
<summary><strong>从源码使用</strong></summary>


在本 repo 的源码目录中，可以直接运行：

```sh
PYTHONPATH=src python3.12 -B -m writing_assistant capabilities
```

需要构建本地 wheel 时，在没有既有 `.venv` 的源码目录执行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip wheel --no-index --no-deps --no-build-isolation . -w dist
.venv/bin/python -m pip install --no-index --no-deps dist/writing_assistant-0.1.1-py3-none-any.whl
```

上手文档中的 `writing-assistant` 可以替换为 `.venv/bin/writing-assistant`。源码方式使用 repo 内的 `examples/synthetic/`；从 wheel 安装后，可按[请求格式](interface.md)创建自己的请求文件。

</details>

### 更新与备份

已有安装请先阅读[下载与升级](release.md)。替换软件前，停止写入并备份项目配置与完整数据目录。不要把创作数据放进安装环境，也不要在项目配置中填写 Codex 登录凭据。

## English

Install **Writing Assistant v0.1.1**, create a local writing project, then give your Agent the [usage guide](agent-usage.md#english).

[Requirements](#requirements) · [Ask Codex to install](#recommended-ask-codex-to-install) · [Manual installation](#manual-installation) · [Updates and backups](#updates-and-backups)

### Requirements

| Component | Requirement |
| --- | --- |
| Operating system | Apple Silicon macOS |
| Python | Python 3.12 with `venv` and `pip` |
| AI writing | A separately installed, signed-in, supported Codex CLI; [accepted versions](codex-support.md#english) |

The application has no third-party Python runtime dependencies. Installation and local record operations do not call a model. AI tasks use Codex's network service.

### Recommended: ask Codex to install

Give Codex this request and specify your preferred directories:

> Install Writing Assistant using this page. Check compatibility and existing installations first, and preserve existing projects. Once the directories are agreed, download and verify the release package, install it and run the local environment check. Report the executable, project and data paths, and explain how to begin writing.

The complete steps are below for the Agent to follow. Preserve and reuse existing projects, then continue with the [Agent guide](agent-usage.md#english).

### Manual installation

**1. Download, verify and install in a separate directory.** Start in your chosen writing workspace, such as a new `writing-workspace` directory. The following block requires that `.venv` does not exist there and stops on failure.

```sh
(
  set -eu
  test ! -e .venv || { printf '%s\n' 'An installation already exists at .venv; inspect it before continuing.' >&2; exit 1; }
  mkdir -p downloads
  curl -fL https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl -o downloads/writing_assistant-0.1.1-py3-none-any.whl
  curl -fL https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/SHA256SUMS -o downloads/SHA256SUMS
  python3.12 - <<'VERIFY'
from pathlib import Path
import hashlib
wheel = Path("downloads/writing_assistant-0.1.1-py3-none-any.whl")
entries = [line.split() for line in Path("downloads/SHA256SUMS").read_text().splitlines()]
expected = [entry[0] for entry in entries if len(entry) == 2 and entry[1] == wheel.name]
if len(expected) != 1 or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected[0]:
    raise SystemExit("SHA-256 verification failed; installation stopped")
print("SHA-256 verified")
VERIFY
  python3.12 -m venv .venv
  .venv/bin/python -m pip install --no-index --no-deps downloads/writing_assistant-0.1.1-py3-none-any.whl
  .venv/bin/writing-assistant --version
)
```

**2. Initialize a new project.** Run from the same directory:

```sh
source .venv/bin/activate
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant config --project ../demo-project
writing-assistant capabilities --project ../demo-project
```

`demo-project` holds configuration; `demo-data` holds manuscripts and run records. Both sit outside the installation directory. Project ID `demo` matches the bundled source examples. You may choose other paths and an ID, then use that ID in requests. For an existing project, inspect `config` instead of running `init` again.

**3. Check the AI integration.**

```sh
writing-assistant doctor
```

`doctor` does not call a model. `live_supported: true` means the local CLI meets integration requirements. `runtime_readiness: not_checked` means no live AI request was sent. Local record operations remain available if this check fails; see [Codex support](codex-support.md#english) for missing requirements.

Continue with [saving an idea](records.md#english) or [Agent usage](agent-usage.md#english). In a new terminal, activate `.venv` again or use the full installed CLI path.

<details>
<summary><strong>Run from source</strong></summary>


From the repository's source directory:

```sh
PYTHONPATH=src python3.12 -B -m writing_assistant capabilities
```

To build a local wheel, run from a source directory without an existing `.venv`:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip wheel --no-index --no-deps --no-build-isolation . -w dist
.venv/bin/python -m pip install --no-index --no-deps dist/writing_assistant-0.1.1-py3-none-any.whl
```

Replace `writing-assistant` in the guides with `.venv/bin/writing-assistant`. Source usage provides `examples/synthetic/`; after a wheel installation, create a request using the [request format](interface.md#english).

</details>

### Updates and backups

For an existing installation, read [Downloads and upgrades](release.md#english). Stop writes and back up project configuration and the complete data directory before replacing the software. Keep writing outside the installation environment, and keep Codex credentials out of project configuration.
