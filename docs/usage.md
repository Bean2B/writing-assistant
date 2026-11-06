# CLI 操作与恢复 / CLI operations and recovery

[中文](#中文) · [English](#english)

## 中文

本页列出供 Agent 调用的本地 CLI 操作。user 提供目标，授权文件访问及 AI 任务，并决定
内容采用。安装见 [README](../README.md#中文)，调用契约见 [Agent 接入说明](agent-usage.md)。
下方英文参考中的命令假定 Agent 的执行环境已将 `writing-assistant` 加入 `PATH`；否则使用安装路径，
例如 `.venv/bin/writing-assistant`。
从源码目录调用时，将命令入口替换为
`PYTHONPATH=src python3.12 -B -m writing_assistant`。若报
`ModuleNotFoundError: No module named 'writing_assistant'`，先核对源码目录及这条调用方式。

先用 `init` 创建项目，再用 `config` 查看已保存的设置。数据目录须与源码和安装环境
分开。设置修改会在下一个任务开始时生效，不会中断正在运行的任务。
初始化时可同时指定 `--writing-mode none --world-sandbox off`；省略时沿用 Lotus 与
World Sandbox 默认开启的设置。

保存前先准备一个 `fragment.txt` 文本文件。下方英文参考中的例子会把保存结果写入 `first.json`，
之后可以用它找回同一个版本。`recent` 查看最近的记录，`search` 搜索内容，`read`
把原文写入新的 `recovered.txt`，不会覆盖已有文件。原文的换行等字节保持原样。
修订和书签用法见[创作记录](records.md)。

Agent 发起写作时，修改示例请求中的 `request`，填入本次要求，并使用对应的
`project_id` 和新的 `request_id`。`capabilities` 发现可用操作；`task prepare` 冻结材料，
`task inspect` 查询状态；将返回的 digest 传给 `task execute` 后才会调用 Codex。
`task reconcile` 根据已保存证据完成本地恢复，不调用模型。旧版顶层 `prepare/execute`
继续保留临时准备和立即执行行为。引用旧稿的方法见[请求格式](interface.md)。

写作、审读和修改分别发起。需要审读时，将 `phase` 设为 `reader-review` 或
`continuity-review`，并选定当前稿件；修改时须同时提供稿件和反馈。生成结果由 user
审读和取舍，写完一稿不会自动开始下一轮。

遇到错误时，先按下方英文参考表核对参数、文件、版本引用和 Codex 环境。占用中的任务应等待
其结束，不要删除仍在使用的 lock。结果不明时保留输入和已有记录，先确认保存了什么；
不要只换一个请求 ID 就重发同一任务。超时或本地进程结束，也不证明远端服务已经停止。
确认失败原因并修正后，再重试受影响的操作。

备份前等待本地写入结束，复制完整数据目录，保留中断保存留下的文件；另存项目的
`.writing-assistant/config.json`、确切 record/bookmark/diagnostic references 和应用版本。
目录外的引用材料还须备份原文件并保留合法访问条件，reference 不能代替原件。

恢复时先停止本地写入，把现有目录与晚于备份的收据另行保留。不要删除 live lock；本地
进程停止不代表后端停止。按下方英文参考中的 `copytree` 示例，把完整备份复制到配置所指、当前不存在
的绝对路径；若项目配置也丢失，将其保存文件恢复到原项目位置。不要合并旧备份到 live
目录，也不要原位覆盖来保留 inode。沿用获授权的 OS 账号及备份权限，不改写 task plan、
绕过 ownership 检查或调整权限来伪装 root authority。

先用下方英文参考中的命令读回确切原文、bookmark 和 diagnostic revision，核对原文 SHA-256 与保存的
reference，保留中断事务直到确认其状态。`records rebuild-index` 只重建导航索引，不修复
损坏的原文。目录副本具有新的物理 root identity；原文、bookmark 和诊断可读，旧 durable
task 的 `inspect`、`execute`、`reconcile` 则可能返回 `authority_changed`。其保存的 plan、
输入和输出仍可通过确切 record reference 读取。普通 task 操作需要原 root authority，
执行及 reconciliation 还保留原 configuration/policy 校验；不支持透明迁移复制后的 task
或跨机器 task。

旧备份缺少某次 dispatch 的记录，不能证明它从未执行。不要执行旧快照中看似 prepared
的 task，不要给结果未知或执行过的 task 换 ID 重发，也不要编辑其 identity。先核查更新
历史及未决外部效果；恢复不会自动触发新创作、采用或重派发。

若曾使用 World Sandbox，完整快照须包含 `world-sandbox/PROJECT_ID/runs/` 下的目录、
bundle、lock 和中断写入文件，并另存项目配置、兼容的应用及 source 版本、run ID、
request/branch ID 和确切 projection reference。原始 `external` policy 创建配置已保存在
bundle 内；打开既有 run 使用该 bundle，无须再次调用 `world create` 或读取创建文件。
不要从初始 scenario 重建 run 来恢复后续状态，也不要改写 source binding。

在同一获授权本地 owner 下，用新调用执行下方英文参考中的 world 恢复命令。解析投影时沿用保存的
actor、branch、purpose 和 selection，并核对返回字节与保存的 digest；例子使用默认
`actor-projection`。`status --replay` 校验已保存状态，不调用模型。明确调用 `settle` 只
完成已保存结果，或返回同一个已完成 receipt；不分配新 request、不调用模型，World
Sandbox 关闭时也可使用。遇到 `uncertain_request`、`settlement_not_ready` 或
`settlement_unavailable`，保留快照和较新的证据，不调用 `advance` 来恢复。旧快照缺少
后续 dispatch，仍不足以证明可以重发。受支持的旧 source run 沿用[只读限制](world.md#runs-from-an-earlier-version)，
不能结算未完成结果。这些 native world 规则不向目录副本转移 durable writing-task authority。

卸载使用同一环境的 `python -m pip uninstall writing-assistant`，重装可用
`python -m pip install --no-index --no-deps WHEEL`；两者都保留独立数据目录。应用版本回退
不等于数据回退，也不会取消后端工作或撤销外部效果。不要用不兼容的旧版打开较新格式，
或静默降级数据。删除创作内容仍是另一项操作。

## English

These are local CLI operations for the calling Agent. The user supplies the goal,
authorizes access and AI tasks, and decides content adoption. Start with the
installation steps in the [README](../README.md) and the invocation contract in
the [Agent interface guide](agent-usage.md). The commands below assume the Agent's
environment has `writing-assistant` on `PATH`; otherwise use the installed path,
such as `.venv/bin/writing-assistant`.
From the source checkout root, use
`PYTHONPATH=src python3.12 -B -m writing_assistant` in place of `writing-assistant`.
If Python reports `ModuleNotFoundError: No module named 'writing_assistant'`,
check this source invocation and the current directory before retrying.

#### Set up a project

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant config --project ../demo-project
```

Keep the data directory outside the source and installation. `config` shows the
saved settings. Setting changes apply at the next task boundary; they do not
interrupt a task already in progress.
`init --writing-mode none --world-sandbox off` selects both initial settings
atomically; omitted options retain the Lotus/World Sandbox defaults.

#### Save and find your writing

Create a plain text file named `fragment.txt`, then save it:

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id note-001 --title "First idea" > first.json
writing-assistant records --project ../demo-project recent
writing-assistant records --project ../demo-project search idea --ignore-case
writing-assistant records --project ../demo-project read first.json --output recovered.txt
```

`first.json` identifies the saved version. Keep it if you want to return to that
exact text. `recovered.txt` must be a new file; reading does not overwrite an
existing file. Saving and reading preserve the original bytes, including line
endings. See [creative records](records.md) for revisions and bookmarks.

#### Request writing or feedback

Start with the [example request](../examples/synthetic/request.json). Change
`request` to describe the task, use your project's `project_id`, and give each
new task a new `request_id`.

```sh
writing-assistant capabilities --project ../demo-project
writing-assistant task --project ../demo-project prepare examples/synthetic/request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant doctor
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

Replace `MODEL` with the selected model and copy `TASK_ID`/`PLAN_SHA256` from the
prepared status. `task prepare` freezes selected input without calling a model.
`doctor` checks Codex compatibility. `task execute` sends the inspected task and
saves its result locally. [Durable tasks](tasks.md) describes bounded context,
exact-reference reads and saved-byte reconciliation. Legacy top-level
`prepare/execute` keep their ephemeral prepare/immediate-execution behavior.
Adding earlier passages requires selecting and binding their saved versions;
see [request format](interface.md).

Writing, review, and revision are separate tasks. A finished draft does not
start a review automatically. For feedback on a draft, use `reader-review` or
`continuity-review` as the request's `phase` and select the current draft.
A revision needs the draft and the feedback to act on. Generated text remains
available for the user to review and choose; it is not automatically adopted.

#### When something goes wrong

| Result | What to do |
| --- | --- |
| `invalid_arguments`, `invalid_model`, `invalid_timeout` | Check the command's `--help`. A timeout must be greater than 0 and no more than 600 seconds. |
| `codex_missing`, `capability_unsupported` | Run `doctor` and check [supported versions](codex-support.md). |
| `data_source_overlap`, `invalid_file`, `local_input_error`, `already_exists` | Check the input file, directory separation, and output name. Use regular files and physical directory paths. |
| `busy`, `owner_busy` | Let the current operation finish. Do not delete a live lock. |
| `not_available`, `parent_conflict` | Check the selected version and permissions. Choose the intended version explicitly. |
| `task_not_found`, `task_conflict`, `stale_plan` | Inspect the original task and exact plan/configuration; preserve its identity and saved bytes. |
| `codex_unknown`, `outcome_unknown`, `uncertain_request` | Keep the input and existing records. Inspect what was saved before starting more work. The tool does not automatically resend an uncertain request. |

A timeout or interruption does not prove that the remote service stopped its
work. Check the saved result and diagnostics; do not change a request ID simply
to resend a task whose outcome is unknown. After a confirmed failure, correct
the cause before trying the affected operation again.

Use explicit [local diagnostic cases](diagnostics.md) to preserve selected evidence,
check applicability, inspect invalidation and recover interrupted case publication.
Confirmed applicable blockers affect their operation; advisory cases do not pause
unrelated work. Optional history damage reports degraded coverage.

#### Task duration records

Durable tasks expose optional `operation_timings` in execute, inspect and reconcile
results. Each entry contains an exact saved record reference and `elapsed_seconds`
measured with a monotonic clock from entry into that local API operation until its
core result handling ends. This includes qualification, local execution, raw
capture, materialization and final result receipt writes that actually occurred.
The timing record's own publication, response serialization/delivery and time
spent waiting between separate user/Agent operations are excluded. The scope is
`local_task_operation_before_timing_persistence`; it is not provider compute time,
network-only latency or a total across separate invocations.

The application retains at most three first observations per task: `preflight`
for a returned blocker or qualification failure before reservation, `execute` for
an outcome after reservation, and `reconcile` for a recovery operation. Each is
marked `sample: first_observed`. Its `outcome` and optional `code` describe that
sample, which can differ from the current task status. Duplicate calls reuse the
saved measurements; they do not overwrite failures or add timing records.

Early invalid or unauthorized requests do not create timing records. A hard
interruption can leave no completed measurement; a later recovery records only
its own duration. Historical tasks without timing records remain readable and
their past durations stay unknown. If ordinary timing-storage I/O fails after
core work, the result reports `timing_recording.status: unavailable`; inspect the
existing task before acting again. Authority and integrity failures remain errors.
Existing adapter-scoped elapsed time, reported usage and unknown cost keep their
separate meanings. No missing usage or cost is converted to zero.

#### Back up and restore local data

1. Wait for local writers to finish before taking a snapshot. Copy the **entire
   data directory**, including interrupted-save files. Separately keep the
   project's `.writing-assistant/config.json`, exact record/bookmark/diagnostic
   references, and application version. External referenced materials need their
   original files and authorized access too; a reference is not a backup of them.
2. Before restoration, stop local writes and preserve the current data directory
   separately, including receipts newer than the backup. Do not delete a live
   lock. A local process stop does not confirm backend stop, and an older snapshot
   can omit a later dispatch intent or result.
3. With a compatible application, restore to the configured absolute `data_dir`
   only after that destination is absent. For example, substitute the actual
   paths in this copy; `copytree` refuses an existing destination:

   ```sh
   python3.12 -c 'import shutil; shutil.copytree("/backup/demo-data", "/configured/demo-data")'
   ```

   Retain the preserved current directory until recovery is checked. Do not merge
   an old snapshot into a live directory or overwrite files in place to retain
   its inode. If project configuration was also lost, restore its saved file to
   the original project path; it must name the intended project and data path.
   Use the same authorized OS account and preserve the backup's permissions. Do
   not rewrite task plans, weaken ownership checks, or change permissions to make
   an unrelated data root look authorized.
4. Verify saved references before any new writing. Use a new output filename,
   compare its SHA-256 with the saved record reference, and compare the bookmark's
   selected reference and diagnostic revision with the retained references:

   ```sh
   writing-assistant config --project ../demo-project
   writing-assistant records --project ../demo-project read first.json --output restored.txt
   writing-assistant records --project ../demo-project read-bookmark --bookmark bookmark-ref.json
   writing-assistant diagnostics --project ../demo-project show case-ref.json
   ```

   Use only references present in your snapshot; these reads do not generate
   writing or adopt content. Inspect preserved interrupted transactions rather
   than discarding them. `records rebuild-index` repairs only navigation after
   originals are verified; it does not restore missing or damaged text.

A copied data directory has a new physical root identity. Records, exact
bookmarks and diagnostic cases can be read through the restored project's local
owner scope, but old durable task `inspect`, `execute` and `reconcile` calls can
return `authority_changed`, even at the same path with identical file bytes.
Their saved plans/input/output remain readable as records using their exact
references. Normal task operations require the original root authority;
execution/reconciliation also retain their frozen configuration and policy
checks. Transparent copied-root or cross-machine task migration is unsupported.

Restoration does not resend a task. Do not execute an apparently prepared task
from an older snapshot, change an uncertain/executed task's ID to resend it, or
edit its saved identity. First account for newer receipts and unresolved external
effects; missing evidence in the snapshot does not prove no dispatch occurred.
New creative work requires its own authorization and is not triggered by restore.

If World Sandbox was used, the complete snapshot must include its
`world-sandbox/PROJECT_ID/runs/` directories, bundles, locks and interrupted-write
files. Keep the saved project configuration, compatible application/source
version, run IDs, request/branch IDs and exact projection references as well.
The original external-policy creation configuration is embedded in each bundle;
opening an existing run uses that bundle and does not require `world create` or
the creation file again. Do not recreate a run from its initial scenario to
recover its later state, or replace its source binding.

Open a restored run in a fresh invocation under the same authorized local owner:

```sh
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID status --replay
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID resolve projection-ref.json --actor SAVED_ACTOR_ID --branch SAVED_BRANCH_ID
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID settle --request-id SAVED_REQUEST_ID --branch SAVED_BRANCH_ID
```

Use the exact retained actor, branch, purpose and selection when resolving a
projection; the example assumes the default actor-projection purpose. Compare
the returned bytes with its retained digest. `status --replay` validates the
saved world state without a model. Explicit `settle` completes only an existing
saved result, or returns the same completed receipt; it does not allocate a new
request or call a model and remains available when World Sandbox is off.
`uncertain_request`, `settlement_not_ready` or `settlement_unavailable` requires
preserving the snapshot and newer evidence, without calling `advance` to recover
it. A snapshot missing a later dispatch remains insufficient evidence to resend.
Supported earlier-source runs retain their [read-only limits](world.md#runs-from-an-earlier-version),
including refusal to settle unfinished results. These native world rules do not
transfer durable writing-task authority to a copied root.

#### Remove or roll back the application

Uninstall from the same environment with
`python -m pip uninstall writing-assistant`. To reinstall a saved wheel, use
`python -m pip install --no-index --no-deps WHEEL`. Both leave the separate data
directory in place. Application rollback does not roll back data, cancel backend
work or reverse external effects. Do not open newer stored formats with an
incompatible older application or silently downgrade them. Deleting your writing
is a separate action.
