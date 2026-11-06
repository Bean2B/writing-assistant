# 下载与版本说明 / Downloads and version information

[中文](#中文) · [English](#english)

## 中文

可以把 [v0.1.1 release 页面](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1)交给 Codex 并要求安装，或按[完整安装指南](install.md)自行操作。指南包括环境检查、下载校验、安装、项目初始化和安装后的检查。

这份源码对应 **0.1.1**。可下载的版本以
[Releases](https://github.com/Bean2B/writing-assistant/releases) 中实际列出的文件为准，
安装时请核对下载文件的版本。
应用、内置技法包和 schema 的版本分别管理，见[版本号规则](versioning.md)。

如果已取得 0.1.1 wheel，可用 Python 3.12 为 Agent 创建本地执行环境并安装：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps writing_assistant-0.1.1-py3-none-any.whl
```

从源码构建的方法
见 [README](../README.md#中文)。创作内容应保存在独立的数据目录，替换已安装版本前
先备份该目录。安装不会移动或自动采用你的创作内容。

分发内容包含应用、内置技法包、必要的接口与使用说明、许可和虚构示例，不包含个人数据、创作数据、凭据、
个人设置或本地运行记录，详见[隐私说明](privacy.md)。项目采用
[Apache-2.0](../LICENSE)，Copyright 2026 Bean2B；外部工具保留各自条款，见
[第三方声明](../THIRD_PARTY_NOTICES.md)。

Agent 通过本地 CLI 调用应用，详见 [Agent 接入说明](agent-usage.md)。
平台与 Codex CLI 要求见 [Codex 支持](codex-support.md)。问题反馈请在
[Issues](https://github.com/Bean2B/writing-assistant/issues) 提供虚构例子。PR 仅用于开发者维护。

## English

Give Codex the [v0.1.1 release page](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1) and request installation, or follow the [complete installation guide](install.md#english) yourself. It includes environment checks, download verification, installation, project initialization and post-install checks.

This source tree describes version **0.1.1**.
Application, technique pack and schema versions follow the [versioning rules](versioning.md).
Check [Releases](https://github.com/Bean2B/writing-assistant/releases)
for available downloads; use the version shown on the asset you download.

Install a supplied 0.1.1 wheel in the Agent's local execution environment with Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps writing_assistant-0.1.1-py3-none-any.whl
```

To build from source, follow the [README](../README.md). Keep your writing in a
separate data directory and back up that directory before replacing an installed
version. Installation does not move or adopt your writing.

The distribution contains the application, built-in technique packs, required interface instructions, licenses,
and fictional examples. It does not contain personal or creative data, credentials,
personal settings, or local execution records. See [privacy](privacy.md).
The project uses [Apache-2.0](../LICENSE), Copyright 2026 Bean2B; external tools
retain their own terms in [third-party notices](../THIRD_PARTY_NOTICES.md).

The local CLI is the Agent's calling interface; see [Agent usage](agent-usage.md).
For the current platform and Codex CLI requirements, see
[Codex support](codex-support.md). Report problems with a fictional example in
[Issues](https://github.com/Bean2B/writing-assistant/issues). Pull requests are
reserved for developer maintenance.
