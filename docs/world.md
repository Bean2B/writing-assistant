# 推进故事 / Developing a story

[中文](#中文) · [English](#english)

## 中文

Agent 通过 `world` CLI，从明确给定的虚构处境中探索人物行动与后果。输入包括人物
眼前的处境、目标和已知信息。

Agent 可以用这些操作：

- 推演人物遇到新问题时可能怎样应对。
- 考虑当前场景之外，其他人物正在做什么。
- 顺着故事里的时间，追踪一个行动的后续影响。
- 保存有用的情节可能性和选定的设定资料，供之后写作参考。

比如，一名旅人错过了离开小镇的最后一班车。动笔之前，可以先考虑他会向谁求助，
对方想得到什么，以及这次耽搁会怎样影响正在等他的人。这些可能性供你判断和取舍，
不必成为固定的结局。

#### 调用 world 操作

项目初始化并启用 World Sandbox 后，Agent 可按下方英文参考中的命令从虚构示例创建 world，
读取 `traveler` 的人物投影，再通过 `advance-time` 推进故事时间。这些操作不调用模型。

在获授权的 AI 任务中，Agent 用 `advance --model MODEL --steps 1` 明确请求人物决策，
将 `MODEL` 换成选定的 Codex 模型。`--steps` 每次允许 1–16 次决策，同时受该次 run
配置的限制。`world status` 用于查看私有运行进度；写作任务应使用获准的投影和明确
选定的材料。输出处理见 [Agent 接入说明](agent-usage.md)。

Agent 在 user 的任务范围内选择获准材料，哪些结果成为故事的一部分由 user 决定。
保存一个设想，不代表它已经在故事里发生。world 只在调用操作时推进，并受 run 配置限制。

#### 旧版本 run

受支持的旧版本 world run 在当前应用中以只读方式打开，可以读取、取得和解析投影、
replay，以及查询已完成的 receipt。旧 run 不能继续 AI 推进、创建 branch、推进时间、
生成新的材料或结算未完成的结果；这些更新操作返回 `legacy_source_read_only`。
原 run 保持原样，不自动迁移。需要开展新的 world 任务时，用当前明确提供的配置创建
新 run。此限制只针对旧 world run，不表示创作记录全部只读。

保存材料的方法见[创作记录](records.md)，写作请求见[使用指南](usage.md)，AI 兼容范围
见 [Codex 支持](codex-support.md)。任务完成后，人物行为是否合理、前后是否连贯、文字
是否合意，仍需要 user 审读。

## English

Agents use the `world` CLI to explore character actions and consequences from
an explicit fictional situation. Inputs describe the characters' present
circumstances, goals, and available information.

An Agent can use these operations to:

- Explore how a character might respond to a new problem.
- Consider what other people might be doing outside the current scene.
- Follow the consequences of an action as time passes in the story.
- Keep possible developments and selected setting notes for later writing.

For example, suppose a traveler misses the last departure from a town. Before
drafting the next scene, you could consider whom they might ask for help, what
that person wants in return, and how the delay affects someone waiting for them.
These are possibilities to assess, rather than a fixed ending to follow.

#### Invoke world operations

With an initialized project and World Sandbox enabled, the Agent can create a
world from the fictional example, read an actor projection, and advance narrative
time without calling a model:

```sh
writing-assistant world --project ../demo-project --run-id town create examples/synthetic/world.json
writing-assistant world --project ../demo-project --run-id town projection --actor traveler --raw
writing-assistant world --project ../demo-project --run-id town advance-time --target 600 --event-limit 8
```

For an authorized AI task, the Agent explicitly requests character decisions:

```sh
writing-assistant world --project ../demo-project --run-id town advance --model MODEL --steps 1
```

Replace `MODEL` with the selected Codex model. `--steps` accepts 1–16 decisions
per call, within the run's configured limits. `world status` describes private
run progress; use permitted projections and explicitly selected material for
writing tasks. See the [Agent interface guide](agent-usage.md) for output handling.

The Agent selects permitted material within the user's task; the user decides
which results become part of the story. Saving a possibility does not make it
an established event. World operations advance only when invoked and remain
bounded by the run configuration.

#### Runs from an earlier version

A world run from a supported earlier version opens read-only. Reading,
projection and resolution, replay, and queries of already completed receipts
remain available. It cannot continue AI advancement, create branches, advance
time, materialize new data, or settle unfinished results; these updates return
`legacy_source_read_only`. The saved run is preserved without automatic migration.
To start new world work, create a new run from an explicit current configuration.
This restriction applies to the old world run, not to creative records generally.

See [creative records](records.md) for keeping useful material and
[usage](usage.md) for writing requests. AI compatibility is described in
[Codex support](codex-support.md). A completed task still needs the user's judgment
about character logic, continuity, and the quality of the writing.
