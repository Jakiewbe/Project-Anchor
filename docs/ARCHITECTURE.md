# Codex-Rules v1.0 架构

## v1.1 Skill 增量

保留现有 memory/tasks/atomic_io/config 和 Hooks，新增 `skills/codex-rules` 作为自然语言流程入口。说明与工作流按需读取，唯一适配器只以参数数组执行现有 kit.py。用户级默认位置按照 [官方 Skill 文档](https://learn.chatgpt.com/docs/build-skills) 为用户目录/.agents/skills，自动选择允许但不保证确定性；显式 `$codex-rules` 保留。

安装定位使用 runtime.json，记录实际解释器、工具箱路径和 CODEX_HOME，版本不同或路径缺失会拒绝调用。状态输入可从 stdin 提交，避免临时 JSON 拼入 shell。任务仍只在 tasks.json，所有状态逻辑仍在原核心。

全局配置与用户 Skill 可能跨磁盘，事务仅增加具名 `skill` 写入范围；恢复须由调用方提供原范围，并与日志范围一致，不能仅凭日志授权外部路径。管理文件哈希验证、用户新增文件保留、备份与卸载共享现有确定性写入程序。旧 v1 安装清单可以安全升级，不复制 Python 核心。

doctor 的可选原生检查使用公开 app-server skills/list，不推断模型调用结果。测试中 Windows 的 OS 用户目录不会随假 USERPROFILE 改变，因此隔离发现测试使用公开的进程级 extraRoots；默认用户路径另做临时安装验证，并单独记录。真实模型测试使用现有登录，ephemeral 临时项目，不复制认证或改变全局配置；测试 Skill 在结束后按清单卸载。

核对日期：2026-10-08；开发环境：Windows、Python 3.11.5、Git 2.52.0、Codex CLI 0.162.0-alpha.2。

## 机制与来源

按 [官方 AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) 分层加载规则；覆盖文件和大小上限由 doctor 检查。按 [官方配置优先级](https://learn.chatgpt.com/docs/config-file/config-basic) 检查项目层、用户层及 profile，命令行和管理层无法仅从项目磁盘完整确定。

按 [官方 Hooks](https://learn.chatgpt.com/docs/hooks) 使用 hooks.json、SessionStart、PreCompact；压缩后通过 SessionStart 的 compact 来源恢复，不重复配置 PostCompact。输入为 stdin JSON，恢复使用 hookSpecificOutput.additionalContext；快照只回报状态，默认 continue=true。Windows 使用 commandWindows。安装不会代替用户信任 Hook。

## 文件与写入

- GOAL/CURRENT/DECISIONS/LESSONS 保存人可读状态；tasks.json 是唯一任务来源。
- state.json 保存项目 UUID、全局修订、任务修订、文件 SHA-256、目标版本及变更历史。CURRENT 落后于任务修订会警告。
- 写入持有 OS 文件锁，在同目录写临时文件并 fsync 后 replace。多文件更新先写事务记录；普通异常回滚，强制终止保留事务。读取发现事务未完成则拒绝；recover 校验每个文件仍是旧值或新值，再完成或回滚。新编辑冲突时拒绝覆盖。
- 状态修改必须给出期望修订号；直接修改 Markdown 通过 state adopt 显式登记。tasks.json 不允许 adopt。
- PROGRESS 是可重建视图；账本和视图一同更新。视图单独被改动可以 rebuild。
- 初始化对 .agent/** 设置 Git -text 属性，保持状态的原始字节，避免 Windows 自动换行转换导致克隆后哈希失效；保留现有 .gitattributes 其他规则。
- `state.json.history` 热记录最多200条，最近10条文档版本保留全文。剥离全文或移出热记录前，先按原内容写入不可变的 `.agent/history/`，与状态更新共用事务；失败不裁剪。归档按内容哈希命名，包含项目身份与来源修订；旧记录修订未知不补造。Git和快照仍可辅助追溯，但不替代冷归档。

## 任务批准协议（1.4）

tasks.json 使用 schema 3；schema 2 的批准快照继续按原哈希协议读取。新增任务只能建立草案；`task approve` 是唯一批准入口，程序把描述、验收标准、依赖、版本、批准声明来源和 SHA-256 快照写入 `approved_scope`。`task update` 不接受 `plan`、`approved_scope` 或内部证据字段；已批准任务的实质范围变化必须先 `task revise` 回到草案，再重新批准。证据记录 `scope_version`、标准文本哈希、记录时间和级别；`done` 只接受当前批准版本、标准文本匹配且未失效的证据。旧证据保留并标记 `invalidated_at`，不直接删除。

schema 1/2 可只读解析，但 `task`/`state` 写入前必须显式 `migrate`。迁移备份原状态，把旧批准任务标记为 `legacy_unverified`，不补造批准记录；旧任务保留原状态，显示 verification_legacy；继续或重新验收前需 revise、补齐 checks 并重新批准。旧 v1.3 读取 schema 2 会拒绝，避免旧写入器静默降级。该协议是本地程序不变量，不是 L3 身份验证：Agent 若能调用 `task approve` 仍可自批；真正独立的批准来源需要 OS 权限边界或独立 runner。

## 信任与边界

批准和修订操作将当时的 `approved_scope` 深拷贝到任务 `history`，保留范围、版本、来源、原因和时间。修订时会存档旧版仍存在的快照；不会改写原历史或虚构此前已经丢失的记录。批准历史继续复用原数组；本轮为检查配置与凭据引用单独升级 schema 3。

SessionStart 默认只注入固定提醒，不读取未审核项目内容作为高级指令。用户执行 trust-project 后，在 CODEX_HOME 中登记真实根目录、项目 UUID 和 GOAL/CURRENT 的精确哈希；文件变化需要重新审核。摘要以 JSON 数据呈现，限制长度，并声明不是规则。此措施不能数学上阻止模型误读数据，仍需人工冒烟验收。

快照只含白名单治理文件，带 UUID、版本和校验信息，永不自动覆盖当前磁盘。默认保留 20 个有效本项目快照；损坏和不明文件保留并由 doctor 报警。日志默认最大 64 KiB，另保留一份轮转文件。状态中禁止放入敏感内容；工具不读取认证文件、transcript 或业务源码。

## 安装

只合并全局 AGENTS 管理块和 hooks.json 中工具拥有的完整组，不写 config.toml。安装清单保存管理块、Hook 定义和安装路径；已有目标文件备份在运行目录。升级先校验旧管理内容，卸载只移除未被修改的管理内容并保留其他新增配置。事务覆盖安装清单本身。

只依赖 Python 3.11 标准库；tomllib 避免猜测 TOML。复制/克隆后重新 install-global 更新脚本路径及解释器；不自动携带 API Key、Hook 信任或项目信任。

## 并发与兼容

适用于本地磁盘、配合工具的单项目写入。锁不约束外部编辑器；校验用于发现外部变化，不支持多会话自动合并。网络盘的锁及原子性未验证。不支持共享 Windows/WSL 安装命令；各环境单独安装。旧版本缺少 Hook 能力时基础 CLI 仍能运行，doctor 必须标记未验证或失败，禁止伪装自动集成成功。


## 1.5.0：schema 3、输入绑定与冷历史

state.json保持schema1，本轮指针只存任务ID/原因/时间。任务账本schema3新增checks与执行凭据引用；checks纳入新版批准哈希。旧schema1/2只读，迁移原样保留旧快照和旧哈希，verification_legacy明确未取得新版验证；继续前revise/配置/重批。状态机保留，批准来源仍是声明。

verify与task review共用输入指纹、凭据和附加路径：准备时短锁核对修订，执行时释放锁，结束时再次核对；冲突保留未附加结果而不重跑。持久receipt先落盘，账本附加失败不会伪造成功；running表示未结束或被中断。scope/criterion与输入哈希分别约束要求和材料。命令由argv参数数组执行，自查固定claimed/self；同权限本地执行者仍能绕过或篡改，非身份认证。

load只做结构与原字节一致性验证，不因外部成果变化改写历史done。status派生pass/pending/stale/failed/invalid/legacy/unconfigured；任务开始/完成需直接依赖的当前有效结果。原始日志不进入稳定账本，日志是否可用单独报告。

归档先于热记录裁剪并与state/PROGRESS在同一事务中提交。归档文件保存被剥离或移出的原记录、项目ID和来源修订，内容哈希寻址；未知/损坏文件明确失败，不清理。热历史不是全部历史，持久归档不跟随快照轮换，也不会自动恢复旧状态。
