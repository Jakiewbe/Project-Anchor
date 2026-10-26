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
| 本轮查询 | status PATH --brief --focus |
| 本轮指针 | focus set/clear PATH --task ID --expected-revision N --reason TEXT（clear 不传 --task） |
| 命令验收 | verify run PATH --task ID --criterion N --expected-revision N --reason TEXT |
| 自查验收 | task review PATH --task-id ID --json-input --expected-revision N --reason TEXT |
| 持久历史 | history list/show PATH [--file NAME] [--archive ID] |
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

原 status 基础字段保留，增量返回统一查询字段。新查询增加 selection、summary 和 external_dependencies；--brief 仅省略任务描述、验收长证据等，保留 ID、标题、里程碑、批准/执行状态、依赖、阻塞；并默认折叠 done/cancelled 任务，只列仍未终结的任务，被折叠的条数在 summary.folded_final 中。传 --all 可显式返回全量；显式 --task/--milestone 选择永远不折叠，已完成任务仍返回真实状态。summary 的 total/statuses/approved_done 口径不受折叠影响。--task 可重复，和 --milestone 同时使用取交集；未知任务、里程碑或空交集报错，不扩大查询。summary 的 approved_active 排除草案与取消任务，approved_done 是其中已完成数；原 PROGRESS 完成率口径保持不变。
筛选查询不能与 --rebuild 组合；重建全项目进度须单独明确请求，避免局部查询顺便修改全局视图。

`init-project` 的“初始化”指新增治理记录：创建 `.agent/`，保留并追加 `AGENTS.md`、`.gitignore`、`.gitattributes`；默认不初始化Git，不改业务代码或依赖。审批和用户说明必须包含这四处写入范围；传入 `--git-init` 需要另有明确授权。

## schema 3 的任务与验收

task add 只建草案，验收配置 `checks` 与标准逐项对应，属于批准范围：

```json
{"task_id":"T1","title":"实现接口","description":"本轮授权范围","acceptance_criteria":["测试通过","实现经自查"],"checks":[{"criterion":1,"kind":"command","inputs":["src","tests"],"argv":["C:/Python311/python.exe","-B","-m","unittest","discover","-s","tests"],"timeout_seconds":600},{"criterion":2,"kind":"review","inputs":["src"]}]}
```

示例路径必须换成真实项目材料和解释器。inputs 是非空、明确的项目相对文件/目录，使用 `/`，不接受通配符、越界、链接、空目录、项目根目录、`.agent` 或 `.git`。目录递归比较文件清单与内容哈希；新增、删除、重命名都会改变指纹。不要将生成缓存和输出文件放进输入目录。检查只覆盖声明的输入，不能证明未覆盖材料。

批准：`task approve PATH --task-id T1 --source user|policy --expected-revision N --reason TEXT`。只记录已有授权；Agent 自查不是用户确认。描述、标准、依赖或 checks 改变前先 `task revise`，再修改和重新批准。旧批准快照与证据历史保留，不补造来源。

命令验收：`verify run PATH --task T1 --criterion 1 --expected-revision N --reason TEXT`。只运行批准的 argv，不接受临时命令。默认600秒，配置范围1到86400秒；总输出上限8MiB。成功、失败、超时、取消都保留执行凭据。运行中不长期持有项目锁；结束时修订或输入变化则保留未附加结果并明确失败，不重跑。不要把凭据、密码或密钥放进命令参数。

查询凭据：`verify show PATH --run-id ID`。持久元数据位于 `.agent/evidence/`；原始输出在 `.agent/runtime/checks/`，不提交。日志缺失或改变由 logs_available 如实报告。running 表示中断或尚未结束，不能当通过；只读查询不重跑、不补记。

自查：`task review PATH --task-id T1 --json-input --expected-revision N --reason TEXT`：

```json
{"criterion":2,"findings":"Review检查的实际问题或无新增问题的依据","resolution":"已修复及复查依据，或未修复原因","simpler":"第一性原理检查后保留当前实现或已简化的理由","result":"pass"}
```

result 为 pass/fail；程序固定记录 `level=claimed`、`reviewer_kind=self`，绑定输入材料。不能写成独立审核。command 标准不能用此接口替代。

完成：`task update` 提交 `{"task_id":"T1","status":"done"}`。不再接受手填证据；只有有效空 evidence 数组可作为无变化请求。程序采集的 command 证据为 observed，自查为 claimed。done 要求当前批准范围的所有标准通过且材料指纹一致；依赖须完成并有当前有效结果。成果后来变化只派生 stale，不自动改写历史 done。

状态机继续为 todo → doing/blocked/cancelled，doing → done/blocked/todo/cancelled，blocked → doing/todo/cancelled，done → doing，cancelled → todo。revise 回到 draft/todo 并使旧证据失效。

## 本轮范围与持久历史

`focus set PATH --task T1 [--task T2] --expected-revision N --reason TEXT` 设置明确指针，不批准、不复制任务；`focus clear PATH --expected-revision N --reason TEXT` 清空。

`status PATH --brief --focus` 不与 --task/--milestone/--rebuild 同用。未设置时 focus_missing=true、tasks为空，summary仍提供项目总量并有 selected_total=0，不猜任务。本轮已完成项仍列出，依赖单列。普通 brief 仍折叠终结项，--all 返回全部。

`history list PATH [--file CURRENT.md]` / `history show PATH --archive ID` 只读查询 `.agent/history/`。先在同一事务中归档原记录，再裁剪热历史；失败不裁剪。归档按内容哈希寻址、校验项目身份，不自动删除或恢复。旧记录无revision时明确未知；此前已丢失内容不能补造。

## 迁移和受保护回退

schema 1/2 只读。`migrate PATH --expected-revision N --reason TEXT --dry-run` 与正式迁移共用完整转换校验；通过后去掉 --dry-run 执行。备份包含受影响状态、全部保护文档和清单，保留原批准哈希/快照/证据/历史，增加 verification_legacy，不生成新版执行凭据。旧任务继续前先 revise、补齐 checks、重新批准。旧 done 保留，查询显示 legacy。

重复迁移 changed=false。旧版不能读写schema3。`migrate PATH --rollback BACKUP绝对路径 --expected-revision N --reason TEXT` 仅允许迁移后修订和全部文件字节仍相同时回退；有新改动就停止。事务中断单独用 recover；不能反复迁移直到成功。

state update 接收完整文档。GOAL 必须有核心目标、项目背景、关键约束、非目标、验收标准、目标版本；CURRENT 必须有当前阶段、当前任务、已完成工作、当前阻塞、下一步动作、状态修订、Git 检查，50 行以内。普通更新禁止直接改原文件；外部既有编辑必须单独审核后 state adopt 登记，不用于绕过冲突。

全局安装/升级及跨电脑迁移由 install-global 或 install-client 统一生成定位文件和哈希；脚本移位或安装版本不同则停止并明确报告。适配器不修改 Hook 配置，移除 Skill 后 CLI 与 Hook 仍可独立执行。

适配器按 runtime.json 的安装来源设置环境：Codex 安装传 CODEX_HOME；`install-client` 安装传 PROJECT_ANCHOR_CLIENT 与 PROJECT_ANCHOR_CLIENT_HOME，此时 doctor 默认检查对应客户端安装，不读取 Codex 配置。`--native-*` 只适用于 Codex。安装、卸载、信任和恢复属于用户操作：`install-client/uninstall-client agents|claude|dsh`、`trust-project PATH --client claude --approved`、`recover --client agents|claude|dsh [--rollback]`，Skill 不自行执行。

`--expect-event` 可重复，仅用于客户端证据已确认应触发的事件，必须同时传 `--session-id`。普通 doctor 的历史成功不能代替本会话检查；本会话缺失但未确认应触发时为 UNVERIFIED，模拟记录不证明客户端执行。

Python检查建议用-B避免产生字节码缓存；输入目录中的生成文件也属于真实变化，不会被自动忽略。检查命令应在前台运行，不启动常驻进程；此执行器不是进程隔离环境。
