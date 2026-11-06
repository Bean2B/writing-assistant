# 写作技法包

[中文](#中文) · [English](#english)

## 中文

技法包提供可明确选择、带版本的数据型指导，包括适用条件、限制与审读角度。它不决定文风、不保证文学效果，也不替 user 决定采用结果。

### 发现与明确选择

```sh
writing-assistant technique list
writing-assistant technique show narrative-structure --version 1.0.0
writing-assistant capabilities --schema technique-pack
```

这些操作不调用模型，不读取项目或稿件。Show 返回完整 pack 及准确 byte digest `sha256`；省略 version 时选最高 numeric version，但 task 仍须明确版本。`1.0.0` 与 `1.1.0` 可分别选择，旧版 bytes 保持；`1.1.0` 增加 suggestions 的适用 selectors。

`--max-bytes` 包含完整 UTF-8 JSON 和换行，默认 131072，最大 1048576；不足时为 `technique_output_limit`，不裁短 pack。

| Technique ID | 用途 |
| --- | --- |
| `shared-task-dependency` | 通过共同任务和依赖连接人物选择 |
| `state-and-knowledge` | 核对状态变化与人物当时可知的信息 |
| `personal-tradeoffs` | 让选择涉及具体个人代价或竞争需求 |
| `local-outcomes` | 使局部行动有可观察的结果 |
| `consequential-recurrence` | 重复出现的细节改变后续选择或结果 |

请求中的 `techniques` 明确给出 `pack_id`、`pack_version`、`pack_sha256`、`technique_ids`；从 discovery 复制 digest。最多八个 pack、合计十六个 technique。选 pack 不等于全选内容；缺省或空数组不载入指导。版本、digest、ID 或 phase 不符时拒绝；prepared task 冻结所选指导，不修改模式本身支持的 phase。

### 检查适用建议

```sh
writing-assistant technique suggest --phase draft --task writing --story-tag knowledge-change --story-tag resource-cost --limit 3
```

建议只匹配明确 phase、task 和 story tags，不扫描稿件、不推断标签、不读 state、不调用模型。每个建议必须匹配 phase/task 和至少一个 tag。`selection_applied: false`，`suggested_selection` 仍只是候选；必须主动复制到请求才选择技法。

只考虑每个 pack 最高 numeric version；没有 selectors 的 pack 仍可直接选择，但不产生建议。匹配 tag 更多者在前，pack ID 和 technique ID 确定排序；最多三项，`omitted_matches` 记录其他匹配。`limit` 为 0–3，空 tags 或零 limit 返回空建议；每次最多十六个唯一 tags。Tags 为最多 64 字符的 lowercase letters/digits/hyphens/underscores，首位为字母或数字；例如 `chapter_11` 保留原拼写。未知 task/tag 不匹配，不替换其含义。

### 增加 data-only pack

在 `src/writing_assistant/technique_packs/PACK_ID/MAJOR.MINOR.PATCH.json` 增加符合 [pack schema](../schemas/technique-pack-v1.schema.json) 的 JSON，文件名/目录与内部 ID/version 一致，并将准确路径加入 `public-files.json`。改变 bytes 使用新版本，不替换旧版本；详见 [版本规则](versioning.md)。

Pack 声明标题、summary、通用与各 phase 指导，以及最多十六项 technique；每项保留适用说明、guidance、limitations、review criteria。可选 applicability 只包含明确 selectors：tasks 最多八项、story_tags 最多十六项。Pack 是文本与数据，不授权材料读取、执行或采用。

加载器验证身份、版本、唯一 ID、phase、文本上限和 regular-file 状态。单包最多 65536 bytes，总共最多 32 个 pack versions；拒绝 symlink 和损坏内容。没有外部 pack 路径、网络查找、动态 import 或可执行扩展。

## English

Technique packs provide explicitly selected writing guidance for concept,
scene planning, drafting, review and revision. They are versioned application
data with applicability, instructions, limitations and review criteria. Guidance
does not establish that a generated story meets those criteria or determine
whether the user should adopt it.

### Discover and select

```sh
writing-assistant technique list
writing-assistant technique show narrative-structure --version 1.0.0
writing-assistant capabilities --schema technique-pack
```

These commands make no model call and read no project or manuscript. `list`
returns bounded validated metadata. `show` returns one complete pack, including
its exact byte digest in `sha256`. Omitting `--version` selects the highest
bundled numeric version; a task selection must still name the exact version.
The `narrative-structure` versions `1.0.0` and `1.1.0` remain independently
selectable. Version `1.1.0` adds declared applicability selectors for suggestions;
version `1.0.0` retains its original bytes.
`--max-bytes` bounds the complete UTF-8 JSON output including its newline; its
default is 131072 and maximum is 1048576. An undersized bound returns
`technique_output_limit` without truncating the pack.

The bundled `narrative-structure` pack offers these abilities:

| Technique ID | Use |
| --- | --- |
| `shared-task-dependency` | Connect people through a practical task and dependencies. |
| `state-and-knowledge` | Keep physical state and participant knowledge explicit. |
| `personal-tradeoffs` | Give a decision a concrete personal cost or competing need. |
| `local-outcomes` | Give a local action an observable result. |
| `consequential-recurrence` | Reuse a detail when its return changes a later choice or result. |

Add `techniques` to a writing request or workflow request. Copy `sha256` from
discovery into `pack_sha256`; the placeholder below is not a usable digest:

```json
{
  "techniques": [{
    "pack_id": "narrative-structure",
    "pack_version": "1.0.0",
    "pack_sha256": "COPY_RETURNED_SHA256",
    "technique_ids": ["state-and-knowledge", "local-outcomes"]
  }]
}
```

At most eight packs and sixteen selected techniques in total are supported.
Technique IDs are explicit; selecting a pack does not select every technique.
An absent or empty array loads no pack guidance. Selection checks the exact pack
version, digest, IDs and phase applicability before preparation. Changed bytes
return `changed_technique_pack`; missing IDs or unsupported phases are errors.
Packs are optional in both writing modes and do not change the active mode's
supported phases. A prepared task freezes the selected guidance and includes
the application policy and bundled assets in its execution binding.

Review instructions ask for observations supported by the selected draft and
materials. Review output remains feedback for that exact draft. It does not
adopt text, create world facts, or mechanically prove prose quality.

### Suggest an applicable set

Applicability assistance uses a declared phase, a task identifier, and explicit
story tags. It does not scan a manuscript, infer tags, read project state, or call
a model:

```sh
writing-assistant technique suggest --phase draft --task writing --story-tag knowledge-change --story-tag resource-cost --limit 3
```

Its Python interface is:

```python
from writing_assistant.techniques import suggest

candidates = suggest(
    "draft", task="writing", story_tags=["knowledge-change", "resource-cost"], limit=3,
)
```

The result identifies each suggested technique by exact pack version and digest,
reports the matched tags, and explains the declared phase and task matches.
`suggested_selection` is a candidate in the ordinary selection format. Copy it
into a writing or workflow request only when choosing those techniques. Discovery
always reports `selection_applied: false`; a suggestion never changes a prepared
task or enables guidance by itself. Supplying `techniques: []` remains a complete
zero-technique choice. An empty tag list or `limit=0` returns no suggestions and
does not load pack guidance.

Suggestion input tags use the story-state identifier vocabulary: lowercase
letters, digits, hyphens and underscores, with a letter or digit first and at
most 64 characters. Tags such as `chapter_11` retain their exact spelling.
Unknown tags yield no match; they are not renamed or treated as pack IDs.
Pack IDs, technique IDs, declared task IDs and versions keep their separate
contracts. Pack applicability selectors remain explicit exact-match data.

Each suggestion must match the declared phase, a declared task selector, and at
least one explicit story tag. Only the highest bundled numeric version of each
pack participates. Packs without selectors remain directly selectable and yield
no suggestions. There is no prose keyword matching or automatic selection of all
techniques. More matching explicit tags rank first; pack ID and technique ID
break ties deterministically. At most three suggestions are returned;
`omitted_matches` exposes additional matching candidates. Adding a pack may
change discovery results, while existing exact selections remain frozen.

Version `1.1.0` declares the tasks `writing`, `review`, and `revision`. Its tags
are:

| Technique ID | Explicit story tags |
| --- | --- |
| `shared-task-dependency` | `shared-task`, `interdependent-characters` |
| `state-and-knowledge` | `knowledge-change`, `resource-cost`, `time-order`, `continuity-constraint` |
| `personal-tradeoffs` | `personal-stakes`, `competing-needs`, `consequential-choice` |
| `local-outcomes` | `local-episode`, `observable-result` |
| `consequential-recurrence` | `recurring-question`, `promise`, `repeated-detail` |

A request supports at most sixteen unique tags. `limit` is an integer from zero
through three. Unknown tags or task IDs simply yield no match. Malformed selectors
return `invalid_technique_suggestion`; unsupported phases return
`unsupported_phase`. Matching explains declared applicability, without asserting
that a technique will improve the story or resolve a review concern.

### Add a data-only pack

Create a JSON file at
`src/writing_assistant/technique_packs/PACK_ID/MAJOR.MINOR.PATCH.json` and follow
the [pack schema](../schemas/technique-pack-v1.schema.json). The filename version
and directory ID must equal `pack_version` and `pack_id` in the JSON. Use a new
version when changing bytes rather than silently replacing a version selected
by an existing task. Include the exact new asset path in `public-files.json`
when distributing it; package construction uses that explicit file list.

A pack declares a title, summary, general guidance, guidance for every supported
phase, and up to sixteen techniques. Each technique declares its ID, title,
applicable phases, `applies_when`, guidance, limitations and review criteria.
Use concise operational instructions and synthetic examples. Pack text cannot
grant material access, add user authorization or override task safety rules.
An optional technique-level `applicability` object declares nonempty unique
`tasks` and `story_tags` arrays, bounded respectively to eight and sixteen IDs.
These data-only selectors enable suggestions; they do not change explicit
selection validation or add guidance to a prompt. Prior pack versions do not need
this optional field. Add selectors through a new version rather than replacing
already versioned bytes.

The loader validates bundled JSON before listing or selecting it, including
identity, version, unique IDs, phase lists, text bounds and a maximum 65536 bytes
per pack. The bundle supports at most 32 pack versions. It rejects symbolic links
and malformed entries. There is no runtime import, external pack path, network
lookup or executable extension hook. The Agent inspects discovery and chooses
applicable versions; the application validates the selection and freezes it in
the task or workflow. Use [durable workflows](workflows.md) for application-owned
chapter sequencing and result dependencies.
