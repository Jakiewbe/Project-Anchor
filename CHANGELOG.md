# 更新记录

## 1.5.1 — 2026-10-30：交付覆盖与只读查询

- 真正只读的status/context/verify show/项目诊断不创建锁或目录；读取前后核对治理状态及事务，变化明确失败。
- CURRENT使用--task或--no-task保存任务/目标版本/任务修订关联，展示unknown/changed/aligned；原current_stale含义不变。
- schema4将deliverables纳入批准快照，漏出inputs覆盖不能批准，交付物缺失不能验收；变更必须修订重批。
- schema1/2/3显式预检、备份迁移；保留历史及原schema3凭据，不反推交付物。未声明交付的旧任务继续执行或用于依赖前需修订重批。
- 筛选后只校验可见任务和完整依赖链；查询内复用文件哈希，无持久缓存或静默文件忽略。
- 展示当前验收、交付覆盖和命令observed/自查claimed/self摘要；历史done不自动重写。复盘提供证据索引，避免复制目标和证据数组。
- 本版本包含下方尚未正式发布的1.5.0能力；实际验证和发布边界见docs/ITERATION_1_5_1_VALIDATION.md。

## 未发布 — 1.5.0 接续、验收与历史归档

- schema3：批准范围新增checks；schema1/2预检、备份迁移、原批准与证据保留，旧结果显示legacy；受保护回退拒绝覆盖后续修改。
- focus显式记录本轮任务，保留已完成结果与范围外依赖；没有指针不猜历史任务。
- verify run执行已批准argv，记录内容指纹、退出码、日志摘要和observed凭据；超时、超限、取消、输入改变、修订冲突均不算通过，不自动重跑。
- task review记录Agent自查材料与结论，固定claimed/self。完成按标准类型匹配当前成果；改变成果派生stale，历史done不自动重写。
- 裁剪前事务性归档到.agent/history，内容哈希标识、失败不裁剪，history list/show按需查询。此前已丢且无备份的内容不承诺恢复。
- Skill与DSH共用核心完整查询；DSH完整/本轮/all映射一致，错误路径、损坏清单、版本不符明确失败，不尝试其他安装。
- 保留Python标准库与唯一核心，不增加默认模型调用、服务或独立审核；同权限本地执行者可绕过的边界继续公开。
- Windows本地回归与隔离原生接续证据见docs/ITERATION_1_5_VALIDATION.md；本轮尚未触发远程CI，不等于已发布。

### pi已有优化及历史验证


- 修复既有缺陷（首次 GitHub Actions 运行暴露）：`atomic_io.transaction()` 用 `Path.resolve()` 后的长路径判断写入范围，却用未解析的短路径做 `relative_to()`。在 8.3 短名根（如 runner 的 `C:\\Users\\RUNNER~1\\...`）下抛 `ValueError`，导致所有写入失败。现在每个更新路径只解析一次，两种写法指同一文件。本机因临时目录没有短名别名而一直未暴露；新增 Windows 回归测试用 `GetShortPathNameW` 复现。

- `state.json` 的 `history` 改为有上限：只让最近 10 条 `document-version` 保留文档全文，更早的剥离 `content` 但保留 `file`、`previous_sha256`、`timestamp`；条目总数上限 200，超出时按顺序丢弃并合并成一条 `history:prune` 记录（累计丢弃数、revision 区间、时间）。本条记录pi阶段行为；本轮已改为先持久归档，Git和快照辅助追溯。
- 本仓库 `state.json` 实测从 477 KB 降到 101 KB（-79%），之后每次写入保持同量级；此数字为pi阶段的原实测；state.json schema保持不变，本轮任务账本独立升级schema3，旧账本只读。
- `status --brief` 默认折叠 `done`/`cancelled` 任务：只列仍未终结的任务，计数仍在 `summary`（新增 `folded_final`）。新增 `--all` 显式返回全量；显式 `--task`/`--milestone` 选择不受折叠影响。本仓库 `--brief` 输出实测从 12.7 KB 降到 7.3 KB。
- 新增 `tests/test_history.py`：覆盖正文剥离窗口、条数上限、单条滚动标记、短历史不变、无新增必填字段、brief 折叠与显式选择。
- 新增 `.github/workflows/tests.yml`：`windows-latest` 阻断（主验证环境），`ubuntu-latest` 为 `continue-on-error` 的信息性任务；Linux 走 `shlex.join` 命令路径，未在本机验证。
- DSH P0 的五条批准标准逐条对上测试或命令证据后结项；真实 DSH 会话证据仍属 P1。
- 本轮实测见 `docs/ITERATION_1_5_VALIDATION.md`；历史轮次的数字不改写。

## 未发布 — DSH 宿主插件 P0

- 新增 `packages/dsh/`：DSH 宿主插件骨架，`anchor_status` 与 `anchor_doctor` 两个只读工具 + `project-anchor:governance` 提示词 section；业务逻辑仍只在 `kit.py`。
- 新增只读 `kit.py context PATH [--json] [--limit] [--managed-dir]`：与 Codex Hook 共用 `core/hook_runtime.context()`，未信任项目只返回读取指引、不注入内容。
- 新增 `tests/test_dsh_plugin.py`：用桩件加载真实 Host 模块，校验清单/patch/locale/icon、schema 关键字子集、`apply()` 注册结果，并实际调用一次只读 `kit.py status`。
- 未安装到任何 DSH profile，未取得真实会话证据；`ANCHOR` 写工具、guard、注入、命令、批准弹窗仍为设计，见 `docs/DSH_PLUGIN_DESIGN.md`。

## 未发布 — 1.4.0 后续修复

- 保留失效证据的原序号和哈希，修复任务缩减验收条目时被历史证据阻止的问题。
- 批准和修订时将完整批准快照追加到历史，避免重新批准后丢失旧来源和时间；不补造此前丢失的历史。
- 空证据数组不再制造无意义的修订，错误的证据容器类型明确拒绝。
- 迁移预检和正式迁移共用完整转换校验；不兼容输入在创建备份前报错，不自动丢弃未知字段。
- DSH 诊断检查重复规则标记，并区分规则块完整性和模板版本；补齐技能参考中的 DSH 命令说明。

## 1.4.0 — 2026-10-19

- 任务账本升级到 `schema 2`：批准范围成为程序拥有的快照，记录描述、验收标准、依赖、版本和哈希；`task add` 只建草案，批准只能通过 `task approve`，范围变更先 `task revise` 再重新批准。
- `task update` 不再接受 `plan`、`approved_scope` 或内部证据字段；一次更新不能同时改范围并完成，也不能删除依赖并同时开始。证据绑定批准版本和标准文本哈希，旧证据保留但标记失效。
- 新增 `migrate`：schema 1 只读，显式迁移并备份；旧任务标记 `legacy_unverified`，不自动补造批准记录；v1.3 读取 schema 2 会拒绝，避免旧写入器静默降级。
- 新增 `install-client dsh`：DeepSeek Harness 的 Skill 与全局 `AGENTS.md` 管理块，不配置 Hook；`doctor --client dsh` 只声明安装检查，原生发现/规则注入/执行保持 UNVERIFIED。
- 新增审批、迁移、旧写入器拒绝和 DSH 安装测试；未实现 observed 证据执行器、Git 自动合并和正式 Python 包分发。

## 1.3.0 — 2026-10-15

- 区分项目总目标与已授权局部任务、路线决定与执行阶段；批准目标不自动生成计划，允许治理写入时当回合保存决定。
- task/state 无变化返回 changed=false，保留修订、历史、原始编码与完成时间；首次目标批准和断点修订同步仍正常写入，旧修订仍拒绝。
- 新增 status --brief、--task 和 --milestone；保留完整目标/断点、单列范围外直接依赖，草案与已批准有效任务分别统计。旧 status、PROGRESS 和 schema 1 保持兼容。
- doctor 列出模板待更新文件及安装文件修改/缺失；精简 Skill 入口，保留客户端参考与唯一核心。
- 验证及本机升级边界见 docs/ITERATION_1_3_VALIDATION.md；第二轮追加/批量写入和证据格式未实现。

## 通用 Agent Skills 适配 — 2026-10-10 合并

- 新增 `install-client agents`：不依赖 CODEX_HOME 的通用 Skill 安装，清单位于 PROJECT_ANCHOR_HOME；`install-client claude`：Claude Code 的 Skill、用户规则文件和 SessionStart/PreCompact Hook。两者复用原有所有权校验、备份、锁、事务恢复与安全卸载。
- 适配器按 runtime.json 安装来源设置环境；`doctor/trust-project/recover` 增加 `--client`。Codex 的 Hook 命令、全局规则和 runtime.json 字节不变；但核心脚本变化会让旧安装的 doctor 报告 Hook 脚本版本 WARN，需重新 install-global。
- Skill 说明与项目模板改为客户端中立；新会话及压缩后先读最新状态，写入使用最新 revision。
- 能力矩阵与验证记录见 docs/CLIENT_VALIDATION.md；未完成的真实客户端验收保持未验证。

## 1.2.0 — Project Anchor 名称与补验

- 主Skill、软件包、全局路由和显示名称统一为project-anchor / Project Anchor；同父目录从旧Skill安全迁移，清单校验、备份、用户文件保留、回滚与崩溃恢复复用现有事务。
- 兼容保留CODEX_HOME/codex-rules存储和旧控制标记；目标项目仍共用.agent与唯一Python核心。
- 新增正式rename-project入口，名称、修订历史和生成进度一起更新，不直接修改账本。
- 客户端能力说明区分通用文件核心与已适配Codex；不宣称其他客户端已通过集成测试。
- 补验自然Desktop自动压缩、原生查询和锁缺口；保留重复状态拒绝失败，其他待验证事项分别报告。

## 1.1.4 — 2026-10-09

- 区分新增治理记录和重建业务工程；旧限制按原文范围判断，明确禁止治理或限定文件范围仍不接入。
- 全局规则及Skill说明完整接入范围：.agent、AGENTS.md、.gitignore、.gitattributes；不把规则更新当成撤销已拒绝操作。
- 补充既有业务及Git保留检查与真实自然语言正反场景，结果见 docs/PURPOSE_REVIEW.md。

## 1.1.3 — 2026-10-09

- 诊断和安装正确区分官方Hook信任元数据与内联事件组，非法配置在写入前拒绝。
- 用户授权后通过官方界面启用两项Hook；真实手动、自动压缩及旧快照与最新断点接续验收完成，限制见 docs/PURPOSE_REVIEW.md。
- 完整回归120通过；原生生命周期测试使用当前contextCompaction完成事件，保留测试器超时和断言误报历史。

## 1.1.2 — 2026-10-09

- 初始化在写入前拒绝用户主目录及磁盘根目录。
- doctor增加只读原生Hook审核、启用及精确定义核对，Skill诊断调用同一入口。

## 1.1.1 — 2026-10-09

- 默认在明确项目的首次实际工作中接入，保留只读及限定文件范围。
- 接续读取最新磁盘状态；doctor核对当前会话与预期事件，历史或模拟日志不能代替本次执行。
- 正式安装保留原规则和其他Skill，真实自然语言使用单独验收。

## 1.1.0 — 2026-10-08

- 增加 codex-rules 原生 Skill，自然语言工作流覆盖初始化、计划、进度、任务、记忆、交接、目标核对、诊断和复盘。
- 安装器统一维护用户级 Skill、定位信息和内容哈希，支持备份、更新、卸载及跨目录事务恢复。
- 薄适配器只调用现有 kit.py；增加 stdin JSON/Markdown 输入，CLI 和 Hook 保持独立可用。
- doctor 增加 Skill 完整性及模板漂移检查，可选择真实 skills/list 查询。
- 自动化、模拟及真实 Codex 触发结果分别记录于 docs/SKILL_VALIDATION.md。

## 1.0.0 — 2026-10-08

- 新建纯标准库 CLI：初始化、状态、任务、进度、快照、复盘、知识审核入库。
- 原子替换、跨进程锁、期望修订、SHA-256、事务恢复和错误拒绝覆盖。
- SessionStart/PreCompact 官方协议及 Windows 命令，项目内容精确审核、日志轮转与诊断。
- 保留现有配置的全局安装、备份、重复安装、升级检查和安全卸载。
- 自动化测试、隔离原生探针和真实模型冒烟验收说明。

1.0/1.1.0阶段未做已信任生命周期或真实压缩验收；1.1.3补齐Windows原生客户端受控验收。所有模型长期遵从、Desktop/IDE、WSL及跨机器仍未验证，不能由模拟协议测试推断。
