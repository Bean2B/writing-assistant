# 写作技法 / Writing techniques

[中文](#中文) · [English](#english)

## 中文

技法包为构思、场景规划、起草、审读和修订提供可选择的指导。Agent 先查看适用条件、限制和审读角度，再把选定 technique 加入请求；user 可以保留自己的文风和取舍。

技法可用于两种写作模式，但不会增加当前模式支持的 phase。它们是随应用提供的版本化文本与数据；查看或建议技法不调用模型、不读取稿件。

### 查看有哪些技法

```sh
writing-assistant technique list
writing-assistant technique show narrative-structure --version 1.1.0
```

`list` 返回 pack metadata，`show` 返回完整 pack 和准确 byte digest `sha256`。省略 `--version` 会选最高 numeric version；task 中仍要写准确版本。`narrative-structure` 的 `1.0.0` 和 `1.1.0` 都可明确选择。

| Technique ID | 用途 | `1.1.0` 的匹配 tags |
| --- | --- | --- |
| `shared-task-dependency` | 通过共同任务和依赖连接人物选择 | `shared-task`, `interdependent-characters` |
| `state-and-knowledge` | 核对状态变化和人物当时可知的信息 | `knowledge-change`, `resource-cost`, `time-order`, `continuity-constraint` |
| `personal-tradeoffs` | 让选择涉及具体个人代价或竞争需求 | `personal-stakes`, `competing-needs`, `consequential-choice` |
| `local-outcomes` | 使局部行动有可观察的结果 | `local-episode`, `observable-result` |
| `consequential-recurrence` | 让再次出现的细节改变后续选择或结果 | `recurring-question`, `promise`, `repeated-detail` |

### 把选定技法加入请求

在[写作请求](interface.md#中文)或 [workflow 请求](workflows.md#中文)中添加 `techniques`。以下为要加入请求的字段片段；将占位值换成 `show` 返回的 `sha256`：

```json
{
  "techniques": [{
    "pack_id": "narrative-structure",
    "pack_version": "1.1.0",
    "pack_sha256": "COPY_RETURNED_SHA256",
    "technique_ids": ["state-and-knowledge", "local-outcomes"]
  }]
}
```

只选择列出的 technique IDs，选 pack 不等于全选。省略 `techniques` 或使用 `[]` 都不加载 pack 指导。最多八个 pack、合计十六个 technique。

Preparation 核对准确 version、digest、ID 和 phase；已准备的 task 固定所选指导。之后想改选，需新建请求和 task。技法指导不代表正文已经满足要求；审读意见仍对应准确稿件与选定材料。

### 根据任务和标签查看建议

如果已经明确写作任务和显式标签，可请求最多三项适用建议：

```sh
writing-assistant technique suggest --phase draft --task writing --story-tag knowledge-change --story-tag resource-cost --limit 3
```

结果包含匹配的 tags、phase/task 原因和可复制的 `suggested_selection`。先检查建议，再将选中的内容放进请求；`selection_applied: false` 表示没有自动启用任何指导。

建议按明确 selectors 匹配：每项必须符合 phase、task，且至少匹配一个 tag。`1.1.0` 声明 `writing`、`review`、`revision` 三种 task selectors。应用不扫描稿件、不推断 tags、不读取 story state。

Python 调用方可用同样的参数：

```python
from writing_assistant.techniques import suggest

candidates = suggest(
    "draft", task="writing",
    story_tags=["knowledge-change", "resource-cost"], limit=3,
)
```

只考虑每个 pack 的最高 numeric version；没有 selectors 的 pack 仍可直接选择，但不产生建议。匹配 tags 较多的排在前面，pack ID 和 technique ID 确定同分顺序；`omitted_matches` 表示其他匹配项。未知 task/tag 或空 tags 不产生匹配，`limit=0` 返回空建议。

### 参数、错误与 pack 格式

| 参数或错误 | 如何处理 |
| --- | --- |
| `--max-bytes` | `list`、`show`、`suggest` 完整 UTF-8 JSON 与最后换行的上限；默认 131072，最大 1048576。 |
| `technique_output_limit` | 提高 byte 上限；应用不会裁短 pack。 |
| `changed_technique_pack` | 重新查看准确 pack，核对 version 与 digest，再明确建立新请求。 |
| `invalid_technique_suggestion` | 检查 task、tags 和 limit 的格式。 |
| `unsupported_phase` | 使用该写作模式和所选技法都支持的 phase。 |

每次建议最多十六个唯一 tags；tag 最多 64 字符，使用 lowercase letters、digits、hyphens、underscores，首位为字母或数字。`chapter_11` 保留原拼写；tag、task ID、pack ID 与 technique ID 分别使用各自的标识，应用不改名或推断同义词。`limit` 为 0–3。

Pack 包含 title、summary、通用指导、各 phase 指导，以及每项 technique 的 `applies_when`、guidance、limitations、review criteria。可选 `applicability` 只含明确 selectors：`tasks` 最多八项、`story_tags` 最多十六项。`1.0.0` 无须具备建议 selectors，准确旧版本选择仍可使用。

当前加载 bundled packs，不支持外部 pack 路径、网络查找或可执行扩展。每包最多 65536 bytes、十六项 technique；应用最多加载 32 个 pack versions，拒绝损坏内容和 symlink。可用 `writing-assistant capabilities --schema technique-pack` 或 [pack schema](../schemas/technique-pack-v1.schema.json)查看格式；版本兼容见[版本规则](versioning.md#中文)。

## English

Technique packs provide optional guidance for concept work, scene planning, drafting, review, and revision. An Agent reads applicability, limitations, and review criteria before adding selected techniques to a request. The user retains control of style and content choices.

Packs work in both writing modes without adding phases to the active mode. They are bundled, versioned text and data. Inspecting or suggesting techniques makes no model call and reads no manuscript.

### Discover available techniques

```sh
writing-assistant technique list
writing-assistant technique show narrative-structure --version 1.1.0
```

`list` returns pack metadata; `show` returns a complete pack and its exact byte digest in `sha256`. Omitting `--version` selects the highest numeric version, but task requests still name an exact version. Both `1.0.0` and `1.1.0` of `narrative-structure` remain directly selectable.

| Technique ID | Use | Matching tags in `1.1.0` |
| --- | --- | --- |
| `shared-task-dependency` | Connect character choices through a practical task and dependencies. | `shared-task`, `interdependent-characters` |
| `state-and-knowledge` | Check changes in state and what each participant can know. | `knowledge-change`, `resource-cost`, `time-order`, `continuity-constraint` |
| `personal-tradeoffs` | Give choices a concrete personal cost or competing need. | `personal-stakes`, `competing-needs`, `consequential-choice` |
| `local-outcomes` | Give local actions observable results. | `local-episode`, `observable-result` |
| `consequential-recurrence` | Let a returning detail change later choices or results. | `recurring-question`, `promise`, `repeated-detail` |

### Add selected techniques to a request

Add `techniques` to a [writing request](interface.md#english) or [workflow request](workflows.md#english). This is a field fragment to include in that request; replace the placeholder with `sha256` returned by `show`:

```json
{
  "techniques": [{
    "pack_id": "narrative-structure",
    "pack_version": "1.1.0",
    "pack_sha256": "COPY_RETURNED_SHA256",
    "technique_ids": ["state-and-knowledge", "local-outcomes"]
  }]
}
```

Only the named technique IDs are selected. Choosing a pack does not select every technique. An omitted `techniques` field or `[]` loads no pack guidance. A request supports at most eight packs and sixteen techniques in total.

Preparation checks the exact version, digest, IDs, and phase applicability. A prepared task freezes its selected guidance; use a new request and task to change it. Selected guidance does not establish that the prose meets its criteria. Review feedback still refers to an exact draft and selected material.

### Suggest techniques from a task and tags

When the task and tags are already explicit, request up to three applicable suggestions:

```sh
writing-assistant technique suggest --phase draft --task writing --story-tag knowledge-change --story-tag resource-cost --limit 3
```

The result includes matched tags, phase/task explanations, and a copyable `suggested_selection`. Inspect it before putting chosen techniques into a request. `selection_applied: false` means no guidance has been enabled automatically.

Matching uses declared selectors: every suggestion must match the phase, task, and at least one explicit tag. Version `1.1.0` declares task selectors `writing`, `review`, and `revision`. The application does not scan prose, infer tags, or read story state.

Python callers can use the same inputs:

```python
from writing_assistant.techniques import suggest

candidates = suggest(
    "draft", task="writing",
    story_tags=["knowledge-change", "resource-cost"], limit=3,
)
```

Only the highest numeric version of each pack participates. Packs without selectors remain directly selectable but yield no suggestions. More matching tags rank first, with pack ID and technique ID breaking ties. `omitted_matches` reports additional matches. Unknown tasks/tags and empty tags yield no match; `limit=0` returns no suggestions.

### Parameters, errors, and pack format

| Parameter or error | What to do |
| --- | --- |
| `--max-bytes` | Bounds complete UTF-8 JSON including the final newline for `list`, `show`, and `suggest`; default 131072, maximum 1048576. |
| `technique_output_limit` | Increase the byte bound; packs are never truncated. |
| `changed_technique_pack` | Inspect the exact pack again, check version and digest, and explicitly prepare a new request. |
| `invalid_technique_suggestion` | Check the task, tags, and limit format. |
| `unsupported_phase` | Choose a phase supported by both the writing mode and selected techniques. |

Suggestions accept at most sixteen unique tags. A tag has at most 64 characters: lowercase letters, digits, hyphens, and underscores, starting with a letter or digit. `chapter_11` keeps its exact spelling. Tags, task IDs, pack IDs, and technique IDs have distinct meanings; the application does not rename them or infer synonyms. `limit` ranges from 0 to 3.

Packs declare a title, summary, general and phase guidance, and each technique's `applies_when`, guidance, limitations, and review criteria. Optional `applicability` contains explicit selectors only: up to eight `tasks` and sixteen `story_tags`. Version `1.0.0` does not need suggestion selectors and remains usable through exact selection.

The application loads bundled packs, without external pack paths, network lookup, or executable extensions. Each pack allows up to 65536 bytes and sixteen techniques; the bundle allows up to 32 pack versions and rejects malformed data and symlinks. Inspect the format with `writing-assistant capabilities --schema technique-pack` or the [pack schema](../schemas/technique-pack-v1.schema.json). See [versioning](versioning.md#english) for compatibility.
