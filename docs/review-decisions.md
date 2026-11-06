# 审读意见与取舍 / Review decisions

[中文](#中文) · [English](#english)

## 中文

Structured review companion 把审读意见连接到一个准确 draft 版本和具体引用。Agent 可以定位意见涉及的原句，区分矛盾、疑问和偏好，再记录 user 接受、拒绝或暂缓的选择。原始审读、完整 `review_text` 和历次取舍都保留，便于修订后回看。

持久 workflow 提供审读和取舍命令；Python 调用方也可单独解析、验证这类结果。执行模型的配置见 [Codex 支持](codex-support.md#中文)，完整章节流程见 [workflow 指南](workflows.md#中文)。

### 阅读一条审读意见

一条 observation 包含目标原句、意见、分类、影响、修改建议和所选材料中的证据。下面是审读结果的 JSON 格式示例：

```json
{
  "schema_version": "writing-assistant-review-output/1",
  "review_text": "The gate action needs a clearer explanation of the lock condition.",
  "outcome": "concerns",
  "observations": [{
    "observation_id": "gate-condition",
    "span": {"quote": "Mira opens the gate.", "occurrence": 1},
    "observation": "The action appears to conflict with the stated lock condition.",
    "classification": "confirmed-contradiction",
    "impact": "material",
    "proposed_change": "Clarify the changed lock condition before the action.",
    "evidence": [{
      "material_id": "evidence-1",
      "quote": "The gate remains locked until sunrise.",
      "occurrence": 1
    }]
  }]
}
```

| 字段 | 含义 |
| --- | --- |
| `classification: confirmed-contradiction` | 审读者声称存在矛盾，必须引用至少一项所选证据。应用核对引用身份与原句，不判断它们是否真的矛盾。 |
| `classification: uncertainty` | 材料缺失、推断不确定或需要澄清。 |
| `classification: preference` | 主观偏好或可选写法。 |
| `impact` | `material` 或 `minor`，表示审读者判断的影响程度。 |
| `proposed_change` | 供 user 取舍的修改建议。 |

Quote 必须逐字复制显示给模型的文本，包括标点与空白。`occurrence` 从 1 开始，计入重叠匹配，上限 4096；只有 quote 唯一时才可省略。应用负责换算 UTF-8 半开 byte 范围，模型无需计算 offset。

没有发现问题时，仍须给出实质 `review_text`，使用 `outcome: "no-concerns"` 和 `observations: []`。这个结论只适用于选定稿件与材料。丢失或格式错误的结果不能成为“没有问题”。

### 记录接受、拒绝或暂缓

在 workflow 中，先 `inspect` 获取当前 plan/checkpoint digest 与准确 `review_decision` reference。将以下请求保存为 `review-choice.json`，用实际 reference 对象替换占位字符串：

```json
{
  "chapter": 1,
  "review_decision": "REPLACE_WITH_EXACT_REFERENCE_OBJECT",
  "observations": [{
    "observation_id": "gate-condition",
    "disposition": "deferred",
    "reason": "The user will decide after reviewing the next scene."
  }],
  "reason": "Record the user's feedback choices.",
  "progression": "apply-policy"
}
```

```sh
writing-assistant workflow --project ../demo-project decide WORKFLOW_ID review-choice.json --expected-plan-sha256 PLAN_SHA --expected-checkpoint-sha256 CHECKPOINT_SHA
```

将 `WORKFLOW_ID`、`PLAN_SHA` 和 `CHECKPOINT_SHA` 换成 inspect 的值。`disposition` 可为 `accepted`、`rejected`、`deferred`；`progression` 可为 `continue` 或 `apply-policy`，具体推进规则见 [workflow 指南](workflows.md#中文)。调用方记录 user 已授权的选择；接受反馈不会自动采用修订稿。

相同当前选择幂等。改变选择时追加 `choices` history，并更新该 observation 的当前值；被拒绝的意见仍保留。执行下一项 task 前检查返回的 workflow 状态。

### Python 接入：绑定准确原文

`review_instructions(target_ref, evidence_refs)` 生成输出契约与有序材料别名：draft 为 `target`，其他材料依次为 `evidence-1`、`evidence-2`。调用方按相同顺序提供准确正文。引用为带版本 ID 与 SHA-256 的 `creative-records/1` reference。

以下示例假定调用方已取得模型原始输出、准确引用和原文 bytes：

```python
from writing_assistant.review_decisions import (
    parse_review_output, validate_choice, verify_decision,
)

decision = parse_review_output(
    original_output,
    target_ref=exact_draft_reference,
    target_text=original_draft_bytes,
    evidence=[{"ref": exact_material_reference, "text": original_material_bytes}],
)
chosen = validate_choice(decision, [{
    "observation_id": "gate-condition",
    "disposition": "rejected",
    "reason": "The user retains this deliberate ambiguity.",
}])
```

Parser 接受一个 JSON 对象，可包在一层 JSON code fence 中。它核对原文 digest、目标和证据身份、quote 位置、ID、outcome 与字段上限。返回的 `writing-assistant-review-decision/1` 保留原输出与 digest、完整意见、解析后的 spans，以及初始空 history；各项初始为 `disposition: "proposed"`、`user_choice: null`。Parser 和 choice validator 自身不写文件、不调用模型，调用方保存每个结果版本。

片段 evidence 可另含 `range: {"byte_start": START, "byte_end": END}`。`text` 仍为本地核对 digest 的完整原件，但匹配与 occurrence 只在选中 UTF-8 slice 内进行；引用保留完整 ref、原文 offset 与 `selected_range`。本地完整原件校验不允许向 provider 发送未选中的 bytes。

`validate_decision` 核对已保存 companion 的结构与原输出 digest；`verify_decision` 用相同准确原件从保留的输出和选择重建 companion，拒绝换版、改 span 或替换证据。审读结果与 user 的内容采用决定分别保存。

### 处理无效结果

Workflow 的 `repair-review` 保存结构化更正并保留首次失败的原始输出，不调用模型：

```sh
writing-assistant workflow --project ../demo-project repair-review WORKFLOW_ID repair.json --expected-plan-sha256 PLAN_SHA --expected-checkpoint-sha256 CHECKPOINT_SHA
```

请求包含 `reason` 与符合上述格式的 `review_output` 对象。先检查原始输出并修正引用或格式，再使用 workflow 当前的 digests；恢复后检查状态。

| 错误 | 检查什么 |
| --- | --- |
| `review_decisions_missing`, `invalid_review_output` | 输出是否完整，schema、字段与 outcome 是否一致。 |
| `review_quote_not_found`, `ambiguous_review_quote` | 原句是否逐字相同，是否需要明确 occurrence。 |
| `review_evidence_not_selected`, `changed_review_reference` | 是否提供了原来准确版本与可见范围。 |
| `invalid_review_decision`, `changed_review_decision` | Companion 是否被更改，是否与保留输出及原件相符。 |
| `invalid_review_choice`, `unknown_review_observation` | 取舍是否引用现有 observation ID，状态与 reason 是否有效。 |

错误不带原文；解析失败时保留原输出，供单独检查。

### 大小上限

| 内容 | 上限 |
| --- | --- |
| 模型 response / 完整 `review_text` | 131072 / 32768 UTF-8 bytes |
| observations / 每项 citations / 其他选定材料 | 32 / 8 / 64 |
| 全部提供的原文 / companion | 16777216 / 524288 bytes |
| 单个 quote | 8192 bytes |
| observation、proposed change、choice reason | 各 4096 bytes |
| changed choices | 128 次 |

完整定义见 [review-decision schema](../schemas/review-decision-v1.schema.json)，其中 `$defs.modelOutput` 定义模型输出。材料选择见[Story context](story-context.md#中文)。

## English

A structured review companion connects feedback to one exact draft and literal supporting passages. An Agent can locate the affected sentence, distinguish contradictions from uncertainty or preference, and record the user's accepted, rejected, or deferred choices. Original output, complete `review_text`, and earlier choices remain available for later revision.

Durable workflows provide review and decision commands. Python callers can also parse and validate companions directly. See [Codex support](codex-support.md#english) for model execution and [workflows](workflows.md#english) for chapter sequencing.

### Read an observation

Each observation includes a target passage, feedback, classification, impact, suggested change, and citations from selected material. The following illustrates the review-result JSON format.

```json
{
  "schema_version": "writing-assistant-review-output/1",
  "review_text": "The gate action needs a clearer explanation of the lock condition.",
  "outcome": "concerns",
  "observations": [{
    "observation_id": "gate-condition",
    "span": {"quote": "Mira opens the gate.", "occurrence": 1},
    "observation": "The action appears to conflict with the stated lock condition.",
    "classification": "confirmed-contradiction",
    "impact": "material",
    "proposed_change": "Clarify the changed lock condition before the action.",
    "evidence": [{
      "material_id": "evidence-1",
      "quote": "The gate remains locked until sunrise.",
      "occurrence": 1
    }]
  }]
}
```

| Field | Meaning |
| --- | --- |
| `classification: confirmed-contradiction` | The reviewer claims a contradiction and must cite at least one selected source. The application checks exact identity and quotations, without proving the contradiction. |
| `classification: uncertainty` | Missing information, uncertain inference, or a point needing clarification. |
| `classification: preference` | A subjective preference or optional alternative. |
| `impact` | `material` or `minor`, expressing the reviewer's assessment. |
| `proposed_change` | A suggested change for the user to consider. |

Quotes copy the selected text literally, including punctuation and whitespace. `occurrence` is one-based, counts overlapping matches, and is bounded to 4096. Omit it only for a unique quote. The application computes half-open UTF-8 byte ranges; the model need not calculate offsets.

A review with no identified concern still needs substantive `review_text`, `outcome: "no-concerns"`, and `observations: []`. That conclusion applies to the selected draft and evidence. Missing or malformed results cannot become a no-concern conclusion.

### Record accepted, rejected, or deferred feedback

In a workflow, first `inspect` the current plan/checkpoint digests and exact `review_decision` reference. Save this request as `review-choice.json`, replacing the placeholder string with the actual reference object:

```json
{
  "chapter": 1,
  "review_decision": "REPLACE_WITH_EXACT_REFERENCE_OBJECT",
  "observations": [{
    "observation_id": "gate-condition",
    "disposition": "deferred",
    "reason": "The user will decide after reviewing the next scene."
  }],
  "reason": "Record the user's feedback choices.",
  "progression": "apply-policy"
}
```

```sh
writing-assistant workflow --project ../demo-project decide WORKFLOW_ID review-choice.json --expected-plan-sha256 PLAN_SHA --expected-checkpoint-sha256 CHECKPOINT_SHA
```

Replace `WORKFLOW_ID`, `PLAN_SHA`, and `CHECKPOINT_SHA` with inspected values. `disposition` accepts `accepted`, `rejected`, or `deferred`; `progression` accepts `continue` or `apply-policy`. See [workflows](workflows.md#english) for progression rules. The caller records choices already authorized by the user; accepting feedback does not adopt a revision.

Repeating the current choice is idempotent. Changing it appends to `choices` history and updates the observation's current value. Rejected concerns remain visible. Inspect the returned workflow state before executing its next task.

### Python integration: bind exact originals

`review_instructions(target_ref, evidence_refs)` provides the response contract and ordered aliases: the draft is `target`, other material is `evidence-1`, `evidence-2`, and so on. Supply corresponding original texts in that order. References are exact `creative-records/1` objects with version IDs and SHA-256 digests.

This example assumes the caller has the raw model output, exact references, and original bytes:

```python
from writing_assistant.review_decisions import (
    parse_review_output, validate_choice, verify_decision,
)

decision = parse_review_output(
    original_output,
    target_ref=exact_draft_reference,
    target_text=original_draft_bytes,
    evidence=[{"ref": exact_material_reference, "text": original_material_bytes}],
)
chosen = validate_choice(decision, [{
    "observation_id": "gate-condition",
    "disposition": "rejected",
    "reason": "The user retains this deliberate ambiguity.",
}])
```

The parser accepts one JSON object, optionally inside one outer JSON code fence. It verifies body digests, target and evidence identity, quote locations, IDs, outcome consistency, and bounds. Its `writing-assistant-review-decision/1` result retains the raw output and digest, complete feedback, resolved spans, and an initially empty history. Each observation starts with `disposition: "proposed"` and `user_choice: null`. Parsing and choice validation do not write files or call a model; callers save each resulting version.

Excerpt evidence may include `range: {"byte_start": START, "byte_end": END}`. `text` remains the complete original for local digest verification, but matching and occurrence counts use only the selected UTF-8 slice. Citations retain the full reference, original offsets, and `selected_range`. Local verification of a full original does not authorize sending unselected bytes to a provider.

`validate_decision` checks a saved companion's structure and retained-output digest. `verify_decision` reconstructs it from the same exact originals, retained output, and choices, refusing a changed version, altered span, or substituted evidence. Review feedback and the user's content-adoption decision remain distinct records.

### Handle invalid feedback

Workflow `repair-review` saves a structured correction while retaining the original failed output, without calling a model:

```sh
writing-assistant workflow --project ../demo-project repair-review WORKFLOW_ID repair.json --expected-plan-sha256 PLAN_SHA --expected-checkpoint-sha256 CHECKPOINT_SHA
```

The request contains `reason` and a `review_output` object in the format above. Inspect the original output, correct its quotes or structure, and use current workflow digests. Inspect state after recovery.

| Error | What to check |
| --- | --- |
| `review_decisions_missing`, `invalid_review_output` | Complete output, schema, required fields, and consistent outcome. |
| `review_quote_not_found`, `ambiguous_review_quote` | Literal quote spelling and explicit occurrence when needed. |
| `review_evidence_not_selected`, `changed_review_reference` | Original exact versions and visible ranges. |
| `invalid_review_decision`, `changed_review_decision` | Companion consistency with retained output and originals. |
| `invalid_review_choice`, `unknown_review_observation` | Existing observation ID, valid disposition, and reason. |

Errors contain no original passages. Preserve raw output separately when parsing fails so it can be inspected.

### Size bounds

| Content | Bound |
| --- | --- |
| Model response / complete `review_text` | 131072 / 32768 UTF-8 bytes |
| Observations / citations per observation / additional material | 32 / 8 / 64 |
| Total supplied original text / companion | 16777216 / 524288 bytes |
| One quote | 8192 bytes |
| Observation, proposed change, choice reason | 4096 bytes each |
| Changed choices | 128 |

The [review-decision schema](../schemas/review-decision-v1.schema.json) defines the companion and `$defs.modelOutput`. See [story context](story-context.md#english) for material selection.
