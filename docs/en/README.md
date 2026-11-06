<h1 align="center">Writing Assistant</h1>

<p align="center">
  <strong>A local AI writing assistant for Agents</strong><br>
  Develop ideas, draft, review and revise within one writing project.
</p>

<p align="center">
  <a href="https://github.com/Bean2B/writing-assistant/releases/tag/v0.1.1"><strong>Download v0.1.1</strong></a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#features">Features</a> ·
  <a href="../agent-usage.md#english">Agent guide</a> ·
  <a href="../../README.md">中文</a>
</p>

<p align="center">
  macOS (Apple Silicon) · Python 3.12 · Apache-2.0 · Developed by Codex
</p>

Writing Assistant gives Agents writing operations and a place to manage a project. You set the creative direction; the Agent uses the local CLI to organize material, prepare tasks, generate drafts and handle review feedback. Settings, draft versions and task progress stay on your machine so they can be retrieved when work continues.

The current version runs AI writing tasks through **Codex CLI**. Check the [compatibility requirements](../codex-support.md#english) before starting. Saving, finding and organizing records work offline.

## Features

<table>
  <tr>
    <td width="50%" valign="top"><strong>✍️ Ideas and writing</strong><br>Generate concepts, scene plans and prose from your requirements, or review and revise an existing draft.</td>
    <td width="50%" valign="top"><strong>📖 Chapter workflows</strong><br>Organize planning, drafting and review by chapter. Save phase progress so an Agent can continue existing work.</td>
  </tr>
  <tr>
    <td valign="top"><strong>🗂️ Creative records</strong><br>Save ideas, settings and drafts. Search originals, inspect revision history and bookmark a version for continuation.</td>
    <td valign="top"><strong>🧭 Characters and setting</strong><br>Record character locations, relationships and knowledge. Select relevant settings and earlier prose for a chapter.</td>
  </tr>
  <tr>
    <td valign="top"><strong>🧩 Writing techniques</strong><br>Choose guidance for interdependent characters, changing knowledge, personal tradeoffs, action outcomes and recurring details.</td>
    <td valign="top"><strong>🎭 Character action simulation</strong><br>Request character decisions, advance schedules and state, and select character-visible information for writing.</td>
  </tr>
</table>

## Using it in a writing project

### Start with an idea or continue an existing draft

Give the Agent your genre, characters, tone and length requirements. It can use the application to develop concepts and scene plans before drafting. Existing prose can also supply material for continuation, review or revision. Each task retains its inputs and outputs so you can revisit the requirements and versions it used.

[Writing tasks](../tasks.md#english) · [Request format](../interface.md#english)

### Keep chapter work in a clear sequence

A chapter workflow organizes planning, prose and review, links earlier results and records progress. The Agent inspects and executes the next task; the application stores results and prepares later phases. Review observations can be accepted, rejected or deferred. You decide which text to adopt.

[Chapter workflows](../workflows.md#english) · [Review decisions](../review-decisions.md#english)

### Find the material you need as the project grows

Creative records retain originals and revisions. Story state tracks characters, relationships, locations and knowledge. Story context assembles selected settings and earlier prose for a task. The Agent can retrieve and select material as needed instead of relying on a retelling of the entire work at every handoff.

[Creative records](../records.md#english) · [Characters and setting](../story-state.md#english) · [Writing context](../story-context.md#english)

### Choose techniques for the current task

Built-in technique packs provide guidance you can combine: connect character choices through shared tasks, check what a character can know, give actions concrete consequences, or make recurring details affect later developments. The Agent can inspect applicability and select techniques for writing and review.

[Techniques and usage](../techniques.md#english) · [Character action simulation](../world.md#english)

## Quick start

**1. Install the application.** Download the [v0.1.1 wheel](https://github.com/Bean2B/writing-assistant/releases/download/v0.1.1/writing_assistant-0.1.1-py3-none-any.whl) and follow the [installation guide](../install.md#english) to verify and install it. You can also give Codex this request:

> Install Writing Assistant using https://github.com/Bean2B/writing-assistant/blob/main/docs/install.md#english. Check compatibility and existing projects first, then agree on project and data directories with me. Preserve existing content and explain how to begin when installation is complete.

**2. Give the Agent the usage guide.** Share the [Agent guide](../agent-usage.md#english) and your project path. Operations are available through a local CLI; some material-management features also provide a Python API.

**3. Set your writing goal.** For a new project, you could use this request:

> Use Writing Assistant to help me develop a new work. First agree on the genre, protagonist, tone and length with me. Then organize the settings and chapter plan, and wait for my confirmation before drafting prose. Keep the material in the specified local project.

This is an example instruction. You and the Agent handle discussion and choices; the application executes explicit tasks and stores project content.

## FAQ

<details>
<summary><strong>Do I need to operate the command line myself?</strong></summary>

An Agent with local command execution can follow the guides for you. You provide creative direction, read the results and make choices. You can also use the CLI directly. See [Codex support](../codex-support.md#english) for the current AI execution path and compatibility requirements.

</details>

<details>
<summary><strong>Are manuscripts uploaded or shared with the developers?</strong></summary>

The application stores creative data in local directories you choose. It collects no usage data and has no telemetry, automatic uploads or network synchronization. Executing an AI task sends relevant material through Codex to its configured model service. Your inputs and creative results remain yours. See [Privacy](../privacy.md#english).

</details>

<details>
<summary><strong>Can interrupted work continue? How do I back it up?</strong></summary>

Tasks and chapter workflows save their progress. After an interruption, ask the Agent to inspect existing state and results before deciding whether to continue or complete local recovery. Back up project configuration and the complete data directory with writes stopped. See [Usage and recovery](../usage.md#english).

</details>

<details>
<summary><strong>Which systems and models are supported?</strong></summary>

The current version supports Apple Silicon macOS, Python 3.12 and the [listed Codex CLI versions](../codex-support.md#english). The model must be available to your Codex account and explicitly selected for the task. The application does not automatically inherit the current conversation's model settings.

</details>

## Documentation

| Goal | Start here |
| --- | --- |
| Install, download or upgrade | [Install](../install.md#english) · [Downloads and upgrades](../release.md#english) |
| Use the application from an Agent | [Agent guide](../agent-usage.md#english) · [Request format](../interface.md#english) |
| Write, continue and review | [Tasks](../tasks.md#english) · [Workflows](../workflows.md#english) · [Review decisions](../review-decisions.md#english) |
| Manage material, settings and techniques | [Records](../records.md#english) · [Story state](../story-state.md#english) · [Context](../story-context.md#english) · [Techniques](../techniques.md#english) · [Character actions](../world.md#english) |
| Resolve a problem or restore data | [Usage and recovery](../usage.md#english) · [Diagnostics](../diagnostics.md#english) · [Codex support](../codex-support.md#english) |

## Feedback and license

Report problems and suggestions in [GitHub Issues](https://github.com/Bean2B/writing-assistant/issues). Include the version and short reproduction steps without manuscripts, private material or credentials. Pull requests are currently reserved for developer maintenance. See the [changelog](../../CHANGELOG.md#english) for version information.

This project is **developed by Codex** and licensed under [Apache-2.0](../../LICENSE). Copyright 2026 Bean2B. The software license does not license your creative content.
