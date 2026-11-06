# 依赖与声明 / Dependencies and notices

[中文](#中文) · [English](#english)

## 中文

写作助手是供 Agent 使用的应用，使用 Python 标准库，没有第三方 Python runtime 依赖。安装包不附带 Python、
pip、Codex 或 Codex 登录数据。Python 3.12 用于运行工具及本地构建；pip 用于按 README
中的命令构建和安装；另行安装的 Codex CLI 用于 AI 任务，版本要求见
[Codex 支持](docs/codex-support.md)。

这些外部工具及服务保留各自的许可证和条款。项目的 [Apache-2.0 许可证](LICENSE)
不对它们或使用者的数据重新许可。

## English

Writing Assistant is an application for Agents. It uses the Python standard library and has no third-party
Python runtime dependencies. Its packages do not bundle Python, pip, Codex,
or Codex authentication data.

| External tool | Use |
| --- | --- |
| [Python](https://www.python.org/) | Python 3.12 runs the application and the local package build. |
| [pip](https://pip.pypa.io/) | Builds and installs a local package using the README commands. |
| Codex | Separately installed local CLI for AI tasks. See [supported versions](docs/codex-support.md). |

These external tools and services retain their own licenses and terms. The
project's [Apache-2.0 license](LICENSE) does not relicense them or the user's data.
