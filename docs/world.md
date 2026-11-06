# 角色行动推演 / Character action simulation

[中文](#中文) · [English](#english)

## 中文

`world` 操作让 Agent 从明确的虚构处境探索人物行动与后果：人物眼下知道什么、有哪些目标，其他人按日程做了什么，以及时间变化如何影响可选行动。

以下操作示例使用通用虚构配置：Agent 查看一个角色可知的信息，推进日程，再明确请求一次 AI 角色决策。你决定哪些信息可用于后续写作。

### 创建并查看一个虚构场景

先按[安装指南](install.md#中文)初始化 `../demo-project`。从 [world.json 配置示例](../examples/synthetic/world.json)保存完整 JSON 到当前目录的 `world.json`；wheel 安装不自带这个示例目录。示例包含 `traveler`、`companion`、小镇居民、地点、物品、日程和待发生事件。

```sh
writing-assistant config --project ../demo-project --world-sandbox on
writing-assistant world --project ../demo-project --run-id town create world.json
writing-assistant world --project ../demo-project --run-id town projection --actor traveler --raw
```

`create` 以明确配置创建 run。`projection` 返回该人物可见的投影，包含当前版本和 actor 身份；默认 JSON 输出含 `reference` 和 `body`，`--raw` 只输出投影 bytes。创建、查看投影和后面的时间推进都不调用模型。

自定义配置使用 `lotus-continuity-config/2` 和 `policy: "external"`，明确提供 scenario、profiles、actor order 与调用上限。以示例为起点修改虚构数据；用新的 run ID 开展独立尝试。

### 推进时间与人物选择

先让场景内时间推进到第 600 分钟，每次最多处理八个到期事件：

```sh
writing-assistant world --project ../demo-project --run-id town advance-time --target 600 --event-limit 8
```

`--target` 是场景内的目标分钟数，不是等待 600 分钟；不能倒退。结果包含实际 `time`、`target`、`processed`、`remaining_due`。事件预算不足时返回 `paused` 和 `event_budget`，保留尚未处理的事件；检查结果后可明确继续到同一目标。不能只看 target 就认定已经到达。

需要 AI 人物决策时，明确执行：

```sh
writing-assistant world --project ../demo-project --run-id town advance --model MODEL --steps 1
```

将 `MODEL` 换成已选定的 Codex 模型。`--steps` 每次允许 1–16 次人物决策，同时受 run 的 `turn_limit`、`request_limit` 等配置约束。它与单纯推进时间不同，会通过 Codex 请求模型。模型兼容与登录要求见 [Codex 支持](codex-support.md#中文)。World 只在调用操作时推进。

### 选出可供写作的材料

`status` 用于 owner 查看运行进度；写作使用人物可见信息中的明确选择。在当前目录保存 `selection.json`：

```json
[["actor", "location"], ["actor", "coins"]]
```

这个例子只选旅人的地点与钱币数。每条 path 从该 actor 的 `observation` 开始，指向一个 scalar 值，不接受整个对象、wildcard 或重复 path。

```sh
writing-assistant world --project ../demo-project --run-id town projection --actor traveler --purpose world-projection --selection selection.json
writing-assistant world --project ../demo-project --run-id town capture --actor traveler --selection selection.json --operation-id town-setting-1 --title "Traveler before the next scene" > town-setting.json
```

`capture` 把明确选定的投影保存为 Creative Records 的 `setting` 版本，结果含 `ref`、原 `projection_reference` 和 `adopted: false`。它可作为后续请求中明确选择的设定材料；保存这个快照不代表情节已经被采用。

人物默认投影使用 `purpose=actor-projection`，不接受 `--selection`；写作选择使用 `purpose=world-projection` 并要求 selection。投影 reference 绑定准确内容。`resolve` 需要同一 actor、branch、purpose 与 selection，只能解析仍与当前状态匹配的准确 reference；状态改变后可能返回 `stale_projection_reference`。需要长期保留的材料先 `capture`。

### 检查进度与中断

```sh
writing-assistant world --project ../demo-project --run-id town status
writing-assistant world --project ../demo-project --run-id town status --replay
```

`status --replay` 还会核对已保存运行的 replay。两者均不调用模型；返回的 owner 进度不自动成为 writer 可用材料。

若中断后已有可结算的 durable result，可用它原来的 request ID 结算，不重新请求模型：

```sh
writing-assistant world --project ../demo-project --run-id town settle --request-id REQUEST_ID --branch main
```

先检查状态，确认 result 和 request ID；未知结果不能靠反复 `advance` 自动解决。`settle` 只处理已有结果，关闭 World Sandbox 后仍可读取、取得投影和结算已有结果。关闭推进使用 `writing-assistant config --project ../demo-project --world-sandbox off`。

| 错误或状态 | 下一步 |
| --- | --- |
| `sandbox_disabled` | 查询配置；在确实需要新推进时明确启用。 |
| `projection_unavailable`, `invalid_projection_selection` | 检查 actor、branch 和当前 observation 中准确 scalar paths。 |
| `stale_projection_reference` | 读取当前投影并明确重新选择，或使用已保存的历史 capture。 |
| `legacy_source_read_only` | 该旧 run 保留只读；新工作用当前明确配置创建新 run。 |

### 旧 run 与 Python 接入

受支持的旧版本 run 可读取、取得或解析投影、replay，并查询已完成 receipt。它们不能继续 AI 推进、创建 branch、推进时间、生成新材料或结算未完成结果；原 run 不自动迁移。这个限制仅针对旧 world run。

Python 调用方可通过 `writing_assistant.world.service.open_run` 使用 session 的投影、时间推进和保存操作；`session.fork(new_branch_id, parent="main")` 可创建明确的 run branch，保留 parent。这里的 run branch 是一次场景推演的分支，与 Git branch 无关。

继续阅读：[创作记录](records.md#中文) · [写作请求](interface.md#中文) · [任务与恢复](tasks.md#中文) · [隐私](privacy.md#中文)。

## English

The `world` commands let an Agent explore character actions and consequences from an explicit fictional situation: what a person knows, what they want, what others do on a schedule, and how time changes the available choices.

The usage example uses a generic fictional configuration: inspect a character's available information, advance schedules, then explicitly request an AI character decision. You decide which information to use in later writing.

### Create and inspect a fictional situation

Initialize `../demo-project` using [installation](install.md#english). Save the complete [world.json configuration example](../examples/synthetic/world.json) in the current directory as `world.json`; wheel installations do not include that example directory. It contains `traveler`, `companion`, residents, locations, items, schedules, and queued events.

```sh
writing-assistant config --project ../demo-project --world-sandbox on
writing-assistant world --project ../demo-project --run-id town create world.json
writing-assistant world --project ../demo-project --run-id town projection --actor traveler --raw
```

`create` starts a run from explicit configuration. `projection` returns that actor's permitted view with version and actor identity. Default JSON contains `reference` and `body`; `--raw` returns projection bytes alone. Creation, projection, and time advancement make no model call.

Custom configurations use `lotus-continuity-config/2` with `policy: "external"`, an explicit scenario, profiles, actor order, and call bounds. Start from the example's fictional data and use a new run ID for an independent attempt.

### Advance time and character decisions

Move simulated time to minute 600, processing at most eight due events in this call:

```sh
writing-assistant world --project ../demo-project --run-id town advance-time --target 600 --event-limit 8
```

`--target` is an absolute narrative minute, not a wait of 600 minutes; time cannot move backward. Results include actual `time`, requested `target`, `processed`, and `remaining_due`. An exhausted event budget returns `paused` with `event_budget` and preserves unprocessed events. Inspect the result before explicitly continuing toward the same target; the target alone does not mean it was reached.

For an AI character decision, explicitly run:

```sh
writing-assistant world --project ../demo-project --run-id town advance --model MODEL --steps 1
```

Replace `MODEL` with the selected Codex model. `--steps` accepts 1–16 actor decisions per call, within the run's configured `turn_limit`, `request_limit`, and other bounds. Unlike time advancement, this operation requests a model through Codex. See [Codex support](codex-support.md#english) for compatibility and login requirements. A world advances only when an operation is invoked.

### Select material for writing

Use `status` for owner progress. For writing, explicitly select information from an actor's permitted observation. Save `selection.json` in the current directory:

```json
[["actor", "location"], ["actor", "coins"]]
```

This selects only the traveler's location and coin amount. Each path starts at the actor's `observation` and ends at a scalar value. Whole objects, wildcards, and duplicate paths are invalid.

```sh
writing-assistant world --project ../demo-project --run-id town projection --actor traveler --purpose world-projection --selection selection.json
writing-assistant world --project ../demo-project --run-id town capture --actor traveler --selection selection.json --operation-id town-setting-1 --title "Traveler before the next scene" > town-setting.json
```

`capture` saves the explicit selected projection as a Creative Records `setting` version. Its result includes `ref`, the original `projection_reference`, and `adopted: false`. Select that setting as material in a later request. Saving the snapshot leaves adoption into a manuscript to the user.

Default actor views use `purpose=actor-projection` and do not accept `--selection`. Writer selections use `purpose=world-projection` and require selection. A projection reference fixes exact content. `resolve` requires the same actor, branch, purpose, and selection and only resolves a reference still matching current state; later changes can return `stale_projection_reference`. Use `capture` for material you need to retain historically.

### Inspect progress and interruptions

```sh
writing-assistant world --project ../demo-project --run-id town status
writing-assistant world --project ../demo-project --run-id town status --replay
```

`status --replay` additionally verifies the saved run's replay. Neither command calls a model. Owner progress does not automatically become writer material.

If an interrupted run already has a durable result ready to settle, use its original request ID without requesting another model response:

```sh
writing-assistant world --project ../demo-project --run-id town settle --request-id REQUEST_ID --branch main
```

Inspect state first to confirm the result and request ID. Repeated `advance` calls do not resolve an unknown outcome. `settle` processes existing results only. Reads, projections, and settlement remain available with World Sandbox off. Disable advancement with `writing-assistant config --project ../demo-project --world-sandbox off`.

| Error or state | Next step |
| --- | --- |
| `sandbox_disabled` | Inspect configuration; explicitly enable it when new advancement is intended. |
| `projection_unavailable`, `invalid_projection_selection` | Check actor, branch, and exact scalar paths in the current observation. |
| `stale_projection_reference` | Read the current projection and explicitly select again, or use a saved historical capture. |
| `legacy_source_read_only` | Preserve this old run read-only; create a new run from explicit current configuration for new work. |

### Earlier runs and Python integration

Supported earlier-version runs allow reading, projection and resolution, replay, and queries of completed receipts. They cannot continue AI advancement, create branches, advance time, materialize new data, or settle unfinished results. They are preserved without automatic migration; this restriction applies to old world runs only.

Python callers can use `writing_assistant.world.service.open_run` for session projection, time advancement, and capture operations. `session.fork(new_branch_id, parent="main")` creates an explicit run branch while preserving its parent. A run branch describes a simulation run and is separate from a Git branch.

Continue with [Creative Records](records.md#english), [writing requests](interface.md#english), [tasks and recovery](tasks.md#english), or [privacy](privacy.md#english).
