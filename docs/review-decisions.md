# 带证据的审读意见

[中文](#中文) · [English](#english)

## 中文

Structured review companion 把审读绑定到一个准确 draft 版本及字面引用。它保留完整 `review_text`、原始模型输出和 digest，不采用正文、不建立 World 事实，也不判断文学意见是否正确。

### 模型输出

`review_instructions(target_ref, evidence_refs)` 提供契约和材料别名：draft 为 `target`，其他选定原文依次为 `evidence-1`、`evidence-2`。调用方按同样顺序提供准确正文。所有 ref 都带 `creative-records/1` 的版本与 SHA-256。

模型输出一个 `writing-assistant-review-output/1` JSON，可包在一层 JSON code fence 中。包含完整 `review_text`、`outcome` 和 `observations`。每条 observation 提供 ID、目标 `span.quote`、判断、`classification`、`impact`、`proposed_change` 与 evidence。没有意见时仍要求实质 review_text，使用 `outcome: no-concerns` 和空数组；材料缺失或格式错误不能变成 no-concerns。

Quote 必须逐字复制所选文本，包含标点和空白。`occurrence` 从 1 开始、包含重叠匹配、最大 4096；仅当 quote 唯一时可省略。应用计算 UTF-8 半开 byte 范围，模型不需要计算偏移。

`classification` 为 `confirmed-contradiction`、`uncertainty`、`preference`；`impact` 为 `material` 或 `minor`。声称矛盾至少要一个选定证据引用；应用只核对准确 bytes 与身份，不证明两段文字真的矛盾。缺少信息和推测应保留为 uncertainty，主观选择为 preference；计划与生成 proposal 不构成采用事实。

### 验证、选择与恢复

`parse_review_output` 核对正文 digest、准确目标与证据、quote 位置、ID、outcome 和字段上限。结果 `writing-assistant-review-decision/1` 保留原输出、正文意见、spans 与初始空 choice history；每项初始为 `disposition: proposed`、`user_choice: null`。

对片段证据可附 `range: {byte_start, byte_end}`。本地为 digest 核验读取完整原件，但 quote 匹配和 occurrence 只发生在已显示的 UTF-8 slice 内；未显示 bytes 不能被引用，也不因此获得 provider 读取权限。

`validate_decision` 核对结构与原输出 digest；供 workflow 使用时，`verify_decision` 以准确原件重建并核对 companion。改变版本、span 或证据会被拒绝。`validate_choice` 保存 user 已授权的 `accepted`、`rejected`、`deferred` 及 reason；相同选择幂等，改变选择追加历史，已拒绝意见仍保留。接受反馈不等于采用修订稿。

Workflow 通过 `workflow decide` 明确保存选择；`workflow repair-review` 保存 structured correction 并保留首次失败的原文，不调用模型。执行后续 task 前 inspect 原 workflow。完整命令和 progression 策略见 [workflow](workflows.md)。

上限：response 131072 UTF-8 bytes；32 observations；每项八个 evidence citations；64 个其他选定材料；总原文字节 16777216；companion 524288 bytes；128 次 changed choices。Quote 最多 8192 bytes，review_text 32768，其余 observation/change/reason 各 4096。

错误包括 `review_decisions_missing`、`invalid_review_output`、`review_quote_not_found`、`ambiguous_review_quote`、`review_evidence_not_selected`、`changed_review_reference`、`invalid_review_decision`、`changed_review_decision`、`invalid_review_choice`、`unknown_review_observation`。错误不带原文；解析失败时另行保留原输出。Schema 见 [review-decision](../schemas/review-decision-v1.schema.json)。

## English

A structured review companion connects a review to one exact draft version and
literal supporting passages. The original model output and its digest remain in
the companion, including the complete `review_text`. A companion does not adopt
prose, establish world facts, or decide whether a literary judgment is correct.

### Model response

`review_instructions(target_ref, evidence_refs)` describes the model response
contract and the ordered material aliases. The target is `target`; other selected
originals are `evidence-1`, `evidence-2`, and so on. The caller must supply the
corresponding original texts in that order. All references are exact
`creative-records/1` references, including a version ID and SHA-256 digest.

The model returns one JSON object, optionally inside one outer JSON code fence:

```json
{
  "schema_version": "writing-assistant-review-output/1",
  "review_text": "A complete review of the supplied draft and evidence.",
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

Quotes copy literal selected text, including punctuation and whitespace. An
explicit `occurrence` is one-based and counts overlapping matches. It may be
omitted only when the quote occurs once. It is bounded to 4096. The application computes half-open
UTF-8 byte ranges from those quotes; the model need not calculate offsets.

`classification` is one of `confirmed-contradiction`, `uncertainty`, and
`preference`. These are reviewer claims. A claimed contradiction requires at
least one citation; the application checks that citation's exact bytes and
identity, without proving that the passages actually contradict each other.
Missing information or uncertain inference belongs under `uncertainty`;
subjective alternatives belong under `preference`. `impact` is `material` or
`minor`, with a bounded `proposed_change`. Provisional plans and generated
proposals do not establish adopted facts.

A review with no identified concern still supplies a substantive `review_text`,
uses `outcome: "no-concerns"`, and supplies `observations: []`. This records the
reviewer's conclusion within the selected evidence. It does not certify quality
or complete coverage of a larger work. Missing, malformed, unavailable, or
inconsistent feedback cannot become a no-concern conclusion.

### Application validation and recovery

The Python interface is:

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
```

The parser verifies every selected body's digest, each target and citation
reference, exact quote location, observation identity, outcome consistency, and
field bounds. Its `writing-assistant-review-decision/1` result contains the exact
target, resolved spans, original output text and digest, review prose, observations,
and an initially empty choice history. Each observation starts with
`disposition: "proposed"` and `user_choice: null`.

For a selected excerpt, an evidence input may additionally supply
`range: {"byte_start": START, "byte_end": END}`. `text` is the full original,
read locally only to verify its exact reference digest. Quote matching and
occurrence counting use only the selected UTF-8 slice. Citations retain the full
original reference, original byte offsets, and `selected_range`. A quote outside
that slice is unavailable even when it exists elsewhere in the original. Range
boundaries must be UTF-8 boundaries. This local verification does not grant a
provider access to the full original; the caller sends only its selected slice.

`validate_decision` validates a saved companion's structure and original-output
digest. When consuming it for workflow progression, `verify_decision` takes the
same exact originals as the parser and reconstructs the companion from retained
output and choices. A changed version, altered span, or substituted evidence is
refused. Callers retain the companion through their existing immutable record
storage; the parser performs no filesystem or model operation.

The caller supplies authorized feedback decisions to `validate_choice`:

```python
chosen = validate_choice(decision, [{
    "observation_id": "gate-condition",
    "disposition": "rejected",
    "reason": "The user retains this deliberate ambiguity.",
}])
```

`accepted`, `rejected`, and `deferred` record feedback handling. Accepting feedback
does not adopt a revised story. Every changed choice appends to `choices`; the
latest choice also appears on the affected observation. Repeating the same
current choice is idempotent. Rejected concerns and earlier choices remain
available after recovery. The caller owns user authorization and immutable
storage of each resulting companion version.

Durable workflows expose feedback handling through
`workflow decide WORKFLOW_ID REQUEST_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA`.
The request binds the `chapter` and exact `review_decision` reference, supplies the
`observations` choices above, a `reason`, and `progression: "continue"` or
`"apply-policy"`. It preserves the original feedback and saves a new choice
companion. A malformed review can be repaired with
`workflow repair-review WORKFLOW_ID REQUEST_FILE --expected-plan-sha256 SHA --expected-checkpoint-sha256 SHA`;
that request supplies a `reason` and a structured `review_output` object. The
original failed output remains retained. Inspect the returned workflow state
before executing its next prepared task. See [durable workflows](workflows.md)
for progression policy and revision bounds.

Responses are bounded to 131072 UTF-8 bytes, 32 observations, eight citations per
observation, and 64 additional selected materials. The total supplied original
text is bounded to 16777216 bytes. Saved companions are bounded to 524288 bytes
and 128 changed choices. A quote is bounded to 8192 bytes, review prose to 32768
bytes, and each observation, proposed change, and choice reason to 4096 bytes.

Stable errors include `review_decisions_missing`, `invalid_review_output`,
`review_quote_not_found`, `ambiguous_review_quote`, `review_evidence_not_selected`,
`changed_review_reference`, `invalid_review_decision`, `changed_review_decision`,
`invalid_review_choice`, and `unknown_review_observation`. Errors contain no
original passages. Preserve the original output separately when parsing fails;
the caller can inspect it without labeling the failed review as a pass.

The [review decision schema](../schemas/review-decision-v1.schema.json) describes
the saved companion and the model response in `$defs.modelOutput`. Runtime
validation additionally enforces byte identity, span matching, and choice history.
