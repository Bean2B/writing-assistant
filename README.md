# Writing Assistant

[English](docs/en/README.md) · [安装](#安装) · [开始写作](#start-writing)

Writing Assistant 是由 Codex 开发、面向 Agent 的本地写作应用。一本书的章节、修订稿、连续性便签、设定和读者反馈保存在同一个 SQLite 书库里。作者可以把已经写进正文的事实、人物的判断以及打算留到以后说明的事情分别记录，并按原文核对。

## 安装

在 Apple Silicon macOS 和 Python 3.12 环境下，下载 [v0.3.1](https://github.com/Bean2B/writing-assistant/releases/tag/v0.3.1) 的 wheel 和 `SHA256SUMS`，核对摘要，然后在虚拟环境中安装。

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps ./writing_assistant-0.3.1-py3-none-any.whl
writing-assistant --version
```

也可以直接使用本仓库的 `./scripts/writing-assistant`。公开发行包提供一个可选的写作 skill。需要时，将 `skills/writing-assistant/` 注册到自己选用的 harness。[安装 skill](docs/operations.md#install-a-skill)

### 在 Windows 上运行此分支

在已安装 Python 3.13 或更高版本的电脑上，从本分支源码目录打开 PowerShell，运行以下命令。Windows 改动尚待原生系统验证，已发布的 v0.3.1 安装包早于这些改动。

```powershell
$wa = '.\scripts\writing-assistant.cmd'
& $wa doctor
& $wa --book 'books\创作作品\渡灯' init '渡灯'
```

[Windows 书库和 skill 配置](docs/operations.md#windows-book-files-and-skills)

<a id="start-writing"></a>
## 开始写作

```sh
book='books/创作作品/示例'
writing-assistant --book "$book" init '示例'
writing-assistant --book "$book" prepare '先规划开篇三章' --phase plan-book
```

有了正文和章卡后，用 `save 1 --file chapter.md --card card.json` 一起保存。用 `chapter 1` 查看该稿的档案，`context 2` 准备下一章交接。普通书库操作在本地运行。选择模型任务并执行时，选定的内容会送给配置的提供商。

### 阅读与书架

在本分支中，创建或还原到 `books/创作作品/` 或 `books/学习样本/` 的书会自动登记到 `books/README.md` 的对应分类。打开书内的 `目录.html` 即可离线阅读。每章优先显示已采纳稿，没有已采纳稿时显示最新草稿。

运行 `writing-assistant bookshelf books` 可补登旧书、保留手写简介，并生成 `books/书架.html`。需要单独刷新一本书时，使用 `writing-assistant --book DIR reading-page`。

[章卡示例](docs/world-and-records.md#chapter-dossiers) · [长篇回读](docs/study-and-recall.md) · [读者盲读](docs/reader-trials.md) · [模型任务](docs/task-runtime.md) · [备份与恢复](docs/operations.md) · [版本变化](CHANGELOG.md) · [安全与隐私](SECURITY.md)

从公开版 0.1.x 升级时，请保留旧环境和资料备份。0.3.1 使用新的 CLI 和书库格式，已选取的旧版 Creative Record 可逐条导入。[迁移说明](docs/prior-creative-records.md)
