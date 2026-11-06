# 版本号 / Versioning

[中文](#中文) · [English](#english)

## 中文

应用、技法包和数据格式各自有版本号。选择材料或恢复任务时，应使用记录中保存的准确版本。

### 应用版本

应用使用 `MAJOR.MINOR.PATCH`，例如 `0.1.1`；对应 Git tag 为 `v0.1.1`。`pyproject.toml`、`writing-assistant --version`、wheel 与源码分发包使用相同应用版本。

| 变化 | 版本变化 |
| --- | --- |
| 兼容的行为、打包或随包文档修正 | 增加 PATCH |
| 兼容的新操作、可选功能或新技法包功能 | 增加 MINOR，PATCH 归零 |
| `1.0.0` 之前的不兼容变化 | 增加 MINOR，PATCH 归零 |
| `1.0.0` 之后的不兼容变化 | 增加 MAJOR，MINOR 与 PATCH 归零 |

兼容范围包括公开的 CLI 参数、退出行为、JSON 字段、配置、数据格式和 Python interface。删除操作、增加必填字段或改变已有字段的含义属于不兼容变化。同一 `0.MINOR` 内的 patch 保持已说明的兼容性。

正式版本采用 [Semantic Versioning](https://semver.org/spec/v2.0.0.html) 的三段格式。Release candidate 使用 Python 的 `X.Y.ZrcN` 格式，例如 `0.2.0rc1`，对应 tag `v0.2.0rc1` 并标记为 prerelease；这只是格式示例。正式版本不使用日期、Git hash、epoch、local、development 或 post-release 后缀。

### 技法包与数据格式

每次技法选择绑定准确的 `pack_id`、`pack_version`、technique IDs 和内容摘要。已发布的技法内容保持固定，修改文字也需要新的 pack 版本。

| 技法包变化 | 版本变化 |
| --- | --- |
| 保持指导含义与 selectors 的文字修正 | PATCH |
| 兼容新增 | MINOR |
| 删除或更名 ID、改变 selector 含义、修改不兼容结构或指导 | MAJOR |

应用 patch 可以包含 pack patch；新增可选 pack 或 pack 功能使用应用 minor。两类版本号不必同步增长。`creative-records/1` 等 schema ID 标识独立的数据契约，不因应用版本改变而自动重写；不兼容格式需要新 ID 和明确的兼容说明。

### 已发布内容

Release tag、安装包和已发布 pack 内容保持固定。修正已分发的软件需要新版本；GitHub 上的 README 和在线说明可单独修正，不替换既有 tag 或下载文件。升级软件不会自动迁移、采用或重写创作记录。升级步骤见[下载与升级](release.md)。

## English

The application, technique packs and data formats have separate versions. Use the exact saved versions when selecting material or recovering a task.

### Application versions

Application versions use `MAJOR.MINOR.PATCH`, such as `0.1.1`, with Git tag `v0.1.1`. `pyproject.toml`, `writing-assistant --version`, the wheel and source distribution identify the same application version.

| Change | Version increment |
| --- | --- |
| Compatible behavior, packaging or bundled documentation correction | PATCH |
| Compatible new operation, optional capability or technique pack feature | MINOR; reset PATCH |
| Incompatible change before `1.0.0` | MINOR; reset PATCH |
| Incompatible change after `1.0.0` | MAJOR; reset MINOR and PATCH |

Compatibility covers documented CLI arguments, exit behavior, JSON fields, configuration, data formats and Python interfaces. Removing operations, adding required fields or changing existing field meanings is incompatible. Patches within a `0.MINOR` line preserve documented compatibility.

Final versions use the three-part [Semantic Versioning](https://semver.org/spec/v2.0.0.html) format. Release candidates use Python's `X.Y.ZrcN`, for example `0.2.0rc1`, with tag `v0.2.0rc1` and a prerelease label; this is a format example only. Final versions do not use dates, Git hashes, epochs, local identifiers, development or post-release suffixes.

### Technique packs and data formats

A technique selection binds exact `pack_id`, `pack_version`, technique IDs and a content digest. Published pack content stays fixed; even a wording correction needs a new pack version.

| Pack change | Version increment |
| --- | --- |
| Wording correction preserving guidance and selectors | PATCH |
| Compatible addition | MINOR |
| Removed or renamed IDs, changed selector meanings, incompatible structure or guidance | MAJOR |

An application patch may include a pack patch. A new optional pack or pack feature uses an application minor version. Application and pack numbers do not advance together. Schema IDs such as `creative-records/1` identify separate data contracts and are not rewritten to match an application release. An incompatible format needs a new ID and an explicit compatibility description.

### Published content

Release tags, packages and published pack content remain fixed. Corrections to distributed software need a new version. GitHub READMEs and online documentation may be corrected separately without replacing existing tags or downloads. Upgrading does not automatically migrate, adopt or rewrite creative records. See [Downloads and upgrades](release.md#english).
