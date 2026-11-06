# 安装指南 / Installation

[中文](#中文) · [English](#english)

## 中文

本页对应 **Writing Assistant v0.1.1**，提供 Codex 代为安装和用户自主安装两条路径。应用的命令名是 `writing-assistant`。安装与初始化不调用写作模型，也不自动采用创作内容。

### 交给 Codex 安装

使用者可以把 [v0.1.1 release](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1) 页面交给 Codex，并要求安装。Codex 应读取本页和 [Agent 接入说明](agent-usage.md)，按以下步骤完成这次安装任务：

1. 检查当前执行环境是否为 Apple Silicon macOS，以及可用的 Python 是否为 3.12。检查既有 `writing-assistant`、目标安装目录、项目配置与数据目录；已存在时先读取版本和配置，保留已有数据。只在需要选择新的工作区或数据位置、且无法从当前任务判断时询问使用者。
2. 使用下面的固定版本下载地址取得 wheel 和 `SHA256SUMS`，核对 wheel 的 SHA-256 后再安装。校验失败即停止，保留失败文件和错误；不改用其他版本或来源。
3. 在当前写作工作区的独立 virtual environment 中安装 wheel，使用 `--no-index --no-deps`。下方命令提供默认目录；使用者已指定路径时遵循其选择。不要把创作数据放进安装目录。
4. 运行 `writing-assistant --version` 和 `capabilities`。运行 `doctor` 检查既有 Codex CLI 的本地资格，按 [Codex 支持](codex-support.md) 解释结果。应用不附带 Python、Codex 或登录凭据。缺少 Python、受支持的 Codex CLI 或登录时，完成仍可执行的安装工作，明确指出尚缺条件；不要声称 AI 已可用，也不要为安装改写全局 Codex 配置、登录资料或调用方 Agent 的设置。
5. 初始化使用者指定的项目和独立数据目录；未指定时可在当前工作区使用下方的 `writing-project`、`writing-data` 与 `my-writing`。若这些路径已有项目或数据，先读取配置并复用匹配项目，避免覆盖或重新初始化。读回 `config` 和项目 `capabilities`。
6. 返回应用版本、准确 CLI 路径、项目目录、数据目录、已完成检查及任何未满足的 Codex 条件。保留这组路径供后续使用，并读取 [Agent 接入说明](agent-usage.md) 了解记录、task、workflow 和恢复。安装任务本身不发起 AI 写作；只有使用者另有写作授权时才准备和执行对应任务。

`doctor` 不调用模型。它的 `runtime_readiness: not_checked` 表示未验证实际 AI 请求；`live_supported` 只说明本地资格。安装完成、项目初始化和实际 AI 生成是不同的结果，应分别报告。

### 自主安装：下载、校验并安装

先准备带 `venv` 和 `pip` 的 Python 3.12。以下命令适用于 Apple Silicon macOS，在你选择的写作工作区执行。整个命令块在 subshell 内运行，任一步失败即停止；它不会覆盖已有的同版本安装目录。需要更新或复用安装时，先核对现有版本和路径。

```sh
(
  set -eu
  python3.12 - <<'PY'
import platform
import sys
if platform.system() != "Darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Requires Apple Silicon macOS and Python 3.12")
print("Platform and Python version are supported")
PY

  WA_ROOT="$PWD/.writing-assistant"
  WA_DOWNLOADS="$WA_ROOT/downloads/0.1.1"
  WA_ENV="$WA_ROOT/venvs/0.1.1"
  if [ -e "$WA_ENV" ]; then
    printf '%s\n' 'Installation directory exists; inspect it before reuse.' >&2
    exit 1
  fi
  mkdir -p "$WA_DOWNLOADS"
  curl -fL 'https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl' -o "$WA_DOWNLOADS/writing_assistant-0.1.1-py3-none-any.whl"
  curl -fL 'https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/SHA256SUMS' -o "$WA_DOWNLOADS/SHA256SUMS"
  python3.12 - "$WA_DOWNLOADS" <<'PY'
from pathlib import Path
import hashlib
import sys
directory = Path(sys.argv[1])
wheel = directory / "writing_assistant-0.1.1-py3-none-any.whl"
entries = [line.split() for line in (directory / "SHA256SUMS").read_text().splitlines() if line.strip()]
matches = [entry[0] for entry in entries if len(entry) == 2 and entry[1] == wheel.name]
actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
if len(matches) != 1 or actual != matches[0]:
    raise SystemExit("Wheel SHA-256 verification failed; installation stopped")
print("Wheel SHA-256 verified")
PY
  python3.12 -m venv "$WA_ENV"
  "$WA_ENV/bin/python" -m pip install --no-index --no-deps "$WA_DOWNLOADS/writing_assistant-0.1.1-py3-none-any.whl"
  "$WA_ENV/bin/writing-assistant" --version
  "$WA_ENV/bin/writing-assistant" capabilities
)
```

在同一工作区检查 Codex 接入并初始化新的项目：

```sh
./.writing-assistant/venvs/0.1.1/bin/writing-assistant doctor
./.writing-assistant/venvs/0.1.1/bin/writing-assistant init --project ./writing-project --data-dir ./writing-data --project-id my-writing
./.writing-assistant/venvs/0.1.1/bin/writing-assistant config --project ./writing-project
./.writing-assistant/venvs/0.1.1/bin/writing-assistant capabilities --project ./writing-project
```

逐条执行并查看结果。`doctor` 不通过时，本地记录功能仍可使用；AI 任务要先满足 [Codex 支持](codex-support.md) 的要求。已有项目应直接读取配置，不重复 `init`。默认初始化选择 `lotus` 写作模式并启用 World Sandbox；它们是应用内部的可选写作能力，调用入口仍是 `writing-assistant`。需要 Direct Mode 时，在新项目的 `init` 命令中明确加入 `--writing-mode none --world-sandbox off`。

安装文件位于 `.writing-assistant/venvs/0.1.1`，下载文件位于 `.writing-assistant/downloads/0.1.1`；创作项目位于 `writing-project`，原文与记录位于 `writing-data`。移动、删除或替换安装环境前备份创作数据目录；软件安装不迁移或删除已有创作内容。保留实际选择的路径。

如何从源码构建见 [README](../README.md#中文)。开始记录和使用 AI 任务见 [Agent 接入说明](agent-usage.md)、[记录](records.md)与 [task](tasks.md)。AI 任务需要另行安装并登录受支持的 Codex CLI；凭据由 Codex 自身管理，不填写到 Writing Assistant 的项目配置或公开反馈中。

## English

This guide is for **Writing Assistant v0.1.1**. You may ask Codex to install it or install it yourself. The executable is `writing-assistant`. Installation and initialization do not call a writing model or adopt creative content.

### Installation by Codex

Give Codex the [v0.1.1 release](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1) page and request installation. Codex should read this guide and [Agent usage](agent-usage.md#english), then complete the following installation task:

1. Check for Apple Silicon macOS and Python 3.12. Inspect any existing `writing-assistant`, installation directory, project configuration and data directory. Read the current version and configuration before reusing them; preserve existing data. Ask about workspace or data location only when the current task does not resolve a necessary choice.
2. Download the wheel and `SHA256SUMS` from the fixed version URLs below. Verify the wheel SHA-256 before installation. On a mismatch, stop and retain the failed files and error; do not substitute another version or source.
3. Install the wheel in a separate virtual environment under the writing workspace, using `--no-index --no-deps`. Use the default paths below unless the user has specified others. Keep creative data outside the installation directory.
4. Run `writing-assistant --version` and `capabilities`. Use `doctor` to check the existing Codex CLI's local qualification, and interpret it according to [Codex support](codex-support.md#english). Python, Codex and credentials are not bundled. If Python, a supported Codex CLI or sign-in is missing, finish the installation work that remains possible and report the missing conditions. Do not claim AI readiness or rewrite global Codex configuration, sign-in data or the calling Agent's settings as part of installation.
5. Initialize the user's chosen project and separate data directory. Without a specified location, use `writing-project`, `writing-data` and `my-writing` in the current workspace as shown below. If project or data paths already exist, inspect configuration and reuse a matching project instead of overwriting or reinitializing it. Read back `config` and project `capabilities`.
6. Return the application version, exact executable path, project and data directories, completed checks and any unmet Codex conditions. Retain the selected paths for subsequent work and read [Agent usage](agent-usage.md#english) for records, tasks, workflows and recovery. Installation alone does not request AI writing; prepare and execute a writing task only when the user has authorized that work.

`doctor` does not call a model. `runtime_readiness: not_checked` means no actual AI request was verified; `live_supported` reports local qualification only. Report application installation, project initialization and actual AI generation as separate outcomes.

### Manual download, verification and installation

Prepare Python 3.12 with `venv` and `pip`. Run the following commands from your chosen writing workspace on Apple Silicon macOS. The block runs in a subshell and stops at the first failure. It refuses to overwrite an existing installation directory for this version; inspect an existing version and its paths before reuse or replacement.

```sh
(
  set -eu
  python3.12 - <<'PY'
import platform
import sys
if platform.system() != "Darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 12):
    raise SystemExit("Requires Apple Silicon macOS and Python 3.12")
print("Platform and Python version are supported")
PY

  WA_ROOT="$PWD/.writing-assistant"
  WA_DOWNLOADS="$WA_ROOT/downloads/0.1.1"
  WA_ENV="$WA_ROOT/venvs/0.1.1"
  if [ -e "$WA_ENV" ]; then
    printf '%s\n' 'Installation directory exists; inspect it before reuse.' >&2
    exit 1
  fi
  mkdir -p "$WA_DOWNLOADS"
  curl -fL 'https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl' -o "$WA_DOWNLOADS/writing_assistant-0.1.1-py3-none-any.whl"
  curl -fL 'https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/SHA256SUMS' -o "$WA_DOWNLOADS/SHA256SUMS"
  python3.12 - "$WA_DOWNLOADS" <<'PY'
from pathlib import Path
import hashlib
import sys
directory = Path(sys.argv[1])
wheel = directory / "writing_assistant-0.1.1-py3-none-any.whl"
entries = [line.split() for line in (directory / "SHA256SUMS").read_text().splitlines() if line.strip()]
matches = [entry[0] for entry in entries if len(entry) == 2 and entry[1] == wheel.name]
actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
if len(matches) != 1 or actual != matches[0]:
    raise SystemExit("Wheel SHA-256 verification failed; installation stopped")
print("Wheel SHA-256 verified")
PY
  python3.12 -m venv "$WA_ENV"
  "$WA_ENV/bin/python" -m pip install --no-index --no-deps "$WA_DOWNLOADS/writing_assistant-0.1.1-py3-none-any.whl"
  "$WA_ENV/bin/writing-assistant" --version
  "$WA_ENV/bin/writing-assistant" capabilities
)
```

In the same workspace, check the Codex integration and initialize a new project:

```sh
./.writing-assistant/venvs/0.1.1/bin/writing-assistant doctor
./.writing-assistant/venvs/0.1.1/bin/writing-assistant init --project ./writing-project --data-dir ./writing-data --project-id my-writing
./.writing-assistant/venvs/0.1.1/bin/writing-assistant config --project ./writing-project
./.writing-assistant/venvs/0.1.1/bin/writing-assistant capabilities --project ./writing-project
```

Run these commands individually and inspect each result. If `doctor` fails, local record operations remain available; AI tasks require the conditions in [Codex support](codex-support.md#english). Inspect existing project configuration instead of repeating `init`. Default initialization selects the `lotus` writing mode and enables World Sandbox, which are optional internal writing capabilities; the executable remains `writing-assistant`. For Direct Mode, explicitly add `--writing-mode none --world-sandbox off` to a new project's `init` command.

Installation files are under `.writing-assistant/venvs/0.1.1`, downloads under `.writing-assistant/downloads/0.1.1`, project configuration under `writing-project`, and original writing and records under `writing-data`. Back up creative data before moving, deleting or replacing an installation. Software installation does not migrate or delete existing writing. Retain the actual paths selected.

See [README](../README.md#english) to build from source. Continue with [Agent usage](agent-usage.md#english), [records](records.md#english) and [tasks](tasks.md#english). AI tasks require a separately installed and signed-in, supported Codex CLI. Codex manages its own credentials; do not put them in Writing Assistant project configuration or public feedback.
