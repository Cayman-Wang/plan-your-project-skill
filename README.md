# Plan Your Project

Plan software or research work, then preserve a small, evidence-backed execution snapshot that another AI or conversation can resume.

用于软件或科研项目的方案讨论、冻结与进展接续。规划决定“做什么、如何验收”；执行者按关键事件记录“实际做到哪里”。本版本使用 `plan-your-project/v2.1` 工作区格式。

## 工作方式

- **DISCUSS / FREEZE**：先查已有材料，再问影响目标、范围和验收的决定。简单路线可用轻量视图，正式冻结仍覆盖全部语义；共同验收的多个模块不机械拆成独立项目。
- **GENERATE**：在已授权保存方案时建立最小工作区。批准方向本身不等于落盘，但“同意方案并生成文件”无需再确认一次。
- **RESUME**：读取项目状态、冻结计划和必要证据，再核对现场；只读查询不修改文件。
- **MAINTAIN**：项目启用一次 tracking 后，已授权执行在交付、验证、重要阻塞及暂停/交接等事件后保存检查点，不反复索取记录许可。

规划不会自行启动开发。用户已要求实施时，转入适用实现 skill 或通用实施工作流；没有专用实现 skill 不构成停止工作的理由，仍遵守宿主运行模式和授权范围。

## 最小文件与跨 AI 入口

```text
research/
├── PLAN.md      # 冻结目标、方案、约束、里程碑及验收
└── STATUS.md    # 当前进展、验证、阻塞、下一步和必要证据
```

STATUS 是接续入口；旧历史和详细产物不全塞入它。`init` 默认只生成上述两份记录，tracking 为 disabled；保存计划不会自动启用记录。新项目已获启用授权时加 `--enable-tracking --authorization ... --coordinator ...`，再按需用 `--with-agents` 合并跨 AI 入口；现有项目使用 `enable-tracking` 预览并应用。需要追溯时按需创建决策、评审、复盘或交接记录；日志、截图、数据等仍存放在项目正常位置。执行、验证与验收分别记录，实验结束不代表研究结论成立。

启用 tracking 可将短协议块幂等合并到项目 `AGENTS.md`，保留已有规则；可选 `CLAUDE.md` 的 `@AGENTS.md` 桥接不维护重复协议。其他 AI 无需安装本 skill，也可读取项目入口并按已有格式维护进度。网页端没有写权限时提供“待同步”交接，本地执行者核实后再保存；不能冒称文件已更新。

共享 STATUS 由一个协调负责人维护，子代理汇报证据；状态写入检查已读取的 PLAN/STATUS 校验值，检测并发变化后先重新核对，不静默覆盖。协议提高记录可靠性，不保证所有宿主自动触发，也不能保证异常退出前保存。

## 使用示例

```text
$plan-your-project 帮我规划这个项目，先讨论，不创建文件。
按刚确认的方案生成计划文件，并启用开发过程的关键事件进度记录。
读取这个项目的状态，告诉我实际做到哪里；先不要修改。
继续当前已授权任务，并在关键事件后更新进度。
我要换一个 AI 接着做，请生成交接。
```

新 AI 从项目 `AGENTS.md` 指向的 STATUS 开始，核对 PLAN、相关证据和当前工作区。旧 handoff 是带基线的历史记录，不能倒退覆盖较新的进展；导出文本同时保留假设、风险、开放问题和冻结就绪度。计划修订保留无关完成项及有效证据，仅重开受影响的工作；修改前后的决策和验收存入已有修订记录，无需依赖 Git 历史。

## CLI

在本 skill 目录调用 `scripts/project_state.py`。所有项目路径指向用户明确选择的工作区；以下 `/path/to/project` 是说明用路径，替换后再运行。

```bash
# 查看具体子命令参数
python scripts/project_state.py --help
python scripts/project_state.py checkpoint --help

# 仅保存计划，tracking 为 disabled；输入 schema_version 为 2.0
python scripts/project_state.py init \
  --workspace-root /path/to/project --plan-file frozen-plan.json

# 新项目同时保存已有授权、协调负责人，并合并跨 AI 入口；先 dry-run 查看差异
python scripts/project_state.py init \
  --workspace-root /path/to/project --plan-file frozen-plan.json \
  --enable-tracking \
  --authorization '用户已确认方案并授权保存及关键进展记录；尚未授权实施。' \
  --coordinator '本项目当前主代理；子代理只汇报证据' \
  --with-agents --claude-bridge --dry-run
# 核对后使用同样参数去掉 --dry-run；仅按用户实际授权填写上述文字

# 只读恢复、校验；resume 输出完整状态及 PLAN / STATUS 校验值
python scripts/project_state.py resume --workspace-root /path/to/project
python scripts/project_state.py validate --workspace-root /path/to/project
```

检查点输入为 JSON：`id`（小写连字符标识）、`date`（YYYY-MM-DD）、`summary`（单行事件摘要）、`changes`（实际变化字符串数组）、`status`（完整状态对象）。key_events 时按约定事件记录；disabled 时仅响应明确的记录请求，单次维护不会启用 tracking。以 resume 返回的完整状态为基础，只调整有证据支持的内容；字段和证据格式见 [文件契约](references/file_contract_zh.md)。提交前提供该次读取的两个校验值：

```bash
python scripts/project_state.py checkpoint \
  --workspace-root /path/to/project --update-file checkpoint.json \
  --expected-plan-hash PLAN_HASH --expected-status-hash STATUS_HASH

# 默认仅输出交接；只有明确指定 --output 才写出文件
python scripts/project_state.py handoff --workspace-root /path/to/project
```

| 命令 | 用途与边界 |
|---|---|
| `init --plan-file` | 新建 v2.1，默认 disabled。`--enable-tracking` 需同时提供 `--authorization` 和 `--coordinator`；启用后可用 `--with-agents` 合并入口，`--claude-bridge` 需同时指定 `--with-agents`。 |
| `resume` / `validate` | 只读恢复或校验；旧 v2 可只读查看，不静默转换。 |
| `checkpoint --update-file --expected-plan-hash --expected-status-hash` | 保存真实进展；不改冻结目标，不把状态当授权。 |
| `refreeze --plan-file --affected-milestone --id --summary --expected-plan-hash --expected-status-hash` | 保存新计划修订，保留无关进度；`--next-action` 明确新的当前动作，避免继续已取消的工作。 |
| `handoff` / `handoff --output` | 输出交接；`--output` 仅接受工作区相对的新 Markdown 文件路径，不覆盖已有文件。 |
| `enable-tracking` | 默认预览格式转换和入口合并；旧 v2 需提供经核实的 `--status-file`。 |
| `enable-tracking --apply --expected-plan-hash --expected-status-hash` | 首次启用还需 `--authorization` 和 `--coordinator`，保存已有约定并保留原进度；`--claude-bridge` 可选。 |
| `recover` | 显式执行中断事务恢复，可能写入文件；不是只读检查。先查看 resume/validate 的错误，不盲目修复。 |

`PLAN_HASH`、`STATUS_HASH` 应分别使用 resume 的 `hashes.plan`、`hashes.status` 实测值，不填固定示例值。实际写入必须提供它们；重复提交相同检查点 ID/内容会无操作返回，复用 ID 改内容会报错。校验失败时先核对报告，不用强制覆盖掩盖冲突。校验器检查结构与必要条件，不代替实际测试、实验和验收判断。所有参数细节以各子命令 `--help` 和 [file_contract_zh.md](references/file_contract_zh.md) 为准。

## 兼容与启用

旧 `plan-your-project/v2` 保持只读恢复；只有明确启用 tracking 时，经 preview / apply 和经核实的状态输入转换。v1、混合或不完整布局先报告问题，不自动迁移。启用预览应展示准确路径和内容；应用时保留用户已有入口文字，重复启用不叠加协议或 Claude import。

新工具兼容现有 v2.1 key_events 记录；本轮新增 disabled 和科研 conclusion 的 not_supported/inconclusive 枚举，旧工具可能拒绝这些值，应使用新版工具维护。结论不支持假设、已评估但不确定、尚未验证分别记录；负结果是否通过验收仍由原冻结标准决定。

已记录的本地引用失效时，`resume` 给出警告；可先核实事实，再通过检查点或迁移输入修正，新的完整状态仍须通过严格校验。修订导致当前里程碑切换时（原项被取消，或原项已验收而出现其他待办），必须用已确认的新计划下一步或 `--next-action` 指定替代动作；旧科研结论及其适用版本留在修订记录中。

`scripts/init_research_workspace.py` 保留旧格式兼容；新建 v2.1 使用 `project_state.py init`。`bootstrap_research_workspace.py` 是 deprecated 兼容入口，不用于新工作区。工作区格式版本不等于上游发布标签；本地修改不会自动发布到源仓库。

## 文档

- [SKILL.md](SKILL.md)：触发、状态和操作边界。
- [讨论协议](references/discussion_protocol_zh.md)：轻量呈现、冻结和共同验收。
- [进展协议](references/progress_protocol_zh.md)：检查点、证据、冷启动、并发与网页交接。
- [文件契约](references/file_contract_zh.md)：精确输入格式与校验。
- [AGENTS 模板](assets/AGENTS_tracking.md) / [Claude 桥接](assets/CLAUDE_bridge.md)：项目入口资源。

## 安装

源仓库为 `https://github.com/Cayman-Wang/plan-your-project-skill`。安装已审阅的版本到宿主的 skills 目录；更新已有安装时先备份，不将本地修改覆盖掉。项目中的 AGENTS 入口是接续协议的共享载体，不要求所有 AI 都具备同一 skill 安装位置。未安装 CLI 的代理可遵守项目模板手工维护 STATUS；它不能因此宣称执行了自动校验或创建了机器可验证的检查点。

## License

MIT
