# 隐私 / Privacy

[中文](#中文) · [English](#english)

## 中文

写作助手是供 Agent 调用、运行于 user 本地环境的应用。user 提供目标和授权并拥有
创作数据，Agent 在这一范围内调用 CLI。项目及开发者不收集你的使用数据；应用不自动
上传数据或诊断信息，也不提供网络共享或同步。分发文件包含应用、文档、许可和虚构
示例，不包含个人数据、创作数据、凭据或私人记录。

#### 内容归你所有

在你与本项目及开发者之间，你输入的内容，以及使用工具产生的草稿、生成文本、保存
记录和本地诊断信息，都归你所有。使用软件不代表授予项目或开发者这些数据的所有权，
也不代表允许收集、使用或再分发。软件许可证不会将你的内容一并许可出去。

#### 哪些内容保存在本地

项目设置保存在 `.writing-assistant/config.json`。创作内容及其历史版本保存在初始化
时选定的独立数据目录。保存、检索和准备材料不调用模型；`doctor` 只通过本机 Codex
CLI 的版本和帮助命令检查兼容性。
`capabilities`、durable task 状态查询及已保存结果的本地恢复不启动 provider process。
[诊断记录](diagnostics.md)只收集明确选定的证据；普通查询返回安全元数据。写作执行可保存
最小 code/stage 失败观察，不把 raw stderr 或稿件重复复制到诊断 case。

AI 请求的输入、输出和诊断记录也可能保存在数据目录里。配置和命令输出可能含有路径、
标题等个人信息。报告问题时，请使用虚构例子，避免直接附上原始日志或稿件。

Codex subprocess 只接收明确 allowlist 中的环境变量，用于可执行文件选择、既有账号和登录
目录、locale、临时目录、已配置的 proxy/bypass routing 与受支持的 CA 路径。无关 API key、
token、调用方 bridge、shell/loader 控制及任意变量不会转交；应用不读取登录存储内容，也
没有增加环境变量 API-key 登录方式。具体名称及限制见 [Codex 支持](codex-support.md)。

已知 proxy/CA 片段会从保留的诊断 stream 和 probe message 中移除，结果标明
redacted/incomplete，长度与 digest 只描述保留字节。final-message 是独立的授权内容
artifact，字节保持原样，并单独记录完整性；显式 raw read 因而可能返回形似 secret 的
选定内容。Redaction 无法识别所有 secret、未知编码或私人含义，也不扫描登录存储。

这些文件位于你的操作系统账号下；同一账号中有文件访问权限的软件，也可能读到它们。
备份时应先停止写入，再复制完整数据目录。

#### 什么时候会向 AI 服务发送材料

只有 Agent 在 user 授权范围内明确发起 AI 任务时，应用才会把任务和必要的选定材料
交给受支持的本地 Codex CLI，
由它使用既有登录和服务完成请求。项目没有额外的开发者上传接口，也没有其他受支持
的 AI 接入方式。

Codex 可能带有它自身的指令和上下文。第三方服务的数据处理和保留方式由其自身条款
及设置决定，本项目也无法保证不存在隐藏指令。发送敏感材料前，请查看该服务的条款和设置。支持范围及
停止请求的限制见 [Codex 支持](codex-support.md)。

## English

Writing Assistant is an application for Agents running in the user's local
environment. The user supplies goals and authorization and owns the creative
data; the Agent invokes the CLI within that scope. The project and its
developers do not collect your usage data. The tool does not automatically
upload data or diagnostics, or provide network sharing or synchronization.
The distributed files contain the application, documentation, licenses, and
made-up examples, without personal data, creative data, credentials, or private records.

#### Your content belongs to you

As between you and this project or its developers, your inputs and everything
produced through your use of the tool remain yours: drafts, generated text,
saved records, and local diagnostics. Using the software gives the project and
its developers no ownership or permission to collect, use, or redistribute that
data. The software license does not license your content.

#### What stays on your computer

Project settings are saved in `.writing-assistant/config.json`. Your writing and
its saved versions live in the separate data directory you choose at setup.
Saving, searching, and preparing material do not call a model. `doctor` checks
the installed Codex CLI through local version and help commands.
`capabilities`, durable task inspection and saved-byte reconciliation do not
start a provider process. Local [diagnostic cases](diagnostics.md) collect only
explicitly selected evidence; ordinary lookup returns safe metadata. Writing
execution can retain minimal code/stage failure observations without copying raw
stderr or manuscript text into a diagnostic case.

AI requests can leave local input, output, and diagnostic records in that data
directory. Configuration and command output can also contain paths, titles, or
other personal details. Keep them private when sharing a bug report. Use a
made-up example instead of attaching raw logs or manuscripts.

Codex subprocesses receive an explicit environment allowlist for executable
selection, existing account/auth directories, locale, temporary directories,
configured HTTP proxy/bypass routing and supported CA paths. Unrelated API keys,
tokens, caller bridges, shell/loader controls and arbitrary variables are not
forwarded. The application does not read authentication-store contents or add
API-key environment authentication. See [Codex support](codex-support.md) for
the exact supported names and limits of this boundary.

Known configured proxy/CA fragments are removed from retained diagnostic streams
and probe messages. Filtered diagnostics are labeled redacted/incomplete; their
lengths and digests describe retained bytes. Final-message output is a separate
authorized content artifact: its bytes remain unchanged and its completeness is
reported separately. Explicit raw reads can therefore return selected user
content that resembles a secret. Redaction is not a general detector for all
secrets, unknown encodings or private meaning, and no auth store is scanned.

These are local files under your operating-system account. Do not assume the
tool protects them from other software with access to that account. Back up
the complete data directory when no task is writing to it.

#### When data is sent to an AI service

The application's only network use is through explicit AI tasks started by the
Agent within the user's authorization. It passes the task and the necessary
selected material to the supported local Codex CLI,
which uses its existing authentication and service. It does not add a developer
upload endpoint or another supported AI integration.

Codex may apply its own instructions and context. This project cannot guarantee
how a third-party service handles or retains data, or that every hidden
instruction is absent. Consult that service's terms and settings before sending
sensitive material. See [Codex support](codex-support.md) for the supported environment
and the limits of stopping a request.
