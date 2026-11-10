# WorkBuddy 适配与使用

本说明只连接宿主能力，不改变讨论、冻结、授权、科研验收、单协调写入者或 v2/v2.1 兼容规则。Codex 的 `agents/openai.yaml` 与 Hermes 适配说明继续保留；不安装后台钩子，也不自动开始任何项目工作。

## 加载与路径

1. WorkBuddy 激活本技能时会把技能所在目录注入上下文，该目录存放说明、脚本和模板。**技能目录**不是**项目目录**。
2. 首次在 WorkBuddy 使用时，先读本文件，再按任务读取讨论、进展或文件契约。
3. 脚本用技能目录的绝对路径调用，项目始终用明确的 `--workspace-root` 传入。技能目录与项目目录可以不在同一台机器上，但必须在同一执行后端可读。
4. 如果当前执行后端是 SSH 或容器，先确认该后端也能读到脚本、模板和项目；本机技能目录路径不是远端可用路径。缺少同后端安装时说明阻塞，不静默切换后端、不复制私有项目，也不声称写入成功。

用户可直接说：

```text
请使用 plan-your-project 技能讨论这个项目，先不要创建文件。
请使用 plan-your-project 技能，只读核对项目的实际进度。
按照已经确认的方案保存项目计划；暂不启用 tracking，也不开始实施。
```

不要求使用 Hermes 或 Codex 的调用写法。不要求清空当前会话；新安装后的自动发现以新会话为稳妥验证入口，当前会话可尝试显式引用技能名。不可用时说明需要新会话，不擅自重置会话或刷新提示缓存。

## 工作模式与写入边界

**先判断当前回合的明确限制，再解释 tracking。** 项目已记录的旧授权不会扩大当前权限。

| 当前请求 | 允许的动作 | 不允许的附带动作 |
|---|---|---|
| 只讨论、先不保存 | 只读调查、澄清、给出方案 | 创建项目记录或开启 tracking |
| 规划模式 | 只读调查、澄清，保存本轮指定的计划产物 | 更新长期记录、实施或启用 tracking |
| 明确同意具体方案并要求保存 | 按既有冻结与文件契约保存批准的记录 | 自动开始实现，或默认启用 tracking |
| 已授权实施且 tracking 已启用 | 在授权工作内执行，按关键事件维护状态 | 扩大任务范围或重复索取已有记录许可 |
| 只读接续预览 | 读 STATUS、PLAN、证据并核对当前事实 | 用旧交接授权新任务、自动 recover 或迁移 |

在规划模式，即使 `tracking: key_events`，也不得运行 `init`、`checkpoint`、`refreeze`、`enable-tracking`、`recover` 或 `handoff --output`，不得另写 `research/PLAN.md`、`research/STATUS.md`、项目入口或输入 JSON 文件。需要保留的待记录事项放进本轮允许的计划或回复，标为“尚未同步”，不声称已经保存检查点。只读 `resume` / `validate` 可在本轮允许终端检查时使用。

退出规划模式后，只有当前有效请求授权保存项目记录时，才把已确认内容按冻结输入契约转换为 JSON，再调用原 CLI；保留已确认决定，不机械重问。仅有一份计划文件不代表冻结授权、tracking 或实施授权自动成立。

## 使用 WorkBuddy 工具

- 文件与事实调查：使用本轮实际提供的文件读取与检索工具；不让用户重复提供可以只读查到的事实。
- 关键取舍：用提问工具向用户提出聚焦问题，按该工具当前 schema 提问；不可用时用普通对话，不假装表单已经发出。问题数量和收敛原则沿用讨论协议。
- 已授权的计划产物或 CLI 输入：使用文件写入工具；结构化项目状态优先通过原 CLI 维护，不绕过并发检查直接覆盖 STATUS。
- 脚本：使用 shell 工具。先只读检查可用 Python，使用 `python` 或已验证的解释器绝对路径，不假定 Windows 有 `python3`。脚本只依赖 Python 标准库，不为它安装第三方包。
- 并行调查：可使用子代理，但子代理只提交发现与证据；共享 STATUS 的协调者负责核验、合并和唯一写入。历史 handoff 不能改变当前协调责任或授权。

Windows 下调用脚本用 `python`，路径写成 `C:/...` 形式；Git Bash 中可用 `/c/...`。参数包含空格或中文时保持整体引用。不要为了寻找脚本改变项目工作目录。

这是指令适配，不是宿主强制沙箱。它不保证每个模型都遵守流程，也不承诺异常退出前保存。

## 从任意项目目录调用脚本

先把两个变量替换成技能目录和用户选定项目目录的真实路径；Windows 原生程序使用 `C:/...` 形式。PowerShell 用户按对应 shell 语法调用，不把 Bash 变量语法直接粘贴过去。

```bash
SKILL_DIR='/absolute/path/to/the/installed/skill'
PROJECT_DIR='/absolute/path/to/the/user-selected-project'
python -B "$SKILL_DIR/scripts/project_state.py" --help
python -B "$SKILL_DIR/scripts/project_state.py" resume --workspace-root "$PROJECT_DIR" --json
python -B "$SKILL_DIR/scripts/project_state.py" validate --workspace-root "$PROJECT_DIR" --json
```

项目尚未初始化时，resume/validate 失败不构成自动初始化授权。已明确授权保存冻结内容后，按 `references/file_contract_zh.md` 准备 JSON，再先预览；下面命令不授权写入输入文件，也不是规划模式可执行的动作：

```bash
python -B "$SKILL_DIR/scripts/project_state.py" init --workspace-root "$PROJECT_DIR" --plan-file '/absolute/path/to/approved-plan.json' --dry-run
```

批准预览所代表的写入后，用同样参数移除 `--dry-run`。如果用户已经明确批准同一组具体文件写入，不重复索取许可。默认保持 tracking disabled；其他写命令仍遵守原文件契约，使用最新读取的 PLAN/STATUS 校验值。

## 项目入口与状态归属

WorkBuddy 读取项目根目录的 `AGENTS.md`，也读取 `.codebuddy/CODEBUDDY.md`；`.codebuddy/` 下的配置是团队共享的项目配置。`--with-agents` 把受管的协议块幂等合并进 `AGENTS.md`，合并后仍保留原有指令，因此它继续作为跨 AI 的共享入口，其他 AI 不需要安装本技能也能按同一份记录维护进度。`--claude-bridge` 只面向 Claude Code，WorkBuddy 不需要它。

WorkBuddy 会话有独立的项目记忆目录，用于按天记录活动日志。两者职责不同：**`research/STATUS.md` 是本技能执行状态的唯一权威来源**，会话记忆目录只是活动流水。不要把项目状态复制进会话记忆目录，也不要用会话记忆代替 `STATUS.md`；恢复工作时先读 `research/STATUS.md`，再读 `research/PLAN.md` 及其 `Must Read`。

## 安装、更新与依赖完整性

先确认目标安装位置，取得用户对该位置的写入授权。默认不覆盖同名已有定制；先比较，再备份需要替换的文件。

- **完整技能目录安装：** 把技能目录整体放入用户级技能目录 `~/.workbuddy/skills/plan-your-project/`，保留 `SKILL.md`、`references/`、`scripts/`、`assets/`、`agents/` 与 `LICENSE`。不要只复制 `SKILL.md` 或单个主脚本；`scripts/workspace_io.py` 是入口脚本的间接依赖，缺失会导致运行期导入失败。
- **版本校验：** 更新安装前比较新旧 `version`，新版必须严格高于旧版，否则拒绝覆盖。版本信息只写在 `SKILL.md` 的 frontmatter。
- **安装后读回核验：** 从真实安装位置运行 `--help`，确认文件清单齐全、脚本可执行，再在隔离的临时项目验证初始化、只读接续和校验。不要用真实业务项目做安装探针。
- **本地适配不等于上游发布。** 上游更新不得静默覆盖本地适配；更新前对比版本与差异，必要时重新合并和验证。

两种分发的运行包安装后至少检查以下文件：

```text
SKILL.md
assets/LICENSE
scripts/project_state.py
scripts/init_research_workspace.py
scripts/workspace_io.py
scripts/bootstrap_research_workspace.py
references/workbuddy_integration_zh.md
references/hermes_integration_zh.md
references/discussion_protocol_zh.md
references/progress_protocol_zh.md
references/file_contract_zh.md
references/software_lens_zh.md
references/research_lens_zh.md
assets/AGENTS_tracking.md
assets/CLAUDE_bridge.md
assets/TEMPLATE_retrospective_zh.md
assets/TEMPLATE_retrospective_en.md
```

## 降级与限制

- **没有可用的 Python 解释器：** 不伪造 CLI 输出。改为按 `references/progress_protocol_zh.md` 的格式手工维护 `research/STATUS.md`，并明确说明没有机器可验证的检查点。
- **没有项目写权限：** 输出标注为“待同步”的交接内容，由本地执行者核实后再保存；不能声称工作区已更新。
- **执行后端不匹配：** 本机技能目录在远端不可读时，说明阻塞并停止该后端的写入动作，不静默换用其他后端。
- **脚本执行中断：** 按 `references/file_contract_zh.md` 的 `recover` 路径处理，不把中断状态当作缺文件重新初始化。

## 测试结果如何解释

`tests/test_workbuddy_portability.py` 检查 WorkBuddy 适配的文件契约、路径锚定与入口一致性；它不证明模型一定遵守指令。原测试继续负责状态、恢复、授权和旧格式回归。`tests/workbuddy_behavior_evals.json` 提供需单独运行的 WorkBuddy 对话案例；若尚未运行模型评测，应写“未运行”，不能把案例存在或静态断言通过说成模型行为通过。
