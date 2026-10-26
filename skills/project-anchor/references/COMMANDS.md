# 命令与输入

安装生成本 Skill 根目录 runtime.json：python、kit 都是绝对路径；Codex 安装另有 codex_home，通用/Claude/DSH 安装另有 client 和绝对路径 home。它是执行定位信息，不是独立项目状态；不复制核心代码。先读这个文件，再运行本目录 scripts/run.py。适配器可以从任何 cwd 调用，保留目标 cwd，并按安装来源设置环境；非 Codex 入口不要求 codex_home。

先读取 runtime.json 中 `python` 的绝对路径。PowerShell 把路径和参数作为独立参数，例如 `& $python '-X' 'utf8' $runner 'status' $project`；不要用字符串拼接后执行，也不要依赖默认 Python 或启动器。实际 Python 由适配器以参数数组启动。

| 操作 | 参数 |
| --- | --- |
| 定位检查 | --locate |
| 初始化 | init-project PATH --name NAME [--git-init] |
| 用户授权项目更名 | rename-project PATH --name NAME --expected-revision N --reason TEXT |
| 读取状态/目标/断点/任务 | status PATH |
| 简洁查询（完整目标和断点） | status PATH --brief |
| 简洁查询含已完成任务 | status PATH --brief --all |
| 明确任务/里程碑查询 | status PATH [--brief] [--task ID ...] [--milestone NAME] |
| 明确授权重建进度 | status PATH --rebuild |
| 任务创建/更新 | task add/update PATH --file JSON --expected-revision N --reason TEXT |
| 任务批准 | task approve PATH --task-id ID --source user\|policy --expected-revision N --reason TEXT |
| 任务范围修订 | task revise PATH --task-id ID --expected-revision N --reason TEXT |
| 旧账本迁移 | migrate PATH --expected-revision N --reason TEXT [--dry-run] |
| 状态更新 | state update PATH GOAL.md/CURRENT.md/DECISIONS.md/LESSONS.md --file MARKDOWN --expected-revision N --reason TEXT [--approved] |
| 检查/保存快照 | snapshot PATH [--check SNAPSHOT_FILE] |
| Codex 诊断 | doctor PATH --json --native-hooks --native-skills |
| 非 Codex 安装诊断 | doctor PATH --json --client agents/claude/dsh [--client-home DIR] |
| 本会话 Hook 检查 | doctor PATH --json --session-id ID [--expect-event SessionStart/PreCompact] |
| 复盘 | retro PATH |
| 知识入库 | knowledge-add --file JSON --approved |

写入 task 可用 `--json-input` 代替 --file，将 UTF-8 JSON 通过 stdin 输入；state 用 `--text-input` 提交 Markdown。两者不允许与 --file 同时使用。revision 是 status 中的项目 revision，不是 task_revision。每次写入后重新读取；冲突需看新状态并重新判断，不能自动覆盖。

通过 Python 子进程发送已含 CRLF 的原文档时，使用 UTF-8 字节输入，避免 Windows 文本模式重复转换换行；不能用格式转换代替原文保留。

task/state 返回 `revision` 和 `changed`。`changed=false` 是有效请求没有实质变化，本次未写入，修订、历史和完成时间保持；仍检查旧修订、非法字段和状态约束。CURRENT 文字不变但落后于任务修订、GOAL 首次批准及外部编辑登记仍可能实际更新。

原 status 返回结构保持不变。新查询增加 selection、summary 和 external_dependencies；--brief 仅省略任务描述、验收长证据等，保留 ID、标题、里程碑、批准/执行状态、依赖、阻塞；并默认折叠 done/cancelled 任务，只列仍未终结的任务，被折叠的条数在 summary.folded_final 中。传 --all 可显式返回全量；显式 --task/--milestone 选择永远不折叠，已完成任务仍返回真实状态。summary 的 total/statuses/approved_done 口径不受折叠影响。--task 可重复，和 --milestone 同时使用取交集；未知任务、里程碑或空交集报错，不扩大查询。summary 的 approved_active 排除草案与取消任务，approved_done 是其中已完成数；原 PROGRESS 完成率口径保持不变。
筛选查询不能与 --rebuild 组合；重建全项目进度须单独明确请求，避免局部查询顺便修改全局视图。

`init-project` 的“初始化”指新增治理记录：创建 `.agent/`，保留并追加 `AGENTS.md`、`.gitignore`、`.gitattributes`；默认不初始化Git，不改业务代码或依赖。审批和用户说明必须包含这四处写入范围；传入 `--git-init` 需要另有明确授权。

task add 输入（只能建立草案）：
```json
{"task_id":"T1","title":"实现接口","description":"目标内的范围","milestone":"阶段一","dependencies":[],"acceptance_criteria":["实际调用成功"]}
```

新增任务默认 `plan=draft`、`status=todo`；不能通过 `task add` 或 `task update` 直接建立 approved 状态。用户明确批准后执行 `task approve PATH --task-id T1 --source user --expected-revision N --reason TEXT`；程序记录批准范围快照（描述、验收标准、依赖）、版本和哈希。`--source` 是调用者声明，不是身份认证。

批准快照同时追加到任务 `history`；修订时也存档当前快照，保留旧版创建但仍存在的批准记录。重新批准不覆盖这些历史；此前已丢失的批准来源和快照不能凭空恢复。

已批准任务的描述、验收标准或依赖不能直接改；先 `task revise PATH --task-id T1 --expected-revision N --reason TEXT` 回到草案，修改后重新 `task approve`。旧证据保留但标记失效。

task update 输入（证据必须来自实际验证）：
```json
{"task_id":"T1","status":"done","evidence":[{"type":"test","criterion":1,"detail":"真实测试命令、结果及证据位置"}]}
```

`task update` 不接受 `plan`、`approved_scope`、`legacy_unverified`，也不能修改证据的 `level`、`scope_version`、`criteria_hash`、`git_head` 等内部字段。提交的 `evidence` 是新增条目，旧条目保留并由程序标记失效；不要试图用新条目覆盖或删除旧证据。程序为证据写入当前批准版本、标准文本哈希、记录时间和 `level=claimed`；`observed` 只能由受控执行路径产生（当前版本未提供）。一次 update 不能同时改验收范围并完成，也不能删除未完成依赖并同时置 doing。

`evidence` 必须是数组；有效的空数组且其他字段未变时返回 `changed=false`。失效旧证据保留原序号和标准哈希，不因新范围减少标准而删除或重编号，也不能用于完成新范围。

todo → doing/blocked/cancelled；doing → done/blocked/todo/cancelled；blocked → doing/todo/cancelled；done → doing；cancelled → todo。`task revise` 是显式的范围修订操作，可从 approved/doing/blocked/done 回到 draft/todo；它会使旧证据失效，随后必须重新 `task approve` 才能执行。草案不能开始；doing/done 要求全部依赖 done；blocked 要求 blocker；done 证据必须覆盖当前批准版本的全部标准，且标准文本哈希匹配。证据类型 test/file/review/manual/command，程序检查结构，不代替实际验收。

旧 schema 1 账本只读；`status`/`doctor` 可读，`task`/`state` 写入前先执行 `migrate PATH --expected-revision N --reason TEXT`。迁移会备份、标记 `legacy_unverified`，不自动补造批准记录；旧任务重新开始或完成前需 `task approve`。旧版 v1.3 读取 schema 2 会直接拒绝。

`migrate --dry-run` 会先构造并校验 schema 2 结果；不兼容的旧字段会明确报错，不自动丢弃。正式迁移也先校验，再备份和提交；预检或校验失败不会产生迁移备份。

state update 接收完整文档。GOAL 必须有核心目标、项目背景、关键约束、非目标、验收标准、目标版本；CURRENT 必须有当前阶段、当前任务、已完成工作、当前阻塞、下一步动作、状态修订、Git 检查，50 行以内。普通更新禁止直接改原文件；外部既有编辑必须单独审核后 state adopt 登记，不用于绕过冲突。

全局安装/升级及跨电脑迁移由 install-global 或 install-client 统一生成定位文件和哈希；脚本移位或安装版本不同则停止并明确报告。适配器不修改 Hook 配置，移除 Skill 后 CLI 与 Hook 仍可独立执行。

适配器按 runtime.json 的安装来源设置环境：Codex 安装传 CODEX_HOME；`install-client` 安装传 PROJECT_ANCHOR_CLIENT 与 PROJECT_ANCHOR_CLIENT_HOME，此时 doctor 默认检查对应客户端安装，不读取 Codex 配置。`--native-*` 只适用于 Codex。安装、卸载、信任和恢复属于用户操作：`install-client/uninstall-client agents|claude|dsh`、`trust-project PATH --client claude --approved`、`recover --client agents|claude|dsh [--rollback]`，Skill 不自行执行。

`--expect-event` 可重复，仅用于客户端证据已确认应触发的事件，必须同时传 `--session-id`。普通 doctor 的历史成功不能代替本会话检查；本会话缺失但未确认应触发时为 UNVERIFIED，模拟记录不证明客户端执行。
