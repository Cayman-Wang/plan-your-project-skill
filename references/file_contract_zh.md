# v2.1 工作区与工具契约

本契约供写入或校验记录时读取。概念和触发时机见 [进展协议](progress_protocol_zh.md)。`scripts/project_state.py` 仅依赖 Python 标准库，命令形式为 `python scripts/project_state.py <command> --workspace-root ROOT ...`。`--json` 返回机器可读结果；错误写入 stderr 并返回非零。`handoff` 即使带 `--json`，未指定输出文件时也直接输出 Markdown。

## 版本与最小布局

新工作区标记为 `plan-your-project/v2.1`，默认只有 `research/PLAN.md` 与 `research/STATUS.md`，`tracking: disabled`。`init` 不创建历史记录目录；已约定启用时加 `--enable-tracking --authorization TEXT --coordinator TEXT`，才设为 key_events，并可选 `--with-agents` 合并项目入口。现有工作区使用 `enable-tracking`。两者均可按需添加 Claude 桥接。命令要求启用约定有记录，不验证自然语言授权的真实性；执行者负责符合用户范围。

统一状态工具可读 v2 与 v2.1，但只写 v2.1；旧工具不保证理解新格式。保留 `init_research_workspace.py` 作为旧 v2 初始化/校验兼容入口，不用其 force-overwrite 修订现有项目：旧入口现已拒绝 force-overwrite，现有项目先明确迁移再用 `refreeze`。安装新 skill 不改变任何项目格式。

本轮在 v2.1 中增加 disabled 及科研结论枚举。新工具继续读取原有 key_events/supported 等记录，不要求重新启用；旧工具可能拒绝新枚举，维护此类文件须使用本轮或更新工具。不自动推断旧记录的实际授权，接续者仍须按 Authorization 与当前用户指令核对。

检测 `research/plans/ACTIVE_PLAN.md`、旧 session prompt 或 `plans/*/master_plan_zh.md` 为 v1；v1 与核心文件并存为 mixed。`resume` 只报告其只读布局；不迁移、不写入。缺一个核心文件或文档损坏时拒绝写入，先诊断。事务中断使用下文 recover；不要将其当普通缺文件重新初始化。

## 冻结计划输入与输出

`init --plan-file FILE`、`refreeze --plan-file FILE` 保留原 JSON 输入 schema_version **2.0**（与输出工作区版本分开）。也可用 `--plan-file -` 读取 stdin。拒绝重复 JSON key、未知/缺失字段。全部文本为 UTF-8 单行非空字符串；列表可为空的字段见下文。冻结就绪度只允许 `READY`、`READY_WITH_ASSUMPTIONS`。

```json
{
  "schema_version": "2.0",
  "project_name": "...",
  "problem": "...",
  "goal": "...",
  "success_criteria": ["..."],
  "scope": {"in": ["..."], "out": ["..."]},
  "constraints": ["..."],
  "selected_approach": "...",
  "alternatives_considered": [{"option": "...", "tradeoffs": ["..."]}],
  "locked_decisions": ["..."],
  "milestones": [{"id": "M1", "outcome": "...", "acceptance": ["..."]}],
  "risks": [{"risk": "...", "mitigation_or_validation": "..."}],
  "assumptions": ["..."],
  "open_questions": ["..."],
  "evidence": ["..."],
  "next_action": "...",
  "freeze_readiness": "READY"
}
```

必需非空列表：success_criteria、locked_decisions、scope.in、alternatives_considered、milestones、每个里程碑 acceptance。其他列表允许空；READY_WITH_ASSUMPTIONS 必须有 assumptions。里程碑 ID 唯一且匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`；备选 option 唯一且不同于 selected_approach。复杂字段严格使用示例键，不添加自定义字段。假设和冻结写入授权由执行者按用户决定核实；一次“确认并写入”即可，不拆成重复确认。

PLAN frontmatter 恰为 workspace_format、record: PLAN、plan_revision、language: zh/en、frozen_at: YYYY-MM-DD。正文覆盖全部输入语义，保留对应语言的标题、范围内/外分区、里程碑非空验收和冻结就绪度。输入和生成 Markdown 共用关键验证约束，不能靠手改 Markdown 绕过空验收、重复 ID 或 NOT_READY。PLAN 只在已授权的实质修订时递增 plan_revision，普通 checkpoint 不改 PLAN 字节。

## STATUS 数据模型

frontmatter 恰为：

```yaml
workspace_format: plan-your-project/v2.1
record: STATUS
plan_revision: 1
status_revision: 1
state: planned
current_milestone: M1
last_updated: YYYY-MM-DD
tracking: disabled
```

正文固定唯一 `# Status`，按顺序恰好八个 H2：`Summary`、`Milestones`、`Running Tasks`、`Blockers`、`Next Action`、`Must Read`、`Evidence`、`Authorization`。字段名固定英文，说明可中文。空列表写 `- (none)`；结构化记录用 `### ID` 和 `- field: value`。不嵌入整段 JSON，不维护另一份长期 JSON 状态。单行字符串避免标题/换行混入结构。目标约100行，超长仅警告，不截断。

tracking 仅 `disabled/key_events`，不是状态 JSON 的可编辑字段。disabled 下可以响应明确的单次维护请求；普通 checkpoint/refreeze 保持原 tracking，只有明确的启用操作才变为 key_events。resume/validate 和 handoff 均显示该值。

`resume --json` 的 `status` 可直接作为更新起点。完整状态 JSON **恰好**含以下字段；更新请求传完整对象，保持无关字段，不做隐式局部覆盖：

```json
{
  "summary": "实现完成，等待验收。",
  "state": "in_progress",
  "current_milestone": "M1",
  "milestones": [{
    "id": "M1", "execution": "done", "validation": "not_run",
    "acceptance": "pending", "summary": "代码已完成，测试尚未运行。",
    "evidence": [], "acceptance_basis": "", "conclusion": "not_applicable"
  }],
  "running_tasks": [],
  "blockers": [],
  "next_action": "执行已授权的验收检查",
  "must_read": ["research/PLAN.md"],
  "evidence": [],
  "authorization": ["用户已授权实施当前计划及关键节点记录；不包含发布。"]
}
```

- `state`: planned/in_progress/blocked/complete；current_milestone 必须属于 PLAN，milestones 与 PLAN ID 集合完全一致且无重复。
- `execution`: pending/running/done；`validation`: not_run/passed/failed；`acceptance`: pending/accepted/rejected；`conclusion`: not_applicable/supported/not_supported/inconclusive/unverified。supported 表示支持指定假设，not_supported 表示已评估且不支持，inconclusive 表示已评估但不足以判定，unverified 表示尚未核实；在 summary 说明假设与适用范围。未跑、跳过、不可用的验证保留 not_run 并说明原因。
- 里程碑 evidence 是 Evidence 的 ID 数组；acceptance_basis 仅未接受时可为空。passed/failed 或已评估结论 supported/not_supported/inconclusive 必须关联至少一个 observed/historical 证据；accepted 还要求 done、passed 和非空验收依据。负结果是否通过验收取决于冻结标准，不将假设被支持当作所有研究的默认验收条件。complete 要求全部 accepted、无活跃任务和阻塞；blocked 要求非空 blockers。
- evidence 描述满足结构不等于证明了科学结论，工具不代替内容审查。旧证据可以保留，但恢复时提示其适用版本，不能将历史通过说成本轮实测。
- must_read 唯一且含 `research/PLAN.md`；每项是已存在的规范工作区相对普通文件路径，不允许 `..`、绝对路径、外逸符号链接。保留直接影响下一步的材料，长清单提示精简。
- authorization 非空，记录用户决定来源、范围和限制；历史授权不覆盖较新用户指令。每项为一句话，不从计划下一步推导新的权限。`Coordinator: NAME` 是当前写入负责人的保留条目，最多一条且 NAME 非空；新 CLI 输入用 --coordinator，不通过 --authorization 注入该条目。没有负责人条目的兼容记录仍可读取。

Evidence 的每条对象恰为：

```json
{
  "id": "check-1", "source": "observed", "ref": "reports/check.txt",
  "summary": "本轮运行对应验收检查，通过；仅覆盖当前模块。",
  "code_ref": "执行时的提交SHA或明确的dirty工作树快照",
  "checked_at": "2026-09-22T10:00:00+08:00"
}
```

source 只能 observed（本轮实测）、historical（引用报告）、unverified（未核验）。本地相对 ref 在 observed/historical 时必须存在；unverified 允许缺失路径但不能作为通过证据。外部 URL、绝对路径或 `remote:` 等来源仅保存描述，不自动联网、SSH或执行。摘要中说明检查方法、结果和局限；不要存密钥。checked_at 和代码基线必须具体，未知时明确写“未现场核验/未知”，不能伪造时间或提交。

Running Tasks 每条对象恰为：

```json
{
  "id": "job-42", "environment": "server-a / 已确认的运行环境",
  "code_ref": "任务实际执行代码SHA", "document_ref": "记录提交SHA或尚未提交",
  "log": "remote:/runs/job-42/log.txt", "artifacts": "remote:/runs/job-42/output",
  "last_checked_at": "2026-09-22T10:00:00+08:00",
  "completion": "进程正常退出且目标产物校验通过",
  "recovery": "支持从检查点恢复；先查任务状态，禁止重复启动"
}
```

id 就是可定位的任务标识；环境、代码SHA、文档SHA分别保存，日志/产物位置与完成判据、恢复能力必填。任务结束从 active 数组移除，在 checkpoint 说明成功/失败及证据；实验结束不自动等于科研验收通过。

## 命令与写入流程

### init、resume、validate

- `init --plan-file plan.json [--language zh|en] [--date YYYY-MM-DD] [--dry-run]`：仅接受空规划工作区，默认保存计划且 tracking 为 disabled；先验证输入和生成结果，再写核心文件并验证完整结果。可重复 `--authorization TEXT` 保存用户实际决定；`--coordinator TEXT` 将共享状态负责人追加到授权段。`--enable-tracking` 必须同时提供这两个参数，将记录范围、来源和负责人保存后启用 key_events。`--with-agents` 需要 --enable-tracking；`--claude-bridge` 要求同时指定 --with-agents。已有一次“生成并启用”的指令即可，不重复确认。核心文件与入口同一事务提交；只备份被修改的已有入口，不为刚创建的核心文件制造备份。dry-run 展示变更，不创建锁或目录。
- `resume [--json]`：不写入；输出 format、两类修订、hashes.plan/status、完整 status、git.head/branch/worktree、warnings。先读项目规则与STATUS，再读PLAN及必读，核对下一动作相关现场。Git 检查不证明远端任务完成。旧快照中的本地引用缺失或不再是普通文件时返回明确警告（含旧 v2），记录中的完成不能据此认定仍有效；工具不扫描所有报告推断最新结论，相关证据由接手者核实。
- `validate`：检查格式、修订、里程碑、引用、完成证据和历史记录。旧v2只读校验；文档损坏返回非零。验证结构不能替代验收内容审查。

### checkpoint

`checkpoint --update-file update.json --expected-plan-hash HASH --expected-status-hash HASH`，输入恰为：

```json
{
  "id": "m1-implementation-done",
  "date": "2026-09-22",
  "summary": "M1实现完成，待验证",
  "changes": ["完成约定实现，尚未运行验收；下一步为已有计划中的检查。"],
  "status": "此处须替换为上节完整状态对象，不是字符串"
}
```

id 匹配 `[a-z0-9]+(?:-[a-z0-9]+)*`，日期严格 YYYY-MM-DD，changes 非空。仅更新STATUS并创建 `research/records/checkpoints/DATE-ID.md`；PLAN保持原字节。status_revision递增。相同ID、相同规范化请求内容重放为unchanged，即使后来状态已推进，也不倒退；同ID不同内容冲突。普通新写入必须匹配两份读取哈希。状态没有新事实则拒绝创建空检查点。旧快照的引用后来缺失或成为目录时仍可诊断并纠正；新的完整状态须通过严格校验，修正引用并重新评估受影响证据和验收，不能借此保留无依据的通过或绕过路径边界。

checkpoint frontmatter 保存格式、类型、id/date、计划/状态修订、源哈希和请求摘要哈希；正文保存 Changes 与本次新增/改变的 Evidence引用，并标明历史适用期。记录追加后不覆盖，不把计划、状态或实验全文复制进去。refreeze 的 Changes 另含已改变的冻结字段前后内容，不复制未改字段。历史 decisions/reviews/retrospectives/handoffs 仍按目的懒创建，不建每日流水账。

### refreeze

`refreeze --plan-file plan.json --id revision-name --summary '修订原因与授权来源' --affected-milestone M3 --expected-plan-hash HASH --expected-status-hash HASH`；可选 `--next-action '新修订下已确认的下一动作'`。

输入已确认的新计划；保留其他里程碑状态、当前里程碑（仍存在时）、阻塞、运行任务和证据。自动识别新增或 outcome/acceptance 已变的里程碑；目标、范围、约束、成功标准、选定方案或锁定决定变化时，必须明确给出受影响ID，可重复该参数。执行者负责传播依赖影响，工具不猜测技术依赖。检查点 Changes 自动记录改变的 PLAN 标题/各节内容的 before/after 及各自修订，包括旧锁定决策和旧验收。原 PLAN 未提交 Git 也能追溯；源哈希不替代历史内容。

受影响项保留 execution（已完成的实现不会凭空消失），validation 变 not_run，acceptance 变 pending，科研结论需重验；旧结果（含 conclusion）、删除项和证据引用连同适用修订写入变更记录。PLAN修订和STATUS修订各递增；完整三文件结果验证后才成功。当前里程碑被删除、或已验收而需要改指向另一未验收项时，工具重新选择当前项，并要求 `--next-action` 或相较旧PLAN已更新的 `next_action`，否则拒绝写入。`--next-action` 优先于计划中的下一步；当前项未切换时，未改变的PLAN旧下一步保留较新的STATUS动作。工具不猜测切换任务后的安排，也不默认清空其他进度或阻塞。

### handoff

`handoff` 默认向 stdout 生成带来源工作区、截止时间、源修订、tracking 及双哈希的 Markdown；包含目标/锁定范围、假设、风险及验证、开放问题、计划证据、冻结就绪度、进展、证据摘要、未完成、下一步和授权限制，网页AI无需访问 PLAN 也能知道方案成立的条件。来源路径用于定位项目，跨电脑时需映射到目标电脑。`--output research/records/handoffs/DATE-name.md` 才保存到工作区内的一个新文件，不覆盖已有文件，不自动checkpoint。若有尚未保存的新进展，先按已授权记录协议checkpoint再导出。

无写权限AI返回“待同步更新”及源哈希；文件型AI先核实当前基线，相同才提交checkpoint，变化时重新整理。不能说网页建议已保存。交接不是另一个事实源，不覆盖新用户决定；跨电脑仍需用户已有Git/文件同步方式。

### enable-tracking

默认仅预览；`--claude-bridge` 可选。预览包含修改路径、AGENTS/CLAUDE具体diff、源哈希、旧状态，v2还给出用于人工核对的完整状态模板。旧引用失效应在预览报告，允许用经核实的迁移输入修复；映射后的新状态严格校验。应用需明确 `--apply --expected-plan-hash HASH --expected-status-hash HASH`；v2额外提供 `--status-file reviewed-state.json`，逐项保留实际进度、阻塞和证据，不从旧complete标签猜测全部验收。填写状态后先带 --status-file 再预览，查看确切PLAN/STATUS差异，再应用。

首次启用（旧 v2 或 v2.1 disabled）应用时还须提供 `--authorization TEXT --coordinator TEXT`。未提供的预览只提示缺少约定，并不伪造授权或显示一份可直接应用的 STATUS；补齐后再预览确切差异。已有状态和普通 Authorization 原文保留，新约定去重追加；显式 --coordinator 替换所有旧 Coordinator 条目，仅保留一个当前负责人。检查点保存旧/新负责人及本次 --authorization 提供的交接原因或依据；没有提供额外原因时如实注明，不编造。v2.1 启用或负责人交接只递增 status_revision，PLAN 字节不变，创建一次 checkpoint；v2 转换创建 migration 记录。已有 key_events 不重复要求启用约定，重复相同负责人及参数不增加修订/备份/记录。

旧工具曾写出多个 Coordinator 时，resume/handoff 仍可只读诊断并警告，validate 拒绝将其报告为有效。用已确认的 `enable-tracking --coordinator NAME` 预览/应用可修正，保留其他进度；不指定负责人时不自动选择。完整 checkpoint 输入也须满足单一负责人约束，避免重新引入歧义。此前已给出的交接指令可直接作为依据，不另设审批步骤。

应用前将PLAN/STATUS及本次会修改的现有AGENTS/CLAUDE原件保存到 `.plan-your-project-backups/<timestamp>/`，与转换共同提交。保留旧记录；PLAN只变格式标记、不变目标或计划修订。STATUS转换为v2.1，并有migration checkpoint引用备份。AGENTS只替换唯一管理块或末尾追加，保留其他内容；CLAUDE只追加缺失的 `@AGENTS.md`。重复启用无变化，不重复备份或叠加入口。v1/mixed不支持此转换。

### recover 与并发

一个协调主代理写入，子代理汇报结果。写命令持短暂非阻塞锁，持锁后重读状态；检查双哈希防止旧快照覆盖。锁文件 `.plan-your-project.lock` 可长期存在，不表示任务正在执行，也不是额外事实源。读命令不建锁；返回的校验值须与实际解析的原始文件字节及读取前后现场一致，避免把写入后又回滚的暂态误报成有效快照。

多文件替换不是一个物理原子快照。`.plan-your-project-transaction/` 保存持久manifest、原字节与阶段；检查结果完整有效后才清理。普通异常/Ctrl+C尝试回滚；硬退出保留事务，拒绝新写入，resume提醒待恢复。显式 `recover` 回滚prepared事务；已完整验证并标记committed的事务仅清理。若目标已恢复到原校验值，清理中断后可继续恢复，不要求已被清理的原件备份；仍需还原的目标必须有有效备份。遇到后来独立修改或必需备份损坏时拒绝覆盖并保留现场。恢复后再validate。

写前解析真实路径，拒绝外逸链接、目标符号链接、特殊文件和目录；expected hash也用于保护只读依赖。该机制防合作式并发与中断，不是对恶意进程的文件系统隔离或断电绝对保证。没有加载项目协议的AI仍可能不遵守，崩溃前尚未记录的工作无法由此恢复。
