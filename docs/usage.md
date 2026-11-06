# 使用与恢复 / Usage and recovery

[中文](#中文) · [English](#english)

## 中文

本页用于完成基本操作，以及在出错或恢复备份时找回准确内容。首次安装见[安装指南](install.md#中文)，Agent 的操作方式见 [Agent guide](agent-usage.md#中文)。命令假定 `writing-assistant` 已在 `PATH`；否则使用安装环境中的完整可执行路径。

### 创建项目并保存文字

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant config --project ../demo-project
```

创作数据与源码、安装目录分开。已有项目先查看 config，无须再次 init。默认 `lotus` 与 World Sandbox 开启；Direct Mode 初始化加 `--writing-mode none --world-sandbox off`。之后的 config 修改在下一任务边界生效，不中断正在执行的任务。

准备 `fragment.txt`，然后保存与读取同一版本：

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id note-001 --title "First idea" > first.json
writing-assistant records --project ../demo-project recent
writing-assistant records --project ../demo-project search idea --ignore-case
writing-assistant records --project ../demo-project read first.json --output recovered.txt
```

`first.json` 保存准确版本引用；`recovered.txt` 必须尚不存在。原文读取保留换行等 bytes。修订、查找与书签见[创作记录](records.md#中文)。

### 发起写作

将[示例请求](../examples/synthetic/request.json)保存为本地 `request.json`，填写本次要求、匹配的 `project_id` 和新 `request_id`：

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

将 `MODEL` 换成选定模型，从返回值复制 task ID 与 digest。只有 execute 调用模型；准备与查看不调用。审读与返修是单独阶段；多章顺序交给 [workflow](workflows.md#中文)维护。详见[请求格式](interface.md#中文)和[可恢复任务](tasks.md#中文)。

从源码根目录调用时，可用 `PYTHONPATH=src python3.12 -B -m writing_assistant` 替换命令名。遇到 `ModuleNotFoundError: No module named 'writing_assistant'`，核对源码根目录、`PYTHONPATH=src` 与 Python 3.12。

### 错误处理

| 错误 | 处理方式 |
| --- | --- |
| `invalid_arguments`、`invalid_model`、`invalid_timeout` | 查看对应 `--help`；timeout 必须大于 0 且不超过 600 秒。 |
| `codex_missing`、`capability_unsupported` | 运行 doctor，并核对 [Codex 支持](codex-support.md#中文)。 |
| `data_source_overlap`、`invalid_file`、`local_input_error`、`already_exists` | 核对目录分离、普通输入文件与新的输出文件名。 |
| `busy`、`owner_busy` | 等待当前操作结束，不删除 live lock。 |
| `not_available`、`parent_conflict` | 核对访问条件与准确版本，保留已生成内容。 |
| `task_not_found`、`task_conflict`、`stale_plan` | 查看原 task、plan 与配置，不替换原身份。 |
| `codex_unknown`、`outcome_unknown`、`uncertain_request` | 保留输入与记录，先确认已保存结果，勿换 ID 重发。 |
| `output_contract_violation` | 写入可能已发生，先 inspect 返回引用对应的对象。 |

同时保留 exit code、stdout 与 stderr；前置失败后停止依赖操作。Timeout 或本地进程结束不证明远端停止。确认原因后修正受影响操作；已有不确定 attempt 仍不能再次 dispatch。需要留存排查结果时，使用明确选定证据的[本地诊断](diagnostics.md#中文)。

### Task 耗时记录

Task 的 `operation_timings` 可包含最多三项 `sample: first_observed`：reservation 前的 `preflight`、reservation 后的 `execute`、本地恢复的 `reconcile`。每项保留准确 record reference、单调时钟 `elapsed_seconds`、该次 `outcome` 和可选 `code`。这次观察可能早于当前 task 状态；重复调用复用原测量，不覆盖首次失败。

Scope `local_task_operation_before_timing_persistence` 从本地 API 入口计到核心结果处理结束，包含实际发生的资格检查、执行、capture、materialization 与 result receipt 保存。不含计时记录自身保存、响应序列化/传输，以及两次操作之间的等待；也不是 provider 计算或单独网络耗时。

提前无效请求、硬中断和历史 task 可能没有计时，缺失值保持未知。`timing_recording.status: unavailable` 表示计时保存失败，不撤销已完成效果，先 inspect。Adapter 耗时、provider usage 与 unknown cost 有各自范围，见 [Codex 支持](codex-support.md#中文)。

### 备份与恢复本地数据

1. 等待本地写入结束，复制**整个数据目录**，包括中断保存文件。另存项目的 `.writing-assistant/config.json`、准确 record/bookmark/diagnostic references 与应用版本。目录外的引用材料需原文件与合法访问条件，reference 不能代替备份。
2. 恢复前停止本地写入，另行保留当前目录和晚于备份的收据。不要删除 live lock。旧快照可能缺少后续 dispatch 或结果，不能据此认定从未执行。
3. 使用兼容应用，把完整备份恢复到配置指定且**尚不存在**的绝对 data path；不要合并到 live 目录或原位覆盖。下面的 `copytree` 会拒绝已有目标，先替换为实际路径：

   ```sh
   python3.12 -c 'import shutil; shutil.copytree("/backup/demo-data", "/configured/demo-data")'
   ```

   项目配置也丢失时，恢复到原项目位置。沿用获准 OS 账号和备份权限，不改 task plan、ownership 检查或权限来伪装数据目录身份。
4. 新调用读回保存的引用，核对 SHA-256、bookmark 选择与 diagnostic revision：

   ```sh
   writing-assistant config --project ../demo-project
   writing-assistant records --project ../demo-project read first.json --output restored.txt
   writing-assistant records --project ../demo-project read-bookmark --bookmark bookmark-ref.json
   writing-assistant diagnostics --project ../demo-project show case-ref.json
   ```

   只使用备份中实际存在的引用，`restored.txt` 必须是新文件。保留当前目录与中断事务，直到核对完成。`records rebuild-index` 只重建导航，不恢复缺失或损坏原文。

目录副本有新的物理 root identity。Records、bookmark 和诊断可在恢复项目的本地 owner scope 下读取；旧 durable task 的 inspect/execute/reconcile 可能返回 `authority_changed`，即使路径与 bytes 相同。Plan、输入和输出仍可按准确 record reference 读取。Task 操作要求原 root authority，execute/reconcile 还检查冻结配置与策略；不支持透明的目录副本或跨机器 task 迁移。

不要执行旧备份中看似 prepared 的 task，或给未知/已执行 task 换 ID 重发。先核对更新历史与未决外部效果。恢复不自动发起创作或采用。

### 恢复 World Sandbox

完整备份还应包含 `world-sandbox/PROJECT_ID/runs/` 下的 bundle、lock 与中断文件，并保留配置、兼容应用/source 版本、run/request/branch ID 与准确 projection reference。原 external-policy 配置已保存在 bundle，恢复既有 run 无须再次 `world create`，也不能从初始 scenario 重建后续状态。

```sh
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID status --replay
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID resolve projection-ref.json --actor SAVED_ACTOR_ID --branch SAVED_BRANCH_ID
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID settle --request-id SAVED_REQUEST_ID --branch SAVED_BRANCH_ID
```

使用原 owner 与准确 actor、branch、purpose、selection，核对投影 bytes 与 digest；示例为默认 `actor-projection` purpose。Replay 不调用模型。Settle 只完成已保存结果或返回同一完成 receipt，不分配新 request、不调用模型，World Sandbox 关闭时也可用。

`uncertain_request`、`settlement_not_ready`、`settlement_unavailable` 要求保留快照与更新证据，不用 advance 恢复。受支持的旧 source run 保持[只读限制](world.md#earlier-runs-and-python-integration)，不能结算未完成结果。World 恢复规则不向副本转移 writing-task authority。

### 卸载或回退应用

在原安装环境使用 `python -m pip uninstall writing-assistant`；重新安装保存的 wheel 使用 `python -m pip install --no-index --no-deps WHEEL`。独立数据目录会保留。应用回退不回退数据、取消远端工作或撤销外部效果；不要用不兼容旧版打开新格式。删除创作数据是单独操作。

## English

Use this page for basic operations and recovering exact content after errors or backup restoration. Start with [installation](install.md#english) and the [Agent guide](agent-usage.md#english). Commands assume `writing-assistant` is on `PATH`; otherwise use the full executable path in the installation environment.

### Set up a project

```sh
writing-assistant init --project ../demo-project --data-dir ../demo-data --project-id demo
writing-assistant config --project ../demo-project
```

Keep creative data outside source and installation directories. Inspect config for an existing project instead of initializing it again. Defaults are `lotus` and World Sandbox enabled; add `--writing-mode none --world-sandbox off` to initialize Direct Mode. Later config changes apply at the next task boundary without interrupting running work.

### Save and find your writing

Prepare `fragment.txt`, then save and read the same version:

```sh
writing-assistant records --project ../demo-project save fragment.txt --operation-id note-001 --title "First idea" > first.json
writing-assistant records --project ../demo-project recent
writing-assistant records --project ../demo-project search idea --ignore-case
writing-assistant records --project ../demo-project read first.json --output recovered.txt
```

`first.json` retains the exact version reference. `recovered.txt` must not exist. Reading preserves original bytes, including line endings. See [creative records](records.md#english) for revision, search and bookmarks.

### Request writing or feedback

Save the [example request](../examples/synthetic/request.json) locally as `request.json`, then set the task, matching `project_id` and new `request_id`:

```sh
writing-assistant task --project ../demo-project prepare request.json --model MODEL
writing-assistant task --project ../demo-project inspect TASK_ID
writing-assistant task --project ../demo-project execute TASK_ID --expected-plan-sha256 PLAN_SHA256
```

Replace `MODEL` with the selected model and copy the returned task ID and digest. Only execute calls the model. Reviews and revisions are separate phases; [workflows](workflows.md#english) maintain multi-chapter order. See [request format](interface.md#english) and [durable tasks](tasks.md#english).

From the source checkout root, replace the executable with `PYTHONPATH=src python3.12 -B -m writing_assistant`. For `ModuleNotFoundError: No module named 'writing_assistant'`, check the checkout root, `PYTHONPATH=src` and Python 3.12.

### When something goes wrong

| Error | Action |
| --- | --- |
| `invalid_arguments`, `invalid_model`, `invalid_timeout` | Read the command's `--help`; timeout must be greater than 0 and at most 600 seconds. |
| `codex_missing`, `capability_unsupported` | Run doctor and check [Codex support](codex-support.md#english). |
| `data_source_overlap`, `invalid_file`, `local_input_error`, `already_exists` | Check separate directories, regular input files and a new output filename. |
| `busy`, `owner_busy` | Wait for the current operation; do not delete a live lock. |
| `not_available`, `parent_conflict` | Check access and the exact selected version; retain generated content. |
| `task_not_found`, `task_conflict`, `stale_plan` | Inspect the original task, plan and configuration; preserve its identity. |
| `codex_unknown`, `outcome_unknown`, `uncertain_request` | Keep inputs and records, inspect saved results and do not resend under a new ID. |
| `output_contract_violation` | Effects may already exist; inspect the object identified by returned references. |

Retain exit code, stdout and stderr; stop dependent operations after prerequisite failure. Timeout or local process exit does not prove remote stop. Correct a confirmed cause before repeating the affected operation; an existing uncertain attempt still cannot dispatch again. Use selected evidence in [local diagnostics](diagnostics.md#english) when retaining an investigation.

### Task duration records

A task's optional `operation_timings` retains up to three `sample: first_observed` entries: `preflight` before reservation, `execute` after reservation and `reconcile` for local recovery. Each has an exact record reference, monotonic `elapsed_seconds`, sampled `outcome` and optional `code`. A sample can predate current task status. Duplicate calls reuse it without overwriting first failures.

Scope `local_task_operation_before_timing_persistence` runs from local API entry through core result handling, including qualification, execution, capture, materialization and result receipt storage that occurred. It excludes timing-record storage itself, response serialization/delivery and waiting between operations. It is not provider compute time or network-only duration.

Early invalid requests, hard interruption and historical tasks can lack measurements; absent values remain unknown. `timing_recording.status: unavailable` means timing storage failed without undoing completed effects; inspect first. Adapter duration, provider usage and unknown cost have separate scopes; see [Codex support](codex-support.md#english).

### Back up and restore local data

1. Wait for local writes to finish. Copy the **entire data directory**, including interrupted-save files. Separately retain `.writing-assistant/config.json`, exact record/bookmark/diagnostic references and application version. External materials need original files and authorized access; a reference is not their backup.
2. Stop local writes before restoring and preserve the current directory and receipts newer than the backup. Do not delete a live lock. Older snapshots can omit later dispatches or results; absence does not prove no execution occurred.
3. With a compatible application, copy the whole backup to its configured absolute data path only when that destination **does not exist**. Do not merge into a live directory or overwrite in place. Substitute actual paths below; `copytree` refuses an existing destination:

   ```sh
   python3.12 -c 'import shutil; shutil.copytree("/backup/demo-data", "/configured/demo-data")'
   ```

   If configuration was lost, restore it to the original project location. Use the authorized OS account and preserve backup permissions. Do not alter task plans, ownership checks or permissions to imitate another data-root identity.
4. In a fresh invocation, read retained references and check SHA-256, bookmark selection and diagnostic revision:

   ```sh
   writing-assistant config --project ../demo-project
   writing-assistant records --project ../demo-project read first.json --output restored.txt
   writing-assistant records --project ../demo-project read-bookmark --bookmark bookmark-ref.json
   writing-assistant diagnostics --project ../demo-project show case-ref.json
   ```

   Use references actually present in the snapshot and a new `restored.txt`. Keep the preserved directory and interrupted transactions until verified. `records rebuild-index` only rebuilds navigation; it cannot restore missing or damaged originals.

A directory copy has a new physical root identity. Records, bookmarks and diagnostics remain readable in the restored project's local owner scope. Old durable task inspect/execute/reconcile can return `authority_changed`, even with identical paths and bytes. Plans, inputs and outputs remain readable through exact record references. Task operations require original root authority; execute/reconcile also check frozen configuration and policy. Transparent copied-directory or cross-machine task migration is unsupported.

Do not execute apparently prepared tasks from an older backup, or resend uncertain/executed tasks under new IDs. Account for newer history and unresolved external effects first. Restore does not start writing or adopt content.

### Restore World Sandbox

A complete backup also includes bundles, locks and interrupted files under `world-sandbox/PROJECT_ID/runs/`. Retain configuration, compatible application/source version, run/request/branch IDs and exact projection references. Original external-policy configuration is embedded in each bundle. Opening an existing run needs no new `world create`; rebuilding from an initial scenario cannot restore later state.

```sh
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID status --replay
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID resolve projection-ref.json --actor SAVED_ACTOR_ID --branch SAVED_BRANCH_ID
writing-assistant world --project ../demo-project --run-id SAVED_RUN_ID settle --request-id SAVED_REQUEST_ID --branch SAVED_BRANCH_ID
```

Use the original owner and exact actor, branch, purpose and selection. Check projection bytes against the retained digest; the example uses default `actor-projection` purpose. Replay calls no model. Settle only completes saved results or returns the same completed receipt, without allocating a request or calling a model; it also works when World Sandbox is off.

For `uncertain_request`, `settlement_not_ready` or `settlement_unavailable`, preserve the snapshot and newer evidence without using advance for recovery. Supported earlier-source runs retain [read-only limits](world.md#earlier-runs-and-python-integration) and cannot settle unfinished results. World restoration does not transfer writing-task authority to a copy.

### Remove or roll back the application

Use `python -m pip uninstall writing-assistant` in the installation environment. Reinstall a saved wheel with `python -m pip install --no-index --no-deps WHEEL`. Separate data stays in place. Application rollback does not roll back data, cancel remote work or reverse external effects. Do not open newer formats with an incompatible older application. Deleting creative data is a separate operation.
