<!-- plan-your-project:tracking:start -->
## 项目进展与接续

本项目已约定关键事件记录；当前是否启用以 STATUS 的 `tracking` 为准，只维护用户已授权的工作，不依赖安装特定 skill。当前用户决定优先于旧计划、状态和交接；冲突时指出影响并按已有授权修订，不重复索取同一许可。

### 恢复与边界

- 先读 `research/STATUS.md`，再读 `research/PLAN.md` 及 STATUS 的 `Must Read`；路径相对本工作区，不查无关项目或私人会话。
- 核对项目、修订、当前任务、相关代码/提交、未提交改动及证据。区分记录、现场事实和未知；旧 handoff 不覆盖新状态，不重做已验证工作。
- 明确已验证结果、阻塞和一个准确下一步；仅在用户已授权且运行模式允许时执行。状态、下一步和交接不授予新工作、提交、推送、部署或对外写入权限。

### 关键事件后记录

`tracking: key_events` 时，已授权开发/研究的里程碑或验证结果改变、阻塞出现/解除、长任务开始/结束/失败、新决定改变下一步时更新检查点；暂停/交接或结束执行前保存尚未记录的新进展，不再逐次申请记录许可；相关事件合并。`tracking: disabled` 时只响应明确的记录请求，不自行启用或自动记录。纯问答、只读查看、无变化读取和 Plan/只读模式不落盘。异常退出可能来不及保存，能预见的暂停前应先记录。

PLAN 保存冻结目标与验收；STATUS 保存实际进度、验证、阻塞、下一步和必要证据。总状态与单项完成由事实决定，代码已写或实验已结束不等于验证通过。改变目标/范围/验收时修订计划，保留无关进度和有效证据，只重开受影响项。

### 文件格式与证据

- STATUS 的 v2.1 二级标题固定顺序：`Summary`、`Milestones`、`Running Tasks`、`Blockers`、`Next Action`、`Must Read`、`Evidence`、`Authorization`；总状态仅 `planned/in_progress/blocked/complete`；保持元数据，状态更新递增 `status_revision`、更新时间，`plan_revision` 对齐 PLAN。空列表写 `- (none)`，正文可中文。
- 条目采用 `### ID` 后接 `- field: value`，字段值单行、不增未知字段。`Milestones` 字段为 `execution`、`validation`、`acceptance`、`summary`、`evidence`（逗号分隔证据 ID，可空）、`acceptance_basis`、`conclusion`。
- `execution`：`pending/running/done`；`validation`：`not_run/passed/failed`；`acceptance`：`pending/accepted/rejected`；`conclusion`：`not_applicable/supported/not_supported/inconclusive/unverified`。已评估结论 supported/not_supported/inconclusive 都需 observed/historical 证据；unverified 表示尚未核实，不能代替已验证负结果。跳过/不可用检查仍为 `not_run` 并说明原因。accepted 需执行完成、验证通过、证据及验收依据；负结果是否验收由冻结标准决定，全部里程碑 accepted 且无运行任务/阻塞才可标总状态 complete。
- `Evidence` 每条字段为 `source`（`observed/historical/unverified`：直接观察/他人历史报告/待验证）、`ref`（实际文件或外部来源）、`summary`（方法与结果）、`code_ref`（适用版本）、`checked_at`（实际核验时间）。未运行不写通过，历史通过不代表修改后仍通过。
- `Running Tasks` 每条字段为 `environment`、`code_ref`、`document_ref`、`log`、`artifacts`、`last_checked_at`、`completion`、`recovery`。未提交文件、后台任务和产物须现场核实；远端未检查写未知。
- 保持摘要简短，只读当前必要材料；历史细节放已授权记录，产物留正常位置并链接，不复制聊天全文或机密。

### 写入与交接

- 一个协调负责人写共享 STATUS，Authorization 中 `Coordinator: NAME` 至多一条且名字非空。明确交接时替换为新负责人，保持原 tracking：有工具且已为 key_events 时可用 `enable-tracking --coordinator`；disabled 时用明确请求的单次 checkpoint，将旧/新负责人及交接依据写入 changes，其他状态保持不变，不调用启用命令。无工具时按下条维护 STATUS，保留交接依据及原 tracking。已有多个负责人先报告歧义，按已确认人选修正，不自行猜选。子代理只汇报事实/证据/阻塞；写前重读最新状态，有并发变化先核对，不用旧快照覆盖。
- 有状态工具时先 resume 取完整状态和校验值，用预期版本检查提交 checkpoint 后 validate。无工具时按上述格式只维护当前 STATUS 并自查，不伪造机器检查点或“工具校验通过”。旧 v2 不直接手改格式，须明确启用并转换。
- 交接列明项目/修订基线、当前任务、已验证结果、假设、风险及验证、开放问题、冻结就绪度、剩余/阻塞、必读与下一步；接收者无文件权限时保留这些条件的正文。网页端或无写权限 AI 输出“待同步”交接，不能声称已保存；本地接手者核对时效、现场及新用户决定后再同步。
<!-- plan-your-project:tracking:end -->
