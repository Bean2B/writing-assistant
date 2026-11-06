# 下载与升级 / Downloads and upgrades

[中文](#中文) · [English](#english)

## 中文

当前公开版本：[Writing Assistant v0.1.1](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1)。主要功能见 [README](../README.md#中文)，完整操作见[安装指南](install.md)。

### 选择下载文件

| 文件 | 用途 |
| --- | --- |
| `writing_assistant-0.1.1-py3-none-any.whl` | 安装应用，推荐使用。 |
| `writing_assistant-0.1.1.tar.gz` | Python 源码分发包，供自行构建。 |
| `SHA256SUMS` | 校验以上两个文件的 SHA-256。 |
| GitHub 的 Source code 归档 | 查看 release tag 对应的源码。 |

运行环境为 Apple Silicon macOS 和 Python 3.12。AI 写作需要另行安装并登录受支持的 Codex CLI，详见[兼容要求](codex-support.md)。wheel 文件名中的 `any` 是 Python 打包标签，不代表支持所有操作系统。

### 更新已有安装

1. 停止正在写入的任务，按[备份与恢复](usage.md)保存项目配置和完整数据目录。
2. 阅读[版本记录](../CHANGELOG.md)和兼容说明。软件升级不会自动迁移旧数据。
3. 将新版本装入独立环境，保留旧安装。通过 `--version` 确认版本，再检查已有项目的配置。
4. 确认适用的操作与数据格式后，再让 Agent 继续任务。旧 World run 的限制见[角色行动推演](world.md)。

已发布的 tag 和安装包保持固定。GitHub 默认 branch 上的说明可能继续修正；安装包内附带的是发布时的文档。软件、技法包和数据格式的版本关系见[版本号规则](versioning.md)。

## English

Current public version: [Writing Assistant v0.1.1](https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1). See the [README](../README.md#english) for features and [Install](install.md#english) for setup.

### Choose a download

| File | Purpose |
| --- | --- |
| `writing_assistant-0.1.1-py3-none-any.whl` | Install the application. Recommended. |
| `writing_assistant-0.1.1.tar.gz` | Python source distribution for building locally. |
| `SHA256SUMS` | SHA-256 checksums for those two files. |
| GitHub Source code archives | Source files at the release tag. |

Requires Apple Silicon macOS and Python 3.12. AI writing needs a separately installed, signed-in, supported Codex CLI; see [compatibility requirements](codex-support.md#english). The wheel's `any` packaging tag does not mean every operating system is supported.

### Update an existing installation

1. Stop tasks that write data. [Back up](usage.md#english) project configuration and the complete data directory.
2. Read the [changelog](../CHANGELOG.md#english) and compatibility notes. Installing an update does not automatically migrate old data.
3. Install the new version in a separate environment and retain the old installation. Confirm `--version`, then inspect the existing project configuration.
4. Check applicable operations and data formats before asking the Agent to continue. See [World](world.md#english) for older run restrictions.

Published tags and packages remain fixed. Documentation on the default branch may receive corrections; packages contain the documentation from publication. See [Versioning](versioning.md#english) for application, technique pack and schema versions.
