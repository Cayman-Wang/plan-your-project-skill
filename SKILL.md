---
name: plan-your-project
display_name: Plan Your Project
display_name_en: Plan Your Project
description: "Discuss, plan, resume, or hand off projects. 规划软件或科研项目：先讨论方案与验收标准，冻结后保存为项目记录；也可读取当前进度、记录关键事件检查点、生成交接说明。Use when the user asks to plan a project, discuss scope before implementation, freeze and save a plan, check what is actually done, update progress, or hand the work to another AI."
description_zh: "讨论并规划软件或科研项目：先讨论方案、范围与验收标准，冻结决策后保存为最小项目记录；也可只读核对当前进度、在已授权执行中记录关键事件检查点、生成交接说明。触发场景：帮我规划项目、先讨论别写文件、方案定下来了存成计划、项目做到哪了、更新一下进度、交接给另一个 AI、这个研究课题怎么设计实验。"
description_en: "Discuss, plan, resume, or hand off projects. Plan software or research work: explore scope and acceptance criteria first, freeze the decisions, then save a minimal planning workspace; also resume recorded state, record key-event checkpoints during authorized work, and produce handoff notes. Use when the user asks to plan a project, discuss scope before implementation, freeze and save a plan, check what is actually done, update progress, or hand work to another AI."
version: 1.1.0
author: Cayman-Wang
agent_created: true
---

# Plan Your Project

按 `DISCUSS -> FREEZE -> GENERATE -> MAINTAIN` 推进。把冻结的终点与观察到的执行状态分开：规划不等于授权实施，启用进展记录也不等于授权新的项目工作。

## When to Use

规划软件或科研项目，在决定是否保存记录、冻结决策、建立最小规划工作区之前先讨论范围与方案。也可用于接续项目工作、查看进度、记录用户要求的交接，或在已启用 tracking 的工作区中维护检查点。与项目规划无关的一次性修改，或不需要项目规划的通用脚手架任务，不使用本技能。

## Hermes

On first use in Hermes, read the [integration guide](references/hermes_integration_zh.md). Resolve the installed `skill_dir` from `skill_view`; it is not the user's project directory. Keep script paths anchored there and pass the selected project explicitly through `--workspace-root`.

When the current turn is Hermes `/plan`, obey its plan-only restrictions and exact output path (normally `.hermes/plans/`). Do not run `init`, `checkpoint`, `refreeze`, `enable-tracking`, `recover`, or `handoff --output`, or create/update project records or entry files, even when tracking was enabled earlier. State any deferred checkpoint without claiming it was saved. Only the plan artifact authorized for this turn may be written; current instructions take precedence over previous tracking agreements. Outside that mode, the existing DISCUSS / FREEZE / GENERATE / MAINTAIN permissions below remain unchanged.

## WorkBuddy

首次在 WorkBuddy 使用时，先读 [WorkBuddy 适配说明](references/workbuddy_integration_zh.md)。WorkBuddy 激活技能时会把技能所在目录注入上下文，该目录存放说明、脚本与模板，**不是**用户的项目目录。脚本路径锚定该目录，项目路径始终用 `--workspace-root` 显式传入。`research/STATUS.md` 与 `research/PLAN.md` 从项目目录读取，不从技能目录读取。

WorkBuddy 的任务有三种模式，各自的写入边界不同。Ask 模式只根据已读到的内容回答，不写项目记录或其他文件。Plan 模式只允许写用户本轮指定的那份计划产物，不运行 `init`、`checkpoint`、`refreeze`、`enable-tracking`、`recover` 或 `handoff --output`，也不创建或更新项目记录与项目入口文件，即使此前已启用 tracking；有尚未记录的检查点时说明待记录，不声称已经保存。Agent 模式下，下面 DISCUSS / FREEZE / GENERATE / MAINTAIN 的权限原样生效。用户当前指令始终优先于既有的 tracking 约定。

使用本轮实际提供的工具。用文件读取与检索工具读文件与事实，用文件编辑工具写入，用 shell 工具运行脚本，用提问工具向用户提出聚焦问题而不是自行编造答案；子代理只汇报发现与证据，不改写共享 STATUS。Windows 下用 `python` 调用解释器，路径写成 `C:/...`；`python3` 不保证存在。参数含空格或中文时保持整体引用，不要为了找脚本而改变当前工作目录。

WorkBuddy 读取项目根目录的 `AGENTS.md`，也读取 `.codebuddy/CODEBUDDY.md`；`.codebuddy/` 下的配置是团队共享的项目配置。`--with-agents` 把受管的协议块幂等合并进 `AGENTS.md`，合并后仍保留项目原有指令，因此它继续作为任何 AI 接手项目时的共享入口；`--claude-bridge` 只面向 Claude Code，WorkBuddy 不需要它。当项目 `AGENTS.md` 与 WorkBuddy 会话记忆目录同时存在时，`research/STATUS.md` 仍是本技能执行状态的唯一权威来源，会话记忆目录只是可追加的活动流水；不要把项目状态复制进会话记忆目录，也不要用会话记忆代替 `STATUS.md`。

## Route The Request

- **DISCUSS（讨论）：** 探索新的、模糊的或发生实质变化的项目。先检查用户范围内的代码、配置、数据、实验记录与论文，再去问那些查不到的事实。只问会影响结果、范围、验收或重大取舍的负责人判断。每一轮提问前把已确认的回答写回 Brief 对应字段；填不进任何字段的回答转为开放决策或直接丢弃。识别证据、假设与开放决策。讨论与只读调研不写项目记录。
- **FREEZE（冻结）：** 确认一组自洽的决策。轻量对话可以用精简视图，但完整冻结语义必须满足。复用用户已给出的决策与授权，不重复请求用户批准同一动作。
- **GENERATE（生成）：** 用户明确授权保存冻结方案后才创建工作区。认可方案方向本身不等于允许创建文件；明确批准方案并要求保存的指令同时提供两项权限。先检查目标位置。
- **RESUME / 只读查状态：** 先读 `research/STATUS.md`，再读 `research/PLAN.md` 与当前 `must_read` 指向的全部路径。把记录状态与相关现场证据对比。在不修改文件的前提下报告差异与未知，包括只读审查和接续预览期间。
- **MAINTAIN（维护）：** 用户要求更新状态，或要求创建决策、评审、复盘、交接记录，即视为授权该记录。在已启用 tracking 的 v2.1 工作区中，已授权的实现或研究工作同样授权在约定范围内记录事件检查点。不要反复索取保存常规进展的许可。纯提问或只读查看永远不因为 tracking 已启用就变成写入。

DISCUSS / FREEZE 读 [讨论协议](references/discussion_protocol_zh.md)；按需选用 [软件视角](references/software_lens_zh.md)、[研究视角](references/research_lens_zh.md) 或两者。创建或修改记录前读 [文件契约](references/file_contract_zh.md)；接续、启用 tracking、记录检查点或生成交接前读 [进展协议](references/progress_protocol_zh.md)。

## Keep The Workspace Small

- 默认记录是 `research/PLAN.md` 与 `research/STATUS.md`，当前格式为 `plan-your-project/v2.1`。PLAN 拥有冻结的目标、约束、决策与验收；STATUS 拥有当前执行快照与必要证据引用。
- `init`、`resume`、`validate`、`checkpoint`、`refreeze`、`handoff`、`enable-tracking`、`recover` 都用 `scripts/project_state.py`；参数细节查文件契约与各子命令的 `--help`。`scripts/init_research_workspace.py` 保留为旧格式兼容入口；v2.1 新建工作区优先用 `project_state.py init`。`bootstrap_research_workspace.py` 是已废弃的兼容支持。
- 既有 v2 记录可以只读查看与接续。只有用户明确要求的 `enable-tracking` 预览及其批准后的应用操作，才能转换并启用 tracking。查看状态时绝不静默升级旧记录。v1、混合、无效或中断的布局需要先诊断并走对应的恢复路径，不覆盖。
- 新工作区默认 `tracking: disabled`：保存计划不启用自动进展记录。用户同时同意启用时，用 `init --enable-tracking --authorization ... --coordinator ...`；`--with-agents` 可合并受管的 [AGENTS 协议块](assets/AGENTS_tracking.md)，`--claude-bridge` 增加 [Claude 导入桥接](assets/CLAUDE_bridge.md)。既有工作区用 `enable-tracking`；首次启用记录同一份约定。先预览确切变更并保留无关指令。复用已给出的许可，不重复索取。tracking 为 disabled 时仍可执行用户明确要求的检查点，且不会因此启用 tracking。
- 决策、评审、复盘与交接记录保持惰性：只为请求的用途，或已启用约定明确覆盖的事件创建。绝不预建空目录、占位符、索引、提示词或平行的证据库。运行产物留在项目正常的输出位置，记录只做链接。

## Track Facts, Not Aspirations

在已启用的 tracking 范围内，出现下列情况时记录检查点：里程碑或验收结果改变、重要的验证结果改变、实质阻塞出现或解除、长任务开始/结束/失败、已确认的决策改变下一步。在计划中的暂停、交接或结束已授权工作之前，保存尚未记录的新进展。相关活动合并为一个检查点。没有变化的读取和常规工具调用不需要记录。准确记录通过、失败、跳过与不可用的验证；区分直接观察、他人报告与未经核实的推断。已验证的否定结论或不确定结论不同于未经核实的断言；验收仍按冻结标准判断。

共享 STATUS 由一个协调写入者负责。仅交接负责人不改变 tracking：tracking 为 disabled 时，用用户明确要求的单次检查点替换 Coordinator 条目，并在 changes 中写明旧/新负责人与授权依据；只有在 key_events 已启用时，才用 `enable-tracking --coordinator` 仅更新负责人。不从交接推断启用许可。执行者汇报发现与证据，不独立改写共享状态。写入前重读当前修订并使用命令的并发检查；绝不静默替换他人更新的状态。原子文件替换成功并不能证明没有陈旧的并发编辑。

接续时核对项目标识、修订、当前任务、证据相关性、既有改动与被引用的交接。较旧的交接是历史背景，不是回退到更旧 STATUS 的指令。无法编辑仓库的纯网页端 AI 应给出明确标注的**待同步**交接；不得声称工作区已更新。

## Revise And Hand Off

终点发生变化——目标、成功标准、范围、已锁定决策、里程碑验收或关键约束——回到 DISCUSS / FREEZE。保留此前决策，说明替换理由，复用已有授权或取得缺失授权后再写入修订。明确协调受影响的里程碑：保留无关的已完成工作及其有效证据，只重开验收或前提已变的部分。保留早前的科研结论及其证据与适用修订。当当前里程碑因被取消或已被验收、而其他工作仍在进行时，给出已确认的替代下一步动作。常规进展变化不改写 PLAN。

一份有用的执行交接包含已批准的范围、相关输入、锁定约束、当前交付物、验收证据、假设、风险及其验证方式、开放决策、冻结就绪度与下一步动作。接收方无法访问 PLAN 时，这些条件必须保留在导出文本中。修订记录保存变更前后的冻结内容，包括旧验收，不依赖 Git 历史。存在适用的实现类或研究执行类技能时优先使用；若没有，而用户已授权执行，则退出规划工作流，转入普通实现工作流，并遵守当前运行模式与权限。不因为缺少实现类技能就停止已授权的工作。若用户只要求规划，交付计划与交接即可，不执行。

接收方看不到本对话或 PLAN 时，从可选的 [交接模板](assets/TEMPLATE_handoff.md) 开始。填写全部必需小节，确实不适用的小节写 `None`，并用 [handoff_check.py](scripts/handoff_check.py) 以可用的 `python` 或 `python3` 校验。该模板是 optional 的，从不要求规划者编写实现代码。

## Runtime Files

完整运行时包放在一起，包括间接导入。通过 URL 直接安装时还必须取到 [workspace_io.py](scripts/workspace_io.py)，入口脚本会导入它。保留 [project_state.py](scripts/project_state.py)、[init_research_workspace.py](scripts/init_research_workspace.py) 与兼容入口 [bootstrap_research_workspace.py](scripts/bootstrap_research_workspace.py)。

复盘仍是可选的，只在获得授权时创建；保留中英两个模板：[中文](assets/TEMPLATE_retrospective_zh.md) 与 [英文](assets/TEMPLATE_retrospective_en.md)。分发保留 [MIT 许可证](assets/LICENSE)。

交接支持包含可选的 [交接模板](assets/TEMPLATE_handoff.md) 与其 [小节校验脚本](scripts/handoff_check.py)。

## Verify And Report

允许的写入完成后，校验记录、PLAN/STATUS 修订一致性、里程碑引用、证据路径、无未解决的占位符，以及确切的文件变更集合。报告保存了什么、什么仍未验证、下一步是什么。文件已保存不等于实现已完成。Hooks 属于可选宿主集成；本协议不能保证在异常终止前留下检查点，也不能保证在从不加载项目指令的代理中生效。
