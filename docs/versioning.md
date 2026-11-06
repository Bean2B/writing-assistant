# 版本号规则

[中文](#中文) · [English](#english)

## 中文

Writing Assistant 的正式应用版本采用 `MAJOR.MINOR.PATCH`。Package metadata、`writing-assistant --version`、源码包和安装包对应同一应用版本。Git tag 加前缀 `v`，例如 `v0.1.1`；产品名为 Writing Assistant，命令与 distribution 名为 `writing-assistant`。

### 应用版本

| 变化 | 版本规则 |
| --- | --- |
| 保持兼容的行为、封装或随包文档修正 | 增加 PATCH |
| 保持兼容的新操作、可选功能、新技法包或技法版本 | 增加 MINOR，PATCH 归零 |
| 1.0 之后不兼容的接口或存储契约变化 | 增加 MAJOR，MINOR/PATCH 归零 |

在 `1.0.0` 之前，不兼容变化增加 MINOR 并将 PATCH 归零；同一 `0.MINOR` 内的 patch 保持文档所述兼容性。Major 为零不免除不兼容说明或原件保存要求。`1.0.0` 需要明确的兼容性决定；功能能运行或某个版本号本身不证明满足它。

兼容表面包括已说明的 CLI 参数与退出行为、JSON 请求/结果字段及含义、持久 records 与准确引用、配置和已公开说明的 Python interface。增加必填字段、删操作、改变字段含义或使已有数据不可读都属于不兼容。多种变化并存时采用最大适用增量。

正式三段版本参照 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)，pre-1.0 的具体规则由本项目明确。需要 release candidate 时使用 [Python 版本规范](https://packaging.python.org/en/latest/specifications/version-specifiers/) 的 `X.Y.ZrcN`（N 从 1 开始），例如 `0.2.0rc1`、tag `v0.2.0rc1`，GitHub 标记为 prerelease；正式版为 `0.2.0`。官方版本不用 epoch、local/build 标识、development 或 post-release 后缀，不以日期或 Git hash 代替版本。

### 技法包与 schema

应用版本与 `pack_version` 分别管理。每次选择保留准确 `pack_id`、version、technique IDs 与 byte digest。已发布的 pack bytes 不变；任何文字或 selector 修改都使用新版本，即使只是 typo，也不使已准备 task 隐式改指新内容。

Pack PATCH 用于保持既有含义与 selectors 的文字修正；MINOR 用于兼容新增；MAJOR 用于删除/更名 technique ID、改变 selector 含义或不兼容的指导/结构。应用 patch 可以包含 pack patch；新可选 pack 或 pack 功能要求应用 minor。两类号码不锁步增长。

`creative-records/1` 等 schema identifier 版本化各自契约。应用或 pack 更新不自动改 schema ID。不兼容 schema 需要新标识与明确的兼容处理，不为追随应用版本重写旧引用。

### 已发布版本

`pyproject.toml` 是应用版本来源。Release tag 绑定一个准确公开 commit；wheel/sdist 使用相同版本。说明只描述现有能力、实际变更和运行限制，不以版本衡量写作质量或承诺未来功能。

发布后，版本、tag、pack bytes 与下载 assets 不替换；修正使用新版本，release candidate 也遵循此规则。未发布候选可在最终 tag/download 确定前调整。安装环境与创作数据分开；版本变化不自动授权采用、迁移或重写 user records。

## English

Writing Assistant uses `MAJOR.MINOR.PATCH` for final application versions.
Package metadata, `writing-assistant --version`, source downloads and installed
packages identify the same application version. The Git release tag adds `v`,
for example `v0.1.1`. The product name is Writing Assistant; the executable and
distribution name are `writing-assistant`.

### Application versions

| Change | Version rule |
| --- | --- |
| Compatible correction to behavior, packaging or shipped documentation | Increase PATCH. |
| Compatible new operation, optional capability or bundled technique pack/version | Increase MINOR and reset PATCH. |
| Incompatible change to a documented interface or stored-data contract after 1.0 | Increase MAJOR and reset MINOR and PATCH. |

Before `1.0.0`, an incompatible change increases MINOR and resets PATCH. A patch
within the same `0.MINOR` line preserves documented compatibility. A zero major
does not waive the requirement to describe an incompatible change or preserve
existing originals. A `1.0.0` designation requires an explicit compatibility
decision; a working feature or a version number alone does not establish it.

The compatibility surface includes documented CLI arguments and exit behavior,
structured request/result fields and meanings, supported persisted records and
exact references, configuration, and explicitly documented Python interfaces.
Adding a required field, removing an operation, changing a field's meaning, or
making existing saved data unreadable is incompatible. Optional additions must
preserve existing valid inputs and consumers' documented output contracts.
When changes require different increments, use the largest applicable increment.

Use the [Semantic Versioning](https://semver.org/spec/v2.0.0.html) principles for
the final-version core. This project defines the pre-1.0 compatibility rule above.
When a release candidate is useful, use Python's canonical form `X.Y.ZrcN`
with `N` starting at one, such as `0.2.0rc1`; its tag is `v0.2.0rc1` and its
GitHub release is marked as a prerelease. The final version is `0.2.0`.
These spellings follow the [Python version specification](https://packaging.python.org/en/latest/specifications/version-specifiers/).
Official versions use no epochs, local identifiers, development suffixes or
post-release suffixes. Dates and Git hashes are not application version numbers.

### Technique packs and schemas

An application version and a pack's `pack_version` are separate. Each selected
pack keeps its exact `pack_id`, version, selected technique IDs and byte digest.
Existing published pack bytes are immutable. Any text or selector change needs
a new pack version, even for a typo; it must not silently retarget a saved task.

For a pack, increase PATCH for a compatible wording correction that preserves
the documented guidance and selectors; increase MINOR for compatible additions;
increase MAJOR for removed or renamed technique IDs, changed selector meanings,
or incompatible guidance/structure. An application patch may include a pack
patch correction. A new optional pack or pack feature requires an application
minor version. App and pack numbers do not advance in lockstep.

Schema identifiers such as `creative-records/1` version their own contracts.
An application release or pack update does not automatically change them.
An incompatible schema change needs a new schema identifier and explicit
compatibility handling. Older exact references are not rewritten merely to
match an application version.

### Published versions

`pyproject.toml` is the application version source. A release tag identifies one
public source commit; its wheel and sdist carry that same version. Each release
lists its current capabilities, operating limits and actual changes. A version
does not measure writing quality or promise future features.

Once published, a version, its tag, pack bytes and download assets are immutable.
A correction gets a new version; an existing asset is not replaced under the
same name or version. Release candidates follow the same rule. An unpublished
candidate can be revised before its public tag and downloads are finalized.
Keep software installation and user writing in separate directories. Version
changes do not authorize adoption, data migration or rewriting user records.
