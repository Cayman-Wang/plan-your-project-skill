# Hermes 适配与使用

本说明只连接宿主能力，不改变讨论、冻结、授权、科研验收、单协调写入者或 v2/v2.1 兼容规则。Codex 的 `agents/openai.yaml` 和原有入口继续保留；不安装后台钩子，也不自动开始任何项目工作。

## 加载与路径

1. 在当前配置档案中发现技能，调用 `skill_view(name="plan-your-project")`。使用返回的 `skill_dir` 定位安装目录；不要假定是 `~/.hermes`、固定分类目录或当前工作目录。
2. 首次在 Hermes 使用时，加载 `skill_view(name="plan-your-project", file_path="references/hermes_integration_zh.md")`，然后按任务读取讨论、进展或文件契约。
3. **技能目录**存放说明、脚本和模板；**项目目录**存放用户的代码及 `research/PLAN.md`、`research/STATUS.md`。二者不是同一个目录。脚本用安装目录的绝对路径调用，项目始终用明确的 `--workspace-root` 传入。
4. 如果终端在 SSH/容器等远端执行，先确认该后端也能读取脚本、模板和项目；本机 `skill_dir` 不是远端可用路径。缺少同后端安装时说明阻塞，不静默切换后端、复制私有项目或声称写入成功。

用户可直接说：

```text
请使用 plan-your-project 技能讨论这个项目，先不要创建文件。
请使用 plan-your-project 技能，只读核对项目的实际进度。
按照已经确认的方案保存项目计划；暂不启用 tracking，也不开始实施。
```

不要求在 Hermes 使用 Codex 的 `$plan-your-project` 语法。不要求清空当前会话；新安装后的自动发现以新会话为稳妥验证入口，当前会话可尝试显式 `skill_view`。不可用时说明需要新会话，不擅自 `/reset` 或刷新提示缓存。

## `/plan` 与长期项目记录

**先判断当前回合的明确限制，再解释 tracking。** 项目已记录的旧授权不会扩大当前权限。

| 当前请求 | 允许的动作 | 不允许的附带动作 |
|---|---|---|
| 只讨论、先不保存 | 只读调查、澄清、给出方案 | 创建项目记录或开启 tracking |
| Hermes `/plan` | 只读调查、澄清，保存本轮指定的计划 Markdown | 更新长期记录、实施或启用 tracking |
| 明确同意具体方案并要求保存 | 按既有冻结与文件契约保存批准的记录 | 自动开始实现，或默认启用 tracking |
| 已授权实施且 tracking 已启用 | 在授权工作内执行，按关键事件维护状态 | 扩大任务范围或重复索取已有记录许可 |
| 只读接续预览 | 读 STATUS、PLAN、证据并核对当前事实 | 用旧交接授权新任务、自动 recover 或迁移 |

Hermes `/plan` 默认产物路径为 `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`，若本轮指定了确切路径则服从该路径。它不是本 skill 的冻结项目记录，也不是 `project_state.py init` 的 JSON 输入；不要直接改名或作为 `--plan-file` 传入。

在 `/plan` 回合，即使 `tracking: key_events`，也不得运行 `init`、`checkpoint`、`refreeze`、`enable-tracking`、`recover` 或 `handoff --output`，不得另写 `research/PLAN.md`、`research/STATUS.md`、项目入口或输入 JSON 文件。需要保留的待记录事项放进本轮允许的计划或回复，标为“尚未同步”，不声称已经保存检查点。只读 `resume` / `validate` 可在本轮允许终端检查时使用。

退出 `/plan` 后，只有当前有效请求授权保存项目记录时，才把已确认内容按冻结输入契约转换为 JSON，再调用原 CLI；保留已确认决定，不机械重问。仅有一份计划文件不代表冻结授权、tracking 或实施授权自动成立。

## 使用 Hermes 工具

- 文件和事实调查：使用 `read_file`、`search_files` 等本轮实际提供的工具；别让用户重复提供可以只读查到的事实。
- 关键取舍：使用 `clarify`，按该工具当前 schema 提问；不可用时用普通对话，不假装表单已经发出。问题数量和收敛原则沿用讨论协议。
- 已授权的计划产物或 CLI 输入：可用 `write_file`；结构化项目状态优先通过原 CLI 维护，不绕过并发检查直接覆盖 STATUS。
- 脚本：使用 `terminal`。先只读检查可用 Python，使用 `python` 或已验证的解释器绝对路径，不假定 Windows 有 `python3`。脚本只依赖 Python 标准库，不为它向 Hermes 受管环境安装包。
- 并行调查：可使用 `delegate_task`，但子代理只提交发现与证据；共享 STATUS 的协调者负责核验、合并和唯一写入。历史 handoff 不能改变当前协调责任或授权。

这是指令适配，不是宿主强制沙箱。它不保证每个模型都遵守流程，也不承诺异常退出前保存。

## 从任意项目目录调用脚本

以下为 Bash/Git Bash 示例。先把两个变量替换成 `skill_view` 返回的真实目录和用户选定的项目目录；Windows 原生程序使用 `C:/...` 形式，不使用 `/c/...`。PowerShell 用户应按对应 shell 语法调用，不把 Bash 变量语法直接粘贴过去。

```bash
SKILL_DIR='/absolute/path/returned/as/skill_dir'
PROJECT_DIR='/absolute/path/to/the/user-selected-project'
python -B "$SKILL_DIR/scripts/project_state.py" --help
python -B "$SKILL_DIR/scripts/project_state.py" resume --workspace-root "$PROJECT_DIR" --json
python -B "$SKILL_DIR/scripts/project_state.py" validate --workspace-root "$PROJECT_DIR" --json
```

项目尚未初始化时，resume/validate 失败不构成自动初始化授权。参数包含空格或中文时保持整体引用。不要为了寻找脚本改变项目工作目录。

已明确授权保存冻结内容后，按 `references/file_contract_zh.md` 准备 JSON，再先预览；下面命令不授权写入输入文件，也不是 `/plan` 回合可执行的动作：

```bash
python -B "$SKILL_DIR/scripts/project_state.py" init --workspace-root "$PROJECT_DIR" --plan-file '/absolute/path/to/approved-plan.json' --dry-run
```

批准预览所代表的写入后，用同样参数移除 `--dry-run`。如果用户已经明确批准同一组具体文件写入，不重复索取许可。默认保持 tracking disabled；其他写命令仍遵守原文件契约，使用最新读取的 PLAN/STATUS 校验值，只检查相关变化，不反复全库哈希。

## 安装、更新与依赖完整性

先确认 `hermes --version` 和 `hermes skills install --help`，并取得目标配置档案的安装授权。默认不覆盖同名已有定制；先比较，再备份需要替换的文件。

- **已审阅的本地适配版：** 通过 Hermes 的本地技能管理流程创建技能并放入完整支持文件；保留许可证、原始 Codex 元数据和测试于发行副本。主入口、scripts、references、assets 必须在同一个技能目录。安装结果读回，而不是仅相信复制成功。
- **发布后的仓库版：** 在支持根目录 identifier 的 Hermes 中，可使用下列仓库安装方式。末尾 `/` 表示技能位于仓库根目录；运行前确认此适配已发布到待安装版本。未发布时，远程命令只会获取旧上游，不包含本地修改。

```bash
hermes skills install 'Cayman-Wang/plan-your-project-skill/' --category productivity
```

- **直接 `SKILL.md` URL：** 使用已审阅提交的链接，检查主入口所有显式支持文件均已取得。URL 运行包通过主入口显式链接的 `assets/LICENSE` 携带完整 MIT 文本，内容与根 `LICENSE` 一致。完整目录和 URL 两种分发可能不同，不用完整目录的测试结果替代 URL 包验证。
- 保持安全扫描和确认。脚本会用本地 Git 子进程观察项目状态，并继承环境但不输出环境内容；扫描警告应结合具体调用人工审查，不改 trusted 列表、不使用 `--force` 绕过阻断，也不删除既有功能来制造“通过”。
- 本地适配不等于上游发布。Hub 更新不得静默覆盖本地适配；更新前对比版本与差异，必要时重新合并和验证，不批量升级其他技能。

两种分发的运行包安装后至少检查以下文件；完整目录分发还须保留根 `LICENSE`：

```text
SKILL.md
assets/LICENSE
scripts/project_state.py
scripts/init_research_workspace.py
scripts/workspace_io.py
scripts/bootstrap_research_workspace.py
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

先从真实安装位置运行 `--help`，再在隔离的临时项目验证初始化、只读接续和校验。不要用真实业务项目做安装探针。

## 测试结果如何解释

`tests/test_hermes_portability.py` 检查精简分发、路径、入口与文档契约；它不证明模型一定遵守指令。原测试继续负责状态、恢复、授权和旧格式回归。`tests/hermes_behavior_evals.json` 提供需单独运行的 Hermes 对话案例；若尚未运行模型评测，应写“未运行”，不能把案例存在或静态断言通过说成模型行为通过。
